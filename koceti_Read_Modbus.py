import time
import threading
import struct
import logging
#from pymodbus.client import ModbusSerialClient
from pymodbus.client.sync import ModbusSerialClient
from pymodbus.server.sync import ModbusSerialServer
#from pymodbus.datastore import ModbusSequentialDataBlock, ModbusDeviceContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

class Crane_Final_Test:
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200, timeout=1):
        print(f"Modbus 클라이언트 초기화: 포트={port}, 속도={baudrate}")
        self.safety_client = ModbusSerialClient(
            method='rtu',
            port=port,
            baudrate=baudrate,
            parity='N',
            stopbits=1,
            bytesize=8,
            timeout=timeout
        )
        
        # -------------------------------------------------------
        # 2. [Server 설정] 메인 크레인용 (데이터 받는 용도)
        # -------------------------------------------------------
        # 메인 크레인 데이터가 저장될 메모리 (0~100번지)
        self.server_store = ModbusSequentialDataBlock(address=0, values=[0]*100)
        # Slave Context 생성 (Unit ID 1번이라고 가정)
        self.server_context = ModbusServerContext(
            slaves={2: self.server_store},
            single=False
        )
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
            return {"level_num": 3, "level_str": "위험", "color": "red", "message": "전복 위험! 즉시 모든 작업을 중단하십시오!"}
                        
    def get_safety_sensor_data(self, unit_id):
        """
        '최신' 데이터를 장비로부터 읽어와서 처리하고, 결과 딕셔너리를 반환합니다.
        """
        if not self.safety_client.is_socket_open():
            print("[ERROR] 장비에 연결되어 있지 않습니다. 먼저 connect_safety()를 호출하세요.")
            return None  # 연결이 안되어 있으면 None 반환

        # 1. 데이터를 '여기서' 실시간으로 읽습니다.
        response = self.safety_client.read_holding_registers(address=0, count=7, unit=unit_id)
        print(f"[SAFETY][RAW] unit={unit_id}, response={response}")

        # 2. 응답에 에러가 있는지 확인합니다.
        if response.isError():
            print(f"[ERROR] Modbus 응답 오류: {response}")
            return None  # 에러 발생 시 None 반환

        # 3. 에러가 없으면 값을 처리합니다.
        raw_values = response.registers
        print(f"[SAFETY][REGS] {raw_values}")

        if raw_values is None or len(raw_values) < 7:
            print(f"[ERROR] 레지스터 수가 부족합니다: {raw_values}")
            return None

        # 1. 먼저 안정도 값을 계산합니다.
        stability_value = self.overturn_stability(raw_values[0])
        print(f"[SAFETY][STABILITY] raw={raw_values[0]} -> {stability_value}%")

        # 2. 계산된 안정도 값을 이용해 위험도를 평가합니다.
        risk_assessment = self.assess_stability_risk(stability_value)
        print(f"[SAFETY][RISK] {risk_assessment}")

        results = {
            "크레인 전복 안정도 (%)": self.overturn_stability(raw_values[0]),
            "무게 중심 위치 X축 (mm)": self.center_x(raw_values[1]),
            "무게 중심 위치 Y축 (mm)": self.center_y(raw_values[2]),
            "평균 부하 (전방) (Ton)": self.load(raw_values[3]),
            "평균 부하 (후방) (Ton)": self.load(raw_values[4]),
            "평균 부하 (우측) (Ton)": self.load(raw_values[5]),
            "평균 부하 (좌측) (Ton)": self.load(raw_values[6]),
        }
        print(f"[SAFETY][CONVERTED] {results}")

        final_result = {
            "raw": results,
            "risk_assessment": risk_assessment
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
                server = ModbusSerialServer(
                    context=self.server_context,
                    port=port,
                    baudrate=115200,
                    bytesize=8,
                    parity='N',
                    stopbits=1
                )
                server.serve_forever()
            except Exception as e:
                print(f"[Server Error] {e}")

        self.server_thread = threading.Thread(target=_server_runner, daemon=True)
        self.server_thread.start()
        
    def get_main_crane_data(self):
        """Unit ID 2번 메모리(self.server_store)에서 데이터를 꺼내옴"""
        try:
            # 필요한 전체 범위 데이터를 한 번에 가져옵니다 (0~40번지 정도면 충분)
            all_regs = self.server_store.getValues(address=0, count=50)
            print(f"[MAIN][RAW REGS 0~49] {all_regs}")

            if all_regs is None or len(all_regs) < 40:
                print(f"[MAIN][ERROR] 레지스터 수가 부족합니다: {all_regs}")
                return None

            # 1. 붐 길이 (Address 2, Count 2) + 붐 각도 (Address 4, Count 2)
            decoder_boom = BinaryPayloadDecoder.fromRegisters(
                all_regs[2:6],
                byteorder=Endian.Little,
                wordorder=Endian.Little
            )
            boom_length = round(decoder_boom.decode_32bit_float(), 2)
            boom_angle = round(decoder_boom.decode_32bit_float(), 2)

            # 2. 인양 중량 (Address 12, Count 2)
            decoder_weight = BinaryPayloadDecoder.fromRegisters(
                all_regs[12:14],
                byteorder=Endian.Little,
                wordorder=Endian.Little
            )
            weight = round(decoder_weight.decode_32bit_float(), 2)

            # 3. 엔진 속도 (Address 16, Count 2)
            decoder_rpm = BinaryPayloadDecoder.fromRegisters(
                all_regs[16:18],
                byteorder=Endian.Little,
                wordorder=Endian.Little
            )
            rpm = round(decoder_rpm.decode_32bit_float(), 2)

            # 4. 풍속 (Address 34, Count 2)
            decoder_wind = BinaryPayloadDecoder.fromRegisters(
                all_regs[34:36],
                byteorder=Endian.Little,
                wordorder=Endian.Little
            )
            wind = round(decoder_wind.decode_32bit_float(), 2)

            # 5. 스윙 각도 (Address 38, Count 2)
            decoder_swing = BinaryPayloadDecoder.fromRegisters(
                all_regs[38:40],
                byteorder=Endian.Little,
                wordorder=Endian.Little
            )
            swing = round(decoder_swing.decode_32bit_float(), 2)

            data = {
                "boom length(m)": boom_length,
                "boom angle(deg)": boom_angle,
                "weight(ton)": weight,
                "engine speed(rpm)": rpm,
                "wind speed(m/s)": wind,
                "swing angle(deg)": swing
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
