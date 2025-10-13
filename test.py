from analysis import AnalysisApp
import time
import subprocess
import socket

def make_local_url(port=5000):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    return f"http://{ip}:{port}"

url = make_local_url()
print(f"url: {url}")
app = AnalysisApp()
app.start_background_capture()
app.start_server(host="0.0.0.0", port=5000)

try:
    subprocess.Popen(["firefox", "--kiosk", url])
    while True:
        print(app.get_current_detections_list())
        time.sleep(0.2)
finally:
    app.stop_background_capture()
