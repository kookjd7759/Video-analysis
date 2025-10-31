from analysis import AnalysisApp
import time
import socket
import queue
from send_ip import send_ip
from modbus_worker import modbus_worker
from CraneDataSimulatorWorker import CraneDataSimulatorWorker
from shared_state import SharedState
from flask import Flask, request # request 임포트 필요
import requests # API 호출을 위해 임포트
send_ip()

def make_local_url(port=5000):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    return f"http://{ip}:{port}"

final_data_queue = queue.Queue()
shared_state = SharedState()
# 2. 각 워커 객체 생성. 'shared_state'를 공통으로 전달합니다.
modbus_poller = modbus_worker(
    port='COM6', 
    data_queue=final_data_queue, 
    period_sec=1.0
)

data_simulator = CraneDataSimulatorWorker(
    data_queue=final_data_queue, 
    period_sec=0.3
)

app = AnalysisApp(
    host="0.0.0.0", 
    port=5000
)

try:
    url = make_local_url()
    print(f"url: {url}")
    print("[Main] Modbus 폴러와 데이터 시뮬레이터를 시작합니다.")
    modbus_poller.start()
    data_simulator.start()
    app.start_background_capture()
    app.start_server()
    
    # 3. 메인 프로그램은 최종 통합된 데이터를 큐에서 꺼내 사용합니다.
    while True:
        try:
            integrated_data = final_data_queue.get(timeout=2.0)
            print(app.get_current_detections_list())
            #time.sleep(0.2)
        except queue.Empty:
            # 워커들이 살아있는지 확인
            if not modbus_poller._th.is_alive() or not data_simulator._th.is_alive():
                print("[Main] [ERROR] 하나 이상의 워커 쓰레드가 중지되었습니다.")
                break
            continue
            
except KeyboardInterrupt:
    print("\n[Main] 종료 요청 수신.")
finally:
    print("[Main] 모든 워커와 리소스를 정리합니다...")
    
    # 2. 서버 종료 API 호출
    try:
        # 서버 스레드를 종료시키기 위해 shutdown API를 호출합니다.
        requests.post(f"http://127.0.0.1:{app.port}/shutdown")
        print("[Main] 서버 종료 요청 전송 완료.")
    except requests.exceptions.ConnectionError:
        # 서버가 이미 내려갔거나 다른 이유로 연결이 안될 수 있습니다.
        print("[Main] 서버에 연결할 수 없어 종료 요청을 보내지 못했습니다.")

    app.stop_background_capture()
    modbus_poller.stop()
    data_simulator.stop()
    
    # 3. 모든 스레드가 종료될 때까지 기다립니다.
    if app.server_thread and app.server_thread.is_alive():
        print("[Main] 서버 스레드가 종료될 때까지 대기합니다...")
        app.server_thread.join(timeout=2.0) # 타임아웃과 함께 대기

    modbus_poller.join()
    data_simulator.join()
    
    print("[Main] 모든 워커가 성공적으로 종료되었습니다.")
    print("[Main] 프로그램 종료.")
