# Video-analysis

크레인 작업 환경에서 영상/센서 데이터를 통합해 **사람 감지 + 거리 추정 + 위험 데이터 전송**을 수행하는 Python 프로젝트입니다.  
RealSense 기반 영상 분석, Modbus/UDP 센서 수집, MQTT 송수신, 웹 대시보드를 하나의 프로세스에서 동작시킵니다.

## 1. 주요 기능

- RealSense + YOLO 기반 사람 검출 및 거리 추정
- Flask 웹 대시보드 제공
- `/video_feed` 실시간 영상 스트리밍(MJPEG)
- `/radar.png` 객체 위치/거리 레이더 뷰
- `/info` 감지 객체 JSON API
- Modbus/UDP 기반 크레인/안전 센서 데이터 수집
- MQTT 기반 CAN 기울기 데이터 수신
- 통합 데이터를 이진 패킷(CRC32 포함)으로 MQTT 송신
- mDNS(`RadarServer._http._tcp.local`) 광고

## 2. 동작 구조

입력 소스:
- RealSense 카메라: 사람 검출용 컬러/깊이 영상
- UDP(기본 5005): 안전 센서 데이터
- Modbus RTU(`/dev/ttyUSB0`): 메인 크레인 데이터
- MQTT 구독(`Event/T-MDS/YJSensing/<MAC>/`): 기울기(CAN) 데이터

공유 상태:
- `shared_state.py`에서 스레드 안전(`threading.Lock`)으로 데이터 통합

출력:
- Flask 서버(`0.0.0.0:5000`)
- MQTT 발행(`Event/CraneTest/`, 바이너리 패킷)

## 3. 핵심 파일

- `main.py`: 전체 시스템 진입점, 워커/서버/MQTT 시작 및 종료 처리
- `analysis.py`: Flask 앱, 스트리밍/레이더/API 라우트, 백그라운드 캡처 루프
- `processor.py`: YOLO + RealSense 추론 및 거리 계산
- `shared_state.py`: 센서/검출 데이터 공용 메모리
- `koceti_worker.py`: 안전/크레인 데이터 폴링 후 `SharedState` 갱신
- `koceti_Read_Modbus.py`: UDP 수신 및 Modbus 서버 구성/데이터 파싱
- `Update_Can_Data.py`: MQTT 수신 메시지에서 기울기 추출
- `transmit_Crane_Data_Worker.py`: 통합 데이터 패킹 + CRC32 + MQTT 송신
- `Crane_MQTT.py`: MQTT 연결/구독/발행 래퍼
- `send_ip.py`: 장치 IP를 ntfy로 보고

참고/테스트 스크립트:
- `sim.py`: 더미 바이너리 패킷 생성/전송
- `yoloPose_test.py`: Pose 기반 거리 추정 실험
- `Test_modbus_server*.py`, `LMI_Comm_Test.py`: Modbus 테스트 코드
- `PI_conn.py`: SSH 업로드/원격 실행 보조 스크립트

## 4. 실행 환경

권장:
- Python 3.10 이상
- Linux/Raspberry Pi 환경
- Intel RealSense 카메라(깊이 스트림 사용)
- Modbus RTU 장치(`/dev/ttyUSB0`)

## 5. 설치

현재 `requirements.txt`에는 일부 패키지만 포함되어 있어, 아래처럼 추가 의존성을 함께 설치해야 합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install flask numpy opencv-python torch ultralytics pyrealsense2 paho-mqtt pymodbus zeroconf psutil onnxruntime
```

Windows(PowerShell) 예시:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt
pip install flask numpy opencv-python torch ultralytics pyrealsense2 paho-mqtt pymodbus zeroconf psutil onnxruntime
```

## 6. 실행 방법

```bash
python main.py
```

기본 접속:
- 대시보드: `http://<장치IP>:5000/`
- 영상 스트림: `http://<장치IP>:5000/video_feed`
- 객체 정보: `http://<장치IP>:5000/info`
- 레이더 이미지: `http://<장치IP>:5000/radar.png`

## 7. HTTP API

### `GET /info`

예시 응답:

```json
{
  "count": 1,
  "objects": [
    {
      "label": "person",
      "distance": 3.42,
      "est_distance": 3.58,
      "bbox_w": 124,
      "bbox_h": 287,
      "center": 0.513
    }
  ]
}
```

### `GET /video_feed`

- MJPEG 스트리밍 응답

### `GET /radar.png`

- 최신 검출 결과를 레이더 형태의 PNG로 반환

### `POST /shutdown`

- 내부 종료용 라우트(`main.py` 종료 시 호출)

## 8. MQTT 송신 패킷 포맷(`Event/CraneTest/`)

`transmit_Crane_Data_Worker.py` 기준(리틀엔디안):

1. `uint32 total_len`  
2. `uint32 serial_len`  
3. `serial_len` 바이트 장치 시리얼 문자열(UTF-8)  
4. 고정 데이터 블록 `struct '<19f8i'`  
5. `uint32 crc32` (`serial_len + serial + fixed_data` 구간 기준)

고정 데이터 블록에는 붐 길이, 하중, 유압/엔진 정보, 각도, 객체 거리/개수, 위험도 등이 포함됩니다.

## 9. 주요 설정 포인트

- `main.py`: Flask 포트(기본 `5000`), 워커 주기(`koceti_worker=0.05s`, `Update_Can_Data=0.2s`, `transmit_Crane_Data_Worker=0.5s`)
- `processor.py`: 모델 기본값(`yolo11n.pt`), RealSense 스트림(`640x360`), Raspberry Pi 감지 시 FPS/추론 부하 자동 완화
- `Crane_MQTT.py`: 브로커 주소/계정/구독 MAC 리스트 하드코딩
- `send_ip.py`: ntfy 토픽 URL 하드코딩

## 10. 트러블슈팅

- RealSense 프레임이 안 들어오면: 케이블(USB 3.x), 권한, `pyrealsense2` 설치, 카메라 연결 상태를 확인하세요.
- `/dev/ttyUSB0` 접근이 실패하면: 포트명/권한(`dialout` 그룹 등)/배선을 확인하세요.
- MQTT 수신/송신이 안 되면: 브로커 주소/포트/계정, 방화벽, 토픽명을 확인하세요.
- 웹 접속이 안 되면: 장치 IP, 포트(5000), 같은 네트워크 여부를 확인하세요.

## 11. 보안 주의사항

- 현재 코드에 MQTT 계정, SSH 로그인 정보(`login.json`) 등 민감 정보가 포함되어 있습니다.
- 운영 환경에서는 반드시 외부 설정 파일 또는 환경 변수로 분리하고, 실제 자격 증명은 저장소에 커밋하지 마세요.
