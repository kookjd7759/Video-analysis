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
        """
        백그라운드 쓰레드에서 실행될 메인 로직.
        기존 main() 함수의 while 루프가 여기에 들어옵니다.
        """
        print("[Worker] 데이터 시뮬레이터 쓰레드 시작.")
        
        # --- MQTT 연결 및 루프 시작 ---
        self.mqtt.connecting()
        self.mqtt.loop_start()
        try:
            # --- 메인 루프 ---
            while not self._stop.is_set():
                start = time.time()
                
                # 1. MQTT 메시지 수신 및 처리
                msg = self.mqtt.get_message()
                if msg is not None:
                    try:
                        jsonObject = json.loads(msg)
                        self.angle = jsonObject.get('INCLINATION_X', [0])[0] / 100
                    except (TypeError, json.JSONDecodeError) as e:
                        print(f"Error decoding JSON: {e}")
                        continue                
                
                self.boom_length = self.shared_state.get_boom_length()
                self.actual_load = random.uniform(2990.0,3010.0)
                self.fluid_temp =  random.uniform(99.1,199.1) #작동유 온도
                self.STATUS1 = 0#STATUS1
                self.STATUS2 = 0#STATUS2
                self.STATUS3 = 0#STATUS3(예비)
                    
                self.voltage = random.uniform(23.9,24.9) # 축전지 전압
                self.MAIN_HEIGHT = 0
                self.spec = 9999#제원
                self.engine_rpm = self.shared_state.get_engine_speed()
                self.AUX_HEIGHT = 0#AUX HEIGHT
                self.wind = self.shared_state.get_wind_speed()
                self.MAIN_radius1 = 0#반경1 MAIN
                self.engine_temp = random.randint(100,200)
                self.RD_HEIGHT = random.randint(0, 4000)
                self.turning_angle =random.randint(0,10)
                self.turning_speed = random.randint(0,10)
                self.AUX_radius2 = random.randint(0,10)
                self.oil_pressure = random.randint(200,1600)
                self.body_angle = random.randint(0,360) # 하체 각도
                self.boom_angle = self.shared_state.get_boom_angle()
                self.X1 = random.uniform(0.0, 10.0) #장애물 위치
                self.X2 = random.uniform(0.0, 10.0)
                self.Y1 = random.uniform(0.0, 10.0)
                self.Y2 = random.uniform(0.0, 10.0)
                self.danger = self.shared_state.get_danger_level()
                
                # 3. 최종 데이터 딕셔너리 생성
                message = {"boom_length":self.boom_length,
                           "actual_load":self.actual_load,
                           "fluid_temp":self.fluid_temp,
                           "STATUS1":self.STATUS1,
                           "STATUS2":self.STATUS2,
                           "STATUS3":self.STATUS3,
                           "angle":self.angle,
                           "voltage":self.voltage,
                           "MAIN_HEIGHT":self.MAIN_HEIGHT,
                           "spec":self.spec,
                           "engine_rpm":self.engine_rpm,
                           "AUX_HEIGHT":self.AUX_HEIGHT,
                           "wind":self.wind,
                           "MAIN_radius1":self.MAIN_radius1,
                           "engine_temp":self.engine_temp,
                           "RD_HEIGHT":self.RD_HEIGHT,
                           "turning_angle":self.turning_angle,
                           "turning_speed":self.turning_speed,
                           "AUX_radius2":self.AUX_radius2,
                           "oil_pressure":self.oil_pressure,
                           "body_angle":self.body_angle,
                           "boom_angle":self.boom_angle,
                           "X1":self.X1,
                           "Y1":self.Y1,
                           "X2":self.X2,
                           "Y2":self.Y2,
                           "danger":self.danger
                        }
                
                # 4. ★★ 가장 중요한 부분: 생성된 데이터를 큐에 넣습니다! ★★
                self.data_queue.put(message)
                self.mqtt.Analysis_msg('Event/CraneTest/', json.dumps(message))
                
                # 5. 정확한 주기 제어
                elapsed = time.time() - start
                remain = self.period_sec - elapsed
                if remain > 0:
                    self._stop.wait(remain)

        finally:
            # 6. 쓰레드가 종료될 때 MQTT 리소스를 안전하게 정리합니다.
            print("[Worker] MQTT 연결을 종료합니다.")
            self.mqtt.loop_stop()
            self.mqtt.disconnect()
            print("[Worker] 데이터 시뮬레이터 쓰레드 종료.")

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