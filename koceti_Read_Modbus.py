import time
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian
from pymodbus.client.sync import ModbusSerialClient

class Crane_Final_Test:
    def __init__(self, port='COM6', baudrate=115200, timeout=1):
        print(f"Modbus 클라이언트 초기화: 포트={port}, 속도={baudrate}")
        self.client = ModbusSerialClient(
            method='rtu',
            port=port,
            baudrate=baudrate,
            parity='N',
            stopbits=1,
            bytesize=8,
            timeout=timeout
        )

    def connect(self):
        print("장비에 연결을 시도합니다...")
        if self.client.connect():
            print("연결 성공!")
            return True
        else:
            print("[ERROR] 장비에 연결할 수 없습니다. 포트와 연결 상태를 확인하세요.")
            return False

    def close(self):
        print("연결을 종료합니다.")
        self.client.close()
        
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
                        
    def get_read_once(self, unit_id):
        """
        '최신' 데이터를 장비로부터 읽어와서 처리하고, 결과 딕셔너리를 반환합니다.
        """
        if not self.client.is_socket_open():
            print("[ERROR] 장비에 연결되어 있지 않습니다. 먼저 connect()를 호출하세요.")
            return None # 연결이 안되어 있으면 None 반환
            
        # 1. 데이터를 '여기서' 실시간으로 읽습니다.
        response = self.client.read_holding_registers(address=0, count=7, unit=unit_id)
        
        # 2. 응답에 에러가 있는지 확인합니다.
        if response.isError():
            print(f"[ERROR] Modbus 응답 오류: {response}")
            return None # 에러 발생 시 None 반환
        
        # 3. 에러가 없으면 값을 처리합니다.
        raw_values = response.registers
        #print("[DATA] 수신된 레지스터 값:", raw_values)
        
        # 1. 먼저 안정도 값을 계산합니다.
        stability_value = self.overturn_stability(raw_values[0])
        
        # 2. 계산된 안정도 값을 이용해 위험도를 평가합니다.
        risk_assessment = self.assess_stability_risk(stability_value)
                
        results = {
            "크레인 전복 안정도 (%)": self.overturn_stability(raw_values[0]),
            "무게 중심 위치 X축 (mm)": self.center_x(raw_values[1]),
            "무게 중심 위치 Y축 (mm)": self.center_y(raw_values[2]),
            "평균 부하 (전방) (Ton)": self.load(raw_values[3]),
            "평균 부하 (후방) (Ton)": self.load(raw_values[4]),
            "평균 부하 (우측) (Ton)": self.load(raw_values[5]),
            "평균 부하 (좌측) (Ton)": self.load(raw_values[6]),
        }
        final_result = {
            "raw": results,
            "risk_assessment": risk_assessment
        }
        # 4. 처리된 결과를 반환하여 다른 곳에서 사용할 수 있도록 합니다.
        return final_result

    def get_main_crane_data(self, unit_id):
        """
        크레인 메인 컨트롤러(Unit ID)로부터 32비트 데이터를 읽어옵니다.
        """
        if not self.client.is_socket_open():
            print("[ERROR] 장비에 연결되어 있지 않습니다.")
            return None
        
        try:
            # 여러 주소의 데이터를 읽어야 하므로, 필요한 만큼 read 함수를 호출합니다.
            # 예: 붐 길이(2), 붐 각도(4), 인양 중량(12)
            
            # 붐 길이(add 2, len 2)와 붐 각도(add 4, len 2) 읽기
            res_boom = self.client.read_holding_registers(address=2, count=4, unit=unit_id)
            if res_boom.isError(): return None # 에러 시 함수 종료
            
            # 인양 중량(add 12, len 2) 읽기
            res_weight = self.client.read_holding_registers(address=12, count=2, unit=unit_id)
            if res_weight.isError(): return None

            # 엔진 속도(add 16, len 2) 읽기
            engine_rpm = self.client.read_holding_registers(address=16, count=2, unit=unit_id)
            if engine_rpm.isError(): return None

            # 바람 속도(add 34, len 2) 읽기
            wind_rpm = self.client.read_holding_registers(address=34, count=2, unit=unit_id)
            if wind_rpm.isError(): return None
            
            # 스윙 각도(add 38, len 2) 읽기
            swing_angle = self.client.read_holding_registers(address=38, count=2, unit=unit_id)
            if swing_angle.isError(): return None
                                                
            # 32비트 실수(float)로 변환
            # Byte Order는 이미지에 명시된 'little endian'으로 설정
            decoder_boom = BinaryPayloadDecoder.fromRegisters(res_boom.registers, byteorder=Endian.Little)
            decoder_weight = BinaryPayloadDecoder.fromRegisters(res_weight.registers, byteorder=Endian.Little)
            
            decoder_rpm = BinaryPayloadDecoder.fromRegisters(engine_rpm.registers, byteorder=Endian.Little)
            decoder_wind = BinaryPayloadDecoder.fromRegisters(wind_rpm.registers, byteorder=Endian.Little)
            decoder_swing = BinaryPayloadDecoder.fromRegisters(swing_angle.registers, byteorder=Endian.Little)
            results = {
                "boom length(m)": round(decoder_boom.decode_32bit_float(), 2),
                "boom angle(deg)": round(decoder_boom.decode_32bit_float(), 2),
                "weight(ton)": round(decoder_weight.decode_32bit_float(), 2),
                "engine speed(rpm)": round(decoder_rpm.decode_32bit_float(), 2),
                "wind speed(m/s)": round(decoder_wind.decode_32bit_float(), 2),
                "swing angle(deg)": round(decoder_swing.decode_32bit_float(), 2)
            }
            return results
        except Exception as e:
            print(f"메인 크레인(ID:{unit_id}) 데이터 처리 중 오류: {e}")
            return None
            
"""
if __name__ == "__main__":    
    crane_tester = Crane_Final_Test(port='COM6')
    
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