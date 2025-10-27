from analysis import AnalysisApp
import time
import socket
from modbus_worker import PollThread
from send_ip import send_ip

send_ip()

def make_local_url(port=5000):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    return f"http://{ip}:{port}"

print("[INFO] 5초 주기 폴링 시작")
worker = PollThread(period_sec=5.0)
worker.start()

url = make_local_url()
print(f"url: {url}")
app = AnalysisApp()
app.start_background_capture()
app.start_server(host="0.0.0.0", port=5000)

try:
    while True:
        print(app.get_current_detections_list())
        time.sleep(0.2)
finally:
    app.stop_background_capture()
