import cv2
import math
import numpy as np
import threading
import time
from flask import Flask, Response, jsonify, request
from processor import YOLORealSenseProcessor


class AnalysisApp:
    def __init__(self):
        # ===== 스트림 / 레이더 기본 설정 =====
        self.STREAM_W = 640          # 스트림 가로 리사이즈(원본이 더 크면 축소)
        self.JPEG_QUALITY = 40       # JPEG 품질(50~70 추천)
        self.HFOV_DEG = 87.0         # 카메라 수평 FOV(도)
        self.DMAX_M = 4.0            # 레이더 최대 표시 거리(미터)

        # Radar helpers 색
        self.GRID = (60, 220, 110)   # 라인 색(초록)
        self.BG   = (10, 10, 10)     # 배경(짙은 회색)
        self.EDGE = (0, 255, 0)      # FOV 경계 라인
        self.RED  = (0, 0, 255)      # 객체 사각형

        # 최신 인식 결과(비디오 루프/백그라운드에서 갱신)
        self._latest_objects = []    # [{"label":"person","distance":..., "center":...}, ...]
        self._lock = threading.Lock()

        # 백그라운드 캡처 스레드 제어
        self._stop_evt = threading.Event()
        self._bg_thread = None

        # 프로세서 & Flask
        self.processor = YOLORealSenseProcessor()
        self.app = Flask(__name__)
        self._register_routes()
        
        # 공유 프레임 버퍼
        self._latest_jpeg = None         # bytes (인코딩된 JPEG)
        self._last_frame_id = 0          # 프레임 증가 카운터
        self._new_frame_evt = threading.Event()

    # -------------------------------
    # 외부 인터페이스
    # -------------------------------
    def get_current_detections_list(self):
        with self._lock:
            return list(self._latest_objects)

    def start_background_capture(self):
        """ /video_feed 연결 없이도 latest를 계속 갱신 """
        if self._bg_thread and self._bg_thread.is_alive():
            return
        self._stop_evt.clear()
        self._bg_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._bg_thread.start()

    def stop_background_capture(self):
        self._stop_evt.set()
        if self._bg_thread:
            self._bg_thread.join(timeout=1.0)

    def run_server(self, host="0.0.0.0", port=5000, debug=False, threaded=True):
        print(f"➡ 접속: http://{host}:{port}/")
        self.app.run(host=host, port=port, debug=debug, threaded=threaded)

    def run_local_preview(self):
        """라즈베리파이 아닌 PC에서 로컬 미리보기"""
        try:
            while True:
                frame, _ = self.processor.get_frame()
                if frame is None:
                    continue
                cv2.imshow("Local Preview", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        finally:
            self.processor.stop()
            cv2.destroyAllWindows()

    # -------------------------------
    # 내부: 백그라운드 캡처 루프
    # -------------------------------
    def _capture_loop(self):
        while not self._stop_evt.is_set():
            frame, detections = self.processor.get_frame()
            if frame is None:
                time.sleep(0.005)
                continue

            if isinstance(detections, list):
                with self._lock:
                    self._latest_objects = detections

            # 스트리밍용 JPEG 프레임을 미리 만들어 공유 버퍼에 저장
            h, w = frame.shape[:2]
            if w > self.STREAM_W:
                new_h = int(h * (self.STREAM_W / w))
                frame_resized = cv2.resize(frame, (self.STREAM_W, new_h), interpolation=cv2.INTER_AREA)
            else:
                frame_resized = frame

            ok, jpeg = cv2.imencode('.jpg', frame_resized,
                                    [int(cv2.IMWRITE_JPEG_QUALITY), self.JPEG_QUALITY])
            if ok:
                with self._lock:
                    self._latest_jpeg = jpeg.tobytes()
                    self._last_frame_id += 1
                self._new_frame_evt.set()   # 새 프레임 신호
                self._new_frame_evt.clear()

            time.sleep(0.001)

    # -------------------------------
    # 레이더 도우미
    # -------------------------------
    def make_radar_bg(self, width=720, height=420, hfov_deg=None,
                      margin=26, outer_th=2):
        if hfov_deg is None:
            hfov_deg = self.HFOV_DEG

        img = np.full((height, width, 3), self.BG, np.uint8)

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
        draw_arc(R, R, max(TOP_START, left_deg_top), min(TOP_END, right_deg_top), self.GRID, th=outer_th)

        # FOV 경계(대각선 2개)
        for ang_deg in (left_deg_top, right_deg_top):
            a = math.radians(ang_deg)
            x = int(cx + R * math.cos(a))  # ellipse 기준각과 일관성 있게 cos/sin 사용
            y = int(cy + R * math.sin(a))
            cv2.line(img, origin, (x, y), self.EDGE, 2, cv2.LINE_AA)

        # 중앙 수직선(270° 방향으로)
        x_top = cx
        y_top = cy - R
        cv2.line(img, (x_top, y_top), (cx, cy), self.GRID, 2, cv2.LINE_AA)

        # 내부 거리 링(윗반원 3개)
        for r in (int(R * 0.30), int(R * 0.55), int(R * 0.80)):
            draw_arc(r, r, TOP_START, TOP_END, self.GRID, th=2)

        # 바닥 기준선
        cv2.line(img, (margin, cy), (width - margin, cy), self.GRID, 2, cv2.LINE_AA)

        # 카메라 아이콘(하단 중앙 작은 사각형)
        cam_w, cam_h = 20, 12
        cv2.rectangle(img,
                      (cx - cam_w // 2, cy - cam_h // 2),
                      (cx + cam_w // 2, cy + cam_h // 2),
                      self.GRID, 2, cv2.LINE_AA)

        return img, origin, R

    def pol2pix_from_center(self, center_norm, dist_m, origin, R, hfov_deg=None, dmax=None):
        if hfov_deg is None:
            hfov_deg = self.HFOV_DEG
        if dmax is None:
            dmax = self.DMAX_M

        cx, cy = origin
        angle_deg = (float(center_norm) - 0.5) * hfov_deg
        a = math.radians(angle_deg)
        r = int(max(0.0, min(1.0, float(dist_m) / max(dmax, 1e-6))) * R)
        x = int(cx + r * math.sin(a))
        y = int(cy - r * math.cos(a))
        return x, y

    # -------------------------------
    # Flask 라우트 등록
    # -------------------------------
    def _register_routes(self):
        app = self.app

        @app.route('/video_feed')
        def video_feed():
            def gen():
                last_id = -1
                while True:
                    # 새 프레임이 올 때까지 잠깐 대기 (최대 100fps 수준)
                    self._new_frame_evt.wait(timeout=0.05)
                    with self._lock:
                        cur_id = self._last_frame_id
                        jpeg = self._latest_jpeg
                    if jpeg is None or cur_id == last_id:
                        # 아직 새 프레임 없음
                        time.sleep(0.01)
                        continue
                    last_id = cur_id

                    yield (b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            resp = Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            return resp

        @app.route('/info')
        def info():
            # distance, center만 간결히 반환
            with self._lock:
                lo = list(self._latest_objects)
            objs = []
            for o in lo:
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
            hfov = float(request.args.get('hfov', self.HFOV_DEG))
            dmax = float(request.args.get('dmax', self.DMAX_M))

            # 레이더 배경 생성
            img, origin, R = self.make_radar_bg(width=width, height=height, hfov_deg=hfov)

            # 최신 객체들 표시
            with self._lock:
                lo = list(self._latest_objects)
            for o in lo:
                if not isinstance(o, dict):
                    continue
                dist = o.get('distance')
                center = o.get('center')
                if not isinstance(dist, (int, float)) or not isinstance(center, (int, float)):
                    continue
                px, py = self.pol2pix_from_center(center, dist, origin, R, hfov_deg=hfov, dmax=dmax)
                cv2.circle(img, (px, py), 6, (0, 0, 255), -1, cv2.LINE_AA)
                cv2.circle(img, (px, py), 6, (0, 0, 0), 1, cv2.LINE_AA)
                cv2.putText(img, f"{dist:.2f}m", (px + 10, py - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

            ok, buf = cv2.imencode('.png', img)
            if not ok:
                return Response(status=500)
            resp = Response(buf.tobytes(), mimetype='image/png')
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
                setInterval(()=>{ document.getElementById('radar').src = '/radar.png?t='+Date.now(); }, 1000);
              </script>
            </body>
            </html>
            '''

    def start_server(self, host="0.0.0.0", port=5000):
        # Flask debug=False 필수(스레드용)
        th = threading.Thread(target=self.app.run, kwargs={
            "host": host, "port": port, "debug": False, "threaded": True, "use_reloader": False
        }, daemon=True)
        th.start()
        return th

    # -------------------------------
    # 유틸
    # -------------------------------
    @staticmethod
    def is_raspberry_pi():
        try:
            with open('/proc/device-tree/model', 'r') as f:
                return 'Raspberry Pi' in f.read()
        except Exception:
            return False


# -------------------------------
# 실행부
# -------------------------------
if __name__ == '__main__':
    app = AnalysisApp()
    if app.is_raspberry_pi():
        app.run_server(host='0.0.0.0', port=5000, debug=False, threaded=True)
    else:
        app.run_local_preview()
