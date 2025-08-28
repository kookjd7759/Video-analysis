from analysis import AnalysisApp
import time

app = AnalysisApp()

app.start_background_capture()
app.start_server(host="0.0.0.0", port=5000)

# 3) 너의 폴링 루프
try:
    while True:
        print(app.get_current_detections_list())
        time.sleep(0.2)
finally:
    app.stop_background_capture()
