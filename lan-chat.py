import socket
import threading
from tkinter import *
from tkinter import ttk, filedialog
import platform
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import webbrowser
import struct

# Basic network stuff
def get_my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # Google DNS
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"  # Fallback to localhost

# Quick check if host responds
def ping_host(ip):
    if platform.system().lower() == "windows":
        cmd = f"ping -n 1 -w 500 {ip}"
    else:
        cmd = f"ping -c 1 -W 1 {ip}"
        
    return subprocess.run(cmd.split(), stdout=subprocess.DEVNULL).returncode == 0

# Try common ports
def check_ports(ip):
    common_ports = [80, 443, 22, 445]
    for p in common_ports:
        try:
            s = socket.socket()
            s.settimeout(0.3)
            if s.connect_ex((ip, p)) == 0:
                s.close()
                return True
        except:
            pass
    return False

def is_host_alive(ip):
    return ping_host(ip) or check_ports(ip)

# Network scanner
def scan_network():
    def do_scan():
        try:
            # Clear old results
            for w in hosts_frame.winfo_children():
                w.destroy()
            Label(hosts_frame, text="Scanning network...", font=('Arial', 10)).pack(pady=5)
            
            my_ip = get_my_ip()
            net_prefix = '.'.join(my_ip.split('.')[:-1])
            live_hosts = []

            # Scan all IPs in parallel
            with ThreadPoolExecutor(max_workers=50) as pool:
                futures = []
                for i in range(1, 255):
                    ip = f"{net_prefix}.{i}"
                    futures.append(pool.submit(is_host_alive, ip))
                
                for i, f in enumerate(futures):
                    if f.result():
                        ip = f"{net_prefix}.{i+1}"
                        live_hosts.append(ip)
                        root.after(0, lambda ip=ip: hosts_listbox.insert(END, ip))

            # Update UI with results
            update_host_list(live_hosts)
            
        except Exception as e:
            status_bar.config(text=f"Scan failed: {str(e)}")

    threading.Thread(target=do_scan, daemon=True).start()

# Simple chat implementation
MSG_PORT = 5001
FILE_PORT = 5002
CHUNK_SIZE = 8192  # Bigger chunks for faster transfer

def chat_server():
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', MSG_PORT))
    sock.listen(5)
    
    while True:
        try:
            conn, addr = sock.accept()
            msg = conn.recv(CHUNK_SIZE).decode()
            if msg:
                show_message(f"{addr[0]}: {msg}")
            conn.close()
        except:
            continue

def send_msg():
    target = target_box.get()
    msg = msg_box.get('1.0', END).strip()
    
    if not target or not msg:
        return
        
    try:
        s = socket.socket()
        s.connect((target, MSG_PORT))
        s.send(msg.encode())
        s.close()
        show_message(f"Me: {msg}")
        msg_box.delete('1.0', END)
    except Exception as e:
        status_bar.config(text=f"Failed to send: {e}")

# File transfer stuff  
def file_server():
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', FILE_PORT))
    sock.listen(5)
    
    while True:
        try:
            conn, addr = sock.accept()
            
            # Receive filename length
            name_len = struct.unpack('!I', conn.recv(4))[0]
            # Receive filename
            fname = conn.recv(name_len).decode()
            
            # Receive file size
            size = struct.unpack('!Q', conn.recv(8))[0]
            
            # Create downloads folder if it doesn't exist
            downloads_dir = "downloads"
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)
            
            # Receive file data
            with open(os.path.join(downloads_dir, fname), 'wb') as f:
                received = 0
                while received < size:
                    chunk = conn.recv(min(CHUNK_SIZE, size - received))
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
            
            show_message(f"Received file from {addr[0]}: {fname}")
            conn.close()
        except Exception as e:
            print(f"File receive error: {e}")
            continue

def send_file():
    target = target_box.get()
    if not target:
        status_bar.config(text="Select a target first")
        return
        
    file = filedialog.askopenfilename()
    if not file:
        return
        
    try:
        s = socket.socket()
        s.connect((target, FILE_PORT))
        
        # Get filename and size
        fname = os.path.basename(file)
        size = os.path.getsize(file)
        
        # Send filename length and filename
        s.send(struct.pack('!I', len(fname)))
        s.send(fname.encode())
        
        # Send file size
        s.send(struct.pack('!Q', size))
        
        # Send file data
        with open(file, 'rb') as f:
            sent = 0
            while sent < size:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                s.send(chunk)
                sent += len(chunk)
                
        show_message(f"Sent file to {target}: {fname}")
        status_bar.config(text=f"File sent successfully: {fname}")
        s.close()
    except Exception as e:
        status_bar.config(text=f"File send failed: {str(e)}")

def show_message(msg):
    chat_area.config(state=NORMAL)
    chat_area.insert(END, msg + "\n")
    chat_area.config(state=DISABLED)
    chat_area.see(END)

def update_host_list(hosts):
    # Clear previous items
    for w in hosts_frame.winfo_children():
        w.destroy()
        
    Label(hosts_frame, text=f"Online Hosts ({len(hosts)})", font=('Arial', 10)).pack()
    
    # Recreate listbox
    global hosts_listbox
    hosts_listbox = Listbox(hosts_frame, width=25)
    hosts_listbox.pack(expand=True, fill=BOTH)
    
    # Add hosts to listbox and combobox
    for host in hosts:
        hosts_listbox.insert(END, host)
    
    target_box['values'] = hosts
    if hosts:
        target_box.set(hosts[0])
    
    status_bar.config(text=f"Found {len(hosts)} hosts")

# GUI stuff
root = Tk()
root.title("Network Chat")
root.geometry("800x600")

# Top bar
top = Frame(root, pady=5)
top.pack(fill=X)

Label(top, text="Your IP: " + get_my_ip()).pack(side=LEFT, padx=5)
target_box = ttk.Combobox(top)
target_box.pack(side=LEFT, padx=5)
Button(top, text="Scan", command=scan_network).pack(side=LEFT)

# Main area
main = ttk.PanedWindow(orient=HORIZONTAL)
main.pack(expand=True, fill=BOTH, pady=5)

# Host list
hosts_frame = Frame(main)
Label(hosts_frame, text="Online Hosts").pack()
hosts_listbox = Listbox(hosts_frame, width=25)
hosts_listbox.pack(expand=True, fill=BOTH)
main.add(hosts_frame, weight=30)

# Chat area  
chat_frame = Frame(main)
chat_area = Text(chat_frame, state=DISABLED)
chat_area.pack(expand=True, fill=BOTH)
msg_box = Text(chat_frame, height=3)
msg_box.pack(fill=X)
Button(chat_frame, text="Send", command=send_msg).pack(pady=5)
Button(chat_frame, text="Send File", command=send_file).pack()
main.add(chat_frame, weight=70)

# Status bar
status_bar = Label(root, text="Ready", bd=1, relief=SUNKEN)
status_bar.pack(fill=X, side=BOTTOM)

# Start everything
threading.Thread(target=chat_server, daemon=True).start()
threading.Thread(target=file_server, daemon=True).start()
scan_network()
root.mainloop()
