import socket, requests, psutil

TOPIC = "https://ntfy.sh/solimatics-raspberryPi-report-IP_dan12kjvh4k6jhj"

def get_ip():
    # 라즈베리파이의 무선랜 이름인 'wlan0'을 직접 찾습니다
    addrs = psutil.net_if_addrs().get('wlan0')
    
    if addrs:
        for addr in addrs:
            if addr.family == socket.AF_INET: # IPv4 주소만
                return addr.address
    return "0.0.0.0"

def send_ip():
    ip = get_ip()
    msg = f"Raspberry Pi IP: {ip}"
    try:
        requests.post(TOPIC, data=msg.encode("utf-8"))
        print("[sent]", msg)
    except Exception as e:
        print("[err]", e)
    return ip

if __name__ == '__main__':
    send_ip()