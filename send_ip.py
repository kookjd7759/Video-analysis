import socket, requests

TOPIC = "https://ntfy.sh/solimatics-raspberryPi-report-IP_dan12kjvh4k6jhj"

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def send_ip():
    ip = get_ip()
    msg = f"Raspberry Pi IP: {ip}"
    try:
        requests.post(TOPIC, data=msg.encode("utf-8"))
        print("[sent]", msg)
    except Exception as e:
        print("[err]", e)
    
if __name__ == '__main__':
    send_ip()