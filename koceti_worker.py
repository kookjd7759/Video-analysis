import threading
import time
import queue
from datetime import datetime
from koceti_Read_Modbus import koceti_Read_Modbus

class koceti_worker:
    def __init__(self, target_ip, port, main_crane_port, shared_state, period_sec=1.0):
        self.period_sec = period_sec
        self._stop = threading.Event()
        self._th = None
        self.target_ip = target_ip        # Client용 Address
        self.port = port        # Client용 포트
        self.main_crane_port = main_crane_port # Server용 포트
        print(f"[Worker] Modbus 워커 쓰레드 시작 (포트: {self.target_ip})")
        print(f"[Worker] Modbus server 쓰레드 시작 (포트: {self.main_crane_port})")
   
        # 1. Crane_Final_Test 객체를 '쓰레드 안에서' 생성하고 연결합니다.
        self.crane_tester = koceti_Read_Modbus(target_ip=self.target_ip, port=self.port)
        self.shared_state = shared_state
        self.crane_tester.start_main_crane_server(self.main_crane_port)
        #self.crane_tester.connect_safety()
    def _run(self):
        try:
            # 각 장비의 Unit ID를 변수로 지정 (실제 ID로 변경 가능)
            STABILITY_SENSOR_ID = 1

            # 3. 주기 루프
            while not self._stop.is_set():
                start = time.time()
                ts = datetime.now().strftime("%H:%M:%S")

                # --- 3-1. 안전센서 데이터 ---
                final_data = self.crane_tester.get_safety_sensor_data()
                if final_data is None:
                    print(f"[{ts}][WORKER] 사이클 실패 (안전센서 응답 오류 또는 예외)")
                else:
                    #print(f"[{ts}][WORKER][SAFETY] raw={final_data.get('raw')}")
                    #print(f"[{ts}][WORKER][SAFETY] risk={final_data.get('risk_assessment')}")

                    # shared_state 위험도 갱신
                    risk_level = final_data.get("roll_over_flag", 0)
                    boom_length = final_data.get("boom length(m)", 0)
                    boom_angle = final_data.get("boom angle(deg)", 0)
                    specifications = final_data.get("specifications", 0)
                    Radius_MAIN = final_data.get("Radius_MAIN", 0)
                    Radius_AUX = final_data.get("Radius_AUX", 0)
                    load_weight = final_data.get("weight(ton)", 0)
                    engine_speed = final_data.get("engine speed(rpm)", 0)
                    wind_speed = final_data.get("wind speed(m/s)", 0)
                    swing_angle = final_data.get("swing angle(deg)", 0)
                    battery_voltage = final_data.get("battery voltage(V)", 0)
                    engine_temp = final_data.get("engine temperature(C)", 0)
                    oil_pressure = final_data.get("oil pressure(kg/cm2)", 0) 
                    Working_oil_temp = final_data.get("hydraulic oil temp(C)", 0)
                    main_height = final_data.get("MAIN HEIGHT(m)", 0)
                    aux_height = final_data.get("AUX HEIGHT(m)", 0)
                    rd_height = final_data.get("3RD HEIGHT(m)", 0)
                    status_1 = final_data.get("STATUS 1", 0) 
                    status_2 = final_data.get("STATUS 2", 0)
                    lower_angle = final_data.get("lower body angle(deg)", 0)
                    
                    # 안전도 데이터
                    self.shared_state.set_danger_level(risk_level)
                    # AML 데이터
                    self.shared_state.set_boom_length(boom_length)
                    self.shared_state.set_boom_angle(boom_angle)
                    self.shared_state.set_weight(load_weight)
                    self.shared_state.set_engine_speed(engine_speed)
                    self.shared_state.set_wind_speed(wind_speed)
                    self.shared_state.set_swing_angle(swing_angle)
                    self.shared_state.set_specifications(specifications)
                    self.shared_state.set_radius_main(Radius_MAIN)
                    self.shared_state.set_radius_aux(Radius_AUX)
                    self.shared_state.set_battery_voltage(battery_voltage)  
                    self.shared_state.set_engine_temp(engine_temp)
                    self.shared_state.set_oil_pressure(oil_pressure)
                    self.shared_state.set_hydraulic_oil_temp(Working_oil_temp)
                    self.shared_state.set_main_height(main_height)
                    self.shared_state.set_aux_height(aux_height)
                    self.shared_state.set_rd_height(rd_height)
                    self.shared_state.set_status_1(status_1)
                    self.shared_state.set_status_2(status_2)
                    self.shared_state.set_lower_angle(lower_angle)
                                        
                    print(f"[{ts}][WORKER] 사이클 OK")
                """
                # --- 3-2. 메인 크레인 데이터 ---
                main_data = self.crane_tester.get_main_crane_data()
                if main_data:
                    boom_length = main_data.get("boom length(m)", 0)
                    boom_angle = main_data.get("boom angle(deg)", 0)
                    specifications = main_data.get("specifications", 0)
                    Radius_MAIN = main_data.get("Radius_MAIN", 0)
                    Radius_AUX = main_data.get("Radius_AUX", 0)
                    load_weight = main_data.get("weight(ton)", 0)
                    engine_speed = main_data.get("engine speed(rpm)", 0)
                    wind_speed = main_data.get("wind speed(m/s)", 0)
                    swing_angle = main_data.get("swing angle(deg)", 0)
                    battery_voltage = main_data.get("battery voltage(V)", 0)
                    engine_temp = main_data.get("engine temperature(C)", 0)
                    oil_pressure = main_data.get("oil pressure(kg/cm2)", 0) 
                    Working_oil_temp = main_data.get("hydraulic oil temp(C)", 0)
                    main_height = main_data.get("MAIN HEIGHT(m)", 0)
                    aux_height = main_data.get("AUX HEIGHT(m)", 0)
                    rd_height = main_data.get("3RD HEIGHT(m)", 0)
                    status_1 = main_data.get("STATUS 1", 0) 
                    status_2 = main_data.get("STATUS 2", 0)
                    lower_angle = main_data.get("lower body angle(deg)", 0)
                    
                    
                    # shared_state에 저장
                    self.shared_state.set_boom_length(boom_length)
                    self.shared_state.set_boom_angle(boom_angle)
                    self.shared_state.set_weight(load_weight)
                    self.shared_state.set_engine_speed(engine_speed)
                    self.shared_state.set_wind_speed(wind_speed)
                    self.shared_state.set_swing_angle(swing_angle)
                    self.shared_state.set_specifications(specifications)
                    self.shared_state.set_radius_main(Radius_MAIN)
                    self.shared_state.set_radius_aux(Radius_AUX)
                    self.shared_state.set_battery_voltage(battery_voltage)  
                    self.shared_state.set_engine_temp(engine_temp)
                    self.shared_state.set_oil_pressure(oil_pressure)
                    self.shared_state.set_hydraulic_oil_temp(Working_oil_temp)
                    self.shared_state.set_main_height(main_height)
                    self.shared_state.set_aux_height(aux_height)
                    self.shared_state.set_rd_height(rd_height)
                    self.shared_state.set_status_1(status_1)
                    self.shared_state.set_status_2(status_2)
                    self.shared_state.set_lower_angle(lower_angle)
                      
                    print(f"[{ts}][WORKER][MAIN] 메인 크레인 데이터 수신 성공.")
                else:
                    print(f"[{ts}][WORKER][MAIN] 메인 크레인 데이터 수신 실패.")
                """
                 
                # --- 3-3. 주기 맞추기 ---
                elapsed = time.time() - start
                remain = self.period_sec - elapsed
                if remain > 0:
                    end = time.time() + remain
                    while not self._stop.is_set() and time.time() < end:
                        time.sleep(0.1)
        except Exception as outer_e:
            print(f"[Worker] [ERROR] 워커 쓰레드에서 예외 발생: {outer_e}")
            
        finally:
            self.crane_tester.close_safety()
            print("[Worker] 연결이 안전하게 종료되었습니다.")
 
    
    def start(self, daemon=True):
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=daemon)
        self._th.start()

    def stop(self):
        self._stop.set()
        self.crane_tester.close_safety()

    def join(self, timeout=None):
        if self._th:
            self._th.join(timeout)
