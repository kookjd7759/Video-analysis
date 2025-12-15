import threading
import time
import queue
from datetime import datetime
from koceti_Read_Modbus import Crane_Final_Test
from shared_state import SharedState

class modbus_worker:
    def __init__(self, port, data_queue, period_sec=1.0):
        self.period_sec = period_sec
        self._stop = threading.Event()
        self._th = None
        self.port = port
        self.data_queue = data_queue
        print(f"[Worker] Modbus 워커 쓰레드 시작 (포트: {self.port})")
        # 각 장비의 Unit ID를 변수로 지정 (실제 ID로 변경해야 합니다)
        STABILITY_SENSOR_ID = 1
        MAIN_CRANE_ID = 2        
        
        # 1. Crane_Final_Test 객체를 '쓰레드 안에서' 생성하고 연결합니다.
        self.crane_tester = Crane_Final_Test(port=self.port)
        self.shared_state = SharedState()

    def _run(self):
        try:
            # 각 장비의 Unit ID를 변수로 지정 (실제 ID로 변경해야 합니다)
            STABILITY_SENSOR_ID = 1
            MAIN_CRANE_ID = 2    
            if self.crane_tester.connect_safety():
                while not self._stop.is_set():
                    start = time.time()
                    ts = datetime.now().strftime("%H:%M:%S")

                    final_data = self.crane_tester.get_safety_sensor_data(STABILITY_SENSOR_ID)
                    if final_data is None:
                        print(f"[{ts}] 사이클 실패 (응답 오류 또는 예외)")
                    else:
                        print(f"[{ts}] 사이클 OK")
                        self.data_queue.put(final_data)
                        risk_assessment = final_data.get("risk_assessment", {})
                        risk_level = risk_assessment.get("level_num", 0)
                        self.shared_state.set_danger_level(risk_level)
                    
                    # 2. 크레인 메인 컨트롤러 데이터 요청
                    main_data = self.crane_tester.get_main_crane_data()
                    if main_data:
                        print(f"[메인 크레인 ID:{MAIN_CRANE_ID}] 수신 데이터: {main_data}")

                        # 1. 붐 길이
                        boom_length = main_data.get("boom length(m)", 0)
                        self.shared_state.set_boom_length(boom_length)

                        # 2. 붐 각도
                        boom_angle = main_data.get("boom angle(deg)", 0)
                        self.shared_state.set_boom_angle(boom_angle)

                        # 3. 실 하중 (앞선 딕셔너리 키와 일치시킴: "load weight(ton)" 혹은 "weight(ton)")
                        # 앞 코드에서 "weight(ton)"을 사용하셨으므로 그대로 유지합니다.
                        weight = main_data.get("weight(ton)", 0) 
                        self.shared_state.set_weight(weight)

                        # 4. 엔진 RPM
                        engine_speed = main_data.get("engine speed(rpm)", 0)
                        self.shared_state.set_engine_speed(engine_speed)

                        # 5. 풍속 (오타 수정: engine_speed -> wind_speed)
                        wind_speed = main_data.get("wind speed(m/s)", 0)
                        self.shared_state.set_wind_speed(wind_speed)

                        # 6. 선회 각도
                        swing_angle = main_data.get("swing angle(deg)", 0)
                        self.shared_state.set_swing_angle(swing_angle)

                        # --- 추가된 항목들 ---

                        # 7. 제원(R)
                        specifications = main_data.get("specifications", 0)
                        self.shared_state.set_specifications(specifications)

                        # 8. 반경 Main
                        radius_main = main_data.get("radius main(m)", 0)
                        self.shared_state.set_radius_main(radius_main)

                        # 9. 반경 Aux
                        radius_aux = main_data.get("radius aux(m)", 0)
                        self.shared_state.set_radius_aux(radius_aux)

                        # 10. 축전지 전압
                        battery_voltage = main_data.get("battery voltage(V)", 0)
                        self.shared_state.set_battery_voltage(battery_voltage)

                        # 11. 엔진 온도
                        engine_temp = main_data.get("engine temp(C)", 0)
                        self.shared_state.set_engine_temp(engine_temp)

                        # 12. 엔진 오일 압력
                        oil_pressure = main_data.get("oil pressure", 0)
                        self.shared_state.set_oil_pressure(oil_pressure)

                        # 13. 작동유 온도
                        hydraulic_temp = main_data.get("hydraulic oil temp(C)", 0)
                        self.shared_state.set_hydraulic_oil_temp(hydraulic_temp)

                        # 14. Main Height
                        main_height = main_data.get("main height(m)", 0)
                        self.shared_state.set_main_height(main_height)

                        # 15. Aux Height
                        aux_height = main_data.get("aux height(m)", 0)
                        self.shared_state.set_aux_height(aux_height)

                        # 16. 3rd Height
                        rd_height = main_data.get("3rd height(m)", 0)
                        self.shared_state.set_3rd_height(rd_height)

                        # 17. Status 1
                        status_1 = main_data.get("status 1", 0)
                        self.shared_state.set_status_1(status_1)

                        # 18. Status 2
                        status_2 = main_data.get("status 2", 0)
                        self.shared_state.set_status_2(status_2)

                        # 19. 하체 각도
                        lower_angle = main_data.get("lower angle(deg)", 0)
                        self.shared_state.set_lower_angle(lower_angle)
                    else:
                        print(f"[메인 크레인 ID:{MAIN_CRANE_ID}] 데이터 수신 실패.")
                    
                    # 1초 간격
                    elapsed = time.time() - start
                    remain = self.period_sec - elapsed
                    if remain > 0:
                        end = time.time() + remain
                        while not self._stop.is_set() and time.time() < end:
                            time.sleep(0.1)
            else:
                print("[Worker] [ERROR] 연결 실패. 쓰레드를 종료합니다.")
                # (선택) 큐에 에러 메시지를 넣어 메인 쓰레드에 알릴 수도 있습니다.
                self.data_queue.put({"error": f"연결 실패: {self.port} 포트를 확인하세요."})
                return            
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

if __name__ == "__main__":
    
    results_queue = queue.Queue()
    # 3. 외부 shutdown_event 불필요
    
    # 3. 워커 생성 시에도 전달하지 않음
    worker = modbus_worker('/dev/ttyUSB0', results_queue, period_sec=1.0)
    try:
        print("[INFO] 1초 주기 폴링 시작 (종료: Ctrl+C)")
        worker.start()
        
        # 4. 이제 큐에서 실제로 데이터를 꺼내서 사용하는 로직을 추가합니다.
        while True:
            try:
                # 1.5초 타임아웃으로 큐에서 데이터를 기다림
                data = results_queue.get(timeout=1.5)
                
                if "error" in data:
                    print(f"[Main] [ERROR] 워커로부터 에러 수신: {data['error']}")
                    break
                
                print(f"[Main] 데이터 수신: {data}")
                
            except queue.Empty:
                print("[Main] 워커로부터 응답이 없습니다. (타임아웃)")
                # 워커 쓰레드가 살아있는지 확인
                if not (worker._th and worker._th.is_alive()):
                    print("[Main] [ERROR] 워커 쓰레드가 중지되었습니다.")
                    break
                continue

    except KeyboardInterrupt:
        print("\n[INFO] 종료 요청")
    finally:
        print("[INFO] 워커 종료 중...")
        worker.stop()
        worker.join()
        print("[INFO] 종료 완료")
