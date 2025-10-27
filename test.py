from analysis import AnalysisApp
import time
import subprocess
from modbus_worker import PollThread
from send_ip import send_ip

send_ip()

print("[INFO] Flask YOLO 서버 시작 중...")

# Modbus 폴링 스레드 시작
worker = PollThread(period_sec=5.0)
worker.start()

# Flask 서버 실행
app = AnalysisApp()
app.start_background_capture()
app.start_server(host="0.0.0.0", port=5000)

CF_URL = "https://video.solimatics.kr"
print(f"[INFO] Cloudflare Tunnel 연결 주소: {CF_URL}")
print(f"[INFO] 외부 접속 주소: {CF_URL}")

time.sleep(5)  # Flask 서버 안정화 대기
try:
    print(f"[INFO] Firefox를 전체화면 모드로 {CF_URL} 에 연결.")
except Exception as e:
    print(f"[WARN] Firefox 실행 실패: {e}")

try:
    while True:
        print(app.get_current_detections_list())
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\n[INFO] 사용자 종료 요청")
finally:
    app.stop_background_capture()
    worker.stop()
    print("[INFO] Flask 서버 종료 완료.")
