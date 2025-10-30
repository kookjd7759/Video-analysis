import threading

class SharedState:
    def __init__(self):
        self._danger_level = 0
        
        self._boom_length = 0
        self._boom_angle = 0
        self._weight = 0
        self._engine_speed = 0
        self._wind_speed = 0
        self._swing_angle = 0
        self._lock = threading.Lock()

    # setter 메소드
    def set_danger_level(self, level):
        """
        Modbus 워커가 이 함수를 호출하여 위험 레벨을 안전하게 업데이트합니다.
        """
        with self._lock:
            self._danger_level = level
    
    def set_boom_length(self, boom_length):
        """
        Modbus 워커가 이 함수를 호출하여 위험 레벨을 안전하게 업데이트합니다.
        """
        with self._lock:
            self._boom_length = boom_length

    def set_boom_angle(self, boom_angle):
        """
        Modbus 워커가 이 함수를 호출하여 위험 레벨을 안전하게 업데이트합니다.
        """
        with self._lock:
            self._boom_angle = boom_angle
    
    def set_weight(self, weight):
        """
        Modbus 워커가 이 함수를 호출하여 위험 레벨을 안전하게 업데이트합니다.
        """
        with self._lock:
            self._weight = weight

    def set_engine_speed(self, engine_speed):
        """
        Modbus 워커가 이 함수를 호출하여 위험 레벨을 안전하게 업데이트합니다.
        """
        with self._lock:
            self._engine_speed = engine_speed

    def set_wind_speed(self, wind_speed):
        """
        Modbus 워커가 이 함수를 호출하여 위험 레벨을 안전하게 업데이트합니다.
        """
        with self._lock:
            self._wind_speed = wind_speed
    
    def set_swing_angle(self, swing_angle):
        """
        Modbus 워커가 이 함수를 호출하여 위험 레벨을 안전하게 업데이트합니다.
        """
        with self._lock:
            self._swing_angle = swing_angle
    
    # getter 메소드                                                                        
    def get_danger_level(self):
        """
        시뮬레이터 워커가 이 함수를 호출하여 최신 위험 레벨을 안전하게 읽어옵니다.
        """
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