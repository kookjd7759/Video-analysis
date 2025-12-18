import threading
import time
import struct
import json
import zlib  # CRC32 계산을 위한 zlib 모듈 임포트

class transmit_Crane_Data_Worker:
    def __init__(self,shared_state, mqttclient, period_sec=1):
        # 시리얼 넘버
        self.device_serial = ""
        # 인식된 객체 정보
        self.obj_couint = 0
        self.obj_distance = 0
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
        self.body_angle_x = 0.00 # 하체 각도 x
        self.body_angle_y = 0.00 # 하체 각도 y
        self.boom_angle = 0.0 # 붐각도
        self.danger = 0 # 위험도
        self.period_sec = period_sec
        self._stop = threading.Event()
        self._th = None

        # MQTT 클라이언트와 같은 내부 객체는 여기서 생성합니다.
        self.mqtt = mqttclient
        self.shared_state =shared_state
    
    def _run(self):
        try:
            """
            백그라운드 쓰레드에서 실행될 메인 로직.
            기존 main() 함수의 while 루프가 여기에 들어옵니다.
            """
            print("[Worker] 데이터 시뮬레이터 쓰레드 시작.")

            # 3. 주기 루프
            while not self._stop.is_set():
                start = time.time()
                # CAN Data
                self.body_angle_x = self.shared_state.get_body_angle_x()
                self.body_angle_y = self.shared_state.get_body_angle_y()
                
                # 장치 의 ID        
                self.device_serial = self.shared_state.get_serial_info()
                
                # AML Data
                self.boom_length = self.shared_state.get_boom_length()
                self.actual_load = self.shared_state.get_weight()
                self.fluid_temp =  self.shared_state.get_hydraulic_oil_temp() #작동유 온도
                
                self.STATUS1 = 0#STATUS1
                self.STATUS2 = 0#STATUS2
                self.STATUS3 = 0#STATUS3(예비)
                    
                self.voltage = self.shared_state.get_battery_voltage() # 축전지 전압
                self.MAIN_HEIGHT = self.shared_state.get_main_height()
                self.spec = self.shared_state.get_specifications() #제원
                self.engine_rpm = self.shared_state.get_engine_speed() # 엔진 RPM
                self.AUX_HEIGHT = self.shared_state.get_aux_height() #AUX HEIGHT
                self.wind = self.shared_state.get_wind_speed() #풍속/풍향
                self.MAIN_radius1 = self.shared_state.get_radius_main() #반경1 MAIN
                self.engine_temp = self.shared_state.get_engine_temp() #엔진 온도
                self.RD_HEIGHT = self.shared_state.get_rd_height() #
                self.turning_angle =self.shared_state.get_swing_angle() #선회각도/속도
                self.turning_speed = 0
                self.AUX_radius2 = self.shared_state.get_radius_aux()
                self.oil_pressure = self.shared_state.get_oil_pressure() # 엔진오일 압력
                self.body_angle = self.shared_state.get_lower_angle() # 하체 각도
                self.boom_angle = self.shared_state.get_boom_angle()
                self.danger = self.shared_state.get_danger_level()
             
                # 객체 인식정보
                self.obj_couint, self.obj_distance = self.shared_state.get_obj_info()
                
                fmt = '<19f8i'
                fixed_data = struct.pack(fmt,
                    # --- [Float 영역 20개] ---
                    float(self.boom_length), # self.boom_length
                    float(self.actual_load),
                    float(self.fluid_temp), # self.fluid_temp
                    float(self.angle),
                    float(self.voltage),
                    float(self.MAIN_HEIGHT),
                    float(self.engine_rpm), # self.engine_rpm
                    float(self.AUX_HEIGHT),
                    float(self.wind), # self.wind
                    float(self.MAIN_radius1),
                    float(self.engine_temp), # self.engine_temp
                    float(self.RD_HEIGHT),
                    float(self.turning_angle),
                    float(self.turning_speed),
                    float(self.AUX_radius2),
                    float(self.oil_pressure),
                    float(self.boom_angle), # self.boom_angle
                    float(self.body_angle), # 하체 각도
                    float(self.obj_distance),  # 추가된 거리 값

                    # --- [Int 영역 5개] ---
                    int(self.body_angle_x),
                    int(self.body_angle_y),
                    int(self.STATUS1),
                    int(self.STATUS2),
                    int(self.STATUS3),
                    int(self.spec), # 정수 인지? 문자열 인지..???
                    int(self.danger), # self.danger
                    int(self.obj_couint) # 추가된 카운트 값 (오타 그대로 반영함)
                )                
                
                serial_bytes = str(self.device_serial).encode('utf-8')
                serial_pack = struct.pack('<I', len(serial_bytes)) + serial_bytes
                payload_body = serial_pack + fixed_data
                
                crc_value = zlib.crc32(payload_body) & 0xffffffff
                payload_with_crc = payload_body + struct.pack('<I', crc_value)
                
                total_len = len(payload_with_crc) + 4  # 헤더(4byte) 포함한 전체 길이
                final_packet = struct.pack('<I', total_len) + payload_with_crc
                
                #print(f"[Worker] 시뮬레이터 데이터 생성 및 큐에 저장: {message}")
                self.mqtt.Analysis_msg("Event/CraneTest/", final_packet)

                # --- 3-3. 주기 맞추기 ---
                elapsed = time.time() - start
                remain = self.period_sec - elapsed
                if remain > 0:
                    end = time.time() + remain
                    while not self._stop.is_set() and time.time() < end:
                        time.sleep(0.1)
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