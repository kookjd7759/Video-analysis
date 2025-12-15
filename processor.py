import os
import platform
import pyrealsense2 as rs
import numpy as np
import cv2
import torch
import math
from ultralytics import YOLO

# [추가] 양자화 도구 임포트
from onnxruntime.quantization import quantize_dynamic, QuantType

class YOLORealSenseProcessor:
    def __init__(
        self,
        model_path='yolo11n.pt',
        device='cpu',
        conf_threshold=0.3,
        iou_threshold=0.5,
        imgsz=640,
        max_det=20,
        use_tta=False,
        enable_depth_filters=None,
    ):

        self._is_raspberry_pi = self._detect_raspberry_pi()

        if self._is_raspberry_pi:
            imgsz = min(imgsz, 640)
            max_det = min(max_det, 8)
            # 추론 스레드가 CPU 전체를 점유하지 않도록 제한
            try:
                cpu_threads = max(1, os.cpu_count() - 1)
                torch.set_num_threads(cpu_threads)
            except Exception:
                pass

        # YOLO 로드
        self.device = device
        # 파일 경로 정의
        base_name = model_path.replace('.pt', '')
        ncnn_path = base_name + 'yolo11n_ncnn_model'
        
        # 2. 일반 ONNX 모델이 없으면 먼저 생성 (pt -> onnx)
        if not os.path.exists(ncnn_path):
            ncnn_path = YOLO(model_path).export(format='ncnn', half=True)
        self.model = YOLO(ncnn_path)   # ✅ 항상 로드


        # 추론 파라미터
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.imgsz = imgsz
        self.max_det = max_det
        self.use_tta = use_tta
        
        # [수정] 라즈베리파이인 경우 FPS를 6으로, PC면 15~30으로 설정
        target_fps = 15 if self._is_raspberry_pi else 30
        
        # RealSense 파이프라인
        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.depth, 640, 360, rs.format.z16, target_fps)
        config.enable_stream(rs.stream.color, 640, 360, rs.format.bgr8, target_fps)
        self.profile = self.pipeline.start(config)
        color_stream = self.profile.get_stream(rs.stream.color).as_video_stream_profile()
        intr = color_stream.get_intrinsics()
        self.fy = float(intr.fy)
        self.person_h_m = 1.7

        sensor = self.profile.get_device().first_depth_sensor()
        self.depth_scale = sensor.get_depth_scale()
        try:
            sensor.set_option(rs.option.laser_power, 360)  # 기기별 허용 범위 다름
        except Exception:
            pass

        self.align = rs.align(rs.stream.color)

        # Depth 필터
        if enable_depth_filters is None:
            # 기본값: 파이에서는 비활성화, 그 외에는 활성화
            self.enable_depth_filters = not self._is_raspberry_pi
        else:
            self.enable_depth_filters = bool(enable_depth_filters)

        if self.enable_depth_filters:
            self.spatial = rs.spatial_filter()
            self.spatial.set_option(rs.option.filter_magnitude, 5)
            self.spatial.set_option(rs.option.filter_smooth_alpha, 0.5)
            self.spatial.set_option(rs.option.filter_smooth_delta, 20)

            self.temporal = rs.temporal_filter()
        else:
            self.spatial = None
            self.temporal = None
        # self.hole_filling = rs.hole_filling_filter()
        # self.hole_filling.set_option(rs.option.holes_fill, 2)

    def _distance_from_roi_closest40_mean(self, depth_img, x1, y1, x2, y2):
        h, w = depth_img.shape[:2]
        x1_c, x2_c = np.clip([x1, x2], 0, w - 1)
        y1_c, y2_c = np.clip([y1, y2], 0, h - 1)
        if x2_c <= x1_c or y2_c <= y1_c:
            return 0.0

        roi = depth_img[y1_c:y2_c, x1_c:x2_c]
        # 1) 먼저 거칠게 다운샘플 (계산량↓)
        if roi.size > 0:
            roi_small = cv2.resize(roi, (0,0), fx=0.25, fy=0.25, interpolation=cv2.INTER_NEAREST)
        else:
            return 0.0

        roi_f = roi_small.astype(np.float32)
        roi_f = roi_f[roi_f > 0]
        if roi_f.size == 0:
            return 0.0

        roi_m = roi_f * self.depth_scale
        # 근거리/원거리 노이즈 컷
        mask = (roi_m >= 0.1) & (roi_m <= 40.0)
        if not np.any(mask):
            return 0.0
        vals = roi_m[mask]

        k = max(1, int(0.10 * vals.size))
        
        closest = np.partition(vals, k - 1)[:k]
        return float(closest.mean())

    def _estimate_distance_from_bbox(self, x1, y1, x2, y2):
        h_px = max(1, (y2 - y1))
        fy = getattr(self, "fy", None)
        if fy is None or fy <= 0:
            return 0.0

        Z = (self.person_h_m * fy) / float(h_px)

        Z = float(np.clip(Z, 0.3, 80.0))
        return Z - math.pow(1.2, Z)


    def get_frame(self, return_depth_vis=False):
        frames = self.pipeline.wait_for_frames()
        aligned = self.align.process(frames)
        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        if not depth_frame or not color_frame:
            return None, []

        # 필터 적용
        if self.spatial is not None:
            depth_frame = self.spatial.process(depth_frame)
        if self.temporal is not None:
            depth_frame = self.temporal.process(depth_frame)
        # depth_frame = self.hole_filling.process(depth_frame)

        color_img = np.asanyarray(color_frame.get_data())
        depth_img = np.asanyarray(depth_frame.get_data())
        H, W = color_img.shape[:2]

        # YOLO 추론 (사람만)
        with torch.inference_mode():
            result = self.model.predict(
                source=color_img,
                imgsz=self.imgsz,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                max_det=self.max_det,
                device=self.device,
                classes=[0],
                verbose=False,
                augment=self.use_tta,
            )[0]

        boxes, scores, clses = [], [], []
        for box in result.boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            conf = float(box.conf[0])
            cls_id = int(box.cls[0]) if hasattr(box, "cls") else 0
            boxes.append([x1, y1, x2, y2])
            scores.append(conf)
            clses.append(cls_id)

        all_boxes = []
        detections = []

        names_map = result.names if hasattr(result, "names") else {}

        for (x1, y1, x2, y2), _conf, cls_id in zip(boxes, scores, clses):
            x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
            label = names_map.get(cls_id, "obj")

            # bbox 크기
            w = max(1, (x2 - x1))
            h = max(1, (y2 - y1))

            # 거리 계산 (depth 기반)
            d_depth = self._distance_from_roi_closest40_mean(depth_img, x1, y1, x2, y2)

            # ✅ 추정거리(bbox 기반)는 항상 계산
            d_est = self._estimate_distance_from_bbox(x1, y1, x2, y2)

            # depth 거리 유효성 판단
            depth_valid = (
                d_depth is not None
                and np.isfinite(d_depth)
                and float(d_depth) > 0.0
            )

            d_depth_out = round(float(d_depth), 2) if depth_valid else None
            d_est_out = round(float(d_est), 2)

            # 중심 x 좌표 정규화 (0~1)
            xc = (x1 + x2) / 2.0
            center_norm = float(np.clip(xc / max(W, 1), 0.0, 1.0))

            all_boxes.append((
                x1, y1, x2, y2,
                label,
                d_depth_out,     # None 가능
                d_est_out,       # 항상 숫자
                w, h,
                center_norm
            ))

            detections.append({
                "label": label,

                # depth 기반 거리(유효 시 숫자, 아니면 None)
                "distance": d_depth_out,

                # ✅ 항상 표시할 추정거리
                "est_distance": d_est_out,

                # ✅ UI 표시용 bbox 크기
                "bbox_w": int(w),
                "bbox_h": int(h),

                "center": round(center_norm, 4)
            })

        # 시각화(박스 + 라벨)
        for x1, y1, x2, y2, label, d_depth_out, d_est_out, w, h, center_norm in all_boxes:
            color = (0, 255, 0)

            depth_txt = f"{d_depth_out:.2f}m" if isinstance(d_depth_out, (int, float)) else "N/A"
            txt = f"depth:{depth_txt}"

            cv2.rectangle(color_img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(color_img, txt, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if return_depth_vis:
            # depth 시각화
            depth_m = depth_img.astype(np.float32) * self.depth_scale
            depth_clip = np.clip(depth_m, 0.0, 4.0)
            depth_u8 = ((depth_clip / 4.0) * 255).astype(np.uint8)
            depth_color = cv2.applyColorMap(depth_u8, cv2.COLORMAP_JET)
            depth_color = cv2.resize(depth_color, (color_img.shape[1], color_img.shape[0]))

            combined = np.hstack((color_img, depth_color))
            return combined, detections
        else:
            return color_img, detections

    def stop(self):
        try:
            self.pipeline.stop()
        except Exception:
            pass

    def __del__(self):
        self.stop()

    @staticmethod
    def _detect_raspberry_pi():
        if platform.system() != "Linux":
            return False
        try:
            with open('/proc/device-tree/model', 'r') as f:
                return 'Raspberry Pi' in f.read()
        except Exception:
            return False
