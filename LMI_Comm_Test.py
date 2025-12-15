import logging, threading, time, struct
import numpy as np

from pymodbus.server import StartSerialServer
from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.datastore import ModbusDeviceContext, ModbusServerContext

# LMI 에서 수신되는 모든 데이터를 수신 하는 테스트용
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

pymodbus_log = logging.getLogger("pymodbus")
pymodbus_log.setLevel(logging.CRITICAL)

store = ModbusSequentialDataBlock(address=0, values=[0] * 100)
slave_context = ModbusDeviceContext(hr=store)
context = ModbusServerContext(devices={1: slave_context}, single=False)

def modbus_com():
    StartSerialServer(context=context, port='COM3', baudrate=115200,  bytesize=8, parity='N', stopbits=1)
    logger.info("modbus client initialized!")

def registers_to_float(regs, index):
    # 현재 작성하신 로직 (index+1이 먼저 옴)
    packed = struct.pack('HH', regs[index+1], regs[index])
    return struct.unpack('f', packed)[0]


modbus_com_task = threading.Thread(target=modbus_com)
modbus_com_task.daemon = True
modbus_com_task.start()

logger.info("program started!")

while True:
    register_values = store.getValues(address=0, count=50)

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

    print(f'{boom_length:.2f}', f'{boom_angle:.2f}', f'{load_weight:.2f}', f'{engine_speed:.2f}', f'{wind_speed:.2f}', f'{swing_angle:.2f}')
    time.sleep(0.1)
	