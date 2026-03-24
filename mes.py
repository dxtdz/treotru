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
import hashlib
from datetime import datetime
from collections import defaultdict
import warnings

warnings.filterwarnings("ignore")

def install_packages():
    packages = ['paho-mqtt', 'psutil', 'requests', 'pyfiglet', 'termcolor', 'bs4']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            print(f"Dang cai dat {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_packages()

import paho.mqtt.client as mqtt
from termcolor import colored
from bs4 import BeautifulSoup

# ==================== CAU HINH MESSENGER ====================
COOKIE_RESET_TIME = 21600  # 6 gio
COOKIE_TEMP_BAN_TIME = 21600  # 6 gio
MAX_DISCONNECT_COUNT = 10
MAX_TEMP_BAN_COUNT = 3
MAX_SEND_ERRORS = 8
REFRESH_DTSG_INTERVAL = 3600  # Refresh fb_dtsg moi 1 gio

running = True
tasks = []
task_counter = 0
current_delay = 1.0
simulate_typing = True
idbox_list = ""
message_content = ""
message_files = []
current_file_index = 0

# Quản lý FROM cho từng task
task_messages = {}      # Lưu nội dung message cho từng task
task_from_names = {}    # Lưu tên from cho từng task

# Quan ly trang thai cookie
cookie_attempts = defaultdict(lambda: {
    'count': 0,
    'last_reset': time.time(),
    'banned_until': 0,
    'permanent_ban': False,
    'ban_count': 0,
    'send_errors': 0,
    'success_count': 0,
    'fail_count': 0,
    'fb_dtsg': None,
    'jazoest': None,
    'last_refresh': 0
})

cookie_map = {}
cookie_delays = {}
cookie_box_map = {}

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

def get_user_id_from_cookie(cookie):
    parts = cookie.split(';')
    for part in parts:
        part = part.strip()
        if part.startswith('c_user='):
            return part.split('=')[1]
    return None

def extract_fb_dtsg_and_jazoest(html):
    soup = BeautifulSoup(html, 'html.parser')
    fb_dtsg = None
    jazoest = None
    
    dtsg_input = soup.find('input', {'name': 'fb_dtsg'})
    if dtsg_input and dtsg_input.get('value'):
        fb_dtsg = dtsg_input['value']
    
    jazoest_input = soup.find('input', {'name': 'jazoest'})
    if jazoest_input and jazoest_input.get('value'):
        jazoest = jazoest_input['value']
    
    return fb_dtsg, jazoest

def get_fb_dtsg_and_jazoest(cookie):
    try:
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        cookie_dict = parse_cookie_string(cookie)
        response = requests.get('https://www.facebook.com/', cookies=cookie_dict, headers=headers, timeout=30)
        
        if response.status_code == 200:
            return extract_fb_dtsg_and_jazoest(response.text)
        return None, None
    except Exception:
        return None, None

def get_uptime(start_time):
    elapsed = (datetime.now() - start_time).total_seconds()
    hours, rem = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

# ==================== HÀM XỬ LÝ FROM ====================
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
                    print(f"{COLOR_INFO}Phat hien '{{from}}' trong file noi dung{COLOR_RESET}")
                    print("Nhap ten from muon thay the (de trong neu khong muon thay):")
                    default_from = input().strip()
                    if default_from:
                        print(f"{COLOR_SUCCESS}Se thay '{default_from}' vao vi tri '{{from}}'{COLOR_RESET}")
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

def update_content_files():
    global message_files, message_content, current_file_index
    
    print("\n" + "="*50)
    print("CAP NHAT FILE NOI DUNG")
    print("="*50)
    print(f"File hien tai: {message_files if message_files else 'Chua co'}")
    
    choice = input("Nhap ten file moi (hoac 'cancel' de huy): ").strip()
    
    if choice.lower() == 'cancel':
        print("Da huy cap nhat.")
        return False
    
    if os.path.exists(choice):
        try:
            with open(choice, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    print("File trong.")
                    return False
            
            if choice not in message_files:
                message_files.append(choice)
            
            message_content = content
            print(f"{COLOR_SUCCESS}Da cap nhat noi dung tu file: {choice}{COLOR_RESET}")
            return True
        except Exception as e:
            print(f"Loi doc file: {e}")
            return False
    else:
        print(f"File {choice} khong ton tai.")
        return False

def rotate_content_file():
    global message_files, message_content, current_file_index
    if not message_files:
        return
    
    current_file_index = (current_file_index + 1) % len(message_files)
    try:
        with open(message_files[current_file_index], 'r', encoding='utf-8') as f:
            message_content = f.read().strip()
        print(f"{COLOR_INFO}[ROTATE] Chuyen sang file: {message_files[current_file_index]}{COLOR_RESET}")
    except Exception as e:
        print(f"{COLOR_ERROR}Loi doc file: {e}{COLOR_RESET}")

def handle_failed_connection(cookie_hash):
    current_time = time.time()
    
    if current_time - cookie_attempts[cookie_hash]['last_reset'] > COOKIE_RESET_TIME:
        cookie_attempts[cookie_hash]['count'] = 0
        cookie_attempts[cookie_hash]['last_reset'] = current_time
        cookie_attempts[cookie_hash]['banned_until'] = 0
    
    cookie_attempts[cookie_hash]['count'] += 1
    
    if cookie_attempts[cookie_hash]['count'] >= MAX_DISCONNECT_COUNT and not cookie_attempts[cookie_hash]['permanent_ban']:
        print(f"{COLOR_WARNING}Cookie bi tam ngung {COOKIE_TEMP_BAN_TIME/3600:.1f} gio{COLOR_RESET}")
        cookie_attempts[cookie_hash]['banned_until'] = current_time + COOKIE_TEMP_BAN_TIME
        cookie_attempts[cookie_hash]['ban_count'] += 1
    
    if cookie_attempts[cookie_hash]['ban_count'] >= MAX_TEMP_BAN_COUNT:
        print(f"{COLOR_ERROR}Cookie bi cam vinh vien{COLOR_RESET}")
        cookie_attempts[cookie_hash]['permanent_ban'] = True
        
        for task in tasks[:]:
            if hasattr(task, 'cookie_hash') and task.cookie_hash == cookie_hash:
                task.stop()
                tasks.remove(task)

def handle_send_error(cookie_hash, task_id):
    cookie_attempts[cookie_hash]['send_errors'] += 1
    
    if cookie_attempts[cookie_hash]['send_errors'] >= MAX_SEND_ERRORS:
        print(f"{COLOR_ERROR}Task {task_id}: Gui loi {MAX_SEND_ERRORS} lan, xoa task...{COLOR_RESET}")
        for task in tasks[:]:
            if task.task_id == task_id:
                task.stop()
                tasks.remove(task)
                break
        cookie_attempts[cookie_hash]['send_errors'] = 0

class FacebookTypingMQTT:
    def __init__(self, cookies, user_id):
        self.cookies = cookies
        self.user_id = user_id
        self.mqtt_client = None
        self.connected = False
        self.ws_req_number = 0
        self.cookie_hash = hashlib.md5(cookies.encode()).hexdigest()
        
    def connect(self):
        current_time = time.time()
        if cookie_attempts[self.cookie_hash]['permanent_ban']:
            return False
        
        if current_time < cookie_attempts[self.cookie_hash]['banned_until']:
            return False
        
        session_id = generate_session_id()
        user = {
            "a": get_random_user_agent(),
            "u": self.user_id,
            "s": session_id,
            "chat_on": True,
            "fg": False,
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
        self.mqtt_client.username_pw_set(username=json_minimal(user))
        
        self.mqtt_client.ws_set_options(path="/chat", headers={
            "Cookie": cookie_str,
            "Origin": "https://www.facebook.com",
            "User-Agent": get_random_user_agent(),
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
            
            return self.connected
        except Exception:
            handle_failed_connection(self.cookie_hash)
            return False
    
    def _on_connect(self, client, userdata, flags, rc):
        self.connected = True
        cookie_attempts[self.cookie_hash]['count'] = 0
        topics = ["/ls_resp", "/thread_typing", "/orca_typing_notifications"]
        for topic in topics:
            client.subscribe(topic, qos=1)
    
    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            handle_failed_connection(self.cookie_hash)
    
    def send_typing_indicator(self, thread_id, is_typing):
        if not self.connected or not self.mqtt_client:
            return False
        
        self.ws_req_number += 1
        try:
            task_payload = {
                "thread_key": thread_id,
                "is_group_thread": 1 if thread_id != self.user_id else 0,
                "is_typing": 1 if is_typing else 0,
                "attribution": 0,
            }
            
            content = {
                "app_id": '2220391788200892',
                "payload": json.dumps({
                    "label": "3",
                    "payload": json.dumps(task_payload),
                    "version": '25393437286970779',
                }),
                "request_id": self.ws_req_number,
                "type": 4,
            }
            
            self.mqtt_client.publish(topic='/ls_req', payload=json.dumps(content), qos=1)
            return True
        except Exception:
            return False
    
    def send_message(self, thread_id, message):
        if not self.connected or not self.mqtt_client:
            return False
        
        try:
            msg_id = str(int(time.time() * 1000))
            payload = {
                "body": message,
                "msgid": msg_id,
                "sender_fbid": self.user_id,
                "to": thread_id
            }
            
            result = self.mqtt_client.publish("/send_message2", json.dumps(payload), qos=1)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception:
            return False
    
    def disconnect(self):
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.connected = False

class Task:
    def __init__(self, task_id, cookie, idbox_list, message, delay, typing_delay):
        self.task_id = task_id
        self.cookie = cookie
        self.cookie_hash = hashlib.md5(cookie.encode()).hexdigest()
        self.idbox_list = idbox_list
        self.message = message
        self.delay = delay
        self.typing_delay = typing_delay
        self.running = True
        self.thread = None
        self.typing_client = None
        self.start_time = datetime.now()
        self.success = 0
        self.fail = 0
        self.user_id = get_user_id_from_cookie(cookie)
        self.last_refresh_check = time.time()
        
        if self.cookie_hash not in cookie_map:
            cookie_map[self.cookie_hash] = {'id': self.user_id, 'task_id': task_id}
    
    def get_message(self):
        """Lấy nội dung tin nhắn đã thay thế {from}"""
        current_message = task_messages.get(self.task_id, self.message)
        from_name = task_from_names.get(self.task_id, None)
        
        if from_name:
            return current_message.replace("{from}", from_name)
        return current_message.replace("{from}", f"User_{self.user_id}" if self.user_id else "Unknown")
    
    def refresh_fb_dtsg(self):
        try:
            fb_dtsg, jazoest = get_fb_dtsg_and_jazoest(self.cookie)
            if fb_dtsg and jazoest:
                cookie_attempts[self.cookie_hash]['fb_dtsg'] = fb_dtsg
                cookie_attempts[self.cookie_hash]['jazoest'] = jazoest
                cookie_attempts[self.cookie_hash]['last_refresh'] = time.time()
                print(f"{COLOR_INFO}[!] Lam moi fb_dtsg cho {self.user_id} thanh cong.{COLOR_RESET}")
                return True
            return False
        except Exception as e:
            print(f"{COLOR_ERROR}[X] Loi lam moi fb_dtsg: {e}{COLOR_RESET}")
            return False
    
    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
    
    def stop(self):
        self.running = False
        if self.typing_client:
            try:
                self.typing_client.disconnect()
            except:
                pass
    
    def run(self):
        global message_content, message_files
        
        try:
            if cookie_attempts[self.cookie_hash]['permanent_ban']:
                return
            
            current_time = time.time()
            if current_time < cookie_attempts[self.cookie_hash]['banned_until']:
                remaining = cookie_attempts[self.cookie_hash]['banned_until'] - current_time
                time.sleep(remaining)
            
            self.typing_client = FacebookTypingMQTT(self.cookie, self.user_id)
            if not self.typing_client.connect():
                return
            
            last_rotate_time = time.time()
            last_refresh_time = time.time()
            
            while self.running:
                try:
                    if cookie_attempts[self.cookie_hash]['permanent_ban']:
                        break
                    
                    if time.time() < cookie_attempts[self.cookie_hash]['banned_until']:
                        remaining = cookie_attempts[self.cookie_hash]['banned_until'] - time.time()
                        time.sleep(min(remaining, 60))
                        continue
                    
                    if time.time() - last_refresh_time > REFRESH_DTSG_INTERVAL:
                        if self.refresh_fb_dtsg():
                            last_refresh_time = time.time()
                    
                    if message_files and time.time() - last_rotate_time > 1800:
                        rotate_content_file()
                        last_rotate_time = time.time()
                    
                    current_delay = self.delay + random.uniform(-1, 1)
                    if current_delay < 0.5:
                        current_delay = 0.5
                    
                    final_message = self.get_message()
                    
                    if simulate_typing and self.typing_client:
                        try:
                            self.typing_client.send_typing_indicator(self.idbox_list, True)
                            time.sleep(self.typing_delay)
                            self.typing_client.send_typing_indicator(self.idbox_list, False)
                        except:
                            pass
                    
                    if self.typing_client.send_message(self.idbox_list, final_message):
                        self.success += 1
                        cookie_attempts[self.cookie_hash]['send_errors'] = 0
                    else:
                        self.fail += 1
                        handle_send_error(self.cookie_hash, self.task_id)
                    
                    uptime = get_uptime(self.start_time)
                    from_display = task_from_names.get(self.task_id, "Chua dat")
                    status = f"[Task {self.task_id}] {self.user_id} | Box:{self.idbox_list} | OK:{self.success} FAIL:{self.fail} | Uptime:{uptime} | From: {from_display}"
                    print(status.ljust(100), end='\r')
                    
                    time.sleep(current_delay)
                    
                except Exception as e:
                    self.fail += 1
                    handle_send_error(self.cookie_hash, self.task_id)
                    time.sleep(self.delay)
                    
        except Exception as e:
            print(f"{COLOR_ERROR}Task {self.task_id}: Loi - {e}{COLOR_RESET}")
        finally:
            if self.typing_client:
                self.typing_client.disconnect()

def add_multiple_tasks():
    global tasks, task_counter, current_delay, simulate_typing, idbox_list, message_content, message_files
    
    print("\n" + "="*50)
    print("NHAP THONG TIN CHUNG")
    print("="*50)
    
    idbox_list = input("Nhap ID Box: ").strip()
    if not idbox_list:
        print("Khong co ID Box")
        return
    
    print("\nNhap file noi dung:")
    message_content, default_from = get_message_from_file()
    if not message_content:
        print("Khong co noi dung")
        return
    
    if message_files and message_files[0] not in message_files:
        message_files.append(message_files[0] if message_files else "temp")
    
    try:
        delay_input = float(input("Nhap delay (giay, mac dinh 15): ").strip())
        current_delay = max(0.5, delay_input)
    except:
        current_delay = 15
    
    try:
        typing_input = float(input("Nhap delay typing (giay, mac dinh 0.5): ").strip())
        typing_delay = max(0.1, typing_input)
    except:
        typing_delay = 0.5
    
    print("\nNHAP COOKIE (moi cookie la 1 task, nhap 'done' de ket thuc):")
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
        print("Khong co cookie")
        return
    
    valid_cookies = []
    for cookie in cookie_list:
        user_id = get_user_id_from_cookie(cookie)
        if user_id:
            valid_cookies.append(cookie)
        else:
            print(f"{COLOR_ERROR}Cookie khong hop le{COLOR_RESET}")
    
    if not valid_cookies:
        return
    
    for cookie in valid_cookies:
        task_counter += 1
        task = Task(task_counter, cookie, idbox_list, message_content, current_delay, typing_delay)
        task.start()
        tasks.append(task)
        
        task_messages[task_counter] = message_content
        if default_from:
            task_from_names[task_counter] = default_from
        
        user_id = get_user_id_from_cookie(cookie)
        print(f"{COLOR_SUCCESS}Da tao Task {task_counter} cho UID: {user_id}{COLOR_RESET}")

def show_task_list():
    """Hiển thị danh sách task dạng dọc"""
    if not tasks:
        print(f"\n{COLOR_WARNING}=== KHONG CO TASK NAO ==={COLOR_RESET}\n")
        return
    
    print("\n" + "="*80)
    print("DANH SACH TASK")
    print("="*80)
    
    for idx, task in enumerate(tasks, 1):
        status = f"{COLOR_SUCCESS}🟢 Dang chay{COLOR_RESET}" if task.running else f"{COLOR_ERROR}🔴 Da dung{COLOR_RESET}"
        uptime = get_uptime(task.start_time)
        from_name = task_from_names.get(task.task_id, "Khong co")
        
        msg_preview = task_messages.get(task.task_id, task.message)
        msg_preview = msg_preview[:50] + "..." if len(msg_preview) > 50 else msg_preview
        
        print(f"\n{COLOR_INFO}📌 Task {task.task_id}{COLOR_RESET}")
        print(f"   ├─ UID       : {task.user_id}")
        print(f"   ├─ ID Box    : {task.idbox_list}")
        print(f"   ├─ Status    : {status}")
        print(f"   ├─ From      : {from_name}")
        print(f"   ├─ Delay     : {task.delay}s")
        print(f"   ├─ Typing    : {task.typing_delay}s")
        print(f"   ├─ OK/Fail   : {task.success}/{task.fail}")
        print(f"   ├─ Uptime    : {uptime}")
        print(f"   └─ Noi dung  : {msg_preview}")
    
    print("\n" + "="*80)
    print(f"Tong so task: {len(tasks)}")
    print("="*80 + "\n")

def list_tasks():
    show_task_list()

def stop_task():
    global tasks
    if not tasks:
        print("Khong co task")
        return
    
    show_task_list()
    try:
        choice = int(input("Chon task de dung: ")) - 1
        if 0 <= choice < len(tasks):
            tid = tasks[choice].task_id
            tasks[choice].stop()
            if tid in task_messages:
                del task_messages[tid]
            if tid in task_from_names:
                del task_from_names[tid]
            tasks.pop(choice)
            print("Da dung task")
    except:
        print("Lua chon khong hop le")

def stop_all():
    global tasks, running
    for task in tasks:
        task.stop()
    tasks.clear()
    task_messages.clear()
    task_from_names.clear()
    running = False

def change_task_content_cmd():
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

def show_help():
    print("\n" + "="*50)
    print("DANH SACH LENH")
    print("="*50)
    print("add     - Them task moi")
    print("stop    - Dung task theo so")
    print("list    - Liet ke task (dang doc)")
    print("file    - Cap nhat file noi dung")
    print("thay    - Thay noi dung file cho task (thay [id])")
    print("from    - Thay ten from cho task (from [id] [ten] hoac from all [ten])")
    print("stopall - Dung tat ca")
    print("help    - Hien thi giup do")
    print("exit    - Thoat")
    print("="*50)
    print(f"\n{COLOR_INFO}[From] Su dung {{from}} trong file de thay the ten nguoi gui{COLOR_RESET}")
    print("="*50)

def auto_clean_memory():
    def clean_loop():
        global running
        while running:
            time.sleep(60)
            gc.collect()
            try:
                import psutil
                process = psutil.Process()
                memory = process.memory_info().rss / 1024 / 1024
                print(f"\n{COLOR_INFO}[CLEAN] RAM: {memory:.2f} MB | Tasks: {len(tasks)}{COLOR_RESET}")
            except:
                pass
    
    thread = threading.Thread(target=clean_loop, daemon=True)
    thread.start()

def main():
    clear()
    
    print("="*50)
    print("Dinh Xuan Thang")
    print("Ho tro {from} trong noi dung")
    print("="*50)
    print("Go 'help' de xem danh sach lenh")
    print("="*50)
    
    auto_clean_memory()
    add_multiple_tasks()
    
    global running
    while running:
        try:
            cmd = input("\n[CMD] > ").strip().lower()
            
            if cmd == 'add':
                add_multiple_tasks()
            elif cmd == 'stop':
                stop_task()
            elif cmd == 'list':
                show_task_list()
            elif cmd == 'file':
                update_content_files()
            elif cmd == 'thay':
                change_task_content_cmd()
            elif cmd == 'from':
                change_task_from_cmd()
            elif cmd == 'stopall':
                stop_all()
            elif cmd == 'help':
                show_help()
            elif cmd == 'exit':
                stop_all()
                break
            elif cmd:
                print("Lenh khong hop le. Go 'help'")
                
        except KeyboardInterrupt:
            stop_all()
            break
    
    print("\nDa thoat!")

if __name__ == "__main__":
    main()
