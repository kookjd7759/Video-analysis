# main.py
import cv2
from flask import Flask, Response, jsonify
from process_frame import YOLORealSenseProcessor

processor = YOLORealSenseProcessor()
app = Flask(__name__)

latest_distances = [] 

def is_raspberry_pi():
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return 'Raspberry Pi' in f.read()
    except Exception:
        return False

@app.route('/video_feed')
def video_feed():
    def gen():
        global latest_distances 
        while True:
            frame, distances = processor.get_frame()
            if frame is None:
                continue
            latest_distances = distances 
            ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/info')
def info():
    distances = [
        round(obj.get("distance", 0.0), 2)
        for obj in latest_distances
        if isinstance(obj, dict) and isinstance(obj.get("distance"), (int, float))
    ]
    return jsonify({
        "count": len(distances),
        "distances": distances
    })

@app.route('/')
def index():
    return '''
    <!doctype html><html lang="ko"><head><meta charset="utf-8"><title>YOLO+Depth</title>
    <style>body{background:#111;color:#eee;font-family:system-ui;margin:0}
    .wrap{max-width:1200px;margin:24px auto;padding:0 16px}
    .panel{margin-top:14px;background:#1b1b1b;border:1px solid #2b2b2b;border-radius:12px;padding:16px}
    pre{white-space:pre-wrap;line-height:1.7;margin:0}</style></head>
    <body><div class="wrap">
      <img src="/video_feed" style="max-width:100%;border-radius:10px;display:block;margin:auto"/>
      <div class="panel"><pre id="info">초기화 중…</pre></div>
    </div>
    <script>
      async function tick(){
        try{
          const r = await fetch('/info',{cache:'no-store'});
          const d = await r.json();
          let s = `[인지된 사람 수 : ${d.count}명]\\n`;
          d.distances.forEach((v,i)=> s += `${i+1}. ${v} m\\n`);
          document.getElementById('info').textContent = s.trim();
        }catch(e){ document.getElementById('info').textContent='오류: '+e.message; }
      }
      setInterval(tick, 500); tick();
    </script></body></html>'''
    
if is_raspberry_pi():
    if __name__ == '__main__':
        print("➡ 접속: http://<라즈베리파이IP>:5000/")
        # ✅ 동시 요청 처리 위해 threaded=True
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
else:
    if __name__ == '__main__':
        try:
            while True:
                frame, _ = processor.get_frame()
                if frame is None: continue
                cv2.imshow("Local Preview", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
        finally:
            processor.stop()
            cv2.destroyAllWindows()
