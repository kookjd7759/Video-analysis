import socket
import requests
import time
import json

SERVER = "http://192.168.1.69:9000/report-ip"

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"
    finally:
        s.close()

def try_post():
    payload = {
        "hostname": socket.gethostname(),
        "local_ip": get_local_ip(),
        "time": time.time()
    }
    try:
        r = requests.post(SERVER, json=payload, timeout=5)
        print("posted:", r.status_code, r.text)
    except Exception as e:
        print("post failed:", e)

if __name__ == "__main__":
    for i in range(10):
        try_post()
        time.sleep(3)
