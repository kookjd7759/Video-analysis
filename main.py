import cv2
import math
import numpy as np
from flask import Flask, Response, jsonify, request
from process_frame import YOLORealSenseProcessor

app = Flask(__name__)
processor = YOLORealSenseProcessor()

# ===== 스트림 / 레이더 기본 설정 =====
STREAM_W = 640          # 스트림 가로 리사이즈(원본이 더 크면 축소)
JPEG_QUALITY = 40       # JPEG 품질(50~70 추천)
HFOV_DEG = 87.0         # 카메라 수평 FOV(도)
DMAX_M = 4.0            # 레이더 최대 표시 거리(미터)

# 최신 인식 결과(비디오 루프에서 갱신)
latest_objects = []     # [{"label":"person","distance":..., "center":...}, ...]

# -------------------------------
# Radar helpers (스타일: 예시 이미지 느낌으로)
# -------------------------------
GRID = (60, 220, 110)   # 라인 색(초록)
BG   = (10, 10, 10)     # 배경(짙은 회색)
EDGE = (0, 255, 0)      # FOV 경계 라인
RED  = (0, 0, 255)      # 객체 사각형

def make_radar_bg(width=720, height=420, hfov_deg=HFOV_DEG,
                  margin=26, outer_th=2):
    """
    원점: (cx, cy=height-margin) — 화면 하단에서 margin만큼 위.
    윗반원(180~360°)을 ellipse2Poly + polylines로 매끈하게 그림.
    """
    img = np.full((height, width, 3), BG, np.uint8)

    cx, cy = width // 2, height - margin
    origin = (cx, cy)

    # 사용 가능한 최대 반지름
    R = min(width // 2 - margin, height - margin - 1)
    R = max(R, 60)

    def draw_arc(rx, ry, a0, a1, color, th=2):
        pts = cv2.ellipse2Poly(center=origin, axes=(rx, ry),
                               angle=0, arcStart=int(a0), arcEnd=int(a1), delta=1)
        if len(pts) > 1:
            cv2.polylines(img, [pts], isClosed=False, color=color, thickness=th, lineType=cv2.LINE_AA)

    # 윗반원 범위(약간 깎아서 가장자리 잘림 방지)
    PAD = 5
    TOP_START = 180 + PAD
    TOP_END   = 360 - PAD

    # FOV 아치(시야각을 위쪽(270°) 기준으로 좌/우로 펼침)
    half_deg = hfov_deg / 2.0
    left_deg_top  = 270 - half_deg
    right_deg_top = 270 + half_deg
    draw_arc(R, R, max(TOP_START, left_deg_top), min(TOP_END, right_deg_top), GRID, th=outer_th)

    # FOV 경계(대각선 2개)
    for ang_deg in (left_deg_top, right_deg_top):
        a = math.radians(ang_deg)
        x = int(cx + R * math.cos(a))  # ellipse 기준각과 일관성 있게 cos/sin 사용
        y = int(cy + R * math.sin(a))
        cv2.line(img, origin, (x, y), EDGE, 2, cv2.LINE_AA)

    # 중앙 수직선(270° 방향으로)
    x_top = cx
    y_top = cy - R
    cv2.line(img, (x_top, y_top), (cx, cy), GRID, 2, cv2.LINE_AA)

    # 내부 거리 링(윗반원 3개)
    for r in (int(R * 0.30), int(R * 0.55), int(R * 0.80)):
        draw_arc(r, r, TOP_START, TOP_END, GRID, th=2)

    # 바닥 기준선
    cv2.line(img, (margin, cy), (width - margin, cy), GRID, 2, cv2.LINE_AA)

    # 카메라 아이콘(하단 중앙 작은 사각형)
    cam_w, cam_h = 20, 12
    cv2.rectangle(img,
                  (cx - cam_w // 2, cy - cam_h // 2),
                  (cx + cam_w // 2, cy + cam_h // 2),
                  GRID, 2, cv2.LINE_AA)

    return img, origin, R

def pol2pix_from_center(center_norm, dist_m, origin, R, hfov_deg=HFOV_DEG, dmax=DMAX_M):
    """
    center∈[0,1], dist_m(미터) -> 레이더 평면 픽셀 좌표
    레이더 원점은 하단 중앙, 위로 부채꼴.
    """
    cx, cy = origin
    angle_deg = (float(center_norm) - 0.5) * hfov_deg
    a = math.radians(angle_deg)
    r = int(max(0.0, min(1.0, float(dist_m) / max(dmax, 1e-6))) * R)
    x = int(cx + r * math.sin(a))
    y = int(cy - r * math.cos(a))
    return x, y

# -------------------------------
# Routes
# -------------------------------
@app.route('/video_feed')
def video_feed():
    def gen():
        global latest_objects
        while True:
            frame, detections = processor.get_frame()
            if frame is None:
                continue

            # 최신 인식 결과 갱신
            if isinstance(detections, list):
                latest_objects = detections

            # 리사이즈 + JPEG 인코딩(지연/대역폭↓)
            h, w = frame.shape[:2]
            if w > STREAM_W:
                new_h = int(h * (STREAM_W / w))
                frame = cv2.resize(frame, (STREAM_W, new_h), interpolation=cv2.INTER_AREA)

            ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if not ret:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

    resp = Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/info')
def info():
    # distance, center만 간결히 반환
    objs = []
    for o in latest_objects:
        if not isinstance(o, dict):
            continue
        dist = o.get("distance")
        center = o.get("center")
        if isinstance(dist, (int, float)) and isinstance(center, (int, float)):
            objs.append({"distance": round(float(dist), 2),
                         "center": round(float(center), 3)})
    return jsonify({"count": len(objs), "objects": objs})

@app.route('/radar.png')
def radar_png():
    # 쿼리 파라미터로 크기, 시야각, 최대거리 변경 가능
    width = int(request.args.get('w', 720))
    height = int(request.args.get('h', 420))
    hfov = float(request.args.get('hfov', HFOV_DEG))
    dmax = float(request.args.get('dmax', DMAX_M))

    # 레이더 배경 생성 (매끈한 타원 아치 포함한 버전)
    img, origin, R = make_radar_bg(width=width, height=height, hfov_deg=hfov)

    # 최신 객체들 빨간 채워진 원으로 표시
    for o in latest_objects:
        if not isinstance(o, dict):
            continue
        dist = o.get('distance')
        center = o.get('center')
        if not isinstance(dist, (int, float)) or not isinstance(center, (int, float)):
            continue
        # 극좌표 -> 화면 좌표 변환
        px, py = pol2pix_from_center(center, dist, origin, R, hfov_deg=hfov, dmax=dmax)
        # 빨간색 꽉 찬 원 (radius=6)
        cv2.circle(img, (px, py), 6, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.circle(img, (px, py), 6, (0, 0, 0), 1, cv2.LINE_AA)
        # 거리 텍스트
        cv2.putText(img, f"{dist:.2f}m", (px + 10, py - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

    # PNG 인코딩 후 응답
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        return Response(status=500)
    resp = Response(buf.tobytes(), mimetype='image/png')
    # 캐시 방지 헤더
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/')
def index():
    return '''
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8" />
      <title>YOLO + Depth + Radar</title>
      <style>
        body{background:#111;color:#eee;font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0}
        .wrap{max-width:1200px;margin:24px auto;padding:0 16px}
        .row{display:grid;grid-template-columns:1fr;gap:12px}
        @media (min-width: 1100px){ .row{grid-template-columns: 3fr 2fr;} }
        .card{background:#1b1b1b;border:1px solid #2b2b2b;border-radius:12px;padding:12px}
        img.view{max-width:100%;height:auto;border-radius:10px;display:block;margin:auto;
                 box-shadow:0 4px 24px rgba(0,0,0,.4)}
        pre{white-space:pre-wrap;line-height:1.7;margin:0}
        .muted{color:#aaa;font-size:12px;margin-top:6px}
        .title{font-weight:700;margin:0 0 8px}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="row">
          <div class="card">
            <div class="title">비디오 스트림</div>
            <img class="view" src="/video_feed" alt="stream"/>
          </div>
          <div class="card">
            <div class="title">레이더 뷰</div>
            <img id="radar" class="view" src="/radar.png" alt="radar"/>
            <div class="muted">1초마다 갱신됩니다.</div>
          </div>
        </div>
        <div class="card" style="margin-top:12px">
          <div class="title">실시간 인식 정보</div>
          <pre id="info">초기화 중…</pre>
          <div class="muted">0.5초 간격으로 갱신됩니다.</div>
        </div>
      </div>
      <script>
        async function tick(){
          try{
            const r = await fetch('/info', {cache:'no-store'});
            const d = await r.json();
            let lines = [];
            lines.push(`[인지된 사람 수 : ${d.count}명]`);
            (d.objects || []).forEach((o,i)=>{
              const dist = (typeof o.distance==='number' && isFinite(o.distance)) ? o.distance.toFixed(2)+' m' : 'N/A';
              const cx = (typeof o.center==='number' && isFinite(o.center)) ? o.center.toFixed(3) : 'N/A';
              lines.push(`${i+1}. 거리=${dist} | center=${cx}`);
            });
            document.getElementById('info').textContent = lines.join('\\n');
          }catch(e){
            document.getElementById('info').textContent = '데이터 수신 오류: ' + e.message;
          }
        }
        setInterval(tick, 500); tick();
        // 레이더 PNG 캐시 무력화용 주기적 새로고침
        setInterval(()=>{ document.getElementById('radar').src = '/radar.png?t='+Date.now(); }, 1000);
      </script>
    </body>
    </html>
    '''

def is_raspberry_pi():
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return 'Raspberry Pi' in f.read()
    except Exception:
        return False

if is_raspberry_pi():
    if __name__ == '__main__':
        print("➡ 접속: http://<라즈베리파이IP>:5000/")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
else:
    if __name__ == '__main__':
        try:
            while True:
                frame, _ = processor.get_frame()
                if frame is None:
                    continue
                cv2.imshow("Local Preview", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        finally:
            processor.stop()
            cv2.destroyAllWindows()
