import threading
import time
import struct
import json
from datetime import datetime
from Crane_MQTT import MQTTClient # Crane_MQTT.py 파일이 있다고 가정
from shared_state import SharedState
import zlib  # CRC32 계산을 위한 zlib 모듈 임포트

class Update_Can_Data:
    def __init__(self,shared_state, mqttclient, period_sec=1):
        self.body_angle_x = 0.00 # 하체 각도 x
        self.body_angle_y = 0.00 # 하체 각도 y
        self.period_sec = period_sec
        self._stop = threading.Event()
        self._th = None

        # MQTT 클라이언트와 같은 내부 객체는 여기서 생성합니다.
        self.mqtt = mqttclient
        self.shared_state =shared_state
    
    def _run(self):
        try:
            # 3. 주기 루프
            while not self._stop.is_set():
                start = time.time()
                # 1. MQTT 메시지 수신 및 처리
                msg = self.mqtt.get_message()
                if msg is not None:
                    try:
                        jsonObject = json.loads(msg)
                        self.body_angle_x = jsonObject.get('INCLINATION_X', [0])[0]
                        self.body_angle_y = jsonObject.get('INCLINATION_Y', [0])[0]
                        self.shared_state.set_body_angle_x(self.body_angle_x)
                        self.shared_state.set_body_angle_y(self.body_angle_y)
                    except (TypeError, json.JSONDecodeError) as e:
                        print(f"Error decoding JSON: {e}")
                        continue
        finally:
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