import threading
import time
import queue
from datetime import datetime
from koceti_Read_Modbus import Crane_Final_Test

class koceti_worker:
    def __init__(self, safety_port, main_crane_port, data_queue, shared_state, period_sec=1.0):
        self.period_sec = period_sec
        self._stop = threading.Event()
        self._th = None
        self.safety_port = safety_port        # Client용 포트
        self.main_crane_port = main_crane_port # Server용 포트
        self.data_queue = data_queue
        print(f"[Worker] Modbus 워커 쓰레드 시작 (포트: {self.safety_port})")
        print(f"[Worker] Modbus server 쓰레드 시작 (포트: {self.main_crane_port})")
   
        # 1. Crane_Final_Test 객체를 '쓰레드 안에서' 생성하고 연결합니다.
        self.crane_tester = Crane_Final_Test(port=self.safety_port)
        self.shared_state = shared_state
        
    def _run(self):
        try:
            # 각 장비의 Unit ID를 변수로 지정 (실제 ID로 변경해야 합니다)
            STABILITY_SENSOR_ID = 1
            MAIN_CRANE_ID = 2    
            # 1. [Server 시작] 메인 크레인 데이터 수신용 서버를 먼저 켭니다. (백그라운드)
            self.crane_tester.start_main_crane_server(port=self.main_crane_port)
            if self.crane_tester.connect_safety():
                while not self._stop.is_set():
                    start = time.time()
                    ts = datetime.now().strftime("%H:%M:%S")

                    final_data = self.crane_tester.get_safety_sensor_data(STABILITY_SENSOR_ID)
                    if final_data is None:
                        print(f"[{ts}] 사이클 실패 (응답 오류 또는 예외)")
                    else:
                        print(f"[{ts}] 사이클 OK")
                        self.data_queue.put(final_data)
                        risk_assessment = final_data.get("risk_assessment", {})
                        risk_level = risk_assessment.get("level_num", 0)
                        self.shared_state.set_danger_level(risk_level)
                    
                    # 2. 크레인 메인 컨트롤러 데이터 요청
                    main_data = self.crane_tester.get_main_crane_data()
                    if main_data:
                        print(f"[메인 크레인 ID:{MAIN_CRANE_ID}] 수신 데이터: {main_data}")
                        boom_length = main_data.get("boom length(m)", 0)
                        self.shared_state.set_boom_length(boom_length)
                        boom_angle = main_data.get("boom angle(deg)", 0)
                        self.shared_state.set_boom_angle(boom_angle)
                        weight = main_data.get("weight(ton)", 0)
                        self.shared_state.set_weight(weight)
                        engine_speed = main_data.get("engine speed(rpm)", 0)
                        self.shared_state.set_engine_speed(engine_speed)
                        wind_speed = main_data.get("wind speed(m/s)", 0)
                        self.shared_state.set_wind_speed(wind_speed)
                        swing_angle = main_data.get("swing angle(deg)", 0)
                        self.shared_state.set_swing_angle(swing_angle)

                    else:
                        print(f"[메인 크레인 ID:{MAIN_CRANE_ID}] 데이터 수신 실패.")
                    
                    # 1초 간격
                    elapsed = time.time() - start
                    remain = self.period_sec - elapsed
                    if remain > 0:
                        end = time.time() + remain
                        while not self._stop.is_set() and time.time() < end:
                            time.sleep(0.1)
            else:
                print("[Worker] [ERROR] 연결 실패. 쓰레드를 종료합니다.")
                # (선택) 큐에 에러 메시지를 넣어 메인 쓰레드에 알릴 수도 있습니다.
                self.data_queue.put({"error": f"연결 실패: {self.safety_port} 포트를 확인하세요."})
                return
        finally:
            self.crane_tester.close_safety()
            print("[Worker] 연결이 안전하게 종료되었습니다.")
  
    
    def start(self, daemon=True):
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=daemon)
        self._th.start()

    def stop(self):
        self._stop.set()
        self.crane_tester.close_safety()

    def join(self, timeout=None):
        if self._th:
            self._th.join(timeout)
