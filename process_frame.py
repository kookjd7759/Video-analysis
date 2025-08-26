import pyrealsense2 as rs
import numpy as np
import cv2
import torch
from ultralytics import YOLO
import torchvision.ops as ops

class YOLORealSenseProcessor:
    def __init__(self, model_path='yolov8n.pt', device='cpu'):
        # YOLO 로드
        self.model = YOLO(model_path)
        self.device = device

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
        self.spatial = rs.spatial_filter()
        self.spatial.set_option(rs.option.filter_magnitude, 5)
        self.spatial.set_option(rs.option.filter_smooth_alpha, 0.5)
        self.spatial.set_option(rs.option.filter_smooth_delta, 20)

        self.temporal = rs.temporal_filter()
        self.hole_filling = rs.hole_filling_filter()
        self.hole_filling.set_option(rs.option.holes_fill, 2)

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
          - detections: [{"label":"person","distance":1.23}, ...]
        """
        frames = self.pipeline.wait_for_frames()
        aligned = self.align.process(frames)
        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        if not depth_frame or not color_frame:
            return None, []

        # 필터 적용
        depth_frame = self.spatial.process(depth_frame)
        depth_frame = self.temporal.process(depth_frame)
        depth_frame = self.hole_filling.process(depth_frame)

        color_img = np.asanyarray(color_frame.get_data())
        depth_img = np.asanyarray(depth_frame.get_data())

        # YOLO 추론 (사람만) — 모든 클래스 원하면 classes=None
        result = self.model.predict(
            source=color_img,
            imgsz=256,
            conf=0.5,
            device=self.device,
            classes=[0],  # person 클래스만. 모두 원하면 주석 처리 or None
            verbose=False
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

        if boxes:
            boxes_tensor = torch.tensor(boxes, dtype=torch.float32)
            scores_tensor = torch.tensor(scores, dtype=torch.float32)
            keep_idxs = ops.nms(boxes_tensor, scores_tensor, iou_threshold=0.45)

            for i in keep_idxs.tolist():
                x1, y1, x2, y2 = map(int, boxes[i])
                cls_id = clses[i]
                label = result.names.get(cls_id, "obj") if hasattr(result, "names") else "obj"

                d = self._distance_from_roi_closest10_mean(depth_img, x1, y1, x2, y2)
                all_boxes.append((x1, y1, x2, y2, label, d))
                detections.append({"label": label, "distance": round(d, 2)})

        # 시각화(박스 + 라벨)
        for x1, y1, x2, y2, label, d in all_boxes:
            color = (0, 255, 0)
            txt = f"{label} ({d:.2f} m)" if d > 0 else f"{label} (N/A)"
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
