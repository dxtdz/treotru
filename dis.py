# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import os
import threading
import queue

# Global variables
tasks = {}
task_counter = 0
input_queue = queue.Queue()
running = True
task_messages = {}  # Lưu nội dung message cho từng task

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

def assign_user_agent(token):
    """Gán User Agent cố định cho token"""
    global ua_index
    if token not in token_user_agents:
        user_agent = USER_AGENTS[ua_index % len(USER_AGENTS)]
        token_user_agents[token] = user_agent
        ua_index += 1
        print(f"[XuanThang] Da gan User Agent cho token {token[:20]}...")
    return token_user_agents[token]

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
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        while tasks.get(task_id, {}).get("active", True):
            try:
                current_message = task_messages.get(task_id, "")
                if not current_message:
                    await asyncio.sleep(1)
                    continue
                
                typing_task = asyncio.create_task(keep_typing(session, url_typing, headers))
                await asyncio.sleep(1.5)
                
                async with session.post(url_send, json={"content": current_message}) as resp:
                    if resp.status == 200:
                        print(f"[XuanThang] [{task_id}] {token[:20]}... Da Gui Thanh Cong (200)")
                    elif resp.status == 429:
                        data = await resp.json()
                        retry = data.get("retry_after", 2)
                        typing_task.cancel()
                        await asyncio.sleep(retry)
                        continue
                
                typing_task.cancel()
                
            except asyncio.CancelledError:
                pass
            except:
                pass
            
            if tasks.get(task_id, {}).get("active", True):
                try:
                    typing_task = asyncio.create_task(keep_typing(session, url_typing, headers))
                    await asyncio.sleep(delay)
                    typing_task.cancel()
                except:
                    pass
    
    print(f"[XuanThang] [{task_id}] Da dung task")

def get_message_from_file():
    """Đọc nội dung từ file"""
    while True:
        filename = input().strip()
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass
        print("File khong ton tai, nhap lai:")

def change_task_content(task_id):
    """Thay đổi nội dung file cho task"""
    print(f"Nhap ten file moi cho task {task_id}:")
    new_content = get_message_from_file()
    task_messages[task_id] = new_content
    print(f"[XuanThang] Da thay noi dung cho task {task_id}")

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
        print("\n=== KHONG CO TASK NAO ===\n")
        return
    
    print("\n" + "="*60)
    print("DANH SACH TASK")
    print("="*60)
    
    for tid, info in tasks.items():
        status = "🟢 Dang chay" if info["active"] else "🔴 Dang dung"
        token_preview = info["token"][:25] + "..."
        channel_preview = info["channel"]
        ua = token_user_agents.get(info["token"], "Chua co UA")
        ua_preview = ua[:50] + "..." if len(ua) > 50 else ua
        msg_preview = task_messages.get(tid, "Chua co noi dung")
        msg_preview = msg_preview[:50] + "..." if len(msg_preview) > 50 else msg_preview
        
        print(f"\n📌 Task {tid}")
        print(f"   ├─ Token     : {token_preview}")
        print(f"   ├─ Channel   : {channel_preview}")
        print(f"   ├─ Status    : {status}")
        print(f"   ├─ User Agent: {ua_preview}")
        print(f"   └─ Noi dung  : {msg_preview}")
    
    print("\n" + "="*60)
    print(f"Tong so task: {len(tasks)}")
    print("="*60 + "\n")

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
                            print(f"[XuanThang] Da dung task {task_id}")
                    except:
                        pass
                        
                elif cmd.startswith("thay "):
                    try:
                        task_id = int(cmd.split()[1])
                        if task_id in tasks:
                            change_task_content(task_id)
                        else:
                            print(f"[XuanThang] Khong tim thay task {task_id}")
                    except:
                        print("[XuanThang] Sai cu phap. Dung: thay [id]")
                        
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
                    message = get_message_from_file()
                    
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
                            asyncio.create_task(spam_message(task_id, token, channel, new_delays[token_idx]))
                            print(f"[XuanThang] Da them task {task_id}")
                            
                elif cmd == "help":
                    print("\n=== LENH DIEU KHIEN ===")
                    print("list          - Xem danh sach task (dang doc)")
                    print("stop [id]     - Dung task theo id")
                    print("thay [id]     - Thay file noi dung cho task")
                    print("add           - Them token/channel moi")
                    print("help          - Hien thi huong dan")
                    print("=====================\n")
            
            await asyncio.sleep(0.5)
        except:
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

async def main():
    global task_counter, running
    
    # Nhập thông tin ban đầu
    print("Nhap token (done de ket thuc):")
    initial_tokens = get_tokens_from_input()
    
    print("\nNhap channel ID (done de ket thuc):")
    initial_channels = get_channel_ids_from_input()
    
    print("\nNhap delay cho tung token (giay):")
    initial_delays = get_delays_from_input(initial_tokens)
    
    print("\nNhap ten file noi dung:")
    message = get_message_from_file()
    
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
            asyncio.create_task(spam_message(task_id, token, channel, initial_delays[token_idx]))
    
    print(f"\n[XuanThang] Da khoi tao {task_counter} task")
    print(f"[XuanThang] Da gan User Agent cho {len(token_user_agents)} token")
    print("\nGo 'help' de xem lenh dieu khien\n")
    
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
        print("\n[XuanThang] Da dung toan bo tool!")
