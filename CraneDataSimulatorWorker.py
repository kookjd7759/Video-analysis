import threading
import time
import queue
import random
import json
from datetime import datetime
from Crane_MQTT import MQTTClient # Crane_MQTT.py 파일이 있다고 가정
from shared_state import SharedState

class CraneDataSimulatorWorker:
    def __init__(self, data_queue,shared_state, period_sec=0.3):
        # 시뮬레이션 할 데이터 를 정의 합니다.
        #각도, 축전지 전압, MAIN HEIGHT, STATUS3(예비), 제원, 엔진 RPM, AUX HEIGHT, 풍속/풍향, 반경1 MAIN, 엔진 온도, 3RD HEIGHT, 선회각도/속도, 반경2 AUX, 엔진 오일압력, STATUS1, 하체 각도, 붐 각도
        self.boom_length = 0.00 # 붐 길이
        self.actual_load = 0.00 #실 하중
        self.fluid_temp = 0.00 #작동유 온도
        self.STATUS1 = 0#STATUS1
        self.STATUS2 = 0#STATUS2
        self.STATUS3 = 0#STATUS3(예비)
        self.angle = 0 # 각도 
        self.voltage = 0 # 축전지 전압
        self.MAIN_HEIGHT = 0
        self.spec = 0#제원
        self.engine_rpm = 0#엔진 RPM
        self.AUX_HEIGHT = 0#AUX HEIGHT
        self.wind = 0.00 #풍속/풍향
        self.MAIN_radius1 = 0#반경1 MAIN
        self.engine_temp = 0.00 #엔진 온도
        self.RD_HEIGHT = 0 #3RD HEIGHT
        self.turning_angle =0.0#선회각도/속도
        self.turning_speed = 0.0 #선회각도/속도
        self.AUX_radius2 = 0 #반경2 AUX
        self.oil_pressure = 0.000 # 엔진오일 압력
        self.body_angle = 0.00 # 하체 각도
        self.boom_angle = 0.0 # 붐각도
        self.X1 = 0.00 #장애물 위치
        self.X2 = 0.00
        self.Y1 = 0.00
        self.Y2 = 0.00
        self.danger = 0 # 위험도
        self.period_sec = period_sec
        self.data_queue = data_queue
        self._stop = threading.Event()
        self._th = None

        # MQTT 클라이언트와 같은 내부 객체는 여기서 생성합니다.
        self.mqtt = MQTTClient()
        self.shared_state =shared_state
    
    def _run(self):
        try:
            # 각 장비의 Unit ID를 변수로 지정 (실제 ID로 변경 가능)
            STABILITY_SENSOR_ID = 1
            MAIN_CRANE_ID = 2    # 지금은 안 쓰지만 의미상 유지

            # 1. 메인 크레인 데이터 수신용 서버 시작
            self.crane_tester.start_main_crane_server(port=self.main_crane_port)

            # 2. 안전센서 쪽 Modbus 접속
            if not self.crane_tester.connect_safety():
                print("[Worker] [ERROR] 연결 실패. 쓰레드를 종료합니다.")
                self.data_queue.put({"error": f"연결 실패: {self.safety_port} 포트를 확인하세요."})
                return

            # 3. 주기 루프
            while not self._stop.is_set():
                start = time.time()
                ts = datetime.now().strftime("%H:%M:%S")

                # --- 3-1. 안전센서 데이터 ---
                final_data = self.crane_tester.get_safety_sensor_data(STABILITY_SENSOR_ID)
                if final_data is None:
                    print(f"[{ts}][WORKER] 사이클 실패 (안전센서 응답 오류 또는 예외)")
                else:
                    print(f"[{ts}][WORKER] 사이클 OK")
                    print(f"[{ts}][WORKER][SAFETY] raw={final_data.get('raw')}")
                    print(f"[{ts}][WORKER][SAFETY] risk={final_data.get('risk_assessment')}")

                    # 큐로 전달
                    self.data_queue.put(final_data)

                    # shared_state 위험도 갱신
                    risk_assessment = final_data.get("risk_assessment", {})
                    risk_level = risk_assessment.get("level_num", 0)
                    self.shared_state.set_danger_level(risk_level)
                    print(f"[{ts}][WORKER][STATE] danger_level -> {risk_level}")

                # --- 3-2. 메인 크레인 데이터 ---
                main_data = self.crane_tester.get_main_crane_data()
                if main_data:
                    print(f"[{ts}][WORKER][MAIN RAW] {main_data}")

                    boom_length = main_data.get("boom length(m)", 0)
                    boom_angle = main_data.get("boom angle(deg)", 0)
                    weight = main_data.get("weight(ton)", 0)
                    engine_speed = main_data.get("engine speed(rpm)", 0)
                    wind_speed = main_data.get("wind speed(m/s)", 0)
                    swing_angle = main_data.get("swing angle(deg)", 0)

                    # shared_state에 저장
                    self.shared_state.set_boom_length(boom_length)
                    self.shared_state.set_boom_angle(boom_angle)
                    self.shared_state.set_weight(weight)
                    self.shared_state.set_engine_speed(engine_speed)
                    self.shared_state.set_wind_speed(wind_speed)
                    self.shared_state.set_swing_angle(swing_angle)

                    print(
                        f"[{ts}][WORKER][STATE] boom_length={boom_length}, boom_angle={boom_angle}, "
                        f"weight={weight}, engine_speed={engine_speed}, "
                        f"wind_speed={wind_speed}, swing_angle={swing_angle}"
                    )
                else:
                    print(f"[{ts}][WORKER][MAIN] 메인 크레인 데이터 수신 실패.")

                # --- 3-3. 주기 맞추기 ---
                elapsed = time.time() - start
                remain = self.period_sec - elapsed
                if remain > 0:
                    end = time.time() + remain
                    while not self._stop.is_set() and time.time() < end:
                        time.sleep(0.1)
        finally:
            self.crane_tester.close_safety()
            print("[Worker] 연결이 안전하게 종료되었습니다.")

    # --- start, stop, join 메소드는 modbus_worker와 동일 ---
    def start(self, daemon=True):
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=daemon)
        self._th.start()

    def stop(self):
        self._stop.set()

    def join(self, timeout=None):
        if self._th:
            self._th.join(timeout)