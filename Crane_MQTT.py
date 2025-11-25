import paho.mqtt.client as mqtt
import json
import queue
import uuid

class MQTTClient:
    def __init__(self):
        # 새로운 클라이언트 생성
        client_id = str(uuid.uuid4())  # 고유한 클라이언트 ID 생성
        self.client = mqtt.Client(client_id=client_id) # 고유한 클라이언트 ID 설정
        self.Mqtt_Connection = False
        self.Mac_dict = {
            "10521C894128": "솔리메틱스1호기"
        }
        self.Module_list = list(self.Mac_dict.keys())
        self.message_queue = queue.Queue() # 메시지 큐 생성
        
    def get_message(self): 
        if not self.message_queue.empty(): 
            return self.message_queue.get() 
        return None
        
    def mqtt_connecting(self):
        return self.Mqtt_Connection
    
    def on_connect(self,client, userdata, flags, rc):
        if rc == 0:
            print("on_connect")
            self.Mqtt_Connection = True
        else:
            self.Mqtt_Connection = False

    def on_disconnect(self,client, userdata, flags, rc=0):
        print("disconnect_MQTT = ",rc)
        pass
    
    def on_publish(self,client, userdata, mid):
        pass
        #print("In on_pub callback mid= ", mid)
        
    def on_subscribe(self,client, userdata, mid, granted_qos):
        #print("subscribed: " + str(mid) + " " + str(granted_qos))
        pass    

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8")
        print(f"[MQTT][RECV] topic={msg.topic}, payload={payload}")
        self.message_queue.put(payload)
    
    def Analysis_msg(self,topics,message):
        self.client.publish(topics,message, 1) #Event/T-MDS/YJSensing/
    
    def subscribe(self):
        if self.Mqtt_Connection: # 이미 연결된 경우에만 구독 수행
            for mac in self.Module_list:
                topic = f"Event/T-MDS/YJSensing/{mac}/"
                print(f"[MQTT][SUB] {topic}")
                self.client.subscribe(topic)
            
    def connecting(self):
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        self.client.username_pw_set('ari_mqtt', "25846ec82")
        self.client.connect('211.169.215.170', 53200, keepalive=120)
        
    def loop_start(self):
        self.client.loop_start()
    
    def loop_forever(self): 
        self.client.loop_forever()
        
    def loop_stop(self):
        self.client.loop_stop()

    def disconnect(self):
        self.client.disconnect()
    