#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import contextlib
import sys
import socket
import math
import os
import io
import re
import signal
import time
import subprocess
import threading
import random

from contextlib import redirect_stdout, redirect_stderr


#from tkinter.font import Font
from PyQt6.QtWidgets import *
#from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer, QUrl, QEvent
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer, QUrl, QEvent,QPropertyAnimation, QEasingCurve,QPoint
from PyQt6.QtCore import QMetaObject
from PyQt6.QtGui import QFont,QTextCursor, QPalette, QColor, QAction, QKeySequence, QIntValidator, QLinearGradient, QPainter, QPen
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon,QFontMetrics,QPainterPath
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtNetwork import QNetworkProxy
from PyQt6.QtCore import QMetaObject, Qt
from PyQt6.QtWidgets import QFileDialog, QInputDialog,QGraphicsDropShadowEffect
from widgets.ai_assistant import AIAssistantWidget

#from core.reporting import REPORT_DIR
# Import LazyFramework
from bin.console import LazyFramework
from core import load_banners_from_folder, get_random_banner
#from modules.payloads.reverse.reverse_tcp import  send_command_to_session
try:
    # Coba import dari path lama
    import modules.payloads.reverse.reverse_tcp as _rtcp_mod
    from modules.payloads.reverse.reverse_tcp import send_command_to_session
except ImportError:
    # Fallback ke path relatif
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import modules.payloads.reverse.reverse_tcp as _rtcp_mod
    from modules.payloads.reverse.reverse_tcp import send_command_to_session
# Import dari folder widgets/
from widgets.notif import CyberpunkToast
from widgets.theme_manager import ThemeManager
from widgets.network_map import NetworkMapWidget
from widgets.proxy_dialog import ProxySettingsDialog

# Import dari folder core/
from core.capture import UniversalCapture
from core.module_runner import ModuleRunner


class GUIConsole:
    def __init__(self, output_callback):
        self.output_callback = output_callback

    def print(self, *args, **kwargs):
        try:
            from io import StringIO
            from rich.console import Console

            with StringIO() as buffer:
                console = Console(file=buffer, force_terminal=False, width=120)
                console.print(*args, **kwargs)
                output = buffer.getvalue().rstrip()
                if output:
                    self.output_callback(output)
        except Exception as e:
            self.output_callback(f"[red]Console error: {e}[/red]")



# === MAIN GUI COMPLETE ===
class LazyFrameworkGUI(QMainWindow):
    session_output_signal = pyqtSignal(str, str)
    console_output_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.show_splash_screen()
        self.setWindowIcon(QIcon(""))
        self.framework = LazyFramework()
        
        #self.current_module_label = None
        
        self.capture = UniversalCapture()
        self.capture.output_signal.connect(self.append_output)

        # Replace framework console dengan GUI console
        self.framework.console = GUIConsole(self.append_output)

    

        self.current_module = None
        self.workers = []
        self.command_history = []
        self.history_index = -1
        self.module_runner = None
        self.active_session_id = None
        self.selected_session_id = None
        self.reverse_listener = None
        self.current_proxy = None
        self.proxy_enabled = False
        
        self.custom_proxies = []        # semua proxy dari proxies.txt
        self.current_proxy_index = -1

        self.browser = None
        
        self.browser_tab = None
        self.browser_controls_widget = None
        self.browser_placeholder = None
        self.sessions = {}  # {id: {'ip': '1.2.3.4', 'port': 4444, 'type': 'bash', 'handler': None, 'output': ''}}
        self.active_listeners = {}  # {('lhost', lport): status}
        self.listener_lock = threading.Lock()
        self.session_lock = threading.Lock()
        self.framework.session['gui_sessions'] = {'dict': self.sessions, 'lock': self.session_lock}
        #self.framework.session['gui_sessions'] = {'dict': self.sessions, 'lock': self.session_lock}
        self.framework.session['gui_instance'] = self
        self.theme_manager = ThemeManager(QApplication.instance(), self)
        self.ensure_monospace_fonts()
        self.init_ui()
        # Connect thread-safe signals SETELAH init_ui() agar widget sudah siap
        self.session_output_signal.connect(self.append_session_output)
        self.console_output_signal.connect(self.append_output)
        #self.start_global_capture()

        import glob
        import shutil
        cache_dirs = glob.glob("**/__pycache__", recursive=True)
        for cache in cache_dirs:
            try:
                shutil.rmtree(cache)
            except Exception as e:
                pass
                
        #self.load_banner()
        QTimer.singleShot(2000, self.start_tor_auto_rotate)
        self.last_tor_ip = None
        self.active_module = ""
        
        self.update_session_info()

        
        #self.module_runner = None

        # Contoh: selamat datang
        QTimer.singleShot(1500, lambda: self.show_cyber_toast(
            "LazyFramework GUI v2.0 ready",
            title="Welcome",
            duration_ms=5000,
            level="success"
        ))
    
    def show_cyber_toast(self, message: str, title: str = "", 
                     duration_ms: int = 5500, level: str = "info",
                     width: int = 420, icon: str = None):
        toast = CyberpunkToast(
            self,
            title=title or "LAZYFRAMEWORK",
            message=message,
            duration=duration_ms,
            level=level,
            width=width,
            icon=icon
        )
        toast.show()

    def stop_module(self):
        if not hasattr(self, "module_runner") or self.module_runner is None:
            return

        if not self.module_runner.isRunning():
            return

        self.append_output("[yellow]Stopping module…[/yellow]")

        try:
            self.module_runner.stop()
        except Exception as e:
            self.append_output(f"[red]Stop error: {e}[/red]")

        self.run_btn.setEnabled(True)
        self.run_btn.setText("START")
        self.run_btn.setProperty("action", "run")

       

        self.append_output("[green]✓ Stop requested[/green]")

        # JANGAN self.module_runner = None DI SINI
        # Tunggu finished.emit() baru reset
        if self.framework.loaded_module and "reverse_tcp" in str(self.framework.loaded_module):
           self.cleanup_reverse_tcp_sessions()





    def handle_run_stop(self):
        action = self.run_btn.property("action")

        if action == "run":
            self.run_module()
            self.run_btn.setText("STOP")
            self.run_btn.setProperty("action", "stop")

        elif action == "stop":
            self.stop_module()

          


    

    
    
    def ensure_monospace_fonts(self):
        """Ensure all text widgets use consistent monospace fonts TANPA OVERRIDE THEME"""
        try:
            # Daftar font monospace yang diurutkan berdasarkan preferensi
            monospace_fonts = [
                "DejaVu Sans Mono",
                "Source Code Pro", 
                "Consolas",
                "Monaco",
                "Courier New",
                "Monospace"
            ]
            
            # Cari font yang tersedia di sistem
            available_font = "Courier New"  # Fallback default
            for font in monospace_fonts:
                if QFont(font).exactMatch():
                    available_font = font
                    break
            
            # Base font untuk aplikasi - HANYA SET FONT, BUKAN STYLESHEET
            base_font = QFont(available_font, 10)
            
            # === APPLY FONT ONLY - NO STYLESHEET OVERRIDE ===
            
            # Console Output - HANYA FONT
            self.console_output.setFont(base_font)
            
            # Module Info - HANYA FONT  
            self.module_detail_info.setFont(base_font)
            
            # Session Output - HANYA FONT
            self.session_output.setFont(base_font)
            
            # Session Info - HANYA FONT
            if hasattr(self, 'session_info'):
                self.session_info.setFont(base_font)
            
            # Module Info (sidebar) - HANYA FONT
            self.module_info.setFont(QFont(available_font, 9))
            
            # Module List - HANYA FONT
            module_list_font = QFont(available_font, 10)
            for i in range(self.module_list.count()):
                item = self.module_list.item(i)
                if item:
                    item.setFont(module_list_font)
            
            # Option Widgets - HANYA FONT
            if hasattr(self, 'option_widgets'):
                for widget in self.option_widgets.values():
                    if isinstance(widget, (QLineEdit, QTextEdit)):
                        widget.setFont(base_font)
            
            # Command Inputs - HANYA FONT
            if hasattr(self, 'session_cmd_input'):
                self.session_cmd_input.setFont(base_font)
                
            if hasattr(self, 'search_input'):
                self.search_input.setFont(base_font)
            
            # URL Bar (browser) - HANYA FONT
            if hasattr(self, 'url_bar') and self.url_bar:
                self.url_bar.setFont(base_font)
            
            # Log success
            self.append_output(f"[green]✓ Font consistency applied: {available_font}[/]")
            
            return available_font
            
        except Exception as e:
            self.append_output(f"[red]Font consistency error: {e}[/]")
            return "Courier New"

          
    def show_splash_screen(self):
        """Show Burp Suite style splash screen"""
        # Buat splash screen dengan ukuran fixed
        splash = QSplashScreen()
        splash.setFixedSize(800, 600)
        splash.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        
        # Set background color (dark theme like Burp Suite)
        splash.setStyleSheet("""
            QSplashScreen {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2b2b2b, stop:0.5 #3c3f41, stop:1 #2b2b2b);
                border: 2px solid #555555;
                border-radius: 10px;
            }
        """)
        
        # Main layout untuk splash screen
        layout = QVBoxLayout(splash)
        layout.setContentsMargins(40, 40, 40, 30)
        layout.setSpacing(30)
        
        # === LOGO / TITLE AREA ===
        logo_widget = QWidget()
        logo_layout = QVBoxLayout(logo_widget)
        logo_layout.setSpacing(15)
        
        # App Name (Burp Suite Style)
        app_name = QLabel("LAZYFRAMEWORK")
        app_name.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 32px;
                font-weight: bold;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Subtitle
        subtitle = QLabel("Professional Security Testing Framework")
        subtitle.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-size: 14px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Version info
        version = QLabel("Version 2.6.0")
        version.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 12px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        logo_layout.addWidget(app_name)
        logo_layout.addWidget(subtitle)
        logo_layout.addWidget(version)
        
        # === LOADING PROGRESS AREA ===
        progress_widget = QWidget()
        progress_layout = QVBoxLayout(progress_widget)
        progress_layout.setSpacing(10)
        
        # Loading text
        loading_text = QLabel("Loading modules and components...")
        loading_text.setStyleSheet("""
            QLabel {
                color: #aaaaaa;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        loading_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Progress bar (Burp Suite Blue Style)
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setFixedHeight(12)
        progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e1e;
                border: 1px solid #555555;
                border-radius: 6px;
                text-align: center;
                color: white;
            }
            
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a90e2, stop:0.5 #5ca0ff, stop:1 #4a90e2);
                border-radius: 5px;
                border: 1px solid #5ca0ff;
            }
        """)
        
        # Percentage label (ubah jadi biru juga)
        self.percentage_label = QLabel("0%")
        self.percentage_label.setStyleSheet("""
            QLabel {
                color: #5ca0ff;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        self.percentage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        progress_layout.addWidget(loading_text)
        progress_layout.addWidget(progress_bar)
        progress_layout.addWidget(self.percentage_label)
        
        # === STATUS MESSAGES ===
        self.status_label = QLabel("Initializing framework...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #66ccff;
                font-size: 13px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # === COPYRIGHT FOOTER ===
        footer = QLabel("© 2024 LazyFramework Security Team")
        footer.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 11px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add semua widget ke layout utama
        layout.addWidget(logo_widget)
        layout.addStretch(1)
        layout.addWidget(progress_widget)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addWidget(footer)
        
        # Center splash screen di layar
        screen_geo = QApplication.primaryScreen().availableGeometry()
        splash_geo = splash.frameGeometry()
        splash.move(
            (screen_geo.width() - splash_geo.width()) // 2,
            (screen_geo.height() - splash_geo.height()) // 2
        )
        
        splash.show()
        
        # === ANIMATED LOADING SEQUENCE ===
        loading_steps = [
            (10, "Loading core modules..."),
            (25, "Initializing user interface..."),
            (40, "Setting up proxy configurations..."),
            (55, "Loading session manager..."),
            (70, "Initializing browser engine..."),
            (85, "Starting security services..."),
            (95, "Finalizing setup..."),
            (100, "Ready!")
        ]
        
        for progress, status in loading_steps:
            progress_bar.setValue(progress)
            self.percentage_label.setText(f"{progress}%")
            self.status_label.setText(status)
            
            QApplication.processEvents()
            time.sleep(0.50)  # Sedikit lebih cepat dari Burp Suite asli
        
        # Tunggu sebentar di 100% sebelum menutup
        time.sleep(0.50)
        splash.close()

    def set_active_module(self, module_name):
        self.active_module = module_name
        self.update_title()

       
    def center_title(self, text):
        padding = " " * ((150 - len(text)) // 2)
        return padding + text + padding

    def update_title(self):
        title = "Lazy Framework GUI"

        if self.active_module:
            title = f"{title}   |   {self.active_module}"

        self.setWindowTitle(self.center_title(title))
       
    def init_ui(self):
        # === SET WINDOW FLAGS UNTUK TITLE DI TENGAH ===
        self.active_module = ""
        self.update_title()
        #self.setWindowTitle(self.center_title("LazyFramework GUI"))
        self.setGeometry(100, 50, 1800, 1000)
        
         # Apply saved font (if any)
        saved_font = self.framework.session.get('font', 'DejaVu Sans Mono Bold')
        saved_size = self.framework.session.get('font_size', 12)
        default_font = QFont(saved_font, saved_size)
        self.setFont(default_font)
        # Set dark theme
        #self.set_dark_theme()
        #self.apply_matrix_border_style()
        # Create menu bar
        self.create_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # === LEFT SIDEBAR ===
        left_sidebar = self.create_left_sidebar()
        layout.addWidget(left_sidebar, 1)

        # === MAIN CONTENT AREA ===
        main_content = self.create_main_content()
        layout.addWidget(main_content, 3)

        # === RIGHT SIDEBAR ===
        right_sidebar = self.create_right_sidebar()
        layout.addWidget(right_sidebar, 1)

        # Load initial modules
        QTimer.singleShot(100, self.load_all_modules)
        font = QFont("DejaVu Sans Mono", 10)
        self.console_output.setFont(font)
        
        # Atau daftar font fallback
        font_family = "DejaVu Sans Mono, Source Code Pro, Consolas, Monaco, Courier New, monospace"
        self.console_output.setStyleSheet(f"font-family: {font_family};")
        #self.load_banner()
        self.update_info_panel()
    #def start_global_capture(self):
        #"""Start global output capture"""
        #self.capture.start_capture()
        

    

    def auto_rotate_proxy(self):
        mode = self.framework.session.get("proxy_mode", "Disabled")

        if mode == "Tor":
            self.rotate_tor_ip()

        elif mode == "FileProxy":
            self.rotate_custom_proxy()

    def rotate_custom_proxy(self):
        if not self.custom_proxies:
            self.append_output("[yellow]No custom proxies loaded[/]")
            return

        # next proxy
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.custom_proxies)
        self.current_proxy = self.custom_proxies[self.current_proxy_index]
        p = self.current_proxy

        self.append_output(f"[cyan]Switched to proxy → {p['server']}:{p['port']} ({p['type']})[/]")
        
        self.append_output(f"[cyan]Browser proxy updated via PAC → {p['server']}:{p['port']}[/]")
    
    def create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu('File')

        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu('View')

        refresh_action = QAction('Refresh Modules', self)
        refresh_action.setShortcut('F5')
        refresh_action.triggered.connect(self.refresh_modules)
        view_menu.addAction(refresh_action)

        # Tools menu
        tools_menu = menubar.addMenu('Tools')

        clear_action = QAction('Clear Console', self)
        clear_action.setShortcut('Ctrl+L')
        clear_action.triggered.connect(self.clear_console)
        tools_menu.addAction(clear_action)

         # Settings menu
        settings_menu = menubar.addMenu('Settings')
        font_action = QAction('Change Font', self)
        font_action.triggered.connect(self.change_font)
        settings_menu.addAction(font_action)

        #theme_action = QAction('Toggle Light/Dark Mode', self)
        #theme_action.triggered.connect(self.toggle_theme)
        #settings_menu.addAction(theme_action)

        # Proxy menu
        proxy_menu = menubar.addMenu('Proxy')
    
        proxy_settings = QAction('Proxy Settings', self)
        proxy_settings.setShortcut('Ctrl+P')
        proxy_settings.triggered.connect(self.show_proxy_settings)
        proxy_menu.addAction(proxy_settings)
        
        proxy_menu.addSeparator()
        
        enable_proxy = QAction('Enable Proxy', self)
        enable_proxy.setShortcut('Ctrl+Shift+P')
        enable_proxy.triggered.connect(self.enable_proxy)
        proxy_menu.addAction(enable_proxy)
        
        disable_proxy = QAction('Disable Proxy', self)
        disable_proxy.triggered.connect(self.disable_proxy)
        proxy_menu.addAction(disable_proxy)
        
        test_proxy = QAction('Test Proxy', self)
        test_proxy.triggered.connect(self.test_proxy_connection)
        proxy_menu.addAction(test_proxy)

        
    def create_main_content(self):
        """Create main content area"""
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        theme_switcher = self.theme_manager.create_theme_switcher()
        layout.addWidget(theme_switcher)
        pty_toolbar = QToolBar("PTY Tools")
        pty_toolbar.setIconSize(QSize(24, 24))
        pty_toolbar.setStyleSheet("""
            QToolBar {
                background: #1e1e1e;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 3px;
                margin: 2px;
            }
            QToolButton {
                background: #2d2d2d;
                color: #50fa7b;
                border: 1px solid #50fa7b;
                border-radius: 4px;
                padding: 5px 10px;
                margin: 2px;
                font-weight: bold;
            }
            QToolButton:hover {
                background: #50fa7b;
                color: #1e1e1e;
            }
        """)
        
        # Tombol-tombol PTY
        nano_btn = QAction("📝 Nano", self)
        nano_btn.triggered.connect(self.open_file_with_nano)
        pty_toolbar.addAction(nano_btn)
        
        vim_btn = QAction("✍️ Vim", self)
        vim_btn.triggered.connect(lambda: self.pty_run_app('vim'))
        pty_toolbar.addAction(vim_btn)
        
        htop_btn = QAction("📊 Htop", self)
        htop_btn.triggered.connect(self.run_htop)
        pty_toolbar.addAction(htop_btn)
        
        tmux_btn = QAction("🖥️ Tmux", self)
        tmux_btn.triggered.connect(self.run_tmux)
        pty_toolbar.addAction(tmux_btn)
        
        mc_btn = QAction("📁 MC", self)
        mc_btn.triggered.connect(self.run_mc)
        pty_toolbar.addAction(mc_btn)
        
        pty_toolbar.addSeparator()
        
        # PTY Spawn manual (full bash)
        pty_spawn_btn = QAction("🐚 Spawn PTY", self)
        pty_spawn_btn.triggered.connect(self.pty_spawn_bash)   # ← ini kita tambahkan
        pty_toolbar.addAction(pty_spawn_btn)
        
        layout.addWidget(pty_toolbar)
        # Tab widget for different views
        self.tabs = QTabWidget()

        # Console tab
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setFont(QFont("DejaVu Sans Mono Bold", 10))
        self.console_output.setAcceptRichText(True)
        self.tabs.addTab(self.console_output, "Console")

        # Options tab
        self.options_widget = QWidget()
        self.options_layout = QFormLayout(self.options_widget)
        self.options_scroll = QScrollArea()
        self.options_scroll.setWidgetResizable(True)
        self.options_scroll.setWidget(self.options_widget)
        self.tabs.addTab(self.options_scroll, "Options")


        
        # Module info tab
        self.module_detail_info = QTextEdit()
        self.module_detail_info.setReadOnly(True)
        self.module_detail_info.setFont(QFont("Hack", 11))
        self.tabs.addTab(self.module_detail_info, "Module Info")
        self.module_detail_info.setObjectName("module_detail_info")
        self.network_map_widget = NetworkMapWidget(self)
        self.tabs.addTab(self.network_map_widget, "Network Map")
        # TAMBAH TAB SESSION MANAGEMENT
        self.session_tab = QWidget()
        self.session_layout = QVBoxLayout(self.session_tab)

        # Header
        header = QLabel("Session Management")
        header.setObjectName("session_header")  # Tambahkan object name untuk styling
        #header.setStyleSheet("""
            #QLabel#session_header {
                #font-weight: bold; 
                #font-size: 16px; 
                #margin: 10px; 
                #font-family: Hack;
                #padding: 8px;
                #border-bottom: 2px solid #0078d4;
            #}
        #""")
        self.session_layout.addWidget(header)

        # Session List (QListWidget)
        self.session_list = QListWidget()
        self.session_list.itemClicked.connect(self.on_session_selected)
        self.session_layout.addWidget(self.session_list)


        # Command Input
        cmd_layout = QHBoxLayout()
        self.session_cmd_input = QLineEdit()
        self.session_cmd_input.setPlaceholderText("Enter command for selected session...")
        self.session_cmd_input.returnPressed.connect(self.send_session_command)
        cmd_layout.addWidget(self.session_cmd_input)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self.send_session_command)
        cmd_layout.addWidget(send_btn)

        self.session_layout.addLayout(cmd_layout)

        # Output Console untuk Session
        self.session_output = QTextEdit()
        self.session_output.setReadOnly(True)
        #self.session_output.setStyleSheet("background: #000; color: #0f0; font-family: 'Courier New';")
        self.session_layout.addWidget(self.session_output)

        

        # Action Buttons
        btn_layout = QHBoxLayout()
        upgrade_btn = QPushButton("Upgrade to Meterpreter")
        upgrade_btn.clicked.connect(self.upgrade_session)
        btn_layout.addWidget(upgrade_btn)

        kill_btn = QPushButton("Kill Session")
        kill_btn.clicked.connect(self.kill_session)
        kill_btn.setStyleSheet("background: #8B0000; color: white;")
        btn_layout.addWidget(kill_btn)

        self.session_layout.addLayout(btn_layout)

        # Tambah Tab
        self.tabs.addTab(self.session_tab, "Sessions")
        
                # === AI ASSISTANT TAB ===
        self.ai_tab = AIAssistantWidget(framework=self.framework)
        self.tabs.addTab(self.ai_tab, "🤖 AI Assistant")

        layout.addWidget(self.tabs)

        # Control buttons
        control_layout = QHBoxLayout()

        #self.run_btn = QPushButton("START")
        #self.run_btn.setProperty("action", "run")
        #self.run_btn.clicked.connect(self.handle_run_stop)
        #self.run_btn.clicked.connect(self.run_module)
        #self.run_btn.setEnabled(False)
        #control_layout.addWidget(self.run_btn)

        self.run_btn = QPushButton("START")
        self.run_btn.setProperty("action", "run")
        self.run_btn.clicked.connect(self.handle_run_stop)
        self.run_btn.setEnabled(False)
        control_layout.addWidget(self.run_btn)



        
        self.back_btn = QPushButton("BACK")
        self.back_btn.clicked.connect(self.unload_module)
        self.back_btn.setEnabled(False)
        control_layout.addWidget(self.back_btn)

        clear_btn = QPushButton("Clear Console")
        clear_btn.clicked.connect(self.clear_console)
        control_layout.addWidget(clear_btn)

        layout.addLayout(control_layout)

        return main_widget

    def pty_spawn_bash(self):
        """Spawn full interactive bash shell"""
        self.pty_run_app('bash')

    def pty_run_app(self, app_name, filename=None):
        """Run interactive PTY application (nano, vim, htop, tmux, mc, bash, etc.)
        Versi lengkap dengan multiple fallback"""
        
        if not self.selected_session_id:
            self.append_output("[red]❌ Pilih session terlebih dahulu![/]")
            return

        session_id = self.selected_session_id
        
        # Bangun command
        if filename:
            target_cmd = f"{app_name} {filename}"
        else:
            target_cmd = app_name

        self.append_output(f"[yellow][*] Spawning {app_name} in PTY...[/yellow]")
        self.append_output(f"[dim]Command: {target_cmd}[/]")

        try:
            from modules.payloads.reverse.reverse_tcp import get_session, send_command_to_session

            session = get_session(session_id)
            success = False

            # METODE 1: Gunakan method dari session class (paling baik)
            if session and hasattr(session, 'spawn_pty_and_run'):
                try:
                    result = session.spawn_pty_and_run(target_cmd)
                    if result:
                        self.append_output(f"[green]{result}[/]")
                        success = True
                except Exception as e:
                    self.append_output(f"[yellow]spawn_pty_and_run error: {e}[/]")

            # METODE 2: Fallback PTY python -c
            if not success:
                self.append_output("[yellow][*] Menggunakan fallback PTY spawn...[/yellow]")
                
                pty_cmd = f'''python3 -c '
    import pty, os, subprocess, time
    os.environ["TERM"] = "xterm-256color"
    os.environ["LANG"] = "en_US.UTF-8"
    try:
        pty.spawn(["/bin/bash", "-c", "{target_cmd}"])
    except:
        try:
            pty.spawn(["/bin/sh", "-c", "{target_cmd}"])
        except:
            try:
                master, slave = os.openpty()
                proc = subprocess.Popen(["/bin/bash", "-c", "{target_cmd}"], 
                                    stdin=slave, stdout=slave, stderr=slave, 
                                    preexec_fn=os.setsid)
                os.close(slave)
                time.sleep(1)
            except:
                os.system("{target_cmd}")
    ' 2>/dev/null &'''

                success = send_command_to_session(session_id, pty_cmd)

            # METODE 3: Emergency fallback
            if not success:
                self.append_output("[yellow][*] Emergency fallback...[/yellow]")
                emergency = f"nohup {target_cmd} > /tmp/{app_name}.log 2>&1 &"
                send_command_to_session(session_id, emergency)

            if success:
                self.append_output(f"[bold green]✓ {app_name} berhasil dijalankan di PTY![/]")
                self.append_output("[cyan]→ Pindah ke tab **Sessions** untuk berinteraksi[/]")
                
                # Auto switch ke tab Sessions
                try:
                    idx = self.tabs.indexOf(self.session_tab)
                    if idx >= 0:
                        self.tabs.setCurrentIndex(idx)
                    self.session_cmd_input.setFocus()
                except:
                    pass
            else:
                self.append_output("[red]❌ Gagal spawn PTY[/red]")

        except Exception as e:
            self.append_output(f"[red]PTY Error: {e}[/]")
            # Ultimate fallback
            try:
                from modules.payloads.reverse.reverse_tcp import send_command_to_session
                fallback = f"python3 -c 'import pty; pty.spawn([\"/bin/bash\", \"-c\", \"{target_cmd}\"])' 2>/dev/null &"
                send_command_to_session(session_id, fallback)
            except:
                pass

    def open_file_with_nano(self):
        """Open file dialog dan edit dengan nano"""
        if not self.selected_session_id:
            self.append_output("[red]❌ Pilih session dulu[/red]")
            return
        
        file_path, ok = QInputDialog.getText(
            self, "Edit File with Nano", 
            "Enter file path to edit:", 
            QLineEdit.EchoMode.Normal,
            "api-green.txt"
        )
        
        if ok and file_path:
            self.pty_run_app('nano', file_path)

    def run_htop(self):
        """Run htop di session"""
        self.pty_run_app('htop')

    def run_tmux(self):
        """Run tmux di session"""
        self.pty_run_app('tmux')

    def run_mc(self):
        """Run midnight commander di session"""
        self.pty_run_app('mc')
    
    def interact_with_session(self, session_id):
        """Handle session interaction from network map click"""
        if not session_id:
            return
            
        # Jika session_id diawali dengan "session_", hilangkan prefix
        if session_id.startswith("session_"):
            actual_id = session_id
        else:
            actual_id = f"session_{session_id}" if not session_id.startswith("session_") else session_id
        
        # Cek apakah session ada
        if actual_id in self.sessions:
            # Set sebagai selected session
            self.selected_session_id = actual_id
            self.active_session_id = actual_id
            
            # Update UI
            self.update_sessions_ui()
            
            # Switch ke Sessions tab
            self.tabs.setCurrentIndex(4)  # Sessions tab index
            
            # Tampilkan pesan
            session = self.sessions[actual_id]
            os_icons = {'linux': '🐧', 'windows': '🪟', 'macos': '🍎', 'unknown': '💻'}
            icon = os_icons.get(session.get('os', 'unknown'), '💻')
            self.append_output(f"[green]✓ Interacting with {icon} Session {actual_id}[/]")
            self.append_output(f"[dim]IP: {session.get('ip', '?')}:{session.get('port', '?')}[/]")
            
            # Auto-focus command input
            self.session_cmd_input.setFocus()
        else:
            # Coba lagi dengan session_id langsung (tanpa prefix)
            if session_id in self.sessions:
                self.selected_session_id = session_id
                self.active_session_id = session_id
                self.update_sessions_ui()
                self.tabs.setCurrentIndex(4)
                self.append_output(f"[green]✓ Interacting with Session {session_id}[/]")
                self.session_cmd_input.setFocus()
            else:
                self.append_output(f"[red]❌ Session {session_id} not found[/]")
                # Debug: tampilkan semua session yang ada
                self.append_output(f"[yellow]Available sessions: {list(self.sessions.keys())}[/]")

    def create_right_sidebar(self):
        """Create right sidebar with session info and quick actions"""
        sidebar = QWidget()
        sidebar.setMaximumWidth(380)
        layout = QVBoxLayout(sidebar)

        # Session info
        session_group = QGroupBox("Session Info")
   
        session_layout = QVBoxLayout()

        self.session_info = QTextEdit()
        self.session_info.setMaximumHeight(480)
        self.session_info.setReadOnly(True)
        self.session_info.setObjectName("session_info")
        #self.session_info.setFont(QFont("Hack", 9))
        #self.session_info.setStyleSheet("color: #ffffff; background-color: #252525;")
        self.session_info.setHtml("")
        session_layout.addWidget(self.session_info)

        session_group.setLayout(session_layout)
        layout.addWidget(session_group)

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_group.setStyleSheet("""
            QGroupBox {
                font-weight: normal;
                color: #ffffff;
                border: 1px solid #404040;
                margin-top: 10px;
                padding-top: 10px;
                border-radius: 4px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px;
                background: #1e1e1e;
                color: #ffffff;
            }
        """)
        actions_layout = QVBoxLayout()

        quick_actions = [
            #("Show Modules", "show modules"),
            #("Show Options", "options"),
            #("Module Info", "info"),
            ("Scan Modules", "scan"),
            #("Show Banner", "show_banner")
        ]

        for action_name, command in quick_actions:
            btn = QPushButton(action_name)
            btn.clicked.connect(
                lambda checked, cmd=command: self.quick_command(cmd))
            actions_layout.addWidget(btn)

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        # Current module status
        status_group = QGroupBox("Current Module")
        status_layout = QVBoxLayout()

        self.current_module_label = QLabel("No module loaded")
        self.current_module_label.setStyleSheet(
            "color: #ff5555; font-weight: bold;")
        status_layout.addWidget(self.current_module_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Spacer
        layout.addStretch()

        return sidebar

    # === BROWSER METHODS - MODIFIED (HIDE/SHOW) ===
    def navigate_to_url(self):
        """Navigate to URL from url bar dengan error handling"""
        try:
            if not hasattr(self, 'url_bar') or not self.url_bar:
                return
                
            url = self.url_bar.text().strip()
            if not url:
                return
                
            # Jika sudah lengkap dengan protocol
            if url.startswith(('http://', 'https://', 'file://')):
                self.browser.setUrl(QUrl(url))
                return
                
            # Coba tambahkan https:// jika seperti domain
            if '.' in url and ' ' not in url:
                self.browser.setUrl(QUrl('https://' + url))
            else:
                # Jika tidak, anggap sebagai pencarian
                self.browser.setUrl(QUrl(f'https://www.google.com/search?q={url.replace(" ", "+")}'))
                
        except Exception as e:
            self.append_output(f"[red]Navigation error: {e}[/]")


    def create_left_sidebar(self):
        """Create left sidebar with modules and categories"""
        sidebar = QWidget()
        sidebar.setMaximumWidth(400)
        layout = QVBoxLayout(sidebar)

        # Search box
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search modules...")
        self.search_input.textChanged.connect(self.search_modules)
        search_layout.addWidget(self.search_input)

        search_btn = QPushButton("🔍")
        search_btn.setFixedWidth(40)
        search_btn.clicked.connect(self.perform_search)
        search_layout.addWidget(search_btn)
        layout.addLayout(search_layout)

        # Category buttons
        categories_layout = QHBoxLayout()
        categories = [
            ("All", "all"), ("Recon", "recon"), ("Strike", "strike"),
            ("Hold", "hold"), ("Ops", "ops"), ("Payloads", "payloads")
        ]

        for name, cat_type in categories:
            btn = QPushButton(name)
            btn.setProperty('category', cat_type)
            btn.clicked.connect(self.on_category_click)
            categories_layout.addWidget(btn)

        layout.addLayout(categories_layout)

        # Module list
        self.module_list = QListWidget()
        self.module_list.itemDoubleClicked.connect(self.load_selected_module)
        layout.addWidget(self.module_list)

        # Info Group dengan Browser Controls
        info_group = QGroupBox()
        info_layout = QVBoxLayout(info_group)

        # Tab widget untuk info dan browser
        self.info_browser_tabs = QTabWidget()

        # Tab 1: Module Info
        module_info_tab = QWidget()
        module_info_layout = QVBoxLayout(module_info_tab)
        module_info_layout.setContentsMargins(0, 0, 0, 0)

        self.module_info = QTextEdit()
        self.module_info.setReadOnly(True)

        self.module_info.setHtml("""
        <html>
        <head>
        <style>
            body { 
                background: #1e1e1e; 
                color: #d4d4d4; 
                font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
                padding: 20px;
                line-height: 1.6;
                font-size: 14px;
            }
            h2 { 
                color: #50fa7b; 
                font-size: 24px; 
                font-weight: 600;
                margin-bottom: 20px;
                border-bottom: 2px solid #50fa7b;
                padding-bottom: 10px;
            }
            h3 { 
                color: #8be9fd; 
                font-size: 18px; 
                font-weight: 600;
                margin: 25px 0 15px 0;
            }
            .card {
                background: #252525; 
                padding: 20px; 
                border-radius: 8px; 
                margin: 15px 0;
                border-left: 4px solid #6272a4;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);
            }
            .tip-card {
                background: #1e2e1e; 
                border-left: 4px solid #50fa7b;
            }
            ul {
                margin: 10px 0;
                padding-left: 20px;
            }
            li {
                margin: 8px 0;
                padding-left: 5px;
            }
            b {
                color: #ffb86c;
                font-weight: 600;
            }
            .category {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 12px;
                margin-right: 8px;
            }
            .recon { background: #1e3a5c; color: #8be9fd; }
            .strike { background: #5c1e1e; color: #ff5555; }
            .hold { background: #5c4c1e; color: #f1fa8c; }
            .ops { background: #1e5c2e; color: #50fa7b; }
            .payloads { background: #3e1e5c; color: #bd93f9; }
        </style>
        </head>
        <body>

        <h2>LazyFramework GUI</h2>

        <div class="card">
            <h3>🚀 Quick Start Guide</h3>
            <ul>
                <li><b>Browse Modules:</b> Select from the list on the left</li>
                <li><b>Load Module:</b> Double-click the desired module</li>
                <li><b>Configure:</b> Set parameters in the "Options" tab</li>
                <li><b>Execute:</b> Click "START" to run the module</li>
                <li><b>Results:</b> View output in the "Console" tab</li>
            </ul>
        </div>

        <div class="card">
            <h3>🎯 Module Categories</h3>
            <ul>
                <li><span class="category recon">RECON</span> Information gathering & enumeration</li>
                <li><span class="category strike">STRIKE</span> Vulnerability assessment & exploitation</li>
                <li><span class="category hold">HOLD</span> Post-exploitation & persistence</li>
                <li><span class="category ops">OPS</span> Operational security & anti-forensics</li>
                <li><span class="category payloads">PAYLOADS</span> Payload generation & delivery</li>
            </ul>
        </div>

        <div class="card tip-card">
            <h3>💡 Professional Tips</h3>
            <ul>
                <li>Use proxy settings for enhanced anonymity during scans</li>
                <li>Save session configurations for different projects</li>
                <li>Always verify module options before execution</li>
                <li>Monitor system resources during large-scale operations</li>
                <li>Utilize the integrated browser for manual testing</li>
            </ul>
        </div>

        <div class="card">
            <h3>🔧 Key Features</h3>
            <ul>
                <li><b>Real-time Output:</b> Live console output with syntax highlighting</li>
                <li><b>Integrated Browser:</b> Built-in web browser for manual testing</li>
                <li><b>Proxy Support:</b> Full proxy configuration with auto-rotation</li>
                <li><b>Session Management:</b> Save and restore your work sessions</li>
                <li><b>Module Library:</b> Extensive collection of security tools</li>
            </ul>
        </div>

        </body>
        </html>
        """)


        module_info_layout.addWidget(self.module_info)

        self.info_browser_tabs.addTab(module_info_tab, "Guides")

        # Tab 2: Browser - MODIFIED STRUCTURE
        browser_tab = QWidget()
        browser_tab_layout = QVBoxLayout(browser_tab)
        browser_tab_layout.setContentsMargins(0, 0, 0, 0)
        browser_tab_layout.setSpacing(5)

        # Browser control buttons
        browser_control_layout = QHBoxLayout()
        
        self.open_browser_btn = QPushButton("🌐 Open Browser")
        self.open_browser_btn.clicked.connect(self.open_browser_panel)
        self.open_browser_btn.setFixedSize(120, 30)
        self.open_browser_btn.setStyleSheet("""
            QPushButton {
                background: #1e1e1e;
                color: white;
                font-weight: bold;
                padding: 5px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #42a5f5;
            }
        """)

        self.close_browser_btn = QPushButton("❌ Hide Browser")
        self.close_browser_btn.clicked.connect(self.close_browser_panel)
        self.close_browser_btn.setFixedSize(120, 30)
        self.close_browser_btn.setStyleSheet("""
            QPushButton {
                background: #1e1e1e;
                color: white;
                font-weight: bold;
                padding: 5px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #ef5350;
            }
        """)
        self.close_browser_btn.setEnabled(False)

        browser_control_layout.addWidget(self.open_browser_btn)
        browser_control_layout.addWidget(self.close_browser_btn)
        browser_control_layout.addStretch()

        # Placeholder untuk browser (default state)
        self.browser_placeholder = QLabel("Browser is closed. Click 'Open Browser' to start.")
        self.browser_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browser_placeholder.setStyleSheet("color: #666; font-style: italic; padding: 40px;")
        self.browser_placeholder.setMinimumHeight(200)

        browser_tab_layout.addLayout(browser_control_layout)
        browser_tab_layout.addWidget(self.browser_placeholder)

        self.info_browser_tabs.addTab(browser_tab, "Browser")

        # Tambahkan tab widget ke layout utama info group
        info_layout.addWidget(self.info_browser_tabs)
        layout.addWidget(info_group)

        return sidebar
    
    
    
    def open_browser_panel(self):
        """Show the browser panel (jika sudah ada) atau buat baru - FIXED VERSION"""
        if hasattr(self, 'browser') and self.browser:
            # Browser sudah ada, cukup tampilkan
            self.browser_controls_widget.show()
            self.browser.show()
            self.browser_placeholder.hide()
            self.open_browser_btn.setEnabled(False)
            self.close_browser_btn.setEnabled(True)
            self.append_output("[dim]Browser panel shown[/]")
            self.update_browser_buttons()
            return
        
        try:
            # === FIX: HANYA BUAT BROWSER SEKALI ===
            
            # Create Browser Control Widgets TERLEBIH DAHULU
            self.browser_controls_widget = QWidget()
            control_layout = QHBoxLayout(self.browser_controls_widget)
            control_layout.setContentsMargins(0, 0, 0, 0)
            
            self.back_browser_btn = QPushButton("⬅")
            self.back_browser_btn.setFixedSize(30, 30)
            self.back_browser_btn.clicked.connect(self.browser_back)
            
            self.forward_browser_btn = QPushButton("⮕")
            self.forward_browser_btn.setFixedSize(30, 30)
            self.forward_browser_btn.clicked.connect(self.browser_forward)
            
            self.refresh_browser_btn = QPushButton("↻")
            self.refresh_browser_btn.setFixedSize(30, 30)
            self.refresh_browser_btn.clicked.connect(self.browser_refresh)

            self.url_bar = QLineEdit()
            self.url_bar.setPlaceholderText("Enter URL or search...")
            self.url_bar.returnPressed.connect(self.navigate_to_url)
            
            control_layout.addWidget(self.back_browser_btn)
            control_layout.addWidget(self.forward_browser_btn)
            control_layout.addWidget(self.refresh_browser_btn)
            control_layout.addWidget(self.url_bar)

            # === SEKARANG BUAT BROWSERNYA ===
            self.browser = QWebEngineView()
            self.browser.setZoomFactor(1.0)
            
            # === FIX: PyQt6 WebEngine Settings - CARA BARU ===
            settings = self.browser.settings()
            
            # Enable basic features
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
            
            # Disable heavy features untuk hindari GPU issues
            settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadIconsForPage, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)
            
            # Setup event handlers
            self.browser.urlChanged.connect(self.update_url_bar)
            self.browser.loadStarted.connect(self.on_load_started)
            self.browser.loadFinished.connect(self.on_load_finished)
            
            # Load default page
            self.browser.setUrl(QUrl("https://www.google.com"))

            # Add to the browser tab layout
            browser_tab = self.info_browser_tabs.widget(1)
            browser_tab_layout = browser_tab.layout()
            
            # Remove placeholder dan tambahkan browser components
            self.browser_placeholder.hide()
            browser_tab_layout.insertWidget(1, self.browser_controls_widget)
            browser_tab_layout.insertWidget(2, self.browser)

            self.browser_tab = browser_tab
            self.append_output("[bold green]🌐 Browser Panel Opened[/]")
            self.update_browser_buttons()
            
            # Apply proxy settings if enabled
            if self.proxy_enabled and self.current_proxy:
                self.set_proxy(self.current_proxy)
                
        except Exception as e:
            self.append_output(f"[red]❌ Browser initialization failed: {e}[/]")
            self.append_output("[yellow]⚠️ Browser functionality disabled[/]")
            
            # Clean up failed browser
            if hasattr(self, 'browser'):
                try:
                    self.browser.deleteLater()
                    del self.browser
                except:
                    pass
                
            # Reset UI state
            self.browser_placeholder.setText("Browser unavailable due to system limitations")
            self.browser_placeholder.setStyleSheet("color: #ff5555; font-style: italic; padding: 40px;")
            self.open_browser_btn.setEnabled(False)
            self.close_browser_btn.setEnabled(False)

    
    def set_browser_proxy(self, proxy_config):
        """Set proxy khusus untuk browser dengan error handling - FIXED"""
        if not hasattr(self, 'browser') or not self.browser:
            return
            
        try:
            from PyQt6.QtNetwork import QNetworkProxy
            
            proxy_type = proxy_config['type'].lower()
            server = proxy_config['server']
            port = proxy_config['port']

            if proxy_type.startswith("socks5"):
                qtype = QNetworkProxy.ProxyType.Socks5Proxy
            elif proxy_type.startswith("socks4"):
                qtype = QNetworkProxy.ProxyType.Socks4Proxy
            else:
                qtype = QNetworkProxy.ProxyType.HttpProxy

            qproxy = QNetworkProxy(qtype, server, port)
            QNetworkProxy.setApplicationProxy(qproxy)
            
            self.append_output(f"✓ Browser proxy applied: {server}:{port}")
            
        except Exception as e:
            self.append_output(f"✗ Browser proxy error: {e}")

    # Update method set_proxy yang sudah ada:
    def set_proxy(self, proxy_config):
        """Set proxy configuration - untuk requests + browser (PyQt6 safe)"""
        try:
            self.current_proxy = proxy_config
            self.proxy_enabled = True
            self.apply_proxy_to_requests()

            # Set browser proxy
            self.set_browser_proxy(proxy_config)

            # === Logging / konfirmasi ===
            proxy_info = f"{proxy_config['server']}:{proxy_config['port']}"
            if proxy_config['type'] != 'http':
                proxy_info += f" [{proxy_config['type'].upper()}]"
            self.append_output(f"✓ Proxy configured: {proxy_info}")
            self.append_output(f"Note: Proxy applied to requests + browser")

            self.update_proxy_status()

        except Exception as e:
            self.append_output(f"✗ Proxy error: {e}")

    def close_browser_panel(self):
        """Hide the browser panel instead of closing it dengan error handling"""
        try:
            if not hasattr(self, 'browser') or not self.browser:
                self.append_output("[dim]Browser is already hidden[/]")
                return

            # Hentikan loading
            self.browser.stop()
            
            # Sembunyikan browser dan controls
            self.browser.hide()
            if hasattr(self, 'browser_controls_widget'):
                self.browser_controls_widget.hide()
            
            # Tampilkan placeholder
            self.browser_placeholder.show()
            
            self.append_output("[dim]Browser panel hidden[/]")
            self.update_browser_buttons()
            
        except Exception as e:
            self.append_output(f"[red]Error hiding browser: {e}[/]")
            # Force cleanup
            try:
                self.browser_placeholder.show()
                self.update_browser_buttons()
            except:
                pass

    def update_browser_buttons(self):
        """Update browser button states based on visibility dengan error handling"""
        try:
            if hasattr(self, 'browser') and self.browser:
                is_visible = self.browser.isVisible()
                self.open_browser_btn.setEnabled(not is_visible)
                self.close_browser_btn.setEnabled(is_visible)
                
                # Update teks tombol berdasarkan state
                if is_visible:
                    self.close_browser_btn.setText("❌ Hide Browser")
                else:
                    self.close_browser_btn.setText("❌ Close Browser")
            else:
                self.open_browser_btn.setEnabled(True)
                self.close_browser_btn.setEnabled(False)
                self.close_browser_btn.setText("❌ Hide Browser")
        except Exception as e:
            # Fallback safe state
            self.open_browser_btn.setEnabled(True)
            self.close_browser_btn.setEnabled(False)

            
    def browser_back(self):
        """Browser back button dengan error handling"""
        try:
            if hasattr(self, 'browser') and self.browser:
                self.browser.back()
        except Exception as e:
            self.append_output(f"[red]Browser back error: {e}[/]")

    def browser_forward(self):
        """Browser forward button dengan error handling"""
        try:
            if hasattr(self, 'browser') and self.browser:
                self.browser.forward()
        except Exception as e:
            self.append_output(f"[red]Browser forward error: {e}[/]")

    def browser_refresh(self):
        """Browser refresh button dengan error handling"""
        try:
            if hasattr(self, 'browser') and self.browser:
                self.browser.reload()
        except Exception as e:
            self.append_output(f"[red]Browser refresh error: {e}[/]")


    def update_url_bar(self, url):
        """Update url bar when page changes dengan error handling"""
        try:
            if hasattr(self, 'url_bar') and self.url_bar:
                self.url_bar.setText(url.toString())
        except Exception as e:
            pass  # Silent fail untuk UI updates

    def on_load_started(self):
        """Handle page load start dengan error handling"""
        try:
            if hasattr(self, 'url_bar') and self.url_bar:
                self.url_bar.setPlaceholderText("Loading...")
        except Exception as e:
            pass

    def on_load_finished(self, ok):
        """Handle page load finish dengan error handling"""
        try:
            if hasattr(self, 'url_bar') and self.url_bar:
                if ok:
                    self.url_bar.setPlaceholderText("Enter URL or search...")
                else:
                    self.url_bar.setPlaceholderText("Failed to load page")
        except Exception as e:
            pass

    # === PROXY METHODS ===
    def show_proxy_settings(self):
        """Show proxy settings dialog"""
        dialog = ProxySettingsDialog(self)
        dialog.exec()

    def set_proxy(self, proxy_config):
        """Set proxy configuration - untuk requests + browser (PyQt6 safe)"""
        try:
            self.current_proxy = proxy_config
            self.proxy_enabled = True
            self.apply_proxy_to_requests()

            # === Browser Proxy (QWebEngineView) ===
            from PyQt6.QtNetwork import QNetworkProxy

            proxy_type = proxy_config['type'].lower()
            server = proxy_config['server']
            port = proxy_config['port']

            if proxy_type.startswith("socks5"):
                qtype = QNetworkProxy.ProxyType.Socks5Proxy
            elif proxy_type.startswith("socks4"):
                qtype = QNetworkProxy.ProxyType.Socks4Proxy
            else:
                qtype = QNetworkProxy.ProxyType.HttpProxy

            qproxy = QNetworkProxy(qtype, server, port)
            QNetworkProxy.setApplicationProxy(qproxy)

            self.append_output("✓ Browser proxy applied via QNetworkProxy")

            # === Logging / konfirmasi ===
            proxy_info = f"{server}:{port}"
            if proxy_type != 'http':
                proxy_info += f" [{proxy_type.upper()}]"
            self.append_output(f"✓ Proxy configured: {proxy_info}")
            self.append_output(f"Note: Proxy applied to requests + browser")

            self.update_proxy_status()

        except Exception as e:
            self.append_output(f"✗ Proxy error: {e}")

    def enable_proxy(self):
        """Enable proxy - otomatis ganti IP Tor"""
        if not self.current_proxy:
            self.append_output("No proxy configured. Please set proxy first.")
            self.show_proxy_settings()
            return

        self.proxy_enabled = True
        self.apply_proxy_to_requests()
        self.append_output("✓ Proxy enabled for system/requests")
        self.append_output("ℹ Browser will use system proxy settings")

        # === Tambahan: jika proxy adalah Tor (127.0.0.1:9050), ganti IP otomatis ===
        try:
            if self.current_proxy['server'] == '127.0.0.1' and str(self.current_proxy['port']) == '9050':
                from stem import Signal
                from stem.control import Controller
                with Controller.from_port(port=9051) as c:
                    c.authenticate()
                    c.signal(Signal.NEWNYM)
                self.append_output("↻ Tor circuit renewed automatically (new IP)")
        except Exception as e:
            self.append_output(f"✗ Could not renew Tor IP automatically: {e}")

        self.update_proxy_status()

    def disable_proxy(self):
        """Disable proxy"""
        self.proxy_enabled = False
        self.apply_proxy_to_requests()
        self.append_output("Proxy disabled")
        self.update_proxy_status()

    def apply_proxy_to_requests(self):
        """Apply proxy settings to requests library"""
        if not self.current_proxy or not self.proxy_enabled:
            # Clear proxy dari environment
            for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
                if var in os.environ:
                    del os.environ[var]
            return

        try:
            proxy_type = self.current_proxy['type']
            server = self.current_proxy['server']
            port = self.current_proxy['port']

            # Build proxy URL
            proxy_url = f"{proxy_type}://{server}:{port}"

            # Set environment variables untuk requests
            os.environ['HTTP_PROXY'] = proxy_url
            os.environ['HTTPS_PROXY'] = proxy_url
            os.environ['http_proxy'] = proxy_url
            os.environ['https_proxy'] = proxy_url

            self.append_output(f"System proxy set: {proxy_url}")
            
        except Exception as e:
            self.append_output(f"System proxy error: {e}")

    def test_proxy_connection(self, proxy_config=None):
        """Test proxy connection"""
        config = proxy_config or self.current_proxy
        
        if not config:
            self.append_output("No proxy configured to test")
            return

        self.append_output(f"Testing proxy {config['server']}:{config['port']}...")

        import socket
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Auto-detect Tor Browser port
        try:
            s = socket.socket()
            s.settimeout(1)
            s.connect(("127.0.0.1", config["port"]))
        except Exception:
            try:
                s = socket.socket()
                s.settimeout(1)
                s.connect(("127.0.0.1", 9150))
                config["port"] = 9150
                self.append_output("Detected Tor Browser (using port 9150)")
            except Exception:
                pass
        finally:
            s.close()

        proxy_scheme = config["type"]
        if proxy_scheme.startswith("socks5"):
            proxy_scheme = "socks5h"

        proxies = {
            "http": f"{proxy_scheme}://{config['server']}:{config['port']}",
            "https": f"{proxy_scheme}://{config['server']}:{config['port']}"
        }

        test_url = "http://api.ipify.org?format=json"
        try:
            response = requests.get(test_url, proxies=proxies, timeout=30, verify=False)
            if response.status_code == 200:
                ip_info = response.json()
                self.append_output(f"✓ Proxy working! Your IP: {ip_info.get('ip', 'Unknown')}")
                return True
            else:
                self.append_output(f"✗ Proxy test failed (status {response.status_code})")
                return False

        except requests.exceptions.ConnectTimeout:
            self.append_output("✗ Proxy test failed: connection timed out (Tor may be slow)")
            return False
        except requests.exceptions.ProxyError as e:
            self.append_output(f"✗ Proxy error: {e}")
            return False
        except Exception as e:
            self.append_output(f"✗ Proxy test failed: {e}")
            return False

    # Proxy Auto
    def start_tor_auto_rotate(self):
        """Rotasi IP Tor otomatis setiap 5 menit"""
        from PyQt6.QtCore import QTimer

        self.tor_timer = QTimer(self)
        self.tor_timer.setInterval(300000)  # 5 menit = 300000 ms
        self.tor_timer.timeout.connect(self.rotate_tor_ip)
        self.tor_timer.start()
        self.append_output("Auto Tor IP rotation enabled (every 5 minutes)")

    def rotate_tor_ip(self):
        from stem import Signal
        from stem.control import Controller
        import requests
        
        # Ambil IP lama
        old_ip = self.get_current_ip()

        for port in [9051, 9151]:
            try:
                with Controller.from_port(port=port) as c:
                    c.authenticate()
                    c.signal(Signal.NEWNYM)

                    # Delay kecil agar circuit benar-benar berubah
                    QTimer.singleShot(2500, lambda p=port, old=old_ip: self.check_new_ip(p, old))
                    return
            except Exception:
                continue

        self.append_output("[red]✗ Tor ControlPort 9051/9151 not found[/]")

    def start_global_proxy_rotate(self):
        """Timer global: bisa rotate Tor atau File Proxy"""
        self.proxy_timer = QTimer()
        self.proxy_timer.timeout.connect(self.auto_rotate_proxy)
        self.proxy_timer.start(5 * 60 * 1000)   # 5 menit

    def detect_tor_socks(self):
        import socket

        for port in [9050, 9150]:
            s = socket.socket()
            try:
                s.settimeout(0.5)
                s.connect(("127.0.0.1", port))
                s.close()
                return port
            except:
                pass
        return None

    def get_current_ip(self):
        import requests

        socks_port = self.detect_tor_socks()
        if socks_port is None:
            return "Unknown"

        try:
            s = requests.get(
                "https://check.torproject.org/api/ip",
                proxies={
                    "http": f"socks5h://127.0.0.1:{socks_port}",
                    "https": f"socks5h://127.0.0.1:{socks_port}",
                },
                timeout=10
            ).json()

            return s.get("IP", "Unknown")

        except Exception:
            return "Unknown"

    def check_new_ip(self, port, old_ip):
        socks_port = self.detect_tor_socks()
        new_ip = self.get_current_ip()

        self.append_output(
            f"[cyan]SOCKS Port Used: {socks_port}[/]\n"
            f"[cyan]Old IP: {old_ip}[/]\n"
            f"[green]New IP: {new_ip}[/]\n"
            f"[green]✓ Tor IP rotated via port {port}[/]"
        )
        
    def update_proxy_status(self):
        """Update proxy status display"""
        self.update_session_info()
   
    def append_output(self, text):
        """Append output ke console GUI dengan:
        - Rich ANSI → HTML dengan Matrix theme
        - Deteksi TABEL Unicode (box-drawing) 
        - Session Management otomatis
        - Auto-switch tab
        - Font monospace untuk tabel
        - Matrix color coding
        """
        if not text or not text.strip():
            return

        # Safety check - ensure console_output exists
        if not hasattr(self, 'console_output') or self.console_output is None:
            return

        

        raw_text = text  # Simpan raw untuk parsing session

        
        # === 1. DETEKSI TABEL (box-drawing characters) ===
        table_chars = ['─', '│', '┌', '┐', '└', '┘', '┬', '┴', '├', '┤', '┼']
        is_table = any(char in text for char in table_chars)
        
        # === 2. PROSES OUTPUT DENGAN MATRIX THEME ===
        if is_table:
            # Format sebagai tabel monospace dengan style Matrix
            html_output = self.format_unicode_table(text)
            self.console_output.insertHtml(html_output)
        
        else:
            # Output biasa dengan rich formatting + Matrix color coding
            html_output = self.rich_to_html_with_matrix(text)
            self.console_output.insertHtml(html_output + "<br>")

        # Pindahkan kursor ke akhir
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)

        # === 3. DETEKSI SESSION BARU ===
        session_patterns = [
            r"Session (.+?) opened \((.+?) -> (.+?)\)",  # Pattern utama
            r"\[\+\]\s+Session (.+?) opened",
            r"Session (\d+) opened \(([\d.]+):(\d+) -> ([\d.]+):(\d+)\)",
            r"\[\+\]\s+Meterpreter session (\d+) opened",
            r"Reverse shell spawned on ([\d.]+):(\d+)",
            r"Shell caught from ([\d.]+) on port (\d+)",
        ]

        detected = False
        for pattern in session_patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                self.create_new_session(match, raw_text)
                detected = True
                break

        # === 4. UPDATE SESSION OUTPUT (jika aktif) ===
        if not detected and self.active_session_id and self.active_session_id in self.sessions:
            sess = self.sessions[self.active_session_id]
            sess['output'] += raw_text + "\n"
            if self.tabs.currentIndex() == 3:  # Tab Sessions
                self.session_output.setPlainText(sess['output'])
                self.session_output.moveCursor(QTextCursor.MoveOperation.End)

        # === 5. AUTO-SWITCH ke Sessions jika session baru ===
        if detected and self.tabs.currentIndex() != 3:
            self.tabs.setCurrentIndex(3)
            # Gunakan Matrix-style message untuk session detection
            self.append_output("[matrix-cyan]🔄 MATRIX SESSION DETECTED! Switching to control panel...[/]")


    

    def rich_to_html_with_matrix(self, text):
        """Convert rich text to HTML dengan Matrix theme color coding"""
        import re

        

        # Matrix Color Mapping - lebih intens dan glowing
        matrix_color_map = {
            # Primary Matrix colors
            'black': '#000000', 
            'red': '#ff5555', 
            'green': '#00ff00',      # Hijau Matrix yang iconic
            'yellow': '#ffff00', 
            'blue': '#5555ff', 
            'magenta': '#ff00ff', 
            'cyan': '#00ffff', 
            'white': '#ffffff', 
            'orange': '#ffaa00',
            
            # Matrix-specific colors dengan glow effect
            'bright_green': '#88ff88', 
            'bright_cyan': '#88ffff',
            'dim': '#008800',
            'matrix_green': '#00ff00',
            'matrix_cyan': '#00ffff',
            'hacker_green': '#00ff00',
            'neon_blue': '#5555ff',
            
            # Status colors dengan glow
            'success': '#00ff00',
            'error': '#ff5555', 
            'warning': '#ffff00',
            'info': '#00ffff',
            'debug': '#ff00ff',
            'session': '#ffaa00'
        }

        # ANSI to Matrix Tag Mapping
        ansi_to_matrix_tag = {
            '0': '[/]',        # Reset
            '1': '[bold]',     # Bold
            '2': '[dim]',      # Dim
            '4': '[underline]',# Underline
            
            # Standard colors
            '30': '[black]', '31': '[red]', '32': '[green]', '33': '[yellow]',
            '34': '[blue]', '35': '[magenta]', '36': '[cyan]', '37': '[white]',
            
            # Bright colors  
            '90': '[black]', '91': '[red]', '92': '[bright_green]', '93': '[yellow]',
            '94': '[blue]', '95': '[magenta]', '96': '[bright_cyan]', '97': '[white]',
            
            # Background colors (simplified)
            '41': '[on_red]', '42': '[on_green]', '43': '[on_yellow]', '44': '[on_blue]',
            '45': '[on_magenta]', '46': '[on_cyan]', '47': '[on_white]',
        }

        # Auto-detect content type untuk Matrix styling
        content_type = self.detect_content_type(text)
        
        # Replace ANSI codes dengan Matrix tags
        def replace_ansi(match):
            code = match.group(1)
            codes = code.split(';')
            html = ""
            for c in codes:
                if c in ansi_to_matrix_tag:
                    html += ansi_to_matrix_tag[c]
            return html

        # Process ANSI sequences
        text = re.sub(r'\x1b\[([0-9;]*)([mG])', replace_ansi, text)

        # Process Matrix-style tags dengan glow effects
        output = ""
        tag_stack = []
        i = 0
        
        while i < len(text):
            if text[i] == "[" and i + 1 < len(text):
                end = text.find("]", i)
                if end != -1:
                    tag = text[i + 1:end]

                    # Closing tag
                    if tag == "/":
                        if tag_stack:
                            last_tag = tag_stack.pop()
                            # Tambahkan glow effect untuk tags tertentu
                            if last_tag in ['green', 'bright_green', 'matrix_green', 'success']:
                                output += "</span>"
                            elif last_tag in ['cyan', 'bright_cyan', 'matrix_cyan', 'info']:
                                output += "</span>"
                            elif last_tag in ['red', 'error']:
                                output += "</span>"
                            elif last_tag in ['yellow', 'warning']:
                                output += "</span>"
                            else:
                                output += "</span>"
                        i = end + 1
                        continue
                    
                    # Opening tags dengan Matrix styling
                    if tag in matrix_color_map:
                        tag_stack.append(tag)
                        color = matrix_color_map[tag]
                        
                        # Special glow effects untuk Matrix colors
                        if tag in ['green', 'bright_green', 'matrix_green', 'success']:
                            output += f'<span style="color: {color}; text-shadow: 0 0 8px {color}, 0 0 12px {color}; font-weight: bold;">'
                        elif tag in ['cyan', 'bright_cyan', 'matrix_cyan', 'info']:
                            output += f'<span style="color: {color}; text-shadow: 0 0 6px {color}, 0 0 10px {color}; font-weight: bold;">'
                        elif tag in ['red', 'error']:
                            output += f'<span style="color: {color}; text-shadow: 0 0 6px {color}, 0 0 10px {color}; font-weight: bold;">'
                        elif tag in ['yellow', 'warning', 'session']:
                            output += f'<span style="color: {color}; text-shadow: 0 0 6px {color}, 0 0 10px {color}; font-weight: bold;">'
                        else:
                            output += f'<span style="color: {color}; text-shadow: 0 0 3px {color};">'
                        
                        i = end + 1
                        continue
                    
                    # Bold tag
                    elif tag.lower() in ["bold", "b"]:
                        tag_stack.append("bold")
                        output += '<span style="font-weight: bold; color: #00ff00; text-shadow: 0 0 5px #00ff00;">'
                        i = end + 1
                        continue

                    # Underline tag  
                    elif tag.lower() in ["underline", "u"]:
                        tag_stack.append("underline")
                        output += '<span style="text-decoration: underline; color: #00ffff;">'
                        i = end + 1
                        continue

                # Special Matrix patterns
                if text[i:i+7] == "[matrix]":
                    output += '<span style="color: #00ff00; text-shadow: 0 0 10px #00ff00, 0 0 20px #00ff00; font-weight: bold; font-family: \"Courier New\", monospace;">'
                    i += 7
                    continue
                elif text[i:i+6] == "[hack]":
                    output += '<span style="color: #00ff00; text-shadow: 0 0 8px #00ff00; font-weight: bold; background: rgba(0,255,0,0.1); padding: 2px 4px; border-left: 2px solid #00ff00;">'
                    i += 6
                    continue

            # Karakter biasa dengan content-based styling
            char = text[i]
            if char == '\n':
                output += "<br>"
            else:
                # Apply content-based styling
                styled_char = self.apply_content_styling(char, content_type, text, i)
                output += styled_char
            i += 1

        # Close any remaining tags
        while tag_stack:
            tag = tag_stack.pop()
            output += "</span>"

        return output

    def detect_content_type(self, text):
        """Detect content type untuk apply appropriate Matrix styling"""
        text_lower = text.lower()
        
        if any(pattern in text_lower for pattern in ['session', 'meterpreter', 'shell', 'reverse']):
            return 'session'
        elif any(pattern in text_lower for pattern in ['error', 'failed', '✗', '[-]']):
            return 'error' 
        elif any(pattern in text_lower for pattern in ['success', '✓', '[+]', 'loaded']):
            return 'success'
        elif any(pattern in text_lower for pattern in ['warning', '⚠', '[!]']):
            return 'warning'
        elif any(pattern in text_lower for pattern in ['info', '[*]', 'scanning', 'detected']):
            return 'info'
        elif any(pattern in text_lower for pattern in ['matrix', 'hack', 'cyber']):
            return 'matrix'
        elif any(pattern in text_lower for pattern in ['command', '>', '$']):
            return 'command'
        else:
            return 'normal'

    def apply_content_styling(self, char, content_type, full_text, position):
        """Apply Matrix styling berdasarkan content type"""
        base_style = "color: #00ff00;"
        
        if content_type == 'session':
            return f'<span style="{base_style} color: #ffaa00; text-shadow: 0 0 6px #ffaa00; font-weight: bold;">{char}</span>'
        elif content_type == 'error':
            return f'<span style="{base_style} color: #ff5555; text-shadow: 0 0 6px #ff5555; font-weight: bold;">{char}</span>'
        elif content_type == 'success':
            return f'<span style="{base_style} color: #00ff00; text-shadow: 0 0 8px #00ff00, 0 0 12px #00ff00; font-weight: bold;">{char}</span>'
        elif content_type == 'warning':
            return f'<span style="{base_style} color: #ffff00; text-shadow: 0 0 6px #ffff00; font-weight: bold;">{char}</span>'
        elif content_type == 'info':
            return f'<span style="{base_style} color: #00ffff; text-shadow: 0 0 6px #00ffff; font-weight: bold;">{char}</span>'
        elif content_type == 'matrix':
            return f'<span style="{base_style} color: #00ff00; text-shadow: 0 0 10px #00ff00, 0 0 20px #00ff00; font-weight: bold; font-family: \"Courier New\", monospace;">{char}</span>'
        elif content_type == 'command':
            return f'<span style="{base_style} color: #ffff00; text-shadow: 0 0 5px #ffff00; font-weight: bold;">{char}</span>'
        else:
            return f'<span style="{base_style}">{char}</span>'

    def format_unicode_table(self, text):
        """Format unicode table dengan Matrix theme"""
        # Escape HTML
        safe = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

        lines = safe.split("\n")
        max_len = max(len(line) for line in lines)
        normalized = []
        
        for line in lines:
            if len(line) < max_len:
                line = line + (" " * (max_len - len(line)))
            elif len(line) > max_len:
                line = line[:max_len]
            normalized.append(line)

        # Style dengan Matrix theme
        styled_lines = [self.style_matrix_table_line(line) for line in normalized]
        styled_text = "<br>".join(styled_lines)

        html = f"""
        <div style="
            width: max-content;
            max-width: 100%;
            overflow-x: auto;
            padding: 10px;
            margin: 5px 0;
            background: rgba(0, 255, 0, 0.05);
            border: 1px solid #008800;
            border-radius: 3px;
            box-shadow: 0 0 10px rgba(0, 255, 0, 0.2);
        ">
            <pre style="
                font-family: 'Courier New', monospace;
                font-size: 11px;
                white-space: pre;
                margin: 0;
                color: #00ff00;
                text-shadow: 0 0 3px rgba(0, 255, 0, 0.5);
            ">{styled_text}</pre>
        </div>
        """
        return html

    def style_matrix_table_line(self, line):
        """Style table line dengan Matrix theme"""
        border_chars = ['─', '│', '┌', '┐', '└', '┘', '┬', '┴', '├', '┤', '┼']
        
        # Jika hanya border characters
        if all(char in border_chars + [' '] for char in line):
            return f'<span style="color: #00ff00; text-shadow: 0 0 5px #00ff00;">{line}</span>'
        
        return self.colorize_matrix_table_content(line)

    def colorize_matrix_table_content(self, line):
        """Colorize table content dengan Matrix theme"""
        result = []
        i = 0
        
        while i < len(line):
            char = line[i]
            
            # Border characters - glow green
            if char in ['─', '│', '┌', '┐', '└', '┘', '┬', '┴', '├', '┤', '┼']:
                result.append(f'<span style="color: #00ff00; text-shadow: 0 0 5px #00ff00;">{char}</span>')
            else:
                # Content dengan contextual coloring
                context_color = self.get_matrix_content_color(line, i)
                result.append(f'<span style="color: {context_color}; text-shadow: 0 0 3px {context_color};">{char}</span>')
            
            i += 1
        
        return ''.join(result)

    def get_matrix_content_color(self, line, position):
        """Tentukan warna content berdasarkan konteks untuk Matrix theme"""
        # Cari kata di sekitar posisi saat ini
        words = line.split()
        current_word = ""
        
        # Cari kata yang sedang diproses
        start_pos = position
        while start_pos > 0 and line[start_pos-1] not in [' ', '│', '┌', '┐', '└', '┘', '├', '┤']:
            start_pos -= 1
        
        end_pos = position
        while end_pos < len(line)-1 and line[end_pos+1] not in [' ', '│', '┌', '┐', '└', '┘', '├', '┤']:
            end_pos += 1
        
        current_word = line[start_pos:end_pos+1].lower().strip()
        
        # Matrix-themed coloring
        if any(keyword in current_word for keyword in ['success', 'active', 'open', 'running', 'enabled', 'true', 'yes']):
            return '#00ff00'  # Hijau Matrix untuk status baik
        elif any(keyword in current_word for keyword in ['failed', 'error', 'closed', 'stopped', 'disabled', 'false', 'no']):
            return '#ff5555'  # Merah untuk status buruk
        elif any(keyword in current_word for keyword in ['warning', 'pending', 'unknown', 'filtered']):
            return '#ffff00'  # Kuning untuk status peringatan
        elif any(keyword in current_word for keyword in ['name', 'host', 'port', 'status', 'type', 'id', 'service']):
            return "#00ffff"  # Cyan untuk header
        elif current_word.replace('.', '').replace(':', '').isdigit():
            return '#ffaa00'  # Orange untuk angka/IP
        else:
            return '#88ff88'  # Hijau terang default untuk text biasa

    # === THREAD-SAFE SESSION MANAGEMENT ===
    def create_new_session(self, match, raw_text):
        """Create new session from detected pattern - DENGAN DETEKSI OS"""
        try:
            print(f"DEBUG: Session match groups: {match.groups()}")
            
            if len(match.groups()) >= 3:
                sess_id = match.group(1)
                source = match.group(2)
                destination = match.group(3)
                
                if ':' in source:
                    src_ip, src_port = source.split(':')
                else:
                    src_ip, src_port = "unknown", "unknown"
                    
                if ':' in destination:
                    dst_ip, dst_port = destination.split(':')
                else:
                    dst_ip, dst_port = "unknown", "unknown"
            else:
                sess_id = f"session_{len(self.sessions) + 1}"
                src_ip = "unknown"
                src_port = "unknown"
                dst_ip = self.framework.session.get('LHOST', '0.0.0.0')
                dst_port = self.framework.session.get('LPORT', 4444)

            # Coba deteksi OS dari raw_text
            detected_os = 'unknown'
            text_lower = raw_text.lower()
            
            if any(keyword in text_lower for keyword in ['linux', 'unix', 'ubuntu', 'debian', 'centos']):
                detected_os = 'linux'
            elif any(keyword in text_lower for keyword in ['windows', 'microsoft', 'cmd.exe', 'powershell']):
                detected_os = 'windows' 
            elif any(keyword in text_lower for keyword in ['macos', 'darwin', 'apple']):
                detected_os = 'macos'

            # Buat session data dengan info OS
            session_data = {
                'id': sess_id,
                'type': 'reverse_tcp',
                'lhost': dst_ip,
                'lport': dst_port,
                'rhost': src_ip,
                'rport': src_port,
                'ip': src_ip,
                'port': src_port,
                'os': detected_os,  # ← SIMPAN INFO OS
                'output': f"[*] Session {sess_id} created\nType: reverse_tcp\nOS: {detected_os}\nSource: {src_ip}:{src_port}\nDestination: {dst_ip}:{dst_port}\n{raw_text}\n\n",
                'handler': None,
                'status': 'alive',
                'created': time.strftime("%H:%M:%S"),
                'socket': None
            }

            # Simpan session dengan lock
            with self.session_lock:
                self.sessions[sess_id] = session_data
            
            # Auto-select new session
            self.selected_session_id = sess_id
            self.active_session_id = sess_id
            
            # Update UI
            self.update_sessions_ui()
            
            # Auto-switch ke sessions tab
            self.tabs.setCurrentIndex(3)
            
            # Output konfirmasi dengan ikon OS
            os_icons = {'linux': '🐧', 'windows': '🪟', 'macos': '🍎', 'unknown': '💻'}
            icon = os_icons.get(detected_os, '💻')
            os_names = {'linux': 'Linux', 'windows': 'Windows', 'macos': 'macOS', 'unknown': 'Unknown'}
            os_name = os_names.get(detected_os, 'Unknown')
            
            self.append_output(f"[bold green][+] {icon} {os_name} Session {sess_id} Auto-detected![/]")
            self.append_output(f"[green]✓ Auto-selected new session[/]")
            
        except Exception as e:
            self.append_output(f"[red]Session creation error: {e}[/]")

    def update_sessions_ui(self):
        """Update sessions UI dengan ikon OS"""
        try:
            # Clear current list
            self.session_list.clear()
            
            # OS icons mapping
            os_icons = {
                'linux': '🐧',      # Penguin untuk Linux
                'windows': '🪟',    # Window untuk Windows  
                'macos': '🍎',      # Apple untuk macOS
                'unknown': '💻'     # Computer untuk unknown
            }
            
            # Add all sessions dengan ikon OS
            for sess_id, sess in self.sessions.items():
                os_type = sess.get('os', 'unknown')
                icon = os_icons.get(os_type, '💻')
                
                item_text = f"{icon} {sess_id} | {sess.get('ip', '?.?.?.?')}:{sess.get('port', '?')} | {sess.get('type', 'unknown')}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, sess_id)
                
                # Color coding based on session type + OS
                color_map = {
                    "reverse_tcp": "#50fa7b",  # Hijau terang
                    "meterpreter": "#ff79c6",  # Pink
                    "bash": "#8be9fd",         # Cyan
                    "python": "#ffb86c",       # Orange
                    "powershell": "#bd93f9",   # Ungu
                    "shell": "#f1fa8c"         # Kuning
                }
                
                # Tambahkan warna berdasarkan OS juga
                os_color_map = {
                    'linux': '#50fa7b',    # Hijau untuk Linux
                    'windows': '#ff79c6',  # Pink untuk Windows  
                    'macos': '#ffb86c',    # Orange untuk macOS
                    'unknown': '#6272a4'   # Biru untuk unknown
                }
                
                base_color = color_map.get(sess.get('type', ''), "#ffffff")
                os_color = os_color_map.get(os_type, '#6272a4')
                
                # Combine colors atau pilih salah satu
                item.setForeground(QColor(os_color))  # Gunakan warna OS sebagai primary
                
                self.session_list.addItem(item)
                
            # Auto-select first session if none selected
            if self.session_list.count() > 0 and not self.selected_session_id:
                self.session_list.setCurrentRow(0)
                self.on_session_selected(self.session_list.currentItem())
                
            # Jika ada session yang aktif, maintain selection
            elif self.selected_session_id and self.selected_session_id in self.sessions:
                for i in range(self.session_list.count()):
                    item = self.session_list.item(i)
                    if item and item.data(Qt.ItemDataRole.UserRole) == self.selected_session_id:
                        self.session_list.setCurrentItem(item)
                        self.on_session_selected(item)
                        break
                    
        except Exception as e:
            self.append_output(f"[red]Session UI Error: {e}[/]")


    def sync_sessions_from_reverse_tcp(self):
        """Sync GUI sessions from reverse_tcp module - FIXED VERSION"""
        try:
            # Akses SESSIONS dari instance module yang benar-benar running
            if (self.framework.loaded_module and 
                hasattr(self.framework.loaded_module, 'module') and
                hasattr(self.framework.loaded_module.module, 'SESSIONS')):
                _active_mod = self.framework.loaded_module.module
                SESSIONS = _active_mod.SESSIONS
                SESSIONS_LOCK = _active_mod.SESSIONS_LOCK
            else:
                SESSIONS = _rtcp_mod.SESSIONS
                SESSIONS_LOCK = _rtcp_mod.SESSIONS_LOCK
            
            self.append_output("[yellow]Syncing sessions from reverse_tcp...[/]")
            
            with SESSIONS_LOCK:
                self.append_output(f"[dim]ReverseTCP has {len(SESSIONS)} sessions[/]")
                
                for sess_id, rev_sess in SESSIONS.items():
                    # Get socket from reverse_tcp session object
                    sock = None
                    if hasattr(rev_sess, 'socket'):
                        sock = rev_sess.socket
                    elif isinstance(rev_sess, dict) and 'socket' in rev_sess:
                        sock = rev_sess['socket']
                    
                    if sess_id not in self.sessions:
                        # Create new GUI session
                        self.sessions[sess_id] = {
                            'id': sess_id,
                            'type': getattr(rev_sess, 'type', 'reverse_tcp'),
                            'ip': getattr(rev_sess, 'rhost', 'unknown'),
                            'port': getattr(rev_sess, 'rport', 'unknown'),
                            'lhost': getattr(rev_sess, 'lhost', 'unknown'),
                            'lport': getattr(rev_sess, 'lport', 'unknown'),
                            'os': getattr(rev_sess, 'os', 'unknown'),
                            'output': f"[*] Session {sess_id} synced from reverse_tcp\n",
                            'status': getattr(rev_sess, 'status', 'alive'),
                            'created': getattr(rev_sess, 'created', time.strftime("%H:%M:%S")),
                            'socket': sock,
                            'handler': rev_sess
                        }
                        self.append_output(f"[green]✓ Added session {sess_id}[/]")
                    else:
                        # Update existing session
                        self.sessions[sess_id]['socket'] = sock
                        self.sessions[sess_id]['handler'] = rev_sess
                        self.sessions[sess_id]['status'] = getattr(rev_sess, 'status', 'alive')
                        self.sessions[sess_id]['os'] = getattr(rev_sess, 'os', 'unknown')
                        self.append_output(f"[dim]Updated session {sess_id}[/]")
            
            self.update_sessions_ui()
            
            if len(SESSIONS) > 0:
                # Auto-select first session
                first_sess = list(SESSIONS.keys())[0]
                self.selected_session_id = first_sess
                self.active_session_id = first_sess
                self.append_output(f"[green]✓ Auto-selected session: {first_sess}[/]")
                self.tabs.setCurrentIndex(4)  # Switch to Sessions tab
                
                # Test socket
                if first_sess in self.sessions and self.sessions[first_sess].get('socket'):
                    self.append_output("[green]✓ Socket is available for command sending[/]")
                else:
                    self.append_output("[yellow]⚠️ Socket not available - commands may fail[/]")
            else:
                self.append_output("[yellow]No sessions found in reverse_tcp[/]")
            
            self.append_output(f"[green]✓ Sync complete: {len(self.sessions)} total sessions[/]")
            
        except Exception as e:
            self.append_output(f"[red]Sync error: {e}[/]")
            import traceback
            self.append_output(f"[red]{traceback.format_exc()}[/]")

    def append_session_output(self, session_id, text):
        """Append output to specific session - CLEAN VERSION"""
        try:
            if session_id in self.sessions:
                session = self.sessions[session_id]
            
               
                # Skip empty lines
                if not text.strip():
                    return
                import re
                clean_text = text
                
                # Hapus semua jenis ANSI sequences (comprehensive)
                clean_text = re.sub(r'\x1b\][^\x07]*\x07', '', clean_text)        # OSC
                clean_text = re.sub(r'\x1b\[[\x20-\x3f]*[\x40-\x7e]', '', clean_text)  # CSI
                clean_text = re.sub(r'\x1b[=><]', '', clean_text)                    # ESC simple
                clean_text = clean_text.replace('\r\n', '\n').replace('\r', '\n')    # fix \r
                # Sisa-sisa bracketed paste
                clean_text = re.sub(r'\[\??[0-9]+[a-zA-Z]', '', clean_text)
                
                clean_text = clean_text.strip()
                
                if not clean_text:
                    return
                    
                # === FORMAT OUTPUT ===
                if clean_text.startswith('$ '):
                    formatted_text = f"\n🔹 {clean_text}"  # Command
                elif any(indicator in clean_text for indicator in ['drwx', '-rw', 'total ']):
                    formatted_text = f"  {clean_text}"     # File listing  
                elif clean_text.startswith('/') and '/' in clean_text:
                    formatted_text = f"📁 {clean_text}"     # Path
                else:
                    formatted_text = clean_text            # Regular output
                
                
                session['output'] += formatted_text + "\n"
                
                # Update display if this session is active
                if self.active_session_id == session_id:
                    # Use plain text untuk session output (no HTML)
                    current_text = self.session_output.toPlainText()
                    self.session_output.setPlainText(current_text + formatted_text + "\n")
                    self.session_output.moveCursor(QTextCursor.MoveOperation.End)
                    
        except Exception as e:
            self.append_output(f"[red]Session Output Error: {e}[/]")

    def format_session_output(self, text):
        """Format session output untuk tampilan yang clean"""
        # Remove any remaining ANSI codes
        import re
        clean_text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
        
        # Simple formatting based on content
        if clean_text.startswith('$ '):
            return f"\n🔹 {clean_text}"  # Command
        elif any(indicator in clean_text for indicator in ['drwx', '-rw', 'total ']):
            return f"  {clean_text}"     # File listing
        elif clean_text.startswith('/') and '/' in clean_text:
            return f"📁 {clean_text}"     # Path
        else:
            return clean_text            # Regular output

    def switch_to_sessions_tab(self):
        """Switch to Sessions tab automatically"""
        try:
            self.tabs.setCurrentIndex(3)  # Sessions tab index
        except Exception as e:
            print("Tab switch error:", e)

    def debug_session_storage(self):
        """Debug session storage secara detail"""
        self.append_output("[yellow]=== SESSION STORAGE DEBUG ===[/]")
        
        try:
            # Akses SESSIONS dari instance module yang benar-benar running
            if (self.framework.loaded_module and 
                hasattr(self.framework.loaded_module, 'module') and
                hasattr(self.framework.loaded_module.module, 'SESSIONS')):
                _active_mod = self.framework.loaded_module.module
                SESSIONS = _active_mod.SESSIONS
                SESSIONS_LOCK = _active_mod.SESSIONS_LOCK
            else:
                SESSIONS = _rtcp_mod.SESSIONS
                SESSIONS_LOCK = _rtcp_mod.SESSIONS_LOCK
            
            # Check SESSIONS in reverse_tcp.py
            with SESSIONS_LOCK:
                reverse_sessions = SESSIONS.copy()
                
            self.append_output(f"ReverseTCP SESSIONS: {len(reverse_sessions)}")
            for sess_id, sess in reverse_sessions.items():
                has_socket = sess.get('socket') is not None
                socket_status = "✓" if has_socket else "❌"
                self.append_output(f"  {socket_status} {sess_id}")
            
            # Check GUI sessions
            self.append_output(f"GUI sessions: {len(self.sessions)}")
            for sess_id, sess in self.sessions.items():
                has_socket = sess.get('socket') is not None
                socket_status = "✓" if has_socket else "❌"
                self.append_output(f"  {socket_status} {sess_id}")
                
            # Detailed comparison
            reverse_ids = set(reverse_sessions.keys())
            gui_ids = set(self.sessions.keys())
            
            self.append_output(f"✓ Matching sessions: {list(reverse_ids & gui_ids)}")
            self.append_output(f"⚠️ Only in ReverseTCP: {list(reverse_ids - gui_ids)}")
            self.append_output(f"⚠️ Only in GUI: {list(gui_ids - reverse_ids)}")
            
            # Check socket objects
            if reverse_ids & gui_ids:
                common_session = list(reverse_ids & gui_ids)[0]
                reverse_socket = reverse_sessions[common_session].get('socket')
                gui_socket = self.sessions[common_session].get('socket')
                
                self.append_output(f"Socket comparison for {common_session}:")
                self.append_output(f"  ReverseTCP socket: {reverse_socket}")
                self.append_output(f"  GUI socket: {gui_socket}")
                self.append_output(f"  Same object: {reverse_socket is gui_socket}")
            
        except Exception as e:
            self.append_output(f"[red]Debug error: {e}[/]")
        
        self.append_output("[yellow]================================[/]")

    def on_session_selected(self, item):
        """Handle session selection dari list - DENGAN INFO OS"""
        try:
            if item is None:
                return
                
            session_id = item.data(Qt.ItemDataRole.UserRole)
            
            # Set BOTH session IDs
            self.selected_session_id = session_id
            self.active_session_id = session_id
            
            if session_id in self.sessions:
                session = self.sessions[session_id]
                
                # Update session output display
                self.session_output.setPlainText(session['output'])
                self.session_output.moveCursor(QTextCursor.MoveOperation.End)
                
                # Dapatkan info OS untuk placeholder
                os_type = session.get('os', 'unknown')
                os_display = {
                    'linux': 'Linux',
                    'windows': 'Windows', 
                    'macos': 'macOS',
                    'unknown': 'Unknown OS'
                }.get(os_type, 'Unknown OS')
                
                # Update command input placeholder dengan info OS
                self.session_cmd_input.setPlaceholderText(
                    f"Enter command for {os_display} Session {session_id} ({session['type']})..."
                )
                
                # Highlight selected item
                for i in range(self.session_list.count()):
                    list_item = self.session_list.item(i)
                    if list_item and list_item.data(Qt.ItemDataRole.UserRole) == session_id:
                        list_item.setBackground(QColor('#0078d4'))  # Blue highlight
                        list_item.setForeground(QColor('#ffffff'))
                    else:
                        if list_item:
                            list_item.setBackground(QColor('transparent'))
                            # Reset text color based on OS
                            sess_os = self.sessions.get(list_item.data(Qt.ItemDataRole.UserRole), {}).get('os', 'unknown')
                            os_color_map = {
                                'linux': '#50fa7b',    # Hijau untuk Linux
                                'windows': '#ff79c6',  # Pink untuk Windows  
                                'macos': '#ffb86c',    # Orange untuk macOS
                                'unknown': '#6272a4'   # Biru untuk unknown
                            }
                            list_item.setForeground(QColor(os_color_map.get(sess_os, '#6272a4')))
                
                # Tampilkan info OS di console juga
                os_icons = {'linux': '🐧', 'windows': '🪟', 'macos': '🍎', 'unknown': '💻'}
                icon = os_icons.get(os_type, '💻')
                self.append_output(f"[green]✓ Selected {icon} {os_display} Session {session_id}[/]")
                
        except Exception as e:
            self.append_output(f"Session selection error: {e}")

    
    def send_session_command(self):
        """Send command to selected session - FIXED FOR GUI"""
        # First, sync sessions if needed
        if not self.sessions:
            self.append_output("[yellow]No sessions, trying to sync...[/]")
            self.sync_sessions_from_reverse_tcp()
            
        if not self.sessions:
            self.append_output("[red]❌ No sessions available![/]")
            return
            
        if not self.selected_session_id:
            first_session_id = list(self.sessions.keys())[0]
            self.selected_session_id = first_session_id
            self.active_session_id = first_session_id
            self.append_output(f"[yellow]⚠️ Auto-selected session: {first_session_id}[/]")
            self.update_sessions_ui()
        
        session_id = self.selected_session_id
        cmd = self.session_cmd_input.text().strip()
        
        if not cmd:
            self.append_output("[yellow]Please enter a command[/]")
            return

        self.append_output(f"[yellow]Sending to session {session_id}: {cmd}[/]")
        self.append_session_output(session_id, f"$ {cmd}")
        
        success = False
        
        # === METHOD 1: Try direct socket from GUI session ===
        if session_id in self.sessions:
            session = self.sessions[session_id]
            sock = session.get('socket')
            
            if sock:
                try:
                    import select
                    # Check if socket is writable
                    ready = select.select([], [sock], [], 0.5)
                    if ready[1]:
                        sock.send((cmd + "\n").encode())
                        success = True
                        self.append_output("[green]✓ Command sent via GUI socket[/]")
                        
                        # Read response in background
                        def read_response():
                            try:
                                time.sleep(0.3)
                                ready_read = select.select([sock], [], [], 5)
                                if ready_read[0]:
                                    data = sock.recv(8192).decode('utf-8', errors='ignore')
                                    if data:
                                        self.append_session_output(session_id, data)
                                else:
                                    self.append_output("[dim]No immediate response (command may be running)[/]")
                            except Exception as e:
                                self.append_output(f"[red]Response error: {e}[/]")
                        
                        threading.Thread(target=read_response, daemon=True).start()
                    else:
                        self.append_output("[yellow]Socket not writable, trying alternate method[/]")
                except Exception as e:
                    self.append_output(f"[red]Socket send error: {e}[/]")
        
        # === METHOD 2: Try handler method from reverse_tcp ===
        if not success and session_id in self.sessions:
            session = self.sessions[session_id]
            handler = session.get('handler')
            
            if handler and hasattr(handler, 'send_command'):
                try:
                    result = handler.send_command(cmd)
                    success = True
                    self.append_output("[green]✓ Command sent via handler[/]")
                    if result:
                        self.append_session_output(session_id, result)
                except Exception as e:
                    self.append_output(f"[yellow]Handler error: {e}[/]")
        
        # === METHOD 3: Ambil session object dari loaded_module, send + baca response ===
        if not success:
            try:
                _active_sess_obj = None
                if (self.framework.loaded_module and
                    hasattr(self.framework.loaded_module, 'module') and
                    hasattr(self.framework.loaded_module.module, 'SESSIONS')):
                    _SESS = self.framework.loaded_module.module.SESSIONS
                    _active_sess_obj = _SESS.get(session_id)

                if _active_sess_obj and hasattr(_active_sess_obj, 'send_command'):
                    # Jalankan di thread supaya GUI tidak freeze
                    def _do_send(sess_obj, command, sid):
                        try:
                            result = sess_obj.send_command(command)
                            if result:
                                self.session_output_signal.emit(sid, result)
                        except Exception as ex:
                            self.console_output_signal.emit(f"[red]Response read error: {ex}[/]")
                    threading.Thread(target=_do_send, args=(_active_sess_obj, cmd, session_id), daemon=True).start()
                    success = True
                    self.append_output("[green]✓ Command sent via reverse_tcp function[/]")
                else:
                    # Fallback: hanya kirim tanpa baca response
                    if (self.framework.loaded_module and
                        hasattr(self.framework.loaded_module, 'module') and
                        hasattr(self.framework.loaded_module.module, 'send_command_to_session')):
                        _fn = self.framework.loaded_module.module.send_command_to_session
                    else:
                        _fn = _rtcp_mod.send_command_to_session
                    success = _fn(session_id, cmd)
                    if success:
                        self.append_output("[green]✓ Command sent (no response capture)[/]")
            except Exception as e:
                self.append_output(f"[yellow]reverse_tcp function error: {e}[/]")
        
        if not success:
            self.append_output("[red]❌ Failed to send command[/]")
            self.append_output("[yellow]Debug: Run sync_sessions_from_reverse_tcp() first[/]")
            # Offer to resync
            self.append_output("[dim]Try: self.sync_sessions_from_reverse_tcp()[/]")
        
        self.session_cmd_input.clear()
        

    def send_command_direct_socket(self, session_id, command):
        """Method 3: Send command directly via socket in GUI session"""
        try:
            session = self.sessions[session_id]
            sock = session.get('socket')
            
            if not sock:
                self.append_output("[red]❌ No socket in GUI session[/]")
                return False
                
            # Test socket
            import select
            ready = select.select([], [sock], [], 0.1)
            if not ready[1]:
                self.append_output("[red]❌ Socket not writable[/]")
                return False
                
            # Send command
            full_command = command + "\n"
            bytes_sent = sock.send(full_command.encode())
            
            self.append_output(f"[green]✓ Method 3: Direct socket send ({bytes_sent} bytes)[/]")
            return True
            
        except Exception as e:
            self.append_output(f"[red]❌ Direct socket error: {e}[/]")
            return False

    def verify_session_sync(self):
        """Verify session synchronization between GUI and reverse_tcp"""
        self.append_output("[yellow]=== SESSION SYNC VERIFICATION ===[/]")
        
        try:
            # Akses SESSIONS dari instance module yang benar-benar running
            if (self.framework.loaded_module and 
                hasattr(self.framework.loaded_module, 'module') and
                hasattr(self.framework.loaded_module.module, 'SESSIONS')):
                _active_mod = self.framework.loaded_module.module
                SESSIONS = _active_mod.SESSIONS
                SESSIONS_LOCK = _active_mod.SESSIONS_LOCK
            else:
                SESSIONS = _rtcp_mod.SESSIONS
                SESSIONS_LOCK = _rtcp_mod.SESSIONS_LOCK
            
            with SESSIONS_LOCK:
                reverse_sessions = set(SESSIONS.keys())
            gui_sessions = set(self.sessions.keys())
            
            self.append_output(f"GUI sessions: {len(gui_sessions)}")
            self.append_output(f"ReverseTCP sessions: {len(reverse_sessions)}")
            
            # Check matches
            matches = reverse_sessions & gui_sessions
            only_in_gui = gui_sessions - reverse_sessions
            only_in_reverse = reverse_sessions - gui_sessions
            
            self.append_output(f"✓ Synced sessions: {len(matches)}")
            self.append_output(f"⚠️ Only in GUI: {len(only_in_gui)}")
            self.append_output(f"⚠️ Only in ReverseTCP: {len(only_in_reverse)}")
            
            if only_in_gui:
                self.append_output(f"[yellow]Sessions only in GUI: {list(only_in_gui)}[/]")
                
            if only_in_reverse:
                self.append_output(f"[yellow]Sessions only in ReverseTCP: {list(only_in_reverse)}[/]")
                
            # Check socket status for matched sessions
            for sess_id in matches:
                gui_has_socket = 'socket' in self.sessions[sess_id] and self.sessions[sess_id]['socket'] is not None
                reverse_has_socket = 'socket' in SESSIONS[sess_id] and SESSIONS[sess_id]['socket'] is not None
                
                self.append_output(f"Session {sess_id}:")
                self.append_output(f"  GUI socket: {'✓' if gui_has_socket else '❌'}")
                self.append_output(f"  ReverseTCP socket: {'✓' if reverse_has_socket else '❌'}")
        
        except Exception as e:
            self.append_output(f"[red]Verification error: {e}[/]")
        
        self.append_output("[yellow]================================[/]")


    def force_sync_sessions(self):
        """Force synchronization between GUI and reverse_tcp sessions"""
        self.append_output("[yellow]=== FORCE SESSION SYNC ===[/]")
        
        try:
            # Akses SESSIONS dari instance module yang benar-benar running
            if (self.framework.loaded_module and 
                hasattr(self.framework.loaded_module, 'module') and
                hasattr(self.framework.loaded_module.module, 'SESSIONS')):
                _active_mod = self.framework.loaded_module.module
                SESSIONS = _active_mod.SESSIONS
                SESSIONS_LOCK = _active_mod.SESSIONS_LOCK
            else:
                SESSIONS = _rtcp_mod.SESSIONS
                SESSIONS_LOCK = _rtcp_mod.SESSIONS_LOCK
            
            with SESSIONS_LOCK:
                reverse_sessions = SESSIONS.copy()
            
            # Add missing sessions to GUI
            added_to_gui = 0
            for sess_id, reverse_sess in reverse_sessions.items():
                if sess_id not in self.sessions:
                    # Create GUI session from reverse_tcp session
                    self.sessions[sess_id] = {
                        'id': sess_id,
                        'type': reverse_sess.get('type', 'reverse_tcp'),
                        'ip': reverse_sess.get('rhost', 'unknown'),
                        'port': reverse_sess.get('rport', 'unknown'),
                        'lhost': reverse_sess.get('lhost', 'unknown'),
                        'lport': reverse_sess.get('lport', 'unknown'),
                        'output': f"[*] Session {sess_id} synced from reverse_tcp\n",
                        'handler': None,
                        'status': 'alive',
                        'created': time.strftime("%H:%M:%S"),
                        'socket': reverse_sess.get('socket')
                    }
                    added_to_gui += 1
            
            # Add missing sessions to reverse_tcp
            added_to_reverse = 0
            for sess_id, gui_sess in self.sessions.items():
                if sess_id not in reverse_sessions:
                    # Can't easily add to reverse_tcp without proper handler
                    self.append_output(f"[yellow]Cannot add {sess_id} to reverse_tcp (requires handler)[/]")
            
            self.append_output(f"[green]✓ Added {added_to_gui} sessions to GUI[/]")
            self.append_output(f"[green]✓ Force sync completed[/]")
            
            # Update UI
            self.update_sessions_ui()
            
        except Exception as e:
            self.append_output(f"[red]Force sync error: {e}[/]")
        
        self.append_output("[yellow]========================[/]")

    def debug_session_connection(self):
        """Detailed debug untuk session connection"""
        self.append_output(f"[yellow]=== SESSION CONNECTION DEBUG ===[/]")
        
        if not self.selected_session_id:
            self.append_output("[red]❌ No session selected[/]")
            return
            
        session_id = self.selected_session_id
        self.append_output(f"Selected Session: {session_id}")
        
        # Check di local sessions
        if session_id in self.sessions:
            session = self.sessions[session_id]
            self.append_output(f"✓ Found in GUI sessions")
            self.append_output(f"  Type: {session.get('type')}")
            self.append_output(f"  Status: {session.get('status')}")
            self.append_output(f"  IP: {session.get('ip')}")
            self.append_output(f"  Port: {session.get('port')}")
            self.append_output(f"  Has socket: {'socket' in session and session['socket'] is not None}")
        else:
            self.append_output("[red]❌ Session not found in GUI sessions[/]")
        
        # Check di reverse_tcp sessions
        try:
            # Akses SESSIONS dari instance module yang benar-benar running
            if (self.framework.loaded_module and 
                hasattr(self.framework.loaded_module, 'module') and
                hasattr(self.framework.loaded_module.module, 'SESSIONS')):
                _active_mod = self.framework.loaded_module.module
                SESSIONS = _active_mod.SESSIONS
                SESSIONS_LOCK = _active_mod.SESSIONS_LOCK
            else:
                SESSIONS = _rtcp_mod.SESSIONS
                SESSIONS_LOCK = _rtcp_mod.SESSIONS_LOCK
            with SESSIONS_LOCK:
                if session_id in SESSIONS:
                    reverse_session = SESSIONS[session_id]
                    self.append_output(f"✓ Found in reverse_tcp sessions")
                    self.append_output(f"  Has socket: {'socket' in reverse_session and reverse_session['socket'] is not None}")
                    if reverse_session.get('socket'):
                        sock = reverse_session['socket']
                        self.append_output(f"  Socket alive: {not sock._closed if hasattr(sock, '_closed') else 'Unknown'}")
                else:
                    self.append_output("[red]❌ Session not found in reverse_tcp sessions[/]")
        except Exception as e:
            self.append_output(f"[red]Error checking reverse_tcp: {e}[/]")
        
        self.append_output(f"[yellow]================================[/]")

    def test_session_communication(self):
        """Test session communication dengan simple command"""
        if not self.selected_session_id:
            self.append_output("[red]❌ Please select a session first![/]")
            return
            
        session_id = self.selected_session_id
        self.append_output(f"[yellow]Testing session: {session_id}[/]")
        
        # Test command sederhana
        test_cmd = "echo 'SESSION_TEST_SUCCESS'"
        self.append_session_output(session_id, f"$ {test_cmd}")
        
        try:
            from modules.payloads.reverse.reverse_tcp import send_command_to_session
            self.append_output(f"[yellow]Sending command via reverse_tcp...[/]")
            
            success = send_command_to_session(session_id, test_cmd)
            
            if success:
                self.append_output("[green]✓ Command sent successfully via reverse_tcp[/]")
                self.append_output("[yellow]Waiting for response...[/]")
            else:
                self.append_output("[red]❌ reverse_tcp reported failure[/]")
                
        except Exception as e:
            self.append_output(f"[red]❌ Error calling reverse_tcp: {e}[/]")
            import traceback
            self.append_output(f"[red]Traceback: {traceback.format_exc()}[/]")


    def kill_session(self):
        """Kill active session"""
        if not self.active_session_id or self.active_session_id not in self.sessions:
            self.append_output("[red]No active session selected[/]")
            return
            
        session_id = self.active_session_id
        session = self.sessions[session_id]
        
        self.append_output(f"[yellow][*] Killing Session {session_id}...[/]")
        
        try:
            # Tutup socket connection jika ada
            if session.get('socket'):
                try:
                    session['socket'].close()
                    self.append_output(f"[green]✓ Socket connection closed[/]")
                except:
                    pass
            
            # Update session status
            session['status'] = 'killed'
            session['output'] += f"\n[Session {session_id} terminated by user]\n"
            
            # Remove dari sessions dict
            with self.session_lock:
                del self.sessions[session_id]
            
            # Remove dari list widget
            self.update_sessions_ui()
            
            # Clear active session dan UI
            self.active_session_id = None
            self.session_output.clear()
            self.session_cmd_input.setPlaceholderText("Enter command for selected session...")
            
            self.append_output(f"[green][+] Session {session_id} successfully terminated[/]")
            
        except Exception as e:
            self.append_output(f"[red]Error killing session: {e}[/]")
            # Force remove meski error
            try:
                with self.session_lock:
                    del self.sessions[session_id]
                self.update_sessions_ui()
                self.active_session_id = None
            except:
                pass

    def kill_selected_session(self):
        item = self.session_list.currentItem()
        if not item:
            return
        sess_id = item.data(Qt.ItemDataRole.UserRole)
        
        # Cari modul reverse_tcp
        if hasattr(self.framework, 'loaded_module') and "reverse_tcp" in self.framework.loaded_module.name.lower():
            import importlib
            mod = importlib.import_module("modules.payloads.reverse.reverse_tcp")
            if hasattr(mod, 'kill_session'):
                mod.kill_session(sess_id)

    def upgrade_session(self):
        """Upgrade session to Meterpreter"""
        if not self.active_session_id or self.active_session_id not in self.sessions:
            self.append_output("[red]No active session selected[/red]")
            return
            
        session = self.sessions[self.active_session_id]
        
        if session['type'] == 'meterpreter':
            self.append_output("[yellow]Session is already Meterpreter[/yellow]")
            return
            
        self.append_output(f"[yellow][*] Attempting to upgrade Session {self.active_session_id} to Meterpreter...[/yellow]")
        
        # Simulate upgrade for now
        session['type'] = 'meterpreter'
        session['output'] += "[+] Session upgraded to Meterpreter\n"
        
        # Update session list display
        self.update_sessions_ui()
                
        self.session_output.setPlainText(session['output'])
        self.session_output.moveCursor(QTextCursor.MoveOperation.End)

    


    

    def kill_selected_session(self):
        item = self.session_list.currentItem()
        if not item:
            return
        sess_id = item.data(Qt.ItemDataRole.UserRole)
        
        # Cari modul reverse_tcp
        if hasattr(self.framework, 'loaded_module') and "reverse_tcp" in self.framework.loaded_module.name.lower():
            import importlib
            mod = importlib.import_module("modules.payloads.reverse.reverse_tcp")
            if hasattr(mod, 'kill_session'):
                mod.kill_session(sess_id)

    
    # === TRANSFER DIALOG & PROGRESS ===
    
    

       

    def send_session_command_direct(self, command):
        """Send command langsung tanpa melalui reverse_tcp"""
        if not self.selected_session_id:
            return
            
        # Simpan command ke input dan trigger send
        self.session_cmd_input.setText(command)
        self.send_session_command()


    def append_banner(self, text):
        """Append banner (ASCII art) dengan ESCAPE backslash, tapi tetap support ANSI color"""
        if not text or not text.strip():
            return

        # 1. ESCAPE backslash agar tidak dianggap escape ANSI
        text = text.replace('\\', '\\\\')

        # 2. Ganti \n jadi <br>
        text = text.replace('\n', '<br>')

        # 3. Proses ANSI → HTML (sama seperti append_output, tapi lebih aman)
        i = 0
        output = ""
        tag_stack = []

        while i < len(text):
            if text[i:i+2] == '\x1b':  # ANSI escape
                end = text.find('m', i)
                if end == -1:
                    output += text[i:]
                    break
                code = text[i+2:end]
                i = end + 1

                # ANSI to HTML (sama seperti append_output)
                if code == '0':
                    while tag_stack: output += '</span>'; tag_stack.pop()
                elif code == '1': output += '<span style="font-weight: bold;">'; tag_stack.append('b')
                elif code == '2': output += '<span style="opacity: 0.6;">'; tag_stack.append('dim')
                elif code in ['31', '91']: output += '<span style="color: #ff5555;">'; tag_stack.append('red')
                elif code in ['32', '92']: output += '<span style="color: #50fa7b;">'; tag_stack.append('green')
                elif code in ['33', '93']: output += '<span style="color: #f1fa8c;">'; tag_stack.append('yellow')
                elif code in ['34', '94']: output += '<span style="color: #6272a4;">'; tag_stack.append('blue')
                elif code in ['35', '95']: output += '<span style="color: #ff79c6;">'; tag_stack.append('magenta')
                elif code in ['36', '96']: output += '<span style="color: #8be9fd;">'; tag_stack.append('cyan')
                elif code == '97': output += '<span style="color: #ffffff;">'; tag_stack.append('white')
                else: continue
            else:
                char = text[i]
                if char == '<': output += "&lt;"
                elif char == '>': output += "&gt;"
                elif char == '&': output += "&amp;"
                else: output += char
                i += 1

        while tag_stack: output += '</span>'; tag_stack.pop()

        # Insert ke console
        cursor = self.console_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(output)
        self.console_output.ensureCursorVisible()
        # === INJECT KE AI ===
        if hasattr(self, 'ai_widget') and self.ai_widget:
             self.ai_widget.inject_output(text)
   
    
    #def load_banner(self):
        #try:
            #from core import load_banners_from_folder, get_random_banner
            
            # Muat banner
            #load_banners_from_folder()
            #raw_banner = get_random_banner()

            #if not raw_banner:
                #self.append_output("[yellow]No banner found in 'banner/' folder[/yellow]")
                #return

            # === SOLUSI SIMPLE: Tampilkan sebagai plain text ===
            #import re
            
            # Hapus SEMUA formatting codes
            #clean_banner = re.sub(r'\[/?[a-zA-Z0-9_]*\]', '', raw_banner)  # Hapus [tags]
            #clean_banner = re.sub(r'\x1b\[[0-9;]*[mG]', '', clean_banner)  # Hapus ANSI
            
            # Pastikan font monospace untuk banner
            #current_font = self.console_output.font()
            #banner_font = QFont("DejaVu Sans Mono", 9)
            #self.console_output.setFont(banner_font)
            
            # Insert sebagai plain text
            #cursor = self.console_output.textCursor()
            #cursor.movePosition(QTextCursor.MoveOperation.End)
            #cursor.insertText(clean_banner)
            #cursor.insertText("\n\n")
            
            # Kembalikan font normal
            #self.console_output.setFont(current_font)
            
            # Info setelah banner
            #self.append_output("LazyFramework GUI v2.6")
            #self.append_output("Type 'help' or click modules to start")
            #self.append_output("Auto Tor IP rotation enabled (every 5 minutes)")

        #except Exception as e:
            #self.append_output(f"Banner error: {e}")
    
    #def cmd_show_banner(self, args=None):
        #"""Show banner command - sama seperti load_banner()"""
        #try:
            #from core import load_banners_from_folder, get_random_banner
            
            # Muat banner
            #load_banners_from_folder()
            #raw_banner = get_random_banner()

            #if not raw_banner:
                #self.append_output("[yellow]No banner found in 'banner/' folder[/yellow]")
                #return

            # === SOLUSI SIMPLE: Tampilkan sebagai plain text ===
            #import re
            
            # Hapus SEMUA formatting codes
            #clean_banner = re.sub(r'\[/?[a-zA-Z0-9_]*\]', '', raw_banner)  # Hapus [tags]
            #clean_banner = re.sub(r'\x1b\[[0-9;]*[mG]', '', clean_banner)  # Hapus ANSI
            
            # Pastikan font monospace untuk banner
            #current_font = self.console_output.font()
            #banner_font = QFont("DejaVu Sans Mono", 9)
            #self.console_output.setFont(banner_font)
            
            # Insert sebagai plain text
            #cursor = self.console_output.textCursor()
            #cursor.movePosition(QTextCursor.MoveOperation.End)
            #cursor.insertText(clean_banner)
            #cursor.insertText("\n\n")
            
            # Kembalikan font normal
            #self.console_output.setFont(current_font)
            
            # Info setelah banner
            #self.append_output("LazyFramework GUI v2.6")
            #self.append_output("Type 'help' or click modules to start")
            #self.append_output("Auto Tor IP rotation enabled (every 5 minutes)")

        #except Exception as e:
            #self.append_output(f"Banner error: {e}")


    def load_all_modules(self):
        """Load all modules into the list"""
        self.module_list.clear()
        modules = self.framework.metadata

        for module_path, meta in sorted(modules.items()):
            if not meta.get("options"):
                continue

            display_name = module_path.replace("modules/", "")
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, module_path)
            font = QFont("Hack", 10)
            item.setFont(font)
            # Color code by type
            if "/recon/" in module_path:
                item.setForeground(QColor("#ffffff"))  # Cyan
            elif "/strike/" in module_path:
                item.setForeground(QColor("#ffffff"))  # Red
            elif "/hold/" in module_path:
                item.setForeground(QColor("#ffffff"))  # Yellow
            elif "/ops/" in module_path:
                item.setForeground(QColor("#ffffff"))  # Green
            elif "/payload" in module_path:
                item.setForeground(QColor("#ffffff"))  # Pink

            self.module_list.addItem(item)

        self.update_session_info()

    def on_category_click(self):
        """Handle category button click"""
        button = self.sender()
        category = button.property('category')
        self.filter_modules_by_category(category)

    def filter_modules_by_category(self, category):
        """Filter modules by category"""
        for i in range(self.module_list.count()):
            item = self.module_list.item(i)
            module_path = item.data(Qt.ItemDataRole.UserRole)

            if category == "all":
                item.setHidden(False)
            elif category == "payloads":
                item.setHidden("payload" not in module_path.lower())
            else:
                item.setHidden(f"/{category}/" not in module_path)

    def search_modules(self):
        """Search modules as user types"""
        search_text = self.search_input.text().lower()

        for i in range(self.module_list.count()):
            item = self.module_list.item(i)
            module_path = item.data(Qt.ItemDataRole.UserRole)
            meta = self.framework.metadata.get(module_path, {})
            description = meta.get("description", "").lower()

            matches = (search_text in module_path.lower() or
                       search_text in description)
            item.setHidden(not matches)

    def perform_search(self):
        """Perform search command"""
        search_text = self.search_input.text()
        if search_text:
            self.execute_command("search", [search_text])

    def load_selected_module(self, item):
        """Load selected module TANPA OUTPUT COMMAND KE CONSOLE"""
        if not item:
            return
        
        import contextlib  # Import di sini
        import io
        import os
        
        module_path = item.data(Qt.ItemDataRole.UserRole)
        module_name = os.path.basename(module_path)
        self.set_active_module(module_name)
        
        import shutil
        module_dir = os.path.dirname(module_path)
        pycache_dir = os.path.join(module_dir, "__pycache__")
        if os.path.exists(pycache_dir):
            try:
                shutil.rmtree(pycache_dir)
                self.append_output(f"[bold cyan][*] Cache dihapus: {pycache_dir}[/]")
            except Exception as e:
                self.append_output(f"[bold red][!] Gagal hapus cache: {e}[/]")
        
        try:
            # Execute use command tanpa output ke console
            output_buffer = io.StringIO()
            
            # Gunakan contextlib.redirect_stdout secara langsung
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                self.framework.cmd_use([module_path])
            
            # Update UI state tanpa output ke console
            if self.framework.loaded_module:
                self.current_module = self.framework.loaded_module.name
                self.current_module_label.setText(f"Loaded: {self.current_module}")
                self.current_module_label.setStyleSheet("color: #50fa7b; font-weight: bold;")
                self.run_btn.setEnabled(True)
                self.back_btn.setEnabled(True)
                
                # Load module options
                self.load_module_options()
                
                # Show module info di tab Module Info (bukan console)
                self.show_module_info_in_tab()

                # === AGENT MODE: AI otomatis isi options & siap run ===
                if hasattr(self, 'ai_tab') and self.ai_tab.api_key_input.text().strip():
                    self.ai_tab.run_agent_mode(self.framework.loaded_module)
                
        except Exception as e:
            self.append_output(f"Error loading module: {e}")

    
  
   

    def show_module_info_in_tab(self):
        """Show module info di tab Module Info - SIMPLE AND CLEAN"""
        try:
            import contextlib
            import io
            
            # Capture info output
            output_buffer = io.StringIO()
            
            # Gunakan contextlib.redirect_stdout
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                self.framework.cmd_info([])
            
            # Get the output
            info_output = output_buffer.getvalue()
            
            # Tampilkan di Module Info tab
            if info_output.strip():
                # Format sederhana dengan HTML pre untuk menjaga formatting
                html_output = self.create_simple_module_info(info_output)
                self.module_detail_info.setHtml(html_output)
                
            # Switch ke Module Info tab
            self.tabs.setCurrentIndex(2)
            
        except Exception as e:
            # Fallback ke plain text
            self.module_detail_info.setPlainText(f"Error loading module info: {e}")
        

    def create_simple_module_info(self, text):
        """Create simple module info display dengan formatting yang terjaga"""
        import re
        
        # Bersihkan ANSI sequences
        clean_text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
        
        # Tambahkan warna untuk informasi penting
        colored_text = self.add_rank_colors(clean_text)
        
        # HTML dengan styling sederhana
        html = f"""
        <html>
        <head>
        <style>
            body {{
                font-family: 'Fira Code';
                font-weight: bold;
                font-size: 12px;
                background: #000;
                color: #ffffff;
                margin: 0;
                padding: 15px;
                line-height: 1.3;
            }}
            .module-header {{
                color: #00ffff;
                font-weight: bold;
                font-size: 14px;
                margin-bottom: 15px;
                border-bottom: 1px solid #00ffff;
                padding-bottom: 5px;
            }}
            .section {{
                margin: 10px 0;
                padding: 10px;
                background: #252525;
                border: 1px solid #404040;
                border-radius: 3px;
            }}
            .option-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 5px 0;
                font-size: 11px;
            }}
            .option-table th {{
                background: #2d2d2d;
                color: #ff79c6;
                padding: 6px 8px;
                text-align: left;
                border: 1px solid #404040;
            }}
            .option-table td {{
                padding: 6px 8px;
                border: 1px solid #404040;
                color: #d4d4d4;
            }}
            .name {{ color: #8be9fd; font-weight: bold; }}
            .current {{ color: #f1fa8c; }}
            .required-yes {{ color: #50fa7b; }}
            .required-no {{ color: #ff5555; }}
            pre {{
                font-family: 'DejaVu Sans Mono', 'Courier New', monospace;
                white-space: pre-wrap;
                margin: 0;
                color: #d4d4d4;
            }}
            .rank-excellent {{ color: #ff5555; font-weight: bold; }}
            .rank-great {{ color: #ff79c6; font-weight: bold; }}
            .rank-good {{ color: #f1fa8c; font-weight: bold; }}
            .rank-normal {{ color: #50fa7b; font-weight: bold; }}
            .rank-average {{ color: #8be9fd; font-weight: bold; }}
            .rank-low {{ color: #bd93f9; font-weight: bold; }}
            .rank-manual {{ color: #ffb86c; font-weight: bold; }}
            .info-name {{ color: #8be9fd; font-weight: bold; }}
            .info-module {{ color: #ff79c6; }}
            .info-type {{ color: #50fa7b; }}
            .info-platform {{ color: #f1fa8c; }}
            .info-arch {{ color: #bd93f9; }}
            .info-author {{ color: #ffb86c; }}
            .info-license {{ color: #ff5555; }}
        </style>
        </head>
        <body>
            <div class="module-header">LAZYFRAMEWORK MODULE INFORMATION</div>
            <pre>{colored_text}</pre>
        </body>
        </html>
        """
        
        return html

    def add_rank_colors(self, text):
        """Tambahkan warna untuk rank dan informasi module"""
        lines = text.split('\n')
        colored_lines = []
        
        for line in lines:
            colored_line = line
            
            # Warna untuk Rank
            if 'Rank:' in line:
                if 'Excellent' in line:
                    colored_line = line.replace('Excellent', '<span class="rank-excellent">Excellent</span>')
                elif 'Great' in line:
                    colored_line = line.replace('Great', '<span class="rank-great">Great</span>')
                elif 'Good' in line:
                    colored_line = line.replace('Good', '<span class="rank-good">Good</span>')
                elif 'Normal' in line:
                    colored_line = line.replace('Normal', '<span class="rank-normal">Normal</span>')
                elif 'Average' in line:
                    colored_line = line.replace('Average', '<span class="rank-average">Average</span>')
                elif 'Low' in line:
                    colored_line = line.replace('Low', '<span class="rank-low">Low</span>')
                elif 'Manual' in line:
                    colored_line = line.replace('Manual', '<span class="rank-manual">Manual</span>')
            
            # Warna untuk informasi module lainnya
            elif 'Name:' in line:
                colored_line = line.replace('Name:', '<span class="info-name">Name:</span>')
            elif 'Module:' in line:
                colored_line = line.replace('Module:', '<span class="info-module">Module:</span>')
            elif 'Type:' in line:
                colored_line = line.replace('Type:', '<span class="info-type">Type:</span>')
            elif 'Platform:' in line:
                colored_line = line.replace('Platform:', '<span class="info-platform">Platform:</span>')
            elif 'Arch:' in line:
                colored_line = line.replace('Arch:', '<span class="info-arch">Arch:</span>')
            elif 'Author:' in line:
                colored_line = line.replace('Author:', '<span class="info-author">Author:</span>')
            elif 'License:' in line:
                colored_line = line.replace('License:', '<span class="info-license">License:</span>')
            
            # Warna untuk section headers
            elif 'Module options' in line or 'Module parameters' in line:
                colored_line = f'<span style="color: #ff5555; font-weight: bold;">{line}</span>'
            elif 'Description:' in line:
                colored_line = f'<span style="color: #50fa7b; font-weight: bold;">{line}</span>'
            
            colored_lines.append(colored_line)
        
        return '\n'.join(colored_lines)
    

    def execute_command(self, command=None, args=None):
        """Execute framework command"""
       
        import io
        import re
        
        if command is None:
            # Get command from input
            full_command = self.command_input.text().strip()
            if not full_command:
                return

            # Add to history
            self.command_history.append(full_command)
            self.history_index = len(self.command_history)

            # Parse command
            parts = full_command.split()
            command = parts[0]
            args = parts[1:] if len(parts) > 1 else []

            # Clear input
            self.command_input.clear()

        # Tampilkan command yang di-execute (kecuali untuk klik module)
        if command != "use" or not args or "modules/" not in args[0]:
            self.append_output(f"> {command} {' '.join(args)}")

        try:
            if hasattr(self.framework, f"cmd_{command}"):
                # Redirect output sementara
                output_buffer = io.StringIO()
                
                # Gunakan contextlib.redirect_stdout
                with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
                    getattr(self.framework, f"cmd_{command}")(args)

                # Capture output dari command
                output = output_buffer.getvalue()
                if output.strip():
                    # Untuk command 'info', tampilkan di tab Module Info saja
                    if command == "info":
                        clean_info = re.sub(r'\x1b\[[0-9;]*[mG]', '', output)
                        self.module_detail_info.setPlainText(clean_info)
                        self.tabs.setCurrentIndex(2)  # Switch ke Module Info tab
                    else:
                        self.append_output(output)

                # Update UI berdasarkan command
                if command == "use":
                    self.on_module_loaded()
                elif command == "back":
                    self.on_module_unloaded()

            else:
                self.append_output(f"Unknown command: {command}")

        except Exception as e:
            self.append_output(f"Error executing command: {e}")

        self.update_session_info()

    def on_module_loaded(self):
        """Handle when module is loaded"""
        if self.framework.loaded_module:
            self.current_module = self.framework.loaded_module.name
            self.current_module_label.setText(f"Loaded: {self.current_module}")
            self.current_module_label.setStyleSheet(
                "color: #50fa7b; font-weight: bold;")

            self.run_btn.setEnabled(True)
            self.back_btn.setEnabled(True)

            # Load module options
            self.load_module_options()

            # Show module info di tab Module Info
            self.show_module_info_in_tab()

            # === AGENT MODE: AI otomatis isi options via command 'use' ===
            if hasattr(self, 'ai_tab') and self.ai_tab.api_key_input.text().strip():
                self.ai_tab.run_agent_mode(self.framework.loaded_module)

    def on_module_unloaded(self):
        """Handle when module is unloaded"""
        self.current_module = None
        self.current_module_label.setText("No module loaded module")
        self.current_module_label.setStyleSheet("color: #ff5555; font-weight: bold;")

        self.run_btn.setEnabled(False)
        self.back_btn.setEnabled(False)

        # Clear options tab
        self.clear_options_tab()
        
        # Clear module info tab
        self.module_detail_info.clear()

        
      
        # ==================================================================


    

    def load_module_options(self):
        """Load module options into options tab"""
        self.clear_options_tab()

        if not self.framework.loaded_module:
            return

        opts = self.framework.loaded_module.get_options()
        self.option_widgets = {}

        for name, info in opts.items():
            label = QLabel(name)
            value = str(info.get('value') or info.get('default') or "")
            required = info.get('required', False)
            description = info.get('description', 'No description available')

            if required:
                label.setStyleSheet("color: #ff5555; font-weight: bold;")
                label.setText(f"{name} *")
            else:
                label.setStyleSheet("color: #d4d4d4;")

            # Create input widget
            line_edit = QLineEdit(value)
            line_edit.setPlaceholderText(description)

            # Tooltip with full description
            line_edit.setToolTip(description)
            label.setToolTip(description)

            self.options_layout.addRow(label, line_edit)
            self.option_widgets[name] = line_edit

        # Switch to options tab
        self.tabs.setCurrentIndex(1)

    def clear_options_tab(self):
        """Clear options tab"""
        for i in reversed(range(self.options_layout.count())):
            item = self.options_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()

    # === GLITCH EFFECT UNTUK TITLE BAR SAAT MODULE JALAN ===
    def start_title_glitch(self):
        """Glitch title bar selama 1.5 detik saat module running"""
        if hasattr(self, '_glitch_timer'):
            self._glitch_timer.stop()

        self.original_title = self.windowTitle()
        glitch_chars = "01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンΣΨΩΔΘΛΞΠ"

        def glitch_step(count=0):
            if count > 12:  # ~1.5 detik (12 × 120ms)
                self.setWindowTitle(self.original_title)
                return

            # Random glitch text
            garbage = ''.join(random.choice(glitch_chars) for _ in range(random.randint(5, 15)))
            glitch_title = self.original_title
            pos = random.randint(0, len(glitch_title))
            glitch_title = glitch_title[:pos] + f"[red bold]{garbage}[/]" + glitch_title[pos:]

            self.setWindowTitle(glitch_title)

            # Next step
            QTimer.singleShot(random.randint(80, 160), lambda: glitch_step(count + 1))

        glitch_step()

    def stop_title_glitch(self):
        """Pastikan title kembali normal"""
        if hasattr(self, '_glitch_timer'):
            self._glitch_timer.stop()
        if hasattr(self, 'original_title'):
            self.setWindowTitle(self.original_title)

    def run_module(self):
        """Run the current module dengan FIXED OUTPUT CAPTURE"""
        if not self.framework.loaded_module:
            self.append_output("No module loaded")
            return

        # Update options from GUI
        for name, widget in self.option_widgets.items():
            value = widget.text().strip()
            self.framework.session[name] = value
            if value:
                try:
                    self.framework.loaded_module.set_option(name, value)
                    self.append_output(f"Set {name} => {value}")
                except Exception as e:
                    self.append_output(f"Error setting {name}: {e}")

        # === CRITICAL: SESSION SYNC REVERSE TCP ===
        if "reverse_tcp" in self.framework.loaded_module.name:
            self.framework.session['gui_sessions'] = {
                'dict': self.sessions,
                'lock': self.session_lock
            }
            self.framework.session['gui_instance'] = self

        # UI saat module berjalan
        
        self.run_btn.setEnabled(True)          # harus TRUE supaya STOP bisa diklik
        self.run_btn.setText("STOP")
        self.run_btn.setProperty("action", "stop")
        
        self.update_session_info()
        # Jalankan module dalam thread
        self.module_runner = ModuleRunner(self.framework, self.framework.loaded_module)
        self.module_runner.output.connect(self.append_output)
        self.module_runner.finished.connect(self.on_module_finished)
        self.module_runner.start()


    def on_module_finished(self):
        """Handle module completion"""
        
        
        self.update_session_info()
        self.run_btn.setEnabled(True)
        self.run_btn.setText("START")
        self.run_btn.setProperty("action", "run")

        self.append_output("[bold green][+] Module execution completed[/]")

        # === AGENT MODE: inject output ke AI dan auto-analyze ===
        if hasattr(self, 'ai_tab') and self.ai_tab.api_key_input.text().strip():
            # Ambil output terbaru dari console sebagai konteks
            console_text = self.console_output.toPlainText()
            # Kirim 4000 karakter terakhir (output terbaru dari module)
            recent_output = console_text[-4000:].strip()
            if recent_output:
                self.ai_tab.inject_output(recent_output)
                # Switch ke AI tab agar user bisa lihat analisis
                self.tabs.setCurrentIndex(self.tabs.indexOf(self.ai_tab))
                self.ai_tab.send_message(
                    "Module telah selesai dijalankan. Analisis output berikut, "
                    "identifikasi temuan penting, potensi vulnerability, "
                    "dan rekomendasikan langkah selanjutnya:\n\n" + recent_output
                )

        self.module_runner = None



    def unload_module(self):
        """Unload current module"""
        self.execute_command("back", [])
    #def quick_command(self, command):
        #"""Execute quick command from buttons"""
        #self.execute_command(command, [])

    def quick_command(self, command):
        """Execute quick command from buttons"""
        if command == "show_banner":
            self.cmd_show_banner()
        else:
            self.execute_command(command, [])

    def refresh_modules(self):
        """Refresh modules list"""
        self.framework.scan_modules()
        self.load_all_modules()
        self.append_output("Modules refreshed")

    def clear_console(self):
        """Clear console output"""
        self.console_output.clear()

    def change_font(self):
        """Open font selection dialog and apply to all text widgets"""
        font, ok = QFontDialog.getFont(self)
        if ok:
            # Terapkan font ke widget utama yang menampilkan teks
            self.console_output.setFont(font)
            self.module_detail_info.setFont(font)
            self.session_info.setFont(font)
            for i in range(self.module_list.count()):
                item = self.module_list.item(i)
                item.setFont(font)

            # Terapkan ke input field juga jika mau
            for widget in getattr(self, 'option_widgets', {}).values():
                widget.setFont(font)

            # Simpan ke framework session (opsional)
            self.framework.session['font'] = font.family()
            self.framework.session['font_size'] = font.pointSize()

            # Konfirmasi ke pengguna
            self.append_output(f"Font changed to {font.family()} ({font.pointSize()}pt)")

    def update_session_info(self):
        if not hasattr(self, 'session_info'):
            return
        import socket, platform
        import requests
        from datetime import datetime

        # === DATA ===
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "0.0.0.0"

        # Public IP
        if not self.framework.session.get("public_ip") or self.framework.session.get("public_ip") == "N/A":
            try:
                import requests
                public_ip = requests.get("https://api.ipify.org", timeout=4).text
                self.framework.session["public_ip"] = public_ip
            except:
                public_ip = "N/A"
        else:
            public_ip = self.framework.session.get("public_ip", "N/A")

        user = self.framework.session.get('user', 'unknown')
        
        # === PERBAIKAN: HITUNG LISTENERS DARI ACTIVE_LISTENERS ===
        with self.listener_lock:
            active_listeners_count = len(self.active_listeners)
        
        # Gunakan GUI sessions sebagai sumber utama
        total_sess = len(self.sessions)
        online_sess = sum(1 for s in self.sessions.values() if s.get('status') == 'alive')

        # === ANALISA SESSIONS UNTUK TARGET OS ===
        target_os_stats = {
            'linux': 0,
            'windows': 0,
            'macos': 0,
            'unknown': 0
        }
        
        # Hitung OS dari GUI sessions
        for sess_id, sess in self.sessions.items():
            os_type = sess.get('os', 'unknown')
            status = sess.get('status', 'alive')
            
            if status == 'alive':
                if os_type in target_os_stats:
                    target_os_stats[os_type] += 1
                else:
                    target_os_stats['unknown'] += 1

        # Format OS statistics
        os_icons = {'linux': '🐧', 'windows': '🪟', 'macos': '🍎', 'unknown': '💻'}
        os_display = []
        
        for os_type, count in target_os_stats.items():
            if count > 0:
                icon = os_icons.get(os_type, '💻')
                os_display.append(f"{icon}×{count}")

        os_summary = " | ".join(os_display) if os_display else "No active targets"

        uptime_sec = int(time.time() - self.framework.session.get("start_time", time.time()))
        d = uptime_sec // 86400
        h = (uptime_sec % 86400) // 3600
        m = (uptime_sec % 3600) // 60
        s = uptime_sec % 60
        uptime_str = f"{d}d {h:02d}h {m:02d}m" if d else f"{h:02d}h {m:02d}m {s:02d}s"

        proxy_status = "ONLINE" if self.proxy_enabled else "OFFLINE"
        proxy_color = "#50fa7b" if self.proxy_enabled else "#ff5555"
        proxy_detail = ""
        if self.proxy_enabled and self.current_proxy:
            p = self.current_proxy
            proxy_detail = f"{p['server']}:{p['port']} <small style='color:#ff8a80;'>({p['type'].upper()})</small>"
        
        current_module = self.current_module or 'IDLE'
        # Tandai jika reverse_tcp sedang berjalan
        if "reverse_tcp" in current_module.lower() and active_listeners_count > 0:
            current_module = f"🚀 {current_module}"

        # === HTML TANPA LISTENER DETAILS & TARGET OS BREAKDOWN ===
        html = f"""
        <div style="line-height:1.5;">
            <div style="text-align:center; color:#ff1744; font-size:11pt; letter-spacing:1px; margin-bottom:8px;">
                <b>SESSION CONTROL</b>
            </div>
            <hr style="border:1px solid #7d0101; margin:8px 0;">

            <b style="color:#ff5252;">OPERATOR</b>     : <span style="color:#ffffff;">{user}</span><br>
            <b style="color:#ff5252;">LHOST</b>        : <span style="color:#f1fa8c;">{local_ip}</span><br>
            <b style="color:#ff5252;">PUBLIC IP</b>    : <span style="color:#ff79c6;">{public_ip}</span><br>
            <b style="color:#ff5252;">LISTENERS</b>    : <span style="color:#8be9fd;">{active_listeners_count} ACTIVE</span><br>
            <b style="color:#ff5252;">SESSIONS</b>     : <span style="color:#bd93f9;">{total_sess} TOTAL</span> | <span style="color:#50fa7b;">{online_sess} ALIVE</span><br>
            <b style="color:#ff5252;">TARGET OS</b>    : <span style="color:#ffffff;">{os_summary}</span><br>
            <b style="color:#ff5252;">MODULES</b>      : <span style="color:#ffffff;">{len(self.framework.modules)}</span><br>
            <b style="color:#ff5252;">CURRENT</b>      : <span style="color:#ff5552;">{current_module}</span><br>
            <b style="color:#ff5252;">PROXY</b>        : <span style="color:{proxy_color};">{proxy_status}</span> {proxy_detail}<br>
            <b style="color:#ff5252;">UPTIME</b>       : <span style="color:#ffb86c;">{uptime_str}</span><br>
            <b style="color:#ff5252;">PLATFORM</b>     : <span style="color:#6272a4;">{platform.system()} {platform.machine()}</span><br>
            
            <div style="margin-top:10px; font-size:8pt; color:#444; text-align:center;">
                LazyFramework GUI •
            </div>
        </div>
        """

        self.session_info.setHtml(html)


    def update_listener_status(self, active, lhost=None, lport=None):
        # Update internal session values
        self.framework.session["LISTENER_ACTIVE"] = active

        if lhost:
            self.framework.session["LHOST"] = lhost
        if lport:
            self.framework.session["LPORT"] = lport

        # GANTI INI:
        # self.update_info_panel()  # ← Ini akan error
        
        # MENJADI INI:
        self.update_session_info()  # ← Gunakan method yang benar


    def update_info_panel(self):
        """Update header info panel (atas GUI)"""
        # HAPUS METHOD INI SELURUHNYA
        pass


    
    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key.Key_Up:
            # Command history up
            if self.command_history and self.history_index > 0:
                self.history_index -= 1
                self.command_input.setText(
                    self.command_history[self.history_index])
        elif event.key() == Qt.Key.Key_Down:
            # Command history down
            if self.command_history and self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self.command_input.setText(
                    self.command_history[self.history_index])
            elif self.history_index == len(self.command_history) - 1:
                self.history_index = len(self.command_history)
                self.command_input.clear()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Cleanup saat aplikasi ditutup"""
        if hasattr(self, 'browser') and self.browser:
            self.browser.deleteLater()
        event.accept()

    def open_in_browser(self, url):
        """Show the browser panel dengan software rendering"""
        if self.browser:
            self.browser_controls_widget.show()
            self.browser.show()
            self.browser_placeholder.hide()
            self.open_browser_btn.setEnabled(False)
            self.close_browser_btn.setEnabled(True)
            self.append_output("[dim]Browser panel shown[/]")
            self.update_browser_buttons()
            return
            
        # Buat browser dengan software rendering
        self.browser = QWebEngineView()
        
        # Force software rendering
        self.browser.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        
        # Disable hardware acceleration
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, False)
        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, False)
        settings.setAttribute(QWebEngineSettings.AutoLoadIconsForPage, False)
        settings.setAttribute(QWebEngineSettings.ErrorPageEnabled, False)
        settings.setAttribute(QWebEngineSettings.ScreenCaptureEnabled, False)
        """Open URL in browser panel"""
        # Pastikan browser panel terbuka
        if not self.browser or not self.browser.isVisible():
            self.open_browser_panel()
            # Tunggu sebentar untuk browser siap
            QTimer.singleShot(500, lambda: self._load_url(url))
        else:
            self._load_url(url)
            
    def _load_url(self, url):
        """Internal method to load URL in browser"""
        try:
            self.browser.setUrl(QUrl(url))
            self.append_output(f"[green]Opened in browser: {url}[/]")
        except Exception as e:
            self.append_output(f"[red]Failed to open URL: {e}[/]")


    

def run_gui():
    """Run the GUI application dengan auto-detect platform"""
    import platform
    # Auto-detect platform backend
    system = platform.system()
    
    if system == "Linux":
        # Cek apakah Wayland available
        wayland_display = os.environ.get('WAYLAND_DISPLAY')
        xdg_desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        
        if wayland_display and ('gnome' in xdg_desktop or 'kde' in xdg_desktop or 'mate' in xdg_desktop):
            os.environ['QT_QPA_PLATFORM'] = 'wayland'
            print("Using Wayland backend")
        else:
            os.environ['QT_QPA_PLATFORM'] = 'xcb'
            print("Using XCB backend")
            
    elif system == "Windows":
        os.environ['QT_QPA_PLATFORM'] = 'windows'
        print("Using Windows backend")
        
    elif system == "Darwin":  # macOS
        os.environ['QT_QPA_PLATFORM'] = 'cocoa'
        print("Using macOS Cocoa backend")
    else:
        os.environ['QT_QPA_PLATFORM'] = 'xcb'
        print("Using fallback XCB backend")
    
    # Fix environment variables for WebEngine
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--no-sandbox --disable-gpu-sandbox'
    os.environ['QT_QUICK_BACKEND'] = 'software'
    os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
    
    # Fix SSL certificates untuk Linux
    if platform.system() == "Linux":
        os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = '1'
        # Coba berbagai path certificate yang umum
        cert_paths = [
            '/etc/ssl/certs/ca-certificates.crt',
            '/etc/ssl/certs/ca-bundle.crt',
            '/etc/pki/tls/certs/ca-bundle.crt'
        ]
        for cert_path in cert_paths:
            if os.path.exists(cert_path):
                os.environ['SSL_CERT_FILE'] = cert_path
                os.environ['REQUESTS_CA_BUNDLE'] = cert_path
                break
    
    app = QApplication(sys.argv)
    app.setApplicationName("LazyFramework GUI")
    app.setApplicationVersion("2.0")

    # Set dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(palette)

    win = LazyFrameworkGUI()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
  run_gui()