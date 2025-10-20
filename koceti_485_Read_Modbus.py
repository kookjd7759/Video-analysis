from pymodbus.client.sync import ModbusSerialClient

client = ModbusSerialClient(
    method='rtu',
    port='COM6',
    baudrate=115200,
    parity='N',
    stopbits=1,
    bytesize=8,
    timeout=1
)

# 환산 함수들 (원본 그대로)
def overturn_stability(val):
    return round((val / 2000) * 200 - 100, 1)

def center_x(val):
    return round((val / 10000) * 10000 - 5000, 1)

def center_y(val):
    return round((val / 10000) * 10000 - 5000, 1)

def load(val):
    return round((val / 10000) * 40, 1)

# 1회 사이클을 함수로
def read_once():
    client.connect()
    try:
        response = client.read_holding_registers(address=0, count=7, unit=1)

        if response.isError():
            print("[ERROR] 응답 오류:", response)
            return None, None

        raw_values = response.registers
        print("[DATA] 수신된 레지스터 값:", raw_values)

        converted = {
            "크레인 전복 안정도 (%)": overturn_stability(raw_values[0]),
            "무게 중심 위치 X축 (mm)": center_x(raw_values[1]),
            "무게 중심 위치 Y축 (mm)": center_y(raw_values[2]),
            "평균 부하 (전방) (Ton)": load(raw_values[3]),
            "평균 부하 (후방) (Ton)": load(raw_values[4]),
            "평균 부하 (우측) (Ton)": load(raw_values[5]),
            "평균 부하 (좌측) (Ton)": load(raw_values[6]),
        }

        for name, value in converted.items():
            print(f"{name}: {value}")

        return raw_values, converted
    except:
        print('[ERROR] Connection error')
        return None, None
    finally:
        client.close()

if __name__ == "__main__":
    read_once()
