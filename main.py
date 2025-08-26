# main.py
import cv2
from flask import Flask, Response, jsonify
from process_frame import YOLORealSenseProcessor

processor = YOLORealSenseProcessor()
app = Flask(__name__)


# 최근 인식 결과 보관 (video_feed 루프에서 갱신)
latest_objects = []   # [{"label":"person","distance":1.23,"center":0.42}, ...]

def is_raspberry_pi():
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return 'Raspberry Pi' in f.read()
    except Exception:
        return False

@app.route('/video_feed')
def video_feed():
    def gen():
        global latest_objects
        while True:
            frame, detections = processor.get_frame()   # (ndarray, list[dict])
            if frame is None:
                continue
            # 최신 인식 결과 갱신
            latest_objects = detections if isinstance(detections, list) else []

            # 스트림 인코딩 (대역폭 줄이려면 품질 낮추기)
            ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/info')
def info():
    # center(0~1), distance(m)만 추려서 반환
    objs = []
    for obj in latest_objects:
        if not isinstance(obj, dict):
            continue
        dist = obj.get("distance")
        center = obj.get("center")
        if isinstance(dist, (int, float)) and isinstance(center, (int, float)):
            objs.append({
                "distance": round(float(dist), 2),
                "center": round(float(center), 3)
            })
    return jsonify({
        "count": len(objs),
        "objects": objs
    })

@app.route('/')
def index():
    # 영상 위, 아래 텍스트 패널 (거리 + center 표시)
    return '''
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8" />
      <title>YOLO + Depth</title>
      <style>
        body{background:#111;color:#eee;font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0}
        .wrap{max-width:1200px;margin:24px auto;padding:0 16px}
        .video{text-align:center}
        img{max-width:100%;height:auto;border-radius:10px;box-shadow:0 4px 24px rgba(0,0,0,.4)}
        .panel{margin-top:14px;background:#1b1b1b;border:1px solid #2b2b2b;border-radius:12px;padding:16px}
        pre{white-space:pre-wrap;line-height:1.7;margin:0}
        .muted{color:#aaa;font-size:12px;margin-top:6px}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="video"><img src="/video_feed" alt="stream"/></div>
        <div class="panel">
          <pre id="info">초기화 중…</pre>
          <div class="muted">0.5초마다 갱신됩니다.</div>
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
              const distStr = (typeof o.distance==='number' && isFinite(o.distance)) ? o.distance.toFixed(2)+' m' : 'N/A';
              const centerStr = (typeof o.center==='number' && isFinite(o.center)) ? o.center.toFixed(3) : 'N/A';
              lines.push(`${i+1}. 거리=${distStr} | center=${centerStr}`);
            });
            document.getElementById('info').textContent = lines.join('\\n');
          }catch(e){
            document.getElementById('info').textContent = '데이터 수신 오류: ' + e.message;
          }
        }
        setInterval(tick, 500);
        tick();
      </script>
    </body>
    </html>
    '''

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
