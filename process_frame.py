import pyrealsense2 as rs
import numpy as np
import cv2
import torch
from ultralytics import YOLO
import torchvision.ops as ops

class YOLORealSenseProcessor:
    def __init__(self, model_path='yolo11s.pt'):
        self.model = YOLO(model_path)
        self.model.fuse()

        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        self.profile = self.pipeline.start(config)

        sensor = self.profile.get_device().first_depth_sensor()
        self.depth_scale = sensor.get_depth_scale()
        sensor.set_option(rs.option.laser_power, 360)

        self.align = rs.align(rs.stream.color)

        self.spatial = rs.spatial_filter()
        self.spatial.set_option(rs.option.filter_magnitude, 5)
        self.spatial.set_option(rs.option.filter_smooth_alpha, 0.5)
        self.spatial.set_option(rs.option.filter_smooth_delta, 20)

        self.temporal = rs.temporal_filter()
        self.hole_filling = rs.hole_filling_filter()
        self.hole_filling.set_option(rs.option.holes_fill, 2)

    def get_frame(self):
        frames = self.pipeline.wait_for_frames()
        aligned = self.align.process(frames)
        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        if not depth_frame or not color_frame:
            return None

        depth_frame = self.spatial.process(depth_frame)
        depth_frame = self.temporal.process(depth_frame)
        depth_frame = self.hole_filling.process(depth_frame)

        depth_img = np.asanyarray(depth_frame.get_data())
        color_img = np.asanyarray(color_frame.get_data())

        result = self.model.predict(source=color_img, imgsz=640, conf=0.25, device="cpu", verbose=False)[0]

        boxes, scores, classes = [], [], []
        for box in result.boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            boxes.append([x1, y1, x2, y2])
            scores.append(float(box.conf[0]))
            classes.append(int(box.cls[0]))

        all_boxes = []
        closest_distance = float('inf')
        closest_box = None

        if boxes:
            boxes_tensor = torch.tensor(boxes)
            scores_tensor = torch.tensor(scores)
            keep_idxs = ops.nms(boxes_tensor, scores_tensor, iou_threshold=0.45)
            for i in keep_idxs:
                x1, y1, x2, y2 = map(int, boxes[i])
                cls = classes[i]
                class_name = self.model.names[cls] if cls is not None else "unknown"

                x1_c, x2_c = np.clip([x1, x2], 0, depth_img.shape[1] - 1)
                y1_c, y2_c = np.clip([y1, y2], 0, depth_img.shape[0] - 1)
                roi = depth_img[y1_c:y2_c, x1_c:x2_c].astype(np.float32)

                if roi.size < 9:
                    continue

                avg = cv2.boxFilter(roi, -1, (3, 3), normalize=True)
                mask = (np.abs(roi - avg) < 500) & (roi > 0)
                valid = roi[mask]

                if valid.size > 0:
                    top5 = np.sort(valid)[:max(1, len(valid) * 5 // 100)]
                    mean_depth = top5.mean() * self.depth_scale

                    avg_distance = 0.0 if not (0.2 <= mean_depth <= 10.0) else mean_depth
                else:
                    avg_distance = 0.0

                all_boxes.append((x1, y1, x2, y2, class_name, avg_distance))

                if 0 < avg_distance < closest_distance:
                    closest_distance = avg_distance
                    closest_box = (x1, y1, x2, y2)

        for x1, y1, x2, y2, class_name, avg_distance in all_boxes:
            color = (0, 0, 255) if (x1, y1, x2, y2) == closest_box else (0, 255, 0)
            label = f"{class_name} ({avg_distance:.2f} m)"
            cv2.rectangle(color_img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(color_img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        depth_m = depth_img.astype(np.float32) * self.depth_scale
        depth_clip = np.clip(depth_m, 0.0, 4.0)
        depth_u8 = ((depth_clip / 4.0) * 255).astype(np.uint8)
        depth_color = cv2.applyColorMap(depth_u8, cv2.COLORMAP_JET)

        combined = np.hstack((color_img, depth_color))
        return combined

    def stop(self):
        self.pipeline.stop()
