
"""
test.py
- RealSense + YOLO11n-Pose 기반 사람 거리 추정 데모
- 거리 산출:
  1) 포즈 키포인트(몸통/머리/손/발) 픽셀 위치에서 Depth 센서 값(유효한 값들)을 모아서 평균 -> 객체 거리
  2) 해당 키포인트들의 Depth가 모두 무효(0/NaN/범위밖)일 때:
     사람 키 1.7m 가정 + 핀홀 모델로 bbox 높이(px) 기반 거리 추정
       dist ~= (H_real * fy) / h_px
- 화면에 Skeleton + bbox + 거리(m) 표시

실행:
  python3 test.py
  (옵션)
  python3 test.py --model yolo11n-pose.pt --device cpu --imgsz 640 --conf 0.3
"""

import argparse
import time
import os
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import cv2

try:
    import pyrealsense2 as rs
except Exception as e:
    raise RuntimeError("pyrealsense2(RealSense SDK)가 필요합니다. 설치/연결 상태를 확인하세요.") from e

try:
    import torch
except Exception:
    torch = None

from ultralytics import YOLO


# -----------------------------
# COCO Keypoints index (17)
# -----------------------------
KP = {
    "nose": 0,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_ankle": 15,
    "right_ankle": 16,
}

# 출력에 쓸 그룹 정의
KP_GROUPS = {
    "head": ["nose"],
    "torso": ["left_hip", "right_hip", "left_shoulder", "right_shoulder"],  # 우선 hips, 없으면 shoulders
    "hands": ["left_wrist", "right_wrist"],
    "feet": ["left_ankle", "right_ankle"],
}


def _safe_float(x) -> Optional[float]:
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return None


def depth_at_pixel_m(depth_img: np.ndarray, depth_scale: float, x: int, y: int,
                     win: int = 5, dmin: float = 0.15, dmax: float = 40.0) -> Optional[float]:
    """키포인트 주변 win x win 영역의 유효 depth(>0)들의 중앙값(m)."""
    h, w = depth_img.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None

    half = max(1, win // 2)
    x1, x2 = max(0, x - half), min(w, x + half + 1)
    y1, y2 = max(0, y - half), min(h, y + half + 1)

    roi = depth_img[y1:y2, x1:x2].astype(np.float32)
    roi = roi[roi > 0]
    if roi.size == 0:
        return None

    roi_m = roi * float(depth_scale)
    roi_m = roi_m[(roi_m >= dmin) & (roi_m <= dmax)]
    if roi_m.size == 0:
        return None

    return float(np.median(roi_m))


def pick_kp_xy(kps_xy: np.ndarray, kps_conf: np.ndarray, name: str, conf_th: float) -> Optional[Tuple[int, int]]:
    """단일 keypoint 이름으로 (x,y) 픽셀 반환."""
    idx = KP.get(name)
    if idx is None or idx >= kps_xy.shape[0]:
        return None
    c = _safe_float(kps_conf[idx])
    if c is None or c < conf_th:
        return None
    x = int(round(float(kps_xy[idx, 0])))
    y = int(round(float(kps_xy[idx, 1])))
    return (x, y)


def torso_point(kps_xy: np.ndarray, kps_conf: np.ndarray, conf_th: float) -> Optional[Tuple[int, int]]:
    """몸통 대표점: hips 평균(가능하면), 아니면 shoulders 평균."""
    hips = []
    for n in ("left_hip", "right_hip"):
        p = pick_kp_xy(kps_xy, kps_conf, n, conf_th)
        if p is not None:
            hips.append(p)

    if len(hips) >= 1:
        xs = [p[0] for p in hips]
        ys = [p[1] for p in hips]
        return (int(round(sum(xs) / len(xs))), int(round(sum(ys) / len(ys))))

    sh = []
    for n in ("left_shoulder", "right_shoulder"):
        p = pick_kp_xy(kps_xy, kps_conf, n, conf_th)
        if p is not None:
            sh.append(p)

    if len(sh) >= 1:
        xs = [p[0] for p in sh]
        ys = [p[1] for p in sh]
        return (int(round(sum(xs) / len(xs))), int(round(sum(ys) / len(ys))))

    return None


def estimate_dist_from_bbox(h_px: int, fy: float, person_h_m: float = 1.7,
                            clip: Tuple[float, float] = (0.3, 80.0)) -> Optional[float]:
    """핀홀 모델로 거리 추정. dist = H_real * fy / h_px"""
    if h_px <= 0 or fy <= 0:
        return None
    d = (person_h_m * float(fy)) / float(h_px)
    d = float(np.clip(d, clip[0], clip[1]))
    return d


def load_model(model_path: str, device: str):
    # 파일이 없으면 흔한 이름들을 자동 탐색
    cand = [model_path]
    if not model_path.endswith(".pt"):
        cand.append(model_path + ".pt")
    # 사용자가 'yolo11n-pose'를 말한 케이스 대비
    if "pose" in model_path and not model_path.endswith(".pt"):
        cand.append(model_path.replace(".pt", "") + ".pt")

    chosen = None
    for p in cand:
        if os.path.exists(p):
            chosen = p
            break
    if chosen is None:
        # ultralytics가 자동 다운로드를 해줄 수도 있으므로 그대로 시도
        chosen = cand[0]

    model = YOLO(chosen)
    try:
        model.to(device)
    except Exception:
        pass
    return model, chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolo11n-pose.pt", help="YOLO pose 모델 경로(예: yolo11n-pose.pt)")
    ap.add_argument("--device", default="cpu", help="cpu | cuda:0 등")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.3, help="det conf threshold")
    ap.add_argument("--kpconf", type=float, default=0.25, help="keypoint conf threshold")
    ap.add_argument("--maxdet", type=int, default=10)
    ap.add_argument("--person_h", type=float, default=1.7, help="fallback 사람 키(m)")
    ap.add_argument("--show_depth_debug", action="store_true", help="키포인트별 depth(m) 디버그 표기")
    args = ap.parse_args()

    model, chosen = load_model(args.model, args.device)
    print(f"[INFO] model loaded: {chosen}")

    # RealSense init
    pipeline = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.depth, 640, 360, rs.format.z16, 30)
    cfg.enable_stream(rs.stream.color, 640, 360, rs.format.bgr8, 30)
    profile = pipeline.start(cfg)

    align = rs.align(rs.stream.color)
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = float(depth_sensor.get_depth_scale())

    # intrinsics (for fallback)
    color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
    intr = color_stream.get_intrinsics()
    fy = float(intr.fy)

    print(f"[INFO] depth_scale={depth_scale}, fy={fy:.2f}")

    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned = align.process(frames)
            depth_frame = aligned.get_depth_frame()
            color_frame = aligned.get_color_frame()
            if not depth_frame or not color_frame:
                continue

            depth_img = np.asanyarray(depth_frame.get_data())
            color_img = np.asanyarray(color_frame.get_data())
            H, W = color_img.shape[:2]

            # YOLO pose inference
            with (torch.inference_mode() if torch is not None else _nullcontext()):
                res = model.predict(
                    source=color_img,
                    imgsz=args.imgsz,
                    conf=args.conf,
                    max_det=args.maxdet,
                    device=args.device,
                    classes=[0],  # person
                    verbose=False,
                )[0]

            # 시각화: ultralytics plot은 편하지만 텍스트 커스텀하려고 직접 그림
            out = color_img.copy()

            if res.boxes is not None and len(res.boxes) > 0 and getattr(res, "keypoints", None) is not None:
                # keypoints shape: (n, 17, 2) / conf: (n, 17)
                kps_xy = res.keypoints.xy.cpu().numpy() if hasattr(res.keypoints.xy, "cpu") else np.array(res.keypoints.xy)
                kps_cf = res.keypoints.conf.cpu().numpy() if hasattr(res.keypoints.conf, "cpu") else np.array(res.keypoints.conf)

                for i, box in enumerate(res.boxes):
                    xyxy = box.xyxy[0].cpu().numpy() if hasattr(box.xyxy[0], "cpu") else np.array(box.xyxy[0])
                    x1, y1, x2, y2 = map(int, xyxy.tolist())
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(W - 1, x2), min(H - 1, y2)

                    # kps for this person
                    p_xy = kps_xy[i]   # (17,2)
                    p_cf = kps_cf[i]   # (17,)

                    # 대표 키포인트들 추출
                    pts: Dict[str, Optional[Tuple[int, int]]] = {}
                    pts["head"] = pick_kp_xy(p_xy, p_cf, "nose", args.kpconf)
                    pts["torso"] = torso_point(p_xy, p_cf, args.kpconf)

                    # hands/feet는 좌/우 2개를 각각 찍고 depth는 그룹 평균
                    pts["left_wrist"] = pick_kp_xy(p_xy, p_cf, "left_wrist", args.kpconf)
                    pts["right_wrist"] = pick_kp_xy(p_xy, p_cf, "right_wrist", args.kpconf)
                    pts["left_ankle"] = pick_kp_xy(p_xy, p_cf, "left_ankle", args.kpconf)
                    pts["right_ankle"] = pick_kp_xy(p_xy, p_cf, "right_ankle", args.kpconf)

                    # 키포인트 depth 수집
                    kp_depths: Dict[str, Optional[float]] = {}

                    # head/torso 단일
                    for name in ("head", "torso"):
                        p = pts.get(name)
                        if p is None:
                            kp_depths[name] = None
                        else:
                            d = depth_at_pixel_m(depth_img, depth_scale, p[0], p[1], win=7)
                            kp_depths[name] = d

                    # hands 평균
                    hand_ds = []
                    for name in ("left_wrist", "right_wrist"):
                        p = pts.get(name)
                        if p is None:
                            continue
                        d = depth_at_pixel_m(depth_img, depth_scale, p[0], p[1], win=7)
                        if d is not None:
                            hand_ds.append(d)
                        if args.show_depth_debug and d is not None:
                            kp_depths[name] = d
                    kp_depths["hands"] = float(np.mean(hand_ds)) if len(hand_ds) > 0 else None

                    # feet 평균
                    feet_ds = []
                    for name in ("left_ankle", "right_ankle"):
                        p = pts.get(name)
                        if p is None:
                            continue
                        d = depth_at_pixel_m(depth_img, depth_scale, p[0], p[1], win=7)
                        if d is not None:
                            feet_ds.append(d)
                        if args.show_depth_debug and d is not None:
                            kp_depths[name] = d
                    kp_depths["feet"] = float(np.mean(feet_ds)) if len(feet_ds) > 0 else None

                    # 최종 거리: head/torso/hands/feet 중 유효값 평균
                    valid = [kp_depths.get("head"), kp_depths.get("torso"),
                             kp_depths.get("hands"), kp_depths.get("feet")]
                    valid = [v for v in valid if v is not None and math.isfinite(v) and v > 0]

                    method = "depth(kp-avg)"
                    dist_m = float(np.mean(valid)) if len(valid) > 0 else None

                    if dist_m is None:
                        # fallback: bbox height 기반
                        h_px = max(1, y2 - y1)
                        dist_m = estimate_dist_from_bbox(h_px=h_px, fy=fy, person_h_m=args.person_h)
                        method = f"fallback({args.person_h:.1f}m)"

                    # draw bbox
                    cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2, cv2.LINE_AA)

                    # draw keypoints (간단히: 선택된 포인트만)
                    # head/torso: 큼직하게
                    for nm, rad in (("head", 6), ("torso", 6)):
                        p = pts.get(nm)
                        if p is not None:
                            cv2.circle(out, p, rad, (0, 0, 255), -1, cv2.LINE_AA)
                    # wrists/ankles: 작게
                    for nm in ("left_wrist", "right_wrist", "left_ankle", "right_ankle"):
                        p = pts.get(nm)
                        if p is not None:
                            cv2.circle(out, p, 4, (255, 0, 0), -1, cv2.LINE_AA)

                    # label
                    if dist_m is None:
                        label = "dist: N/A"
                    else:
                        label = f"{dist_m:.2f}m  [{method}]"

                    # outline text
                    org = (x1, max(0, y1 - 10))
                    cv2.putText(out, label, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
                    cv2.putText(out, label, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

                    # optional debug text: head/torso/hands/feet
                    if args.show_depth_debug:
                        dy = 18
                        dbg_lines = []
                        for k in ("head", "torso", "hands", "feet"):
                            v = kp_depths.get(k)
                            dbg_lines.append(f"{k}:{v:.2f}" if isinstance(v, (int, float)) else f"{k}:N/A")
                        for j, s in enumerate(dbg_lines):
                            porg = (x1, min(H - 5, y2 + 20 + j * dy))
                            cv2.putText(out, s, porg, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
                            cv2.putText(out, s, porg, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

            cv2.imshow("YOLO11n-Pose Distance (keypoints avg)", out)
            k = cv2.waitKey(1) & 0xFF
            if k == ord('q') or k == 27:
                break

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


class _nullcontext:
    def __enter__(self): return None
    def __exit__(self, exc_type, exc, tb): return False


if __name__ == "__main__":
    main()
