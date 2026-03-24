 # -*- coding: utf-8 -*-
import asyncio
import aiohttp
import os
import threading
import queue
import re
import random
import time
import signal
import gc
from datetime import datetime
from collections import defaultdict

# ==================== CPU GUARD CONFIG ====================
TARGET_CPU_PERCENT = 10.0  # Mục tiêu CPU dưới 10%
CHECK_INTERVAL = 1.0       # Kiểm tra mỗi 1 giây
RESUME_FACTOR = 0.75       # Resume khi CPU < 7.5%
MAX_SUSPEND_SECONDS = 30   # Tạm dừng tối đa 30s
MIN_SUSPEND_SECONDS = 0.05 # Tạm dừng tối thiểu 0.05s

USE_PSUTIL = True
try:
    import psutil
except Exception:
    psutil = None
    USE_PSUTIL = False

# ==================== CPU GUARD FUNCTIONS ====================
PARENT_PID = os.getpid()
_CPU_GUARD_WATCHDOG = None

def _get_num_cpus():
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1

NUM_CPUS = _get_num_cpus()

def _measure_process_cpu_percent_fallback(pid, interval):
    """Fallback khi không có psutil"""
    try:
        if pid != os.getpid():
            return 0.0
        t0 = time.perf_counter()
        cpu0 = time.process_time()
        time.sleep(interval)
        t1 = time.perf_counter()
        cpu1 = time.process_time()
        wall = t1 - t0
        if wall <= 0:
            return 0.0
        cpu_delta = cpu1 - cpu0
        percent = (cpu_delta / wall) * 100.0
        return max(0.0, percent)
    except Exception:
        return 0.0

def _suspend_process_unix(pid):
    try:
        os.kill(pid, signal.SIGSTOP)
        return True
    except Exception:
        return False

def _resume_process_unix(pid):
    try:
        os.kill(pid, signal.SIGCONT)
        return True
    except Exception:
        return False

def _suspend_process_psutil(p_proc):
    try:
        p_proc.suspend()
        return True
    except Exception:
        return False

def _resume_process_psutil(p_proc):
    try:
        p_proc.resume()
        return True
    except Exception:
        return False

def _watchdog_main():
    """Watchdog chạy trong thread riêng: giám sát CPU và suspend/resume"""
    use_ps = USE_PSUTIL and (psutil is not None)
    if use_ps:
        try:
            p = psutil.Process(PARENT_PID)
        except Exception:
            p = None
            use_ps = False
    else:
        p = None

    target = TARGET_CPU_PERCENT
    
    print(f"\033[94m[CPU Guard] Khoi dong - Muc tieu CPU: {target}%\033[0m")
    
    while True:
        try:
            # Đo CPU
            if use_ps:
                try:
                    usage = p.cpu_percent(interval=CHECK_INTERVAL)
                except Exception:
                    usage = 0.0
            else:
                usage = _measure_process_cpu_percent_fallback(PARENT_PID, CHECK_INTERVAL)

            # Nếu CPU vượt target -> suspend
            if usage > target:
                suspend_time = min(MAX_SUSPEND_SECONDS, 
                                  max(MIN_SUSPEND_SECONDS, 
                                      CHECK_INTERVAL * (usage / target - 1) * 2))
                
                print(f"\033[93m[CPU Guard] CPU: {usage:.1f}% > {target}% - Suspend {suspend_time:.2f}s\033[0m")
                
                # Suspend process
                suspended = False
                if use_ps and p is not None:
                    suspended = _suspend_process_psutil(p)
                else:
                    if hasattr(signal, "SIGSTOP"):
                        suspended = _suspend_process_unix(PARENT_PID)
                
                if suspended:
                    time.sleep(suspend_time)
                    # Resume process
                    if use_ps and p is not None:
                        _resume_process_psutil(p)
                    else:
                        if hasattr(signal, "SIGCONT"):
                            _resume_process_unix(PARENT_PID)
                    print(f"\033[92m[CPU Guard] Resume - CPU: {usage:.1f}%\033[0m")
                    time.sleep(0.5)
                else:
                    time.sleep(min(suspend_time, 1.0))
            else:
                # CPU ổn định, ngủ nhẹ
                time.sleep(CHECK_INTERVAL)
                
        except Exception as e:
            time.sleep(1.0)

def start_cpu_guard():
    """Khởi động CPU Guard trong thread riêng"""
    global _CPU_GUARD_WATCHDOG
    
    if os.getenv("CPU_GUARD_DISABLE", "0") == "1":
        print("\033[93m[CPU Guard] Da tat bang bien moi truong\033[0m")
        return None
    
    _CPU_GUARD_WATCHDOG = threading.Thread(target=_watchdog_main, daemon=True)
    _CPU_GUARD_WATCHDOG.start()
    print(f"\033[92m[CPU Guard] Da khoi dong - Gioi han CPU: {TARGET_CPU_PERCENT}%\033[0m")
    return _CPU_GUARD_WATCHDOG

# ==================== DISCORD BOT CODE ====================

# Global variables
tasks = {}
task_counter = 0
input_queue = queue.Queue()
running = True
task_messages = {}  # Lưu nội dung message cho từng task
task_from_names = {}  # Lưu tên from cho từng task
task_stats = {}  # Lưu thống kê cho từng task

# Danh sách User Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
]

# Lưu User Agent cho từng token
token_user_agents = {}
ua_index = 0

# Màu sắc
COLOR_ERROR = '\033[91m'
COLOR_SUCCESS = '\033[92m'
COLOR_WARNING = '\033[93m'
COLOR_INFO = '\033[94m'
COLOR_RESET = '\033[0m'

def get_uptime(start_time):
    """Lấy thời gian chạy"""
    if not start_time:
        return "00:00:00"
    elapsed = (datetime.now() - start_time).total_seconds()
    hours, rem = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def assign_user_agent(token):
    """Gán User Agent cố định cho token"""
    global ua_index
    if token not in token_user_agents:
        user_agent = USER_AGENTS[ua_index % len(USER_AGENTS)]
        token_user_agents[token] = user_agent
        ua_index += 1
        print(f"[XuanThang] Da gan User Agent cho token {token[:20]}...")
    return token_user_agents[token]

def process_message_with_from(message, from_name):
    """Thay thế {from} trong nội dung"""
    if from_name:
        return message.replace("{from}", from_name)
    return message

async def keep_typing(session, url_typing, headers):
    """Liên tục gửi typing indicator"""
    while True:
        try:
            async with session.post(url_typing, headers=headers) as resp:
                pass
            await asyncio.sleep(5)
        except:
            await asyncio.sleep(5)

async def spam_message(task_id, token, channel_id, delay):
    """Gửi tin nhắn với typing effect liên tục"""
    user_agent = assign_user_agent(token)
    
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": user_agent
    }
    url_send = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    url_typing = f"https://discord.com/api/v9/channels/{channel_id}/typing"
    
    # Khởi tạo thống kê
    if task_id not in task_stats:
        task_stats[task_id] = {
            'success': 0,
            'fail': 0,
            'start_time': datetime.now()
        }
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        while tasks.get(task_id, {}).get("active", True):
            try:
                current_message = task_messages.get(task_id, "")
                if not current_message:
                    await asyncio.sleep(1)
                    continue
                
                # Lấy tên from cho task này
                from_name = task_from_names.get(task_id, "")
                
                # Xử lý nội dung với {from}
                final_message = process_message_with_from(current_message, from_name)
                
                # Gửi typing indicator
                typing_task = asyncio.create_task(keep_typing(session, url_typing, headers))
                await asyncio.sleep(1.5)
                
                # Gửi tin nhắn
                async with session.post(url_send, json={"content": final_message}) as resp:
                    if resp.status == 200:
                        task_stats[task_id]['success'] += 1
                        print(f"[XuanThang] [{task_id}] {token[:20]}... Da Gui Thanh Cong (200)")
                    elif resp.status == 429:
                        data = await resp.json()
                        retry = data.get("retry_after", 2)
                        typing_task.cancel()
                        await asyncio.sleep(retry)
                        continue
                    else:
                        task_stats[task_id]['fail'] += 1
                
                typing_task.cancel()
                
                # Hiển thị trạng thái
                uptime = get_uptime(task_stats[task_id]['start_time'])
                from_display = task_from_names.get(task_id, "Chua dat")
                status = f"[Task {task_id}] OK:{task_stats[task_id]['success']} FAIL:{task_stats[task_id]['fail']} | Uptime:{uptime} | From: {from_display}"
                print(status.ljust(100), end='\r')
                
            except asyncio.CancelledError:
                pass
            except Exception as e:
                task_stats[task_id]['fail'] += 1
            
            if tasks.get(task_id, {}).get("active", True):
                try:
                    typing_task = asyncio.create_task(keep_typing(session, url_typing, headers))
                    await asyncio.sleep(delay)
                    typing_task.cancel()
                except:
                    pass
    
    print(f"[XuanThang] [{task_id}] Da dung task")

def get_message_from_file():
    """Đọc nội dung từ file và kiểm tra {from}"""
    while True:
        filename = input().strip()
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                
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
    print(f"Nhap ten file moi cho task {task_id}:")
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

def get_tokens_from_input():
    """Nhập token mới từ input, tự động gán User Agent"""
    tokens = []
    while True:
        token = input().strip()
        if token.lower() == 'done':
            if tokens:
                break
            continue
        if token:
            tokens.append(token)
            assign_user_agent(token)
    return tokens

def get_channel_ids_from_input():
    """Nhập channel ID mới"""
    channels = []
    while True:
        channel = input().strip()
        if channel.lower() == 'done':
            if channels:
                break
            continue
        if channel:
            channels.append(channel)
    return channels

def get_delays_from_input(tokens):
    """Nhập delay cho token mới"""
    delays = []
    for i in range(len(tokens)):
        while True:
            try:
                delay = float(input().strip())
                if delay >= 0:
                    delays.append(delay)
                    break
            except:
                pass
    return delays

def show_task_list():
    """Hiển thị danh sách task dạng dọc"""
    if not tasks:
        print(f"\n{COLOR_WARNING}=== KHONG CO TASK NAO ==={COLOR_RESET}\n")
        return
    
    print("\n" + "="*70)
    print("DANH SACH TASK")
    print("="*70)
    
    for tid, info in tasks.items():
        status = f"{COLOR_SUCCESS}🟢 Dang chay{COLOR_RESET}" if info["active"] else f"{COLOR_ERROR}🔴 Da dung{COLOR_RESET}"
        token_preview = info["token"][:25] + "..."
        channel_preview = info["channel"]
        ua = token_user_agents.get(info["token"], "Chua co UA")
        ua_preview = ua[:50] + "..." if len(ua) > 50 else ua
        msg_preview = task_messages.get(tid, "Chua co noi dung")
        msg_preview = msg_preview[:50] + "..." if len(msg_preview) > 50 else msg_preview
        from_name = task_from_names.get(tid, "Khong co")
        
        stats = task_stats.get(tid, {'success': 0, 'fail': 0})
        uptime = get_uptime(stats.get('start_time', None))
        
        print(f"\n{COLOR_INFO}📌 Task {tid}{COLOR_RESET}")
        print(f"   ├─ Token     : {token_preview}")
        print(f"   ├─ Channel   : {channel_preview}")
        print(f"   ├─ Status    : {status}")
        print(f"   ├─ User Agent: {ua_preview}")
        print(f"   ├─ From      : {from_name}")
        print(f"   ├─ OK/Fail   : {stats['success']}/{stats['fail']}")
        print(f"   ├─ Uptime    : {uptime}")
        print(f"   └─ Noi dung  : {msg_preview}")
    
    print("\n" + "="*70)
    print(f"Tong so task: {len(tasks)}")
    print("="*70 + "\n")

async def add_new_tasks():
    """Thêm task mới khi có input"""
    global task_counter
    
    while running:
        try:
            if not input_queue.empty():
                cmd = input_queue.get_nowait()
                
                if cmd.startswith("stop "):
                    try:
                        task_id = int(cmd.split()[1])
                        if task_id in tasks:
                            tasks[task_id]["active"] = False
                            print(f"{COLOR_SUCCESS}Da dung task {task_id}{COLOR_RESET}")
                    except:
                        pass
                
                elif cmd.startswith("from "):
                    parts = cmd.split(' ', 2)
                    if len(parts) >= 2:
                        try:
                            task_id = int(parts[1])
                            if task_id in tasks:
                                if len(parts) == 3:
                                    change_task_from(task_id, parts[2])
                                else:
                                    change_task_from(task_id)
                            else:
                                print(f"{COLOR_ERROR}Khong tim thay task {task_id}{COLOR_RESET}")
                        except:
                            print(f"{COLOR_WARNING}Sai cu phap. Dung: from [id] [ten] hoac from [id]{COLOR_RESET}")
                    else:
                        print(f"{COLOR_WARNING}Sai cu phap. Dung: from [id] [ten]{COLOR_RESET}")
                        
                elif cmd.startswith("fromall "):
                    name = cmd[8:].strip()
                    if name:
                        for tid in tasks:
                            change_task_from(tid, name)
                        print(f"{COLOR_SUCCESS}Da thay from cho tat ca {len(tasks)} task thanh: {name}{COLOR_RESET}")
                    else:
                        print(f"{COLOR_WARNING}Vui long nhap ten{COLOR_RESET}")
                        
                elif cmd.startswith("thay "):
                    try:
                        task_id = int(cmd.split()[1])
                        if task_id in tasks:
                            change_task_content(task_id)
                        else:
                            print(f"{COLOR_ERROR}Khong tim thay task {task_id}{COLOR_RESET}")
                    except:
                        print(f"{COLOR_WARNING}Sai cu phap. Dung: thay [id]{COLOR_RESET}")
                        
                elif cmd == "list":
                    show_task_list()
                    
                elif cmd == "add":
                    print("Nhap token (done de ket thuc):")
                    new_tokens = get_tokens_from_input()
                    print("Nhap channel ID (done de ket thuc):")
                    new_channels = get_channel_ids_from_input()
                    print("Nhap delay (giay) cho tung token:")
                    new_delays = get_delays_from_input(new_tokens)
                    print("Nhap ten file noi dung:")
                    message, default_from = get_message_from_file()
                    
                    for token_idx, token in enumerate(new_tokens):
                        for channel in new_channels:
                            task_counter += 1
                            task_id = task_counter
                            
                            tasks[task_id] = {
                                "active": True,
                                "token": token,
                                "channel": channel
                            }
                            task_messages[task_id] = message
                            if default_from:
                                task_from_names[task_id] = default_from
                            
                            asyncio.create_task(spam_message(task_id, token, channel, new_delays[token_idx]))
                            print(f"{COLOR_SUCCESS}Da them task {task_id}{COLOR_RESET}")
                            
                elif cmd == "stopall":
                    for tid in tasks:
                        tasks[tid]["active"] = False
                    tasks.clear()
                    task_messages.clear()
                    task_from_names.clear()
                    task_stats.clear()
                    print(f"{COLOR_SUCCESS}Da dung tat ca task{COLOR_RESET}")
                    
                elif cmd == "help":
                    print("\n" + "="*50)
                    print("DANH SACH LENH")
                    print("="*50)
                    print("list          - Xem danh sach task (dang doc)")
                    print("stop [id]     - Dung task theo id")
                    print("thay [id]     - Thay file noi dung cho task")
                    print("from [id]     - Thay ten from cho task")
                    print("from [id] [ten] - Thay ten from cu the")
                    print("fromall [ten] - Thay ten from cho tat ca task")
                    print("add           - Them token/channel moi")
                    print("stopall       - Dung tat ca task")
                    print("help          - Hien thi huong dan")
                    print("="*50)
                    print(f"\n{COLOR_INFO}[CPU Guard] Gioi han CPU: {TARGET_CPU_PERCENT}%{COLOR_RESET}")
                    print(f"{COLOR_INFO}[From] Su dung '{{from}}' trong file de thay the ten nguoi gui{COLOR_RESET}")
                    print("="*50 + "\n")
            
            await asyncio.sleep(0.5)
        except Exception as e:
            await asyncio.sleep(0.5)

def input_listener():
    """Lắng nghe input từ console"""
    while running:
        try:
            cmd = input().strip()
            if cmd:
                input_queue.put(cmd)
        except:
            pass

def auto_clean_memory():
    """Tự động dọn dẹp bộ nhớ"""
    def clean_loop():
        while running:
            time.sleep(60)
            gc.collect()
            if USE_PSUTIL and psutil:
                process = psutil.Process()
                memory = process.memory_info().rss / 1024 / 1024
                print(f"\n{COLOR_INFO}[CLEAN] RAM: {memory:.2f} MB | Tasks: {len(tasks)}{COLOR_RESET}")
    thread = threading.Thread(target=clean_loop, daemon=True)
    thread.start()

async def main():
    global task_counter, running
    
    # Khởi động CPU Guard
    start_cpu_guard()
    
    # Khởi động auto clean memory
    auto_clean_memory()
    
    print("="*60)
    print("Dinh Xuan Thang ")
    print("Anh Em Phat Xit")
    print(f"CPU Guard: Gioi han duoi {TARGET_CPU_PERCENT}%")
    print("="*60)
    
    # Nhập thông tin ban đầu
    print("\nNhap token (done de ket thuc):")
    initial_tokens = get_tokens_from_input()
    
    print("\nNhap channel ID (done de ket thuc):")
    initial_channels = get_channel_ids_from_input()
    
    print("\nNhap delay cho tung token (giay):")
    initial_delays = get_delays_from_input(initial_tokens)
    
    print("\nNhap ten file noi dung:")
    message, default_from = get_message_from_file()
    
    # Khởi tạo task ban đầu
    for token_idx, token in enumerate(initial_tokens):
        for channel in initial_channels:
            task_counter += 1
            task_id = task_counter
            
            tasks[task_id] = {
                "active": True,
                "token": token,
                "channel": channel
            }
            task_messages[task_id] = message
            if default_from:
                task_from_names[task_id] = default_from
            
            asyncio.create_task(spam_message(task_id, token, channel, initial_delays[token_idx]))
    
    print(f"\n{COLOR_SUCCESS}Da khoi tao {task_counter} task{COLOR_RESET}")
    print(f"{COLOR_SUCCESS}Da gan User Agent cho {len(token_user_agents)} token{COLOR_RESET}")
    print(f"\n{COLOR_INFO}Go 'help' de xem lenh dieu khien{COLOR_RESET}\n")
    
    # Chạy input listener trong thread riêng
    input_thread = threading.Thread(target=input_listener, daemon=True)
    input_thread.start()
    
    # Chạy task quản lý
    await add_new_tasks()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        running = False
        print(f"\n{COLOR_SUCCESS}Da dung toan bo tool!{COLOR_RESET}")
