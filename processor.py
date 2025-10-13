import os
import platform
import pyrealsense2 as rs
import numpy as np
import cv2
import torch
from ultralytics import YOLO

class YOLORealSenseProcessor:
    def __init__(
        self,
        model_path='yolo11x.pt',
        device='cpu',
        conf_threshold=0.35,
        iou_threshold=0.45,
        imgsz=640,
        max_det=20,
        use_tta=False,
        enable_depth_filters=None,
    ):
        """
        Args:
            model_path: 사용할 YOLO 가중치 파일.
            device: 'cpu' 또는 'cuda:0' 등 추론에 사용할 장치.
            conf_threshold: confidence threshold. 기본값을 다소 높여 오탐을 줄임.
            iou_threshold: NMS 시 IoU 임계값.
            imgsz: 추론 해상도. 192 -> 640 으로 올려 작은 객체 인식률 향상.
            max_det: 한 프레임에서 허용할 최대 탐지 수.
            use_tta: Test Time Augmentation(TTA) 사용 여부. 정확도 향상하지만 속도 저하.
            enable_depth_filters: 깊이 필터 사용 여부. None이면 플랫폼에 맞춰 자동 결정.
        """

        self._is_raspberry_pi = self._detect_raspberry_pi()

        if self._is_raspberry_pi:
            # 라즈베리파이에서는 경량 모델/낮은 해상도로 기본값 조정
            if model_path == 'yolo11x.pt':
                model_path = 'yolo11n.pt'
            imgsz = min(imgsz, 448)
            max_det = min(max_det, 10)
            # 추론 스레드가 CPU 전체를 점유하지 않도록 제한
            try:
                cpu_threads = max(1, os.cpu_count() - 1)
                torch.set_num_threads(cpu_threads)
            except Exception:
                pass

        # YOLO 로드
        self.model = YOLO(model_path)
        self.device = device
        try:
            # 장치 지정 (GPU 사용 시 정확도 및 속도 향상)
            self.model.to(self.device)
        except Exception:
            # to() 미지원 환경 대비
            pass

        # 추론 파라미터
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.imgsz = imgsz
        self.max_det = max_det
        self.use_tta = use_tta

        # RealSense 파이프라인
        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 15)
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 15)
        self.profile = self.pipeline.start(config)

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

    def _distance_from_roi_closest10_mean(self, depth_img, x1, y1, x2, y2):
        """ROI에서 가까운 픽셀 하위 10% 평균(미터). 유효값 없으면 0.0"""
        h, w = depth_img.shape[:2]
        x1_c, x2_c = np.clip([x1, x2], 0, w - 1)
        y1_c, y2_c = np.clip([y1, y2], 0, h - 1)
        if x2_c <= x1_c or y2_c <= y1_c:
            return 0.0

        roi = depth_img[y1_c:y2_c, x1_c:x2_c].astype(np.float32)
        roi = roi[roi > 0]  # 미측정값 제거
        if roi.size == 0:
            return 0.0

        roi_m = roi * self.depth_scale
        roi_m = roi_m[(roi_m >= 0.2) & (roi_m <= 10.0)]
        if roi_m.size == 0:
            return 0.0

        k = max(1, int(0.10 * roi_m.size))
        closest = np.partition(roi_m, k - 1)[:k]
        return float(closest.mean())

    def get_frame(self):
        """
        반환:
        - combined: (컬러 + 뎁스 색상맵) 합친 프레임 (H x 2W x 3)
        - detections: [{"label":"person","distance":1.23, "center":0.42}, ...]
            * center: 컬러 프레임 기준 x중심 정규화(왼쪽=0.0 ~ 오른쪽=1.0)
        """
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

            # 거리 계산
            d = self._distance_from_roi_closest10_mean(depth_img, x1, y1, x2, y2)

            # 중심 x 좌표 정규화 (0~1)
            xc = (x1 + x2) / 2.0
            center_norm = float(np.clip(xc / max(W, 1), 0.0, 1.0))

            all_boxes.append((x1, y1, x2, y2, label, d, center_norm))
            detections.append({
                "label": label,
                "distance": round(d, 2),
                "center": round(center_norm, 4)  # 소수 4자리 정도로
            })

        # 시각화(박스 + 라벨)
        for x1, y1, x2, y2, label, d, center_norm in all_boxes:
            color = (0, 255, 0)
            txt = f"{label} ({d:.2f} m)"
            cv2.rectangle(color_img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(color_img, txt, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # depth 시각화
        depth_m = depth_img.astype(np.float32) * self.depth_scale
        depth_clip = np.clip(depth_m, 0.0, 4.0)
        depth_u8 = ((depth_clip / 4.0) * 255).astype(np.uint8)
        depth_color = cv2.applyColorMap(depth_u8, cv2.COLORMAP_JET)
        depth_color = cv2.resize(depth_color, (color_img.shape[1], color_img.shape[0]))

        combined = np.hstack((color_img, depth_color))
        return combined, detections

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
