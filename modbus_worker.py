import threading
import time
from datetime import datetime
from koceti_485_Read_Modbus import read_once

class PollThread:
    def __init__(self, period_sec=5.0):
        self.period_sec = period_sec
        self._stop = threading.Event()
        self._th = None

    def _run(self):
        while not self._stop.is_set():
            start = time.time()
            ts = datetime.now().strftime("%H:%M:%S")

            raw, conv = read_once()
            if raw is None:
                print(f"[{ts}] 사이클 실패 (응답 오류 또는 예외)")
            else:
                print(f"[{ts}] 사이클 OK")

            # 5초 간격
            elapsed = time.time() - start
            remain = self.period_sec - elapsed
            if remain > 0:
                end = time.time() + remain
                while not self._stop.is_set() and time.time() < end:
                    time.sleep(0.1)

    def start(self, daemon=True):
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=daemon)
        self._th.start()

    def stop(self):
        self._stop.set()

    def join(self, timeout=None):
        if self._th:
            self._th.join(timeout)

if __name__ == "__main__":
    worker = PollThread(period_sec=5.0)
    try:
        print("[INFO] 5초 주기 폴링 시작")
        worker.start()
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[INFO] 종료 요청")
    finally:
        worker.stop()
        worker.join()
        print("[INFO] 종료 완료")
