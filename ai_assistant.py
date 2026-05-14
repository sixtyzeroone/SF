#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus Framework — AI Assistant Widget
Provider: OpenRouter (openrouter.ai)
"""

import json
import requests
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QComboBox,
    QSplitter, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer
from PyQt6.QtGui import QFont, QTextCursor

# ─── OpenRouter ────────────────────────────────────────────────────────────────
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Model gratis & murah yang tersedia di OpenRouter
OPENROUTER_MODELS = [
    "inclusionai/ring-2.6-1t:free",
    "openai/gpt-oss-120b:free",
    "google/gemma-4-26b-a4b-it:free",
    "meta-llama/llama-3.3-8b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-2-9b-it:free",
    "deepseek/deepseek-r1:free",
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-sonnet-4-5",
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "mistralai/mistral-small",
    "google/gemini-flash-1.5",
]

SYSTEM_PROMPT = """You are LazyAI, a penetration testing assistant embedded in the Lazy Framework.

Your role:
- Analyze scan and enumeration output, explain findings clearly
- Suggest next enumeration steps based on discovered information
- Explain CVEs, vulnerabilities, and attack vectors
- Interpret tool output: nmap, smbmap, enum4linux, nikto, gobuster, etc.
- Recommend which Nexus modules to use next
- Answer security methodology and concept questions

Rules:
- Be concise and actionable
- Use plain text without markdown headers
- Always remind the user that any action requires explicit written authorization
"""

# ─── Streaming Worker ──────────────────────────────────────────────────────────
class AIWorker(QObject):
    token_received = pyqtSignal(str)
    finished       = pyqtSignal()
    error          = pyqtSignal(str)

    def __init__(self, model, api_key, messages, site_url="", site_name="Lazy Framework"):
        super().__init__()
        self.model     = model
        self.api_key   = api_key
        self.messages  = messages
        self.site_url  = site_url
        self.site_name = site_name
        self._stop     = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            headers = {
                "Authorization":  f"Bearer {self.api_key}",
                "Content-Type":   "application/json",
                "HTTP-Referer":   self.site_url or "https://lazyframework.local",
                "X-Title":        self.site_name,
            }
            payload = {
                "model":    self.model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages,
                "stream":   True,
            }
            with requests.post(OPENROUTER_URL, headers=headers, json=payload,
                               stream=True, timeout=120) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if self._stop:
                        break
                    if not line or line == b"data: [DONE]":
                        continue
                    raw = line.decode().removeprefix("data: ")
                    try:
                        data  = json.loads(raw)
                        token = data["choices"][0]["delta"].get("content", "")
                        if token:
                            self.token_received.emit(token)
                    except Exception:
                        pass

        except requests.exceptions.ConnectionError:
            self.error.emit("Tidak bisa terhubung ke OpenRouter. Cek koneksi internet.")
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else "?"
            if code == 401:
                self.error.emit("API key salah atau tidak valid (401).")
            elif code == 402:
                self.error.emit("Kredit OpenRouter habis (402). Top up di openrouter.ai.")
            elif code == 429:
                self.error.emit("Rate limit (429). Tunggu sebentar lalu coba lagi.")
            else:
                self.error.emit(f"HTTP error {code}: {e}")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


# ─── Main Widget ───────────────────────────────────────────────────────────────
class AIAssistantWidget(QWidget):

    # Status constants
    STATUS_DISCONNECTED = "disconnected"
    STATUS_CONNECTING = "connecting"
    STATUS_CONNECTED = "connected"
    STATUS_AUTH_FAILED = "auth_failed"
    STATUS_CHANNEL_ACTIVE = "channel_active"

    def __init__(self, framework=None, parent=None):
        super().__init__(parent)
        self.framework     = framework
        self.chat_history  = []
        self.worker        = None
        self.worker_thread = None
        self._ai_buf       = ""
        self.current_status = self.STATUS_DISCONNECTED
        self._build_ui()
        self._load_api_key()

    # ── Build UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Config bar ──
        cfg = QHBoxLayout()

        self.model_cb = QComboBox()
        self.model_cb.addItems(OPENROUTER_MODELS)
        self.model_cb.setEditable(True)
        self.model_cb.setToolTip("Pilih model atau ketik manual.")

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("API Key (sk-or-...)")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setStyleSheet("""
            QLineEdit {
                background: #161b22; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 4px; padding: 4px 8px;
            }
            QLineEdit:focus { border-color: #bd93f9; }
        """)
        self.api_key_input.textChanged.connect(self._on_api_key_changed)

        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setFixedWidth(30)
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setToolTip("Tampilkan/sembunyikan API key")
        self.show_key_btn.toggled.connect(
            lambda on: self.api_key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )

        self.status_lbl = QLabel("○ Disconnected")
        self.status_lbl.setStyleSheet("color:#6272a4; font-size:11px;")

        # Tombol Connect dengan teks dinamis
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setFixedWidth(110)
        self.connect_btn.clicked.connect(self.toggle_connection)
        self._update_button_style_and_text()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(55)
        clear_btn.clicked.connect(self._clear_chat)

        cfg.addWidget(self.model_cb, 2)
        cfg.addWidget(self.api_key_input, 3)
        cfg.addWidget(self.show_key_btn)
        cfg.addWidget(self.status_lbl)
        cfg.addWidget(self.connect_btn)
        cfg.addWidget(clear_btn)
        root.addLayout(cfg)

        # ── Splitter: chat | context ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Chat panel
        chat_frame = QFrame()
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(4)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Hack", 13))
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background: #0d1117; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 4px; padding: 8px;
            }
        """)
        self._append_bubble("system",
            "LazyAI.\nOffensive intelligence terminal online.\n"
            "Click Connect to initialize provider access."
        )

        input_row = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask anything... (Enter)")
        self.input_box.setFont(QFont("Courier New", 10))
        self.input_box.setStyleSheet("""
            QLineEdit {
                background: #161b22; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 4px; padding: 6px 10px;
            }
            QLineEdit:focus { border-color: #919090; }
        """)
        self.input_box.returnPressed.connect(self.send_message)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedWidth(65)
        self.send_btn.setStyleSheet(self._btn("#111113", "#fff"))
        self.send_btn.clicked.connect(self.send_message)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedWidth(55)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(self._btn("#050404", "#fff"))
        self.stop_btn.clicked.connect(self._stop_generation)

        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_btn)
        input_row.addWidget(self.stop_btn)

        chat_layout.addWidget(self.chat_display)
        chat_layout.addLayout(input_row)

        # Context panel
        ctx_frame = QFrame()
        ctx_layout = QVBoxLayout(ctx_frame)
        ctx_layout.setContentsMargins(0, 0, 0, 0)
        ctx_layout.setSpacing(4)

        ctx_layout.addWidget(self._lbl("Output context (auto / manual):"))

        self.context_box = QTextEdit()
        self.context_box.setPlaceholderText(
            "Output terminal masuk otomatis.\nAtau paste manual."
        )
        self.context_box.setFont(QFont("Hack", 9))
        self.context_box.setStyleSheet("""
            QTextEdit {
                background: #0d1117; color: #8b949e;
                border: 1px solid #30363d; border-radius: 4px; padding: 6px;
            }
        """)

        ctx_btns = QHBoxLayout()
        analyze_btn = QPushButton("Analyze Output")
        analyze_btn.setStyleSheet(self._btn("#238636", "#fff"))
        analyze_btn.clicked.connect(self._analyze_context)
        clear_ctx = QPushButton("Clear")
        clear_ctx.setFixedWidth(55)
        clear_ctx.setStyleSheet(self._btn("#333", "#aaa"))
        clear_ctx.clicked.connect(self.context_box.clear)
        ctx_btns.addWidget(analyze_btn)
        ctx_btns.addWidget(clear_ctx)

        ctx_layout.addWidget(self.context_box)
        ctx_layout.addLayout(ctx_btns)
        ctx_layout.addWidget(self._lbl("Quick prompts:"))

        for label, prompt in [
            ("Next Steps", "Berdasarkan output di context, rekomendasikan langkah selanjutnya."),
            ("Find Vulns", "Identifikasi potensi vulnerability dari output ini."),
            ("Explain Findings", "Jelaskan temuan dari output ini dengan bahasa sederhana."),
            ("Suggest Modules", "Module Nexus mana yang cocok digunakan selanjutnya?"),
            ("CVE Check", "Adakah CVE relevan dengan service/versi yang ditemukan?"),
            ("Port Summary", "Buat ringkasan port dan service yang ditemukan."),
        ]:
            b = QPushButton(label)
            b.setStyleSheet("""
                QPushButton {
                    background: #161b22; color: #8b949e;
                    border: 1px solid #30363d; border-radius: 4px;
                    padding: 5px 8px; text-align: left; font-size: 11px;
                }
                QPushButton:hover { background: #21262d; color: #e6edf3; }
            """)
            b.clicked.connect(lambda _, p=prompt: self.send_message(p))
            ctx_layout.addWidget(b)

        ctx_layout.addStretch()

        splitter.addWidget(chat_frame)
        splitter.addWidget(ctx_frame)
        splitter.setSizes([620, 280])
        root.addWidget(splitter)

    def _btn(self, bg, fg):
        return (f"QPushButton {{ background:{bg}; color:{fg}; border:none; "
                f"border-radius:4px; padding:6px; font-weight:bold; }}"
                f"QPushButton:disabled {{ background:#333; color:#555; }}")

    def _lbl(self, text):
        l = QLabel(text)
        l.setStyleSheet("color:#6272a4; font-size:11px;")
        return l

    # ── Update Button Style & Text Based on Status ──────────────────────────────
    def _update_button_style_and_text(self):
        """Update tombol berdasarkan status saat ini"""
        if self.current_status == self.STATUS_DISCONNECTED:
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background: #238636; color: white;
                    border: none; border-radius: 4px; padding: 6px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #2ea043; }
            """)
            self.status_lbl.setStyleSheet("color:#6272a4; font-size:11px;")
            self.status_lbl.setText("○ Disconnected")

        elif self.current_status == self.STATUS_CONNECTING:
            self.connect_btn.setText("Connecting...")
            self.connect_btn.setEnabled(False)
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background: #f1fa8c; color: #1e1e1e;
                    border: none; border-radius: 4px; padding: 6px;
                    font-weight: bold;
                }
            """)
            self.status_lbl.setStyleSheet("color:#f1fa8c; font-size:11px;")
            self.status_lbl.setText("◌ Connecting...")

        elif self.current_status == self.STATUS_CONNECTED:
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setEnabled(True)
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background: #da3633; color: white;
                    border: none; border-radius: 4px; padding: 6px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #f85149; }
            """)
            self.status_lbl.setStyleSheet("color:#50fa7b; font-size:11px;")
            self.status_lbl.setText("● Connected")

        elif self.current_status == self.STATUS_AUTH_FAILED:
            self.connect_btn.setText("Auth Failed")
            self.connect_btn.setEnabled(True)
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background: #8B0000; color: #ff8888;
                    border: 1px solid #ff5555;
                    border-radius: 4px; padding: 6px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #aa0000; }
            """)
            self.status_lbl.setStyleSheet("color:#ff5555; font-size:11px;")
            self.status_lbl.setText("● Auth Failed")

        elif self.current_status == self.STATUS_CHANNEL_ACTIVE:
            self.connect_btn.setText("Channel Active")
            self.connect_btn.setEnabled(True)
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background: #50fa7b; color: #1e1e1e;
                    border: none; border-radius: 4px; padding: 6px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #69ff94; }
            """)
            self.status_lbl.setStyleSheet("color:#50fa7b; font-size:11px;")
            self.status_lbl.setText("● Channel Active")

    def _reset_from_auth_failed(self):
        """Reset dari status Auth Failed ke Disconnected (dipanggil via singleShot)"""
        if self.current_status == self.STATUS_AUTH_FAILED:
            self.current_status = self.STATUS_DISCONNECTED
            self._update_button_style_and_text()
            self.api_key_input.setEnabled(True)
            self.model_cb.setEnabled(True)
            self.show_key_btn.setEnabled(True)

    def _on_api_key_changed(self):
        """Jika API key berubah saat status Auth Failed, reset tombol"""
        if self.current_status == self.STATUS_AUTH_FAILED:
            self.current_status = self.STATUS_DISCONNECTED
            self._update_button_style_and_text()
            self.connect_btn.setEnabled(True)

    # ── Toggle Connection ──────────────────────────────────────────────────────
    def toggle_connection(self):
        """Toggle koneksi On/Off"""
        if self.current_status == self.STATUS_CONNECTED or self.current_status == self.STATUS_CHANNEL_ACTIVE:
            self.disconnect()
        elif self.current_status == self.STATUS_DISCONNECTED or self.current_status == self.STATUS_AUTH_FAILED:
            self._connect()

    def _connect(self):
        """Melakukan koneksi ke API"""
        key = self.api_key_input.text().strip()
        if not key:
            self.current_status = self.STATUS_AUTH_FAILED
            self._update_button_style_and_text()
            self._append_bubble("error", "API key cannot be empty!")
            # Auto reset setelah 3 detik menggunakan QTimer.singleShot
            QTimer.singleShot(3000, self._reset_from_auth_failed)
            return

        self.current_status = self.STATUS_CONNECTING
        self._update_button_style_and_text()
        self.api_key_input.setEnabled(False)
        self.model_cb.setEnabled(False)
        self.show_key_btn.setEnabled(False)

        def check():
            try:
                r = requests.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=8
                )
                if r.status_code == 200:
                    data = r.json().get("data", {})
                    label = data.get("label", "")
                    self.current_status = self.STATUS_CONNECTED
                    self._save_api_key(key)
                    # Update UI di main thread
                    QTimer.singleShot(0, lambda: self._append_bubble("system", f"Connected! Account: {label}"))
                elif r.status_code == 401:
                    self.current_status = self.STATUS_AUTH_FAILED
                    QTimer.singleShot(0, lambda: self._append_bubble("error", "API key invalid (401)"))
                    # Auto reset setelah 3 detik
                    QTimer.singleShot(3000, self._reset_from_auth_failed)
                else:
                    self.current_status = self.STATUS_AUTH_FAILED
                    QTimer.singleShot(0, lambda: self._append_bubble("error", f"Error: {r.status_code}"))
                    QTimer.singleShot(3000, self._reset_from_auth_failed)
            except Exception as e:
                self.current_status = self.STATUS_AUTH_FAILED
                QTimer.singleShot(0, lambda: self._append_bubble("error", f"Failed: {e}"))
                QTimer.singleShot(3000, self._reset_from_auth_failed)
            finally:
                # Update UI di main thread
                QTimer.singleShot(0, self._update_ui_after_connect)

        threading.Thread(target=check, daemon=True).start()

    def _update_ui_after_connect(self):
        """Update UI setelah proses koneksi selesai"""
        self._update_button_style_and_text()

        if self.current_status == self.STATUS_CONNECTED:
            self.api_key_input.setEnabled(False)
            self.model_cb.setEnabled(False)
            self.show_key_btn.setEnabled(False)
            QTimer.singleShot(0, lambda: self._append_bubble("assistant", "Channel active. Ready for analysis."))
        elif self.current_status == self.STATUS_AUTH_FAILED:
            self.api_key_input.setEnabled(True)
            self.model_cb.setEnabled(True)
            self.show_key_btn.setEnabled(True)

    def disconnect(self):
        """Memutus koneksi"""
        self.current_status = self.STATUS_DISCONNECTED
        self._update_button_style_and_text()

        self.api_key_input.setEnabled(True)
        self.model_cb.setEnabled(True)
        self.show_key_btn.setEnabled(True)

        if self.worker:
            self.worker.stop()

        self._append_bubble("system", "Disconnected.")

    def set_channel_active(self, active=True):
        """Set status channel active"""
        if active:
            self.current_status = self.STATUS_CHANNEL_ACTIVE
            self._append_bubble("system", "Channel active - AI analysis in progress")
        else:
            if self.current_status == self.STATUS_CHANNEL_ACTIVE:
                self.current_status = self.STATUS_CONNECTED
                self._append_bubble("system", "Channel inactive - back to idle")
        self._update_button_style_and_text()

    def _save_api_key(self, key):
        """Simpan API key ke framework session"""
        if self.framework:
            self.framework.session['openrouter_api_key'] = key

    def _load_api_key(self):
        """Load API key dari session"""
        if self.framework and 'openrouter_api_key' in self.framework.session:
            key = self.framework.session['openrouter_api_key']
            if key:
                self.api_key_input.setText(key)

    # ── Chat ──────────────────────────────────────────────────────────────────────
    def _append_bubble(self, role, text):
        colors = {"user": "#bd93f9", "assistant": "#50fa7b",
                  "system": "#6272a4", "error": "#ff5555"}
        labels = {"user": "You", "assistant": "LazyAI",
                  "system": "System", "error": "Error"}
        c = colors.get(role, "#fff")
        l = labels.get(role, role)
        self.chat_display.append(
            f'<span style="color:{c};font-weight:bold;">[{l}]</span>'
        )
        self.chat_display.append(
            f'<span style="color:#e6edf3;white-space:pre-wrap;">{text}</span><br>'
        )
        self.chat_display.ensureCursorVisible()

    def _clear_chat(self):
        self.chat_history.clear()
        self.chat_display.clear()
        self._ai_buf = ""

        self.chat_display.append(
            '<span style="color:#444;">[ session cleared ]</span><br>'
        )

    # ── Send ──────────────────────────────────────────────────────────────────────
    def send_message(self, text=None):
        if text is None:
            text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()

        if self.current_status not in [self.STATUS_CONNECTED, self.STATUS_CHANNEL_ACTIVE]:
            self._append_bubble("error", "Not connected. Click 'Connect' first.")
            return

        key = self.api_key_input.text().strip()
        if not key:
            self._append_bubble("error", "API key is empty.")
            return

        self._append_bubble("user", text)
        self.chat_history.append({"role": "user", "content": text})
        self._start_worker(key)

    def _analyze_context(self):
        ctx = self.context_box.toPlainText().strip()
        if not ctx:
            self._append_bubble("system", "Context is empty. Paste scan output first.")
            return
        self.send_message(
            "Analisis output berikut. Identifikasi service, versi, "
            "potensi vulnerability, dan rekomendasikan langkah selanjutnya:\n\n" + ctx
        )

    # ── Worker ────────────────────────────────────────────────────────────────────
    def _start_worker(self, api_key):
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._ai_buf = ""
        self.chat_display.append(
            '<span style="color:#50fa7b;font-weight:bold;">[LazyAI]\t</span>'
        )

        self.worker = AIWorker(
            model=self.model_cb.currentText(),
            api_key=api_key,
            messages=list(self.chat_history),
        )
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.token_received.connect(self._on_token)
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker_thread.start()

    def _on_token(self, token):
        self._ai_buf += token
        c = self.chat_display.textCursor()
        c.movePosition(QTextCursor.MoveOperation.End)
        c.insertText(token)
        self.chat_display.ensureCursorVisible()

    def _on_done(self):
        if self._ai_buf:
            self.chat_history.append({"role": "assistant", "content": self._ai_buf})
        self.chat_display.append("<br>")
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()

    def _on_error(self, msg):
        self.chat_display.append(
            f'<span style="color:#ff5555;">{msg}</span><br>'
        )
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _stop_generation(self):
        if self.worker:
            self.worker.stop()

    # ── Public API ────────────────────────────────────────────────────────────────
    def inject_output(self, text: str):
        """Auto-inject output terminal ke context box"""
        current = self.context_box.toPlainText()
        merged = (current + "\n" + text).strip()
        self.context_box.setPlainText(merged[-8000:])

    def ask(self, question: str):
        """Kirim pertanyaan langsung ke AI"""
        self.send_message(question)

    def run_agent_mode(self, loaded_module):
        """
        Run agent mode to auto-configure module options
        Dipanggil dari gui.py ketika module diload
        """
        if not loaded_module:
            return
            
        if not self.current_status == self.STATUS_CONNECTED:
            self._append_bubble("system", "⚠️ Agent mode: Connect to AI first")
            return
            
        # Get module info
        module_name = loaded_module.name.replace("modules/", "")
        
        # Get module options
        opts = loaded_module.get_options()
        
        # Build context message
        options_text = "\n".join([f"  - {name}: {info.get('description', 'No description')}" 
                                for name, info in opts.items()])
        
        # Send to AI
        prompt = f"""Module '{module_name}' has been loaded.

    Module Options:
    {options_text}

    Please analyze these options and suggest appropriate values based on common penetration testing practices.

    If you detect a TARGET or RHOST option, suggest using the target from context or ask the user.

    Be concise and actionable."""
        
        self.send_message(prompt)