import threading

class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        
        # 기존 변수들
        self._danger_level = 0
        self._boom_length = 0
        self._boom_angle = 0
        self._weight = 0
        self._engine_speed = 0
        self._wind_speed = 0
        self._swing_angle = 0

        # --- 새로 추가된 변수들 ---
        self._specifications = 0      # 제원(R)
        self._radius_main = 0         # 반경1 MAIN
        self._radius_aux = 0          # 반경2 AUX
        self._battery_voltage = 0     # 축전지 전압
        self._engine_temp = 0         # 엔진 온도
        self._oil_pressure = 0        # 엔진 오일 압력
        self._hydraulic_oil_temp = 0  # 작동유 온도
        self._main_height = 0         # MAIN HEIGHT
        self._aux_height = 0          # AUX HEIGHT
        self._rd_height = 0           # 3RD HEIGHT (변수명 숫자 시작 불가로 rd_height 사용)
        self._status_1 = 0            # STATUS 1
        self._status_2 = 0            # STATUS 2
        self._lower_angle = 0         # 하체 각도

        self._body_angle_x = 0
        self._body_angle_y = 0
                
        # --- 객체 인식관련 변수 ---
        self._obj_couint = 0
        self._obj_distance = 0
        
        #기기의 시리얼 넘버
        self._device_serial = "0000000000000000"
    # ==========================
    # Setter 메소드
    # ==========================
    def set_danger_level(self, level):
        with self._lock:
            self._danger_level = level
    
    def set_boom_length(self, boom_length):
        with self._lock:
            self._boom_length = boom_length

    def set_boom_angle(self, boom_angle):
        with self._lock:
            self._boom_angle = boom_angle
    
    def set_weight(self, weight):
        with self._lock:
            self._weight = weight

    def set_engine_speed(self, engine_speed):
        with self._lock:
            self._engine_speed = engine_speed

    def set_wind_speed(self, wind_speed):
        with self._lock:
            self._wind_speed = wind_speed
    
    def set_swing_angle(self, swing_angle):
        with self._lock:
            self._swing_angle = swing_angle

    # --- 추가된 Setter ---
    def set_specifications(self, specifications):
        with self._lock:
            self._specifications = specifications

    def set_radius_main(self, radius):
        with self._lock:
            self._radius_main = radius

    def set_radius_aux(self, radius):
        with self._lock:
            self._radius_aux = radius

    def set_battery_voltage(self, voltage):
        with self._lock:
            self._battery_voltage = voltage

    def set_engine_temp(self, temp):
        with self._lock:
            self._engine_temp = temp

    def set_oil_pressure(self, pressure):
        with self._lock:
            self._oil_pressure = pressure

    def set_hydraulic_oil_temp(self, temp):
        with self._lock:
            self._hydraulic_oil_temp = temp

    def set_main_height(self, height):
        with self._lock:
            self._main_height = height

    def set_aux_height(self, height):
        with self._lock:
            self._aux_height = height

    def set_rd_height(self, height): # 3rd height
        with self._lock:
            self._rd_height = height

    def set_status_1(self, status):
        with self._lock:
            self._status_1 = status

    def set_status_2(self, status):
        with self._lock:
            self._status_2 = status

    def set_lower_angle(self, angle):
        with self._lock:
            self._lower_angle = angle

    def set_obj_info(self, count, distance):
        with self._lock:
            self._obj_couint = count
            self._obj_distance = distance

    def set_serial_info(self, device_serial):
        with self._lock:
            self._device_serial = device_serial            

    def set_body_angle_x(self, _body_angle_x):
        with self._lock:
            self._body_angle_x = _body_angle_x

    def set_body_angle_y(self, _body_angle_y):
        with self._lock:
            self._body_angle_y = _body_angle_y
            
    # ==========================
    # Getter 메소드
    # ==========================
    def get_danger_level(self):
        with self._lock:
            return self._danger_level

    def get_boom_length(self):
        with self._lock:
            return self._boom_length

    def get_boom_angle(self):
        with self._lock:
            return self._boom_angle
    
    def get_weight(self):
        with self._lock:
            return self._weight
 
    def get_engine_speed(self):
        with self._lock:
            return self._engine_speed

    def get_wind_speed(self):
        with self._lock:
            return self._wind_speed
    
    def get_swing_angle(self):
        with self._lock:
            return self._swing_angle

    # --- 추가된 Getter ---
    def get_specifications(self):
        with self._lock:
            return self._specifications

    def get_radius_main(self):
        with self._lock:
            return self._radius_main

    def get_radius_aux(self):
        with self._lock:
            return self._radius_aux

    def get_battery_voltage(self):
        with self._lock:
            return self._battery_voltage

    def get_engine_temp(self):
        with self._lock:
            return self._engine_temp

    def get_oil_pressure(self):
        with self._lock:
            return self._oil_pressure

    def get_hydraulic_oil_temp(self):
        with self._lock:
            return self._hydraulic_oil_temp

    def get_main_height(self):
        with self._lock:
            return self._main_height

    def get_aux_height(self):
        with self._lock:
            return self._aux_height

    def get_rd_height(self):
        with self._lock:
            return self._rd_height

    def get_status_1(self):
        with self._lock:
            return self._status_1

    def get_status_2(self):
        with self._lock:
            return self._status_2

    def get_lower_angle(self):
        with self._lock:
            return self._lower_angle
            
    def get_obj_info(self):
        with self._lock:
            return self._obj_couint, self._obj_distance       

    def get_serial_info(self):
        with self._lock:
            return self._device_serial        

    def get_body_angle_x(self):
        with self._lock:
            return self._body_angle_x         

    def get_body_angle_y(self):
        with self._lock:
            return self._body_angle_y       