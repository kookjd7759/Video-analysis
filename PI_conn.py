import paramiko
import json
import os

base_path = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_path, 'login.json')

with open(config_path, 'r', encoding='utf-8') as file:
    data = json.load(file)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print(f"Connecting to {data['hostname']}...")
    client.connect(
        hostname=data["hostname"],
        port=data["port"],
        username=data["username"],
        password=data["password"]
    )
    print('✅ SSH 연결 성공, 동작 설정 \n [1] 코드 자동 update \n [2] PI 접속 (세션 유지) \n [3] PI video analysis 바로 실행 ')
    flow = input('>> ')

    if flow == '1':
        print(' - 코드 자동 update - ')

        remote_dir = '/home/solimatics/Video_analysis'
        client.exec_command(f"mkdir -p {remote_dir}")

        file_names = ['analysis', 'Crane_MQTT', 'CraneDataSimulatorWorker', 
                      'koceti_485_Read_Modbus', 'koceti_Read_Modbus', 'modbus_worker', 
                      'processor', 'send_ip', 'shared_state', 
                      'main'
                      ]
        for name in file_names:
            try:
                local_path = os.path.join(base_path, f'{name}.py')
                target_path = remote_dir + f'/{name}.py'

                check_cmd = f"test -f {target_path} && echo EXISTS || echo MISSING"
                stdin, stdout, stderr = client.exec_command(check_cmd)
                status = stdout.read().decode().strip()

                if status == "MISSING":
                    print(f"🆕 {name}.py가 라즈베리파이에 없으므로 새로 만듭니다.")
                    client.exec_command(f"touch {target_path}")
                else:
                    print(f"🔄 기존 {name}.py가 존재합니다. 덮어씌웁니다.")

                sftp = client.open_sftp()
                sftp.put(local_path, target_path)
                sftp.close()

                print(f"✅ {name}.py가 성공적으로 업로드되었습니다.")
            except Exception as e:
                print(f'🟥 업로드 실패: {e}')
    elif flow == '2':
        print(' - PI 접속 -')
        current_dir = '~'

        while True:
            cmd = input(f'{current_dir} > ').strip()

            if cmd.lower() == 'exit':
                print('🔌 연결 종료 중...')
                break

            if cmd.startswith('cd '):
                target_dir = cmd[3:].strip()
                test_cmd = f'cd {current_dir} && cd {target_dir} && pwd'
                stdin, stdout, stderr = client.exec_command(test_cmd)
                new_path = stdout.read().decode().strip()
                err = stderr.read().decode().strip()

                if new_path:
                    current_dir = new_path
                elif err:
                    print(f'[Error] {err}')
                else:
                    print('⚠️ 경로 변경 실패')
                continue

            full_cmd = f'cd {current_dir} && {cmd}'
            stdin, stdout, stderr = client.exec_command(full_cmd)

            if cmd.startswith('sudo'):
                stdin.write(data["password"] + '\n')
                stdin.flush()

            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()

            if out:
                print(out)
            if err and not err.lower().startswith('warning'):
                print(f'[Error] {err}')
    elif flow == '3':
        print(' - PI video analysis 바로 실행 -')
        try:
            command = 'cd ~/Video_analysis && python3 test.py'
            stdin, stdout, stderr = client.exec_command(command)

            for line in iter(stdout.readline, ''):
                print(line, end='')

            error_output = stderr.read().decode().strip()
            if error_output:
                print(f'[Error] {error_output}')
        except Exception as e:
            print(f'[실행 실패] {e}')
    else:
        print('❌ 올바른 선택이 아님')

except Exception as e:
    print(f'[Connection failed] {e}')
finally:
    client.close()
    print("✅ SSH 연결이 종료되었습니다.")