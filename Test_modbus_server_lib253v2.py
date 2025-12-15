import logging, threading, time, struct
from pymodbus.server import StartSerialServer
from pymodbus.datastore import ModbusSequentialDataBlock,  ModbusDeviceContext, ModbusServerContext

# 전체 로깅 기본 설정
logging.basicConfig()

# 루트 로거는 INFO로 두고
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# pymodbus 로거만 CRITICAL로 올려서 숨기기
logging.getLogger("pymodbus").setLevel(logging.CRITICAL)


# HR 블록 정의
store = ModbusSequentialDataBlock(0, [0]*100)

# Slave Context 생성
slave_context = ModbusDeviceContext(hr=store)

# Server Context 생성 (ID=1 등록)
context = ModbusServerContext(devices={2: slave_context}, single=False)


# 서버 실행 함수
def modbus_server():
    StartSerialServer(
        context=context,
        port='COM5',       # Windows에서는 COM 포트, Linux에서는 /dev/ttyUSB0
        baudrate=115200,
        bytesize=8,
        parity='N',
        stopbits=1
    )

# 서버를 별도 스레드에서 실행
server_thread = threading.Thread(target=modbus_server)
server_thread.daemon = True
server_thread.start()
logger.info("Modbus RTU Server started on COM5 (Slave ID=2)")

while True:
    register_values = context[2].getValues(3, 0, count=50)


    packed_bytes = struct.pack('HH', register_values[2], register_values[3])
    boom_length = struct.unpack('f', packed_bytes)[0]

    packed_bytes = struct.pack('HH', register_values[4], register_values[5])
    boom_angle = struct.unpack('f', packed_bytes)[0]

    packed_bytes = struct.pack('HH', register_values[12], register_values[13])
    load_weight = struct.unpack('f', packed_bytes)[0]

    packed_bytes = struct.pack('HH', register_values[16], register_values[17])
    engine_speed = struct.unpack('f', packed_bytes)[0]

    packed_bytes = struct.pack('HH', register_values[34], register_values[35])
    wind_speed = struct.unpack('f', packed_bytes)[0]

    packed_bytes = struct.pack('HH', register_values[38], register_values[39])
    swing_angle = struct.unpack('f', packed_bytes)[0]

    print(f'{boom_length:.2f}', f'{boom_angle:.2f}', f'{load_weight:.2f}', f'{engine_speed:.2f}', f'{wind_speed:.2f}', f'{swing_angle:.2f}')
    time.sleep(0.1)