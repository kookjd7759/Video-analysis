import struct
import zlib
import time
import random
from Crane_MQTT import MQTTClient # Crane_MQTT.py 파일이 있다고 가정

# ==========================================
# 2. 더미 데이터 생성 및 전송 루프
# ==========================================
def create_dummy_packet():
    # --- [A] 가변 데이터 (랜덤하게 값을 조금씩 흔들어줌) ---
    boom_length = 10.5 + random.uniform(-0.1, 0.1)
    actual_load = 2.5 + random.uniform(-0.05, 0.05)
    angle = 45.0 + random.uniform(-1.0, 1.0)
    
    # 장애물 시뮬레이션 (10% 확률로 장애물 감지)
    if random.random() < 0.1:
        obj_count = random.randint(1, 3)
        obj_distance = random.uniform(1.5, 5.0) # 1.5m ~ 5m 사이
        danger = 1 # 위험
    else:
        obj_count = 0
        obj_distance = 99.0
        danger = 0 # 안전

    # 기타 고정값들 (테스트용)
    fluid_temp = 60.5
    voltage = 24.1
    MAIN_HEIGHT = 15.0
    engine_rpm = 1200.0
    AUX_HEIGHT = 0.0
    wind = 3.2
    MAIN_radius1 = 8.5
    engine_temp = 85.0
    RD_HEIGHT = 0.0
    turning_angle = 120.5
    turning_speed = 0.0
    AUX_radius2 = 0.0
    oil_pressure = 150.0
    body_angle_x = 0.1
    body_angle_y = -0.1
    boom_angle = 45.0

    # 상태값
    STATUS1 = 1
    STATUS2 = 0
    STATUS3 = 0
    spec = 250 # 숫자라고 가정 (GT-250 -> 250)

    # --- [B] 고정 데이터 패킹 (Float 20개 + Int 6개) ---
    # 순서: Float 20개 -> Int 6개 (안드로이드와 순서 100% 일치해야 함)
    fmt = '<20f6i'
    fixed_data = struct.pack(fmt,
        float(boom_length), float(actual_load), float(fluid_temp),
        float(angle), float(voltage), float(MAIN_HEIGHT),
        float(engine_rpm), float(AUX_HEIGHT), float(wind),
        float(MAIN_radius1), float(engine_temp), float(RD_HEIGHT),
        float(turning_angle), float(turning_speed), float(AUX_radius2),
        float(oil_pressure), float(body_angle_x), float(body_angle_y),
        float(boom_angle), float(obj_distance),

        int(STATUS1), int(STATUS2), int(STATUS3),
        int(spec), int(danger), int(obj_count)
    )

    # --- [C] 가변 데이터 (Serial) ---
    device_serial = "SIMULATOR_001"
    serial_bytes = str(device_serial).encode('utf-8')
    # 시리얼 길이 + 시리얼 내용
    serial_pack = struct.pack('<I', len(serial_bytes)) + serial_bytes

    # --- [D] Body 합체 (Serial이 먼저!) ---
    payload_body = serial_pack + fixed_data

    # --- [E] CRC32 계산 및 추가 ---
    crc_value = zlib.crc32(payload_body) & 0xffffffff
    payload_with_crc = payload_body + struct.pack('<I', crc_value)

    # --- [F] 헤더(전체길이) 추가 ---
    total_len = len(payload_with_crc) + 4
    final_packet = struct.pack('<I', total_len) + payload_with_crc

    return final_packet

# 0.25초마다 전송 (초당 4회)
count = 0
mqtt = MQTTClient()

# --- MQTT 연결 및 루프 시작 ---
mqtt.connecting()
mqtt.loop_start()

while True:
    packet = create_dummy_packet()
    mqtt.Analysis_msg("Event/CraneTest/", packet)
    
    count += 1
    if count % 4 == 0:
        print(f"Sending packet... Size: {len(packet)} bytes")
    
    time.sleep(0.25)