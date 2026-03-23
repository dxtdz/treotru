import subprocess
import sys
import os
import re
import time
import threading
import requests
import gc
import random
import uuid
import ssl
import json
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

def install_packages():
    packages = ['paho-mqtt', 'psutil', 'requests', 'pyfiglet', 'termcolor']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            print(f"Dang cai dat {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_packages()

import paho.mqtt.client as mqtt
import psutil
from termcolor import colored

running = True
tasks = []
task_counter = 0
current_delay = 1.0
simulate_typing = True
idbox_list = ""
message_content = ""
task_messages = {}      # Lưu nội dung message cho từng task
task_from_names = {}    # Lưu tên from cho từng task

COLOR_ERROR = '\033[91m'
COLOR_SUCCESS = '\033[92m'
COLOR_WARNING = '\033[93m'
COLOR_INFO = '\033[94m'
COLOR_RESET = '\033[0m'

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:108.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def generate_client_id():
    return f"mqttwsclient_{uuid.uuid4().hex[:8]}"

def generate_session_id():
    return str(int(time.time() * 1000))

def json_minimal(obj):
    return json.dumps(obj, separators=(',', ':'))

def parse_cookie_string(cookie_str):
    cookies = {}
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key] = value
    return cookies

def get_uid_from_cookie(cookie):
    """Lấy UID từ cookie"""
    cookie_dict = parse_cookie_string(cookie)
    return cookie_dict.get("c_user", None)

def get_uptime(start_time):
    elapsed = (datetime.now() - start_time).total_seconds()
    hours, rem = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_help():
    print("\n" + "="*50)
    print("DANH SACH LENH")
    print("="*50)
    print(f"{COLOR_INFO}add{COLOR_RESET}     - Them task moi (cookie, id box, file, delay, typing delay)")
    print(f"{COLOR_INFO}stop{COLOR_RESET}    - Dung task theo so thu tu (hien thi danh sach de chon)")
    print(f"{COLOR_INFO}list{COLOR_RESET}    - Liet ke tat ca task dang chay (dang doc)")
    print(f"{COLOR_INFO}thay{COLOR_RESET}    - Thay noi dung file cho task (thay [id])")
    print(f"{COLOR_INFO}from{COLOR_RESET}    - Thay ten from cho task (from [id] [ten] hoac from all [ten])")
    print(f"{COLOR_INFO}delay{COLOR_RESET}   - Thay doi thoi gian delay giua cac tin nhan")
    print(f"{COLOR_INFO}typing{COLOR_RESET}  - Bat/tat che do typing indicator")
    print(f"{COLOR_INFO}stopall{COLOR_RESET} - Dung tat ca task dang chay")
    print(f"{COLOR_INFO}help{COLOR_RESET}    - Hien thi danh sach lenh nay")
    print(f"{COLOR_INFO}exit{COLOR_RESET}    - Thoat chuong trinh")
    print("="*50)
    print(f"\n{COLOR_WARNING}Ghi chu:{COLOR_RESET}")
    print("- Trong file noi dung, su dung {from} de thay the bang ten nguoi gui")
    print("- Khi phat hien {from} trong file, tool se hoi ten de thay the")
    print("- Dung 'thay [id]' de thay doi noi dung file cho task")
    print("- Dung 'from [id] [ten]' de thay doi ten hien thi")
    print("- Dung 'list' de xem danh sach task dang doc")
    print("="*50 + "\n")

def process_message_with_from(message, from_name):
    """Thay thế {from} trong nội dung"""
    if from_name:
        return message.replace("{from}", from_name)
    return message

def get_message_from_file():
    """Đọc nội dung từ file và kiểm tra {from}"""
    while True:
        filename = input("Nhap ten file: ").strip()
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                if not content:
                    print(f"{COLOR_WARNING}File rong, nhap lai:{COLOR_RESET}")
                    continue
                
                # Kiểm tra nếu có {from} trong nội dung
                if "{from}" in content:
                    print(f"{COLOR_INFO}Phat hien {from} trong file noi dung{COLOR_RESET}")
                    print("Nhap ten from muon thay the (de trong neu khong muon thay):")
                    default_from = input().strip()
                    if default_from:
                        print(f"{COLOR_SUCCESS}Se thay '{default_from}' vao vi tri {from}{COLOR_RESET}")
                        return content, default_from
                
                return content, None
            except Exception as e:
                print(f"{COLOR_ERROR}Loi doc file: {e}{COLOR_RESET}")
        else:
            print(f"{COLOR_ERROR}File khong ton tai, nhap lai:{COLOR_RESET}")

def change_task_content(task_id):
    """Thay đổi nội dung file cho task"""
    print(f"{COLOR_INFO}Nhap ten file moi cho task {task_id}:{COLOR_RESET}")
    new_content, default_from = get_message_from_file()
    
    if new_content:
        task_messages[task_id] = new_content
        if default_from:
            task_from_names[task_id] = default_from
        print(f"{COLOR_SUCCESS}Da thay noi dung cho task {task_id}{COLOR_RESET}")
    else:
        print(f"{COLOR_ERROR}Khong the thay doi noi dung{COLOR_RESET}")

def change_task_from(task_id, new_from=None):
    """Thay đổi tên from cho task"""
    if new_from:
        task_from_names[task_id] = new_from
        print(f"{COLOR_SUCCESS}Da thay from cho task {task_id} thanh: {new_from}{COLOR_RESET}")
    else:
        if task_id in task_from_names:
            del task_from_names[task_id]
        print(f"{COLOR_SUCCESS}Da xoa from cho task {task_id}{COLOR_RESET}")

def show_task_list():
    """Hiển thị danh sách task dạng dọc"""
    if not tasks:
        print(f"\n{COLOR_WARNING}=== KHONG CO TASK NAO ==={COLOR_RESET}\n")
        return
    
    print("\n" + "="*70)
    print("DANH SACH TASK")
    print("="*70)
    
    for idx, task in enumerate(tasks, 1):
        status = f"{COLOR_SUCCESS}🟢 Dang chay{COLOR_RESET}" if task.running else f"{COLOR_ERROR}🔴 Da dung{COLOR_RESET}"
        uptime = get_uptime(task.start_time)
        user_id = get_uid_from_cookie(task.cookie) or "Unknown"
        from_name = task_from_names.get(task.task_id, "Khong co")
        
        # Lấy nội dung message preview
        msg_preview = task_messages.get(task.task_id, task.message_template)
        msg_preview = msg_preview[:50] + "..." if len(msg_preview) > 50 else msg_preview
        
        print(f"\n{COLOR_INFO}📌 Task {task.task_id}{COLOR_RESET}")
        print(f"   ├─ UID       : {user_id}")
        print(f"   ├─ ID Box    : {task.idbox_list}")
        print(f"   ├─ Status    : {status}")
        print(f"   ├─ From      : {from_name}")
        print(f"   ├─ Delay     : {task.delay}s")
        print(f"   ├─ Typing    : {task.typing_delay}s")
        print(f"   ├─ OK/Fail   : {task.success}/{task.fail}")
        print(f"   ├─ Uptime    : {uptime}")
        print(f"   └─ Noi dung  : {msg_preview}")
    
    print("\n" + "="*70)
    print(f"Tong so task: {len(tasks)}")
    print("="*70 + "\n")

class FacebookTypingMQTT:
    def __init__(self, cookies, options=None):
        self.cookies = cookies
        self.ctx = self.create_context(cookies, options)
        self.mqtt_client = None
        self.connected = False
        self.ws_req_number = 0
        
    def create_context(self, cookies, options=None):
        if options is None:
            options = {
                "user_agent": get_random_user_agent(),
                "online": True,
                "self_listen": False,
                "listen_events": True,
                "update_presence": False,
            }
        
        user_id = None
        cookie_dict = parse_cookie_string(cookies)
        if "c_user" in cookie_dict:
            user_id = cookie_dict["c_user"]
        
        ctx = {
            "cookieFacebook": cookies,
            "user_id": user_id,
            "options": options,
            "first_listen": True,
            "last_seq_id": None,
            "sync_token": None,
            "mqtt_endpoint": None,
            "region": None,
            "logged_in": True,
            "req_callbacks": {},
            "callback": None,
            "api": None,
            "mqtt_client": None,
        }
        return ctx
    
    def get_thread_info(self, thread_id):
        try:
            is_group = thread_id != self.ctx["user_id"]
            return {"isGroup": is_group, "threadInfo": None}
        except Exception:
            return {"isGroup": thread_id != self.ctx["user_id"], "threadInfo": None}
    
    def connect(self):
        session_id = generate_session_id()
        chat_on = self.ctx["options"]["online"]
        foreground = False
        
        user = {
            "a": self.ctx["options"]["user_agent"],
            "u": self.ctx["user_id"],
            "s": session_id,
            "chat_on": chat_on,
            "fg": foreground,
            "d": generate_client_id(),
            "ct": "websocket",
            "aid": "219994525426954",
            "mqtt_sid": "",
            "cp": 3,
            "ecp": 10,
            "st": [],
            "pm": [],
            "dc": "",
            "no_auto_fg": True,
            "gas": None,
            "pack": [],
        }
        
        cookie_dict = parse_cookie_string(self.cookies)
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        
        self.mqtt_client = mqtt.Client(
            client_id="mqttwsclient",
            clean_session=True,
            protocol=mqtt.MQTTv31,
            transport="websockets",
        )
        
        self.mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
        self.mqtt_client.tls_insecure_set(True)
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.username_pw_set(username=json_minimal(user))
        
        self.mqtt_client.ws_set_options(path="/chat", headers={
            "Cookie": cookie_str,
            "Origin": "https://www.facebook.com",
            "User-Agent": self.ctx["options"]["user_agent"],
            "Referer": "https://www.facebook.com/",
            "Host": "edge-chat.facebook.com",
        })
        
        try:
            self.mqtt_client.connect("edge-chat.facebook.com", 443, 60)
            self.mqtt_client.loop_start()
            
            timeout = 10
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if not self.connected:
                raise Exception("Failed to connect")
            return True
        except Exception as e:
            print(f"{COLOR_ERROR}Failed to connect: {e}{COLOR_RESET}")
            return False
    
    def _on_connect(self, client, userdata, flags, rc):
        self.connected = True
        topics = ["/ls_resp", "/thread_typing", "/orca_typing_notifications"]
        for topic in topics:
            client.subscribe(topic, qos=1)
        client.publish(topic="/ls_app_settings", payload=json_minimal({
            "ls_fdid": "", "ls_sv": "6928813347213944"
        }), qos=1, retain=False)
    
    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc == mqtt.MQTT_ERR_CONN_REFUSED:
            client.disconnect()
    
    def _on_message(self, client, userdata, msg):
        pass
    
    def send_typing_indicator(self, thread_id, is_typing, callback=None):
        if not self.connected or not self.mqtt_client:
            raise Exception('Not connected to MQTT')
        
        self.ws_req_number += 1
        
        try:
            thread_data = self.get_thread_info(thread_id)
            label = '3'
            is_group_thread = 1 if thread_data.get("isGroup", False) else 0
            attribution = 0
            
            task_payload = {
                "thread_key": thread_id,
                "is_group_thread": is_group_thread,
                "is_typing": 1 if is_typing else 0,
                "attribution": attribution,
            }
            
            content = {
                "app_id": '2220391788200892',
                "payload": json.dumps({
                    "label": label,
                    "payload": json.dumps(task_payload),
                    "version": '25393437286970779',
                }),
                "request_id": self.ws_req_number,
                "type": 4,
            }
            
            if callback and callable(callback):
                self.ctx["req_callbacks"][self.ws_req_number] = callback
            
            self.mqtt_client.publish(topic='/ls_req', payload=json.dumps(content), qos=1, retain=False)
            return True
        except Exception as e:
            raise Exception(f'Failed to send typing indicator: {str(e)}')
    
    def disconnect(self):
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.connected = False

class Task:
    def __init__(self, task_id, cookie, idbox_list, message_template, delay, typing_delay):
        self.task_id = task_id
        self.cookie = cookie
        self.idbox_list = idbox_list
        self.message_template = message_template
        self.delay = delay
        self.typing_delay = typing_delay
        self.running = True
        self.thread = None
        self.typing_client = None
        self.start_time = datetime.now()
        self.success = 0
        self.fail = 0
        self.uid = get_uid_from_cookie(cookie)
        
    def get_message(self):
        """Lấy nội dung tin nhắn đã thay thế {from}"""
        # Lấy từ task_messages nếu có, nếu không dùng message_template
        current_message = task_messages.get(self.task_id, self.message_template)
        from_name = task_from_names.get(self.task_id, None)
        
        if from_name:
            return current_message.replace("{from}", from_name)
        return current_message.replace("{from}", f"User_{self.uid}" if self.uid else "Unknown")
        
    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.typing_client:
            try:
                self.typing_client.disconnect()
            except:
                pass
    
    def run(self):
        try:
            self.typing_client = FacebookTypingMQTT(self.cookie)
            if not self.typing_client.connect():
                print(f"{COLOR_ERROR}Task {self.task_id}: Khong the ket noi{COLOR_RESET}")
                return
            
            token = get_token(self.cookie)
            
            while self.running:
                try:
                    current_delay = self.delay + random.uniform(-1, 1)
                    if current_delay < 0.5:
                        current_delay = 0.5
                    
                    msg_id = str(int(time.time() * 1000))
                    
                    # Lấy nội dung tin nhắn đã thay thế {from}
                    message = self.get_message()
                    
                    try:
                        if simulate_typing:
                            self.typing_client.send_typing_indicator(self.idbox_list, True)
                            time.sleep(self.typing_delay)
                            self.typing_client.send_typing_indicator(self.idbox_list, False)
                    except Exception as e:
                        pass
                    
                    payload = {
                        "body": message,
                        "msgid": msg_id,
                        "sender_fbid": token.split('|')[0] if '|' in token else token,
                        "to": self.idbox_list,
                        "offline_threading_id": msg_id
                    }
                    
                    if self.typing_client.mqtt_client:
                        result = self.typing_client.mqtt_client.publish(
                            "/send_message2",
                            json.dumps(payload),
                            qos=1
                        )
                        
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            self.success += 1
                        else:
                            self.fail += 1
                    
                    uptime = get_uptime(self.start_time)
                    from_display = task_from_names.get(self.task_id, "Chua dat")
                    print(f"[Task {self.task_id}] {self.idbox_list} | OK:{self.success} FAIL:{self.fail} | Uptime:{uptime} | From: {from_display}".ljust(100), end='\r')
                    
                    time.sleep(current_delay)
                    
                except Exception as e:
                    self.fail += 1
                    time.sleep(self.delay)
                    
        except Exception as e:
            print(f"{COLOR_ERROR}Task {self.task_id}: Loi - {e}{COLOR_RESET}")

def get_token(cookie):
    parts = cookie.split(';')
    c_user = None
    xs = None
    
    for part in parts:
        part = part.strip()
        if part.startswith('c_user='):
            c_user = part.split('=')[1]
        elif part.startswith('xs='):
            xs = part.split('=')[1]
    
    return f"{c_user}|{xs}" if c_user and xs else cookie

def add_multiple_tasks():
    global tasks, task_counter, current_delay, simulate_typing, idbox_list
    
    print("\n" + "="*50)
    print("NHAP THONG TIN CHUNG")
    print("="*50)
    
    # Nhap ID Box chung
    idbox_list = input("Nhap ID Box (1 ID): ").strip()
    if not idbox_list:
        print("Khong co ID Box")
        return
    
    # Nhap file txt chung
    print("\nNhap file noi dung:")
    message_content, default_from = get_message_from_file()
    if not message_content:
        print("Khong co noi dung")
        return
    
    # Nhap delay chung
    try:
        delay_input = float(input("Nhap delay (giay): ").strip())
        current_delay = max(0.5, delay_input)
    except:
        current_delay = 15
        print(f"Su dung delay mac dinh: {current_delay}")
    
    # Nhap typing delay chung
    try:
        typing_input = float(input("Nhap delay typing (giay, mac dinh 0.5): ").strip())
        typing_delay = max(0.1, typing_input)
    except:
        typing_delay = 0.5
        print(f"Su dung typing delay mac dinh: {typing_delay}")
    
    # Nhap nhieu cookie
    print("\n" + "="*50)
    print("NHAP COOKIE (moi cookie la 1 task)")
    print("Nhap 'done' de ket thuc")
    print("="*50)
    
    cookie_list = []
    count = 1
    while True:
        cookie = input(f"Cookie {count}> ").strip()
        if cookie.lower() == 'done':
            break
        if cookie:
            cookie_list.append(cookie)
            count += 1
    
    if not cookie_list:
        print("Khong co cookie nao duoc nhap")
        return
    
    # Tao task cho tung cookie
    print(f"\nDang tao {len(cookie_list)} task...")
    for cookie in cookie_list:
        task_counter += 1
        task = Task(task_counter, cookie, idbox_list, message_content, current_delay, typing_delay)
        task.start()
        tasks.append(task)
        
        # Lưu message và from cho task
        task_messages[task_counter] = message_content
        if default_from:
            task_from_names[task_counter] = default_from
        
        print(f"{COLOR_SUCCESS}Da tao Task {task_counter} cho UID: {get_uid_from_cookie(cookie) or 'Khong xac dinh'}{COLOR_RESET}")
    
    print(f"\n{COLOR_SUCCESS}Da tao xong {len(cookie_list)} task{COLOR_RESET}")

def add_single_task():
    global tasks, task_counter, current_delay, simulate_typing
    
    print("\n" + "="*50)
    print("THEM TASK MOI")
    print("="*50)
    
    cookie = input("Nhap Cookie: ").strip()
    if not cookie:
        print("Khong co cookie")
        return
    
    idbox = input("Nhap ID Box: ").strip()
    if not idbox:
        print("Khong co ID Box")
        return
    
    print("\nNhap file noi dung:")
    message, default_from = get_message_from_file()
    if not message:
        print("Khong co noi dung")
        return
    
    try:
        delay_input = float(input("Nhap delay (giay): ").strip())
        delay = max(0.5, delay_input)
    except:
        delay = 15
    
    try:
        typing_input = float(input("Nhap delay typing (giay, mac dinh 0.5): ").strip())
        typing_delay = max(0.1, typing_input)
    except:
        typing_delay = 0.5
    
    task_counter += 1
    task = Task(task_counter, cookie, idbox, message, delay, typing_delay)
    task.start()
    tasks.append(task)
    
    # Lưu message và from cho task
    task_messages[task_counter] = message
    if default_from:
        task_from_names[task_counter] = default_from
    
    print(f"{COLOR_SUCCESS}Da them Task {task_counter} cho UID: {get_uid_from_cookie(cookie) or 'Khong xac dinh'}{COLOR_RESET}")

def stop_task():
    global tasks
    if not tasks:
        print("Khong co task nao dang chay")
        return
    
    print("\nDanh sach task:")
    for i, task in enumerate(tasks, 1):
        status = "DANG CHAY" if task.running else "DA DUNG"
        uptime = get_uptime(task.start_time)
        user_id = get_uid_from_cookie(task.cookie) or "Unknown"
        from_display = task_from_names.get(task.task_id, "Khong co")
        print(f"{i}. Task {task.task_id} - UID: {user_id} - From: {from_display} - OK:{task.success} FAIL:{task.fail} - {status}")
    
    try:
        choice = int(input("Chon task de dung (nhap so): ")) - 1
        if 0 <= choice < len(tasks):
            tasks[choice].stop()
            print(f"{COLOR_SUCCESS}Da dung Task {tasks[choice].task_id}{COLOR_RESET}")
            # Xóa dữ liệu của task
            tid = tasks[choice].task_id
            if tid in task_messages:
                del task_messages[tid]
            if tid in task_from_names:
                del task_from_names[tid]
            tasks.pop(choice)
        else:
            print("Lua chon khong hop le")
    except:
        print("Lua chon khong hop le")

def change_task_content_cmd():
    """Xử lý lệnh thay đổi nội dung"""
    global tasks
    if not tasks:
        print("Khong co task nao")
        return
    
    try:
        task_id = int(input("Nhap ID task can thay noi dung: ").strip())
        task_found = None
        for task in tasks:
            if task.task_id == task_id:
                task_found = task
                break
        
        if task_found:
            change_task_content(task_id)
        else:
            print(f"Khong tim thay task {task_id}")
    except:
        print("ID task khong hop le")

def change_task_from_cmd():
    """Xử lý lệnh thay đổi tên from"""
    global tasks
    if not tasks:
        print("Khong co task nao")
        return
    
    print("Cu phap: from [task_id] [ten_moi] hoac from all [ten_moi]")
    cmd = input("Nhap lenh: ").strip()
    parts = cmd.split(' ', 2)
    
    if len(parts) < 2:
        print("Cu phap khong hop le")
        return
    
    target = parts[0]
    name = parts[1] if len(parts) == 2 else ' '.join(parts[1:])
    
    if target.lower() == 'all':
        confirm = input(f"Thay doi ten cho TAT CA {len(tasks)} task thanh '{name}'? (y/n): ").strip().lower()
        if confirm in ['y', 'yes', '1']:
            for task in tasks:
                change_task_from(task.task_id, name)
            print(f"{COLOR_SUCCESS}Da thay doi ten cho {len(tasks)} task{COLOR_RESET}")
    else:
        try:
            task_id = int(target)
            task_found = None
            for task in tasks:
                if task.task_id == task_id:
                    task_found = task
                    break
            
            if task_found:
                change_task_from(task_id, name)
            else:
                print(f"Khong tim thay task {task_id}")
        except:
            print("ID task khong hop le")

def stop_all():
    global tasks, running
    print("Dang dung tat ca task...")
    for task in tasks:
        task.stop()
    tasks.clear()
    task_messages.clear()
    task_from_names.clear()
    print("Da dung tat ca")

def set_delay():
    global current_delay
    try:
        val = float(input("Nhap delay moi (giay): ").strip())
        current_delay = val
        print(f"{COLOR_SUCCESS}Da doi delay thanh {val} giay{COLOR_RESET}")
    except:
        print("Delay khong hop le")

def set_typing():
    global simulate_typing
    choice = input("Bat che do typing? (y/n): ").strip().lower()
    if choice in ['y', 'yes', '1']:
        simulate_typing = True
        print(f"{COLOR_SUCCESS}Da bat che do typing{COLOR_RESET}")
    else:
        simulate_typing = False
        print(f"{COLOR_SUCCESS}Da tat che do typing{COLOR_RESET}")

def auto_clean_memory():
    def clean_loop():
        while True:
            time.sleep(60)
            gc.collect()
            if psutil:
                process = psutil.Process()
                memory = process.memory_info().rss / 1024 / 1024
                print(f"\n{COLOR_INFO}[CLEAN] Ram usage: {memory:.2f} MB{COLOR_RESET}")
    thread = threading.Thread(target=clean_loop, daemon=True)
    thread.start()

def main():
    clear()
    global running, tasks, current_delay, simulate_typing
    
    auto_clean_memory()
    
    print("CHUONG TRINH GUI TIN NHAN FACEBOOK")
    print("Go 'help' de xem danh sach lenh")
    print("="*50)
    
    # Nhap thong tin ban dau voi nhieu cookie
    add_multiple_tasks()
    
    print(f"\n{COLOR_INFO}Da khoi dong xong. Nhap lenh de dieu khien (go help de xem lenh){COLOR_RESET}")
    
    while running:
        try:
            cmd = input("\n[CMD] > ").strip().lower()
            
            if cmd == 'add':
                add_single_task()
            elif cmd == 'stop':
                stop_task()
            elif cmd == 'list':
                show_task_list()
            elif cmd == 'thay':
                change_task_content_cmd()
            elif cmd == 'from':
                change_task_from_cmd()
            elif cmd == 'delay':
                set_delay()
            elif cmd == 'typing':
                set_typing()
            elif cmd == 'stopall':
                stop_all()
            elif cmd == 'help':
                show_help()
            elif cmd == 'exit':
                stop_all()
                running = False
                break
            elif cmd == '':
                continue
            else:
                print(f"{COLOR_WARNING}Lenh khong hop le. Go 'help' de xem danh sach lenh{COLOR_RESET}")
                
        except KeyboardInterrupt:
            stop_all()
            break
        except Exception as e:
            print(f"Loi: {e}")
    
    print("\nCam on da su dung tool!")

if __name__ == "__main__":
    main()
