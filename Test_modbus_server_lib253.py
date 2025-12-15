import logging, threading, time, struct
import numpy as np
from pymodbus.client.sync import ModbusSerialClient
from pymodbus.server.sync import ModbusSerialServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian



logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)
pymodbus_log = logging.getLogger("pymodbus")
pymodbus_log.setLevel(logging.CRITICAL)


#S = ModbusSequentialDataBlock(address=0, values=[0] * 100)
slave_context = ModbusSlaveContext(
    di=ModbusSequentialDataBlock(0, [0]*100),  # Discrete Inputs
    co=ModbusSequentialDataBlock(0, [0]*100),  # Coils
    hr=ModbusSequentialDataBlock(0, [0]*100),  # Holding Registers
    ir=ModbusSequentialDataBlock(0, [0]*100)   # Input Registers
)

#context = ModbusServerContext(slaves={2: slave_context}, single=False)
context = ModbusServerContext(slaves={
    1: slave_context,   # ID=1
    2: slave_context    # ID=2
}, single=False)
#slave_context = ModbusServerContext(hr=store)
#context = ModbusServerContext(devices={2: slave_context}, single=False)

def modbus_com():
    ModbusSerialServer(context=context, port='/dev/ttyUSB0', baudrate=115200,  bytesize=8, parity='N', stopbits=1)
    logger.info("modbus client initialized!")


modbus_com_task = threading.Thread(target=modbus_com)
modbus_com_task.daemon = True
modbus_com_task.start()
logger.info("program started!")



while True:
    #register_values = store.getValues(address=0, count=50)
    register_values = context[2].getValues(3, 0, count=50)
    print(register_values)
    packed_bytes = struct.pack('HH', register_values[3], register_values[2])
    boom_length = struct.unpack('f', packed_bytes)[0]
    packed_bytes = struct.pack('HH', register_values[5], register_values[4])
    boom_angle = struct.unpack('f', packed_bytes)[0]
    packed_bytes = struct.pack('HH', register_values[13], register_values[12])
    load_weight = struct.unpack('f', packed_bytes)[0]
    packed_bytes = struct.pack('HH', register_values[17], register_values[16])
    engine_speed = struct.unpack('f', packed_bytes)[0]
    packed_bytes = struct.pack('HH', register_values[35], register_values[34])
    wind_speed = struct.unpack('f', packed_bytes)[0]
    packed_bytes = struct.pack('HH', register_values[39], register_values[38])
    swing_angle = struct.unpack('f', packed_bytes)[0]
    #print(f'{boom_length:.2f}', f'{boom_angle:.2f}', f'{load_weight:.2f}', f'{engine_speed:.2f}', f'{wind_speed:.2f}', f'{swing_angle:.2f}')
    time.sleep(0.1)

	

