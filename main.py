import platform
import cv2
from flask import Flask, Response
from process_frame import YOLORealSenseProcessor

processor = YOLORealSenseProcessor()

def is_raspberry_pi():
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return 'Raspberry Pi' in f.read()
    except Exception:
        return False

if is_raspberry_pi():
    print('🍓 raspberry pi version execution')
    app = Flask(__name__)

    def gen():
        while True:
            frame = processor.get_frame()
            if frame is None:
                continue
            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

    @app.route('/video_feed')
    def video_feed():
        return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

    if __name__ == '__main__':
        print("🌐  Raspberry Pi에서 웹 스트리밍을 시작합니다: http://192.168.0.15:5000/video_feed")
        app.run(host='0.0.0.0', port=5000, debug=False)
        processor.stop()
else:
    print('🖥️ window version execution')
    try:
        while True:
            frame = processor.get_frame()
            if frame is None:
                continue
            cv2.imshow("YOLO + Depth Stream", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        processor.stop()
        cv2.destroyAllWindows()
