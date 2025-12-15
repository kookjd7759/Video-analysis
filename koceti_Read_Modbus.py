import time
import threading
import struct
import logging
import socket

from pymodbus.server import StartSerialServer
from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.datastore import ModbusDeviceContext, ModbusServerContext

class Crane_Final_Test:
    def __init__(self, target_ip ="0.0.0.0", port=5005, timeout=1):
        print(f"Modbus UDP 클라이언트 초기화: 주소={target_ip}, port={port}")
        self.safety_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            # 0.0.0.0은 '내 컴퓨터의 모든 IP'를 의미, S
            # port는 '장비가 데이터를 보내는 목적지 포트 번호'여야 함 (보통 받는 포트와 보내는 포트가 같으면 port 사용)
            self.safety_client.bind(("0.0.0.0", port)) 
            print(f"수신 대기 시작 (Bind): 192.168.0.10:{port}")
        except Exception as e:
            print(f"[주의] Bind 실패 (송신 전용이면 무시 가능): {e}")

        # 2. 타임아웃 설정
        self.safety_client.settimeout(3.0)
        # 3. 타겟 정보 저장 (UDP는 연결 지향이 아니므로 보낼 때마다 주소가 필요함)
        self.target_address = (target_ip, 5005) # (IP, Port) 튜플 형태
        
        logging.basicConfig()
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        pymodbus_log = logging.getLogger("pymodbus")
        pymodbus_log.setLevel(logging.CRITICAL)
        # -------------------------------------------------------
        # 2. [Server 설정] 메인 크레인용 (데이터 받는 용도)
        # -------------------------------------------------------
        # 메인 크레인 데이터가 저장될 메모리 (0~100번지)
        # Slave Context 생성 (Unit ID 1번이라고 가정)
        self.server_store = ModbusSequentialDataBlock(address=0, values=[0] * 100)
        slave_context = ModbusDeviceContext(hr=self.server_store)
        self.server_context = ModbusServerContext(devices={2: slave_context}, single=False)
        self.server_thread = None
        
    def connect_safety(self):
        print("장비에 연결을 시도합니다...")
        if self.safety_client.connect():
            print("연결 성공!")
            return True
        else:
            print("[ERROR] 장비에 연결할 수 없습니다. 포트와 연결 상태를 확인하세요.")
            return False

    def close_safety(self):
        print("연결을 종료합니다.")
        self.safety_client.close()
        
    # --- 환산 함수들은 그대로 유지 ---
    def overturn_stability(self, val):
        return round((val / 2000) * 200 - 100, 1)

    def center_x(self, val):
        return round((val / 10000) * 10000 - 5000, 1)

    def center_y(self, val):
        return round((val / 10000) * 10000 - 5000, 1)

    def load(self, val):
        return round((val / 400.0) * 40, 1)

    # 1. 평가 함수를 하나로 통합하여 모든 정보를 반환
    def assess_stability_risk(self, stability_percentage):
        if stability_percentage > 75:
            return {"level_num": 0, "level_str": "안전", "color": "green", "message": "정상 범위 내에서 안정적으로 작업 중입니다."}
        elif 50 <= stability_percentage <= 75:
            return {"level_num": 1, "level_str": "주의", "color": "yellow", "message": "작업 한계에 근접하고 있습니다. 주의가 필요합니다."}
        elif 25 <= stability_percentage < 50:
            return {"level_num": 2, "level_str": "경고", "color": "orange", "message": "위험 수준입니다. 작업 하중 및 반경을 재검토하세요."}
        else:
            return {"  ": 3, "level_str": "위험", "color": "red", "message": "전복 위험! 즉시 모든 작업을 중단하십시오!"}
                        
    def get_safety_sensor_data(self, device_id):
        """
        '최신' 데이터를 장비로부터 읽어와서 처리하고, 결과 딕셔너리를 반환합니다.
        """
        if self.safety_client is None:
            print("[ERROR] 소켓이 초기화되지 않았습니다.")
            return None

        # 1. 데이터를 '여기서' 실시간으로 읽습니다.
        response, addr = self.safety_client.recvfrom(1024)
        print(f"[SAFETY][RAW] unit={addr}, response={response}")

        expected_length = 25 
        if len(response) < expected_length:
            print(f"[ERROR] 데이터 길이가 부족합니다. 수신: {len(response)}B, 예상: {expected_length}B")
            return None

        try:
            # 25바이트만 잘라서 파싱
            unpacked_data = struct.unpack('<6fB', response[:25])
        except struct.error as e:
            print(f"[ERROR] 데이터 파싱 실패: {e}")
            return None
        
        left_lc_1 = unpacked_data[0]
        left_lc_2 = unpacked_data[1]
        left_lc_3 = unpacked_data[2]
        right_lc_1 = unpacked_data[3]
        right_lc_2 = unpacked_data[4]
        right_lc_3 = unpacked_data[5]
        roll_over_flag = unpacked_data[6] # 0: Normal, 1: Warning


        #print(f"[SAFETY][RECV] L1={left_lc_1:.2f}, L2={left_lc_2:.2f}, L3={left_lc_3:.2f}")
        #print(f"[SAFETY][RECV] R1={right_lc_1:.2f}, R2={right_lc_2:.2f}, R3={right_lc_3:.2f}")
        #print(f"[SAFETY][RECV] Warning Level={roll_over_flag}")

        results = {
            "left_lc_1": left_lc_1,
            "left_lc_2": left_lc_2,
            "left_lc_3": left_lc_3,
            "right_lc_1": right_lc_1,
            "right_lc_2": right_lc_2,
            "right_lc_3": right_lc_3,
            "roll_over_flag": roll_over_flag,
        }

        final_result = {
            "raw": results,
            "risk_assessment": roll_over_flag
        }
        return final_result

    # --- [기능 2] 메인 크레인 서버 구동 및 데이터 읽기 (Server) ---
    def start_main_crane_server(self, port):
        """메인 크레인용 서버를 별도 쓰레드로 시작"""
        if self.server_thread is not None:
            return

        def _server_runner():
            try:
                print(f"[Server] 메인 크레인 수신 대기 중... (Port: {port})")
                StartSerialServer(context=self.server_context, port='/dev/ttyUSB0', baudrate=115200,  bytesize=8, parity='N', stopbits=1)
            except Exception as e:
                print(f"[Server Error] {e}")

        self.server_thread = threading.Thread(target=_server_runner)
        self.server_thread.daemon = True
        self.server_thread.start()  
              
    def get_main_crane_data(self):
        """Unit ID 2번 메모리(self.server_store)에서 데이터를 꺼내옴"""
        try:
            # 필요한 전체 범위 데이터를 한 번에 가져옵니다 (0~40번지 정도면 충분)
            register_values = self.server_store.getValues(address=0, count=50)

            if register_values is None or len(register_values) < 40:
                print(f"[MAIN][ERROR] 레지스터 수가 부족합니다: {register_values}")
                return None

            packed_bytes = struct.pack('HH', register_values[3], register_values[2]) # 붐 길이
            boom_length = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[5], register_values[4]) # 붐 각도
            boom_angle = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[7], register_values[6]) # 제원(R)
            specifications = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[9], register_values[8]) # 반경1(R) MAIN
            Radius_MAIN = struct.unpack('f', packed_bytes)[0]
            
            packed_bytes = struct.pack('HH', register_values[11], register_values[10]) # 반경2(R) AUX
            Radius_AUX = struct.unpack('f', packed_bytes)[0]
                    
            packed_bytes = struct.pack('HH', register_values[13], register_values[12]) # 실 하중
            load_weight = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[15], register_values[14]) # 축전지 전압
            battery_voltage = struct.unpack('f', packed_bytes)[0]
            
            packed_bytes = struct.pack('HH', register_values[17], register_values[16]) # 엔진 RPM
            engine_speed = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[19], register_values[18]) # 엔진 온도
            engine_temp = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[21], register_values[20]) # 엔진오일압력
            oil_pressure = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[23], register_values[22]) # 작동유온도
            Working_oil_temp = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[25], register_values[24]) # MAIN HEIGHT
            main_height = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[27], register_values[26]) # AUX HEIGHT
            aux_height = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[29], register_values[28]) # 3RD HEIGHT
            _rd_height = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[31], register_values[30]) # STATUS1
            status_1 = struct.unpack('f', packed_bytes)[0]
            
            packed_bytes = struct.pack('HH', register_values[33], register_values[32]) # STATUS2
            status_2 = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[37], register_values[36]) # 하체 각도(R)
            lower_angle = struct.unpack('f', packed_bytes)[0]
                                                
            packed_bytes = struct.pack('HH', register_values[35], register_values[34]) # 풍속/풍향
            wind_speed = struct.unpack('f', packed_bytes)[0]

            packed_bytes = struct.pack('HH', register_values[39], register_values[38]) # 선회 각도/속도
            swing_angle = struct.unpack('f', packed_bytes)[0]

            data = {
                "boom length(m)": round(boom_length, 2),          # 붐 길이
                "boom angle(deg)": round(boom_angle, 2),          # 붐 각도
                "specifications": round(specifications, 2),       # 제원(R)
                "radius main(m)": round(Radius_MAIN, 2),          # 반경1(R) MAIN
                "radius aux(m)": round(Radius_AUX, 2),            # 반경2(R) AUX
                "load weight(ton)": round(load_weight, 2),        # 실 하중
                "battery voltage(V)": round(battery_voltage, 2),  # 축전지 전압
                "engine speed(rpm)": round(engine_speed, 2),      # 엔진 RPM
                "engine temp(C)": round(engine_temp, 2),          # 엔진 온도
                "oil pressure": round(oil_pressure, 2),           # 엔진 오일 압력
                "hydraulic oil temp(C)": round(Working_oil_temp, 2), # 작동유 온도
                "main height(m)": round(main_height, 2),          # MAIN HEIGHT
                "aux height(m)": round(aux_height, 2),            # AUX HEIGHT
                "3rd height(m)": round(_rd_height, 2),            # 3RD HEIGHT
                "status 1": round(status_1, 2),                   # STATUS 1 (필요 시 정수형 변환 고려)
                "status 2": round(status_2, 2),                   # STATUS 2
                "lower angle(deg)": round(lower_angle, 2),        # 하체 각도
                "wind speed(m/s)": round(wind_speed, 2),          # 풍속/풍향
                "swing angle(deg)": round(swing_angle, 2)         # 선회 각도/속도
            }
               
            print(f"[MAIN][DECODED] {data}")

            return data
        except Exception as e:
            print(f"[Data Error] 데이터 해석 중 오류: {e}")
            return None

"""
if __name__ == "__main__":    
    crane_tester = Crane_Final_Test(port='/dev/ttyUSB0')
    
    # 2. 장비에 연결
    if crane_tester.connect():
        try:
            # 1초 간격으로 최신 데이터를 요청
            while True:
                final_data = crane_tester.get_latest_result()
                if final_data:
                    pass
                else:
                    pass    
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n사용자에 의해 프로그램이 중단되었습니다.")
        finally:
            # 4. 작업이 끝나면 반드시 연결을 종료
            crane_tester.close()
"""            
