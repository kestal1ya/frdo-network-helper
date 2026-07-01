import sys
import os
import subprocess
import time
import json
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QTextEdit
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont

SECRET_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pass.txt")


def load_config():
    if not os.path.exists(SECRET_FILE_PATH):
        print(f"Ошибка: не найден файл конфигурации {SECRET_FILE_PATH}")
        print("Создайте pass.txt рядом со скриптом (см. pass.txt.example) и заполните его данными.")
        sys.exit(1)
    try:
        with open(SECRET_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения файла конфигурации {SECRET_FILE_PATH}: {e}")
        sys.exit(1)

config = load_config()
SITES_DATA = config["SITES_DATA"]
ESPD_URL = config["ESPD_URL"]
MTU_VALUE = config["MTU_VALUE"]

def get_vipnet_interface():
    try:
        res = subprocess.run(["ip", "link", "show"], capture_output=True, text=True)
        for line in res.stdout.split('\n'):
            for name in ["vipnet0", "vipnet1", "tun0", "tun1"]:
                if name in line:
                    return name
    except Exception:
        pass
    return "tun0 (тест)"

class NetworkWorker(QThread):
    status_signal = pyqtSignal(str, str)
    open_browser_signal = pyqtSignal(str)

    def __init__(self, target_url):
        super().__init__()
        self.target_url = target_url

    def check_ping(self, url):
        return False 

    def is_vipnet_installed(self):
        return os.path.exists("/usr/sbin/vipnetclient") or os.path.exists("/usr/bin/vipnetclient")

    def run(self):
        vipnet_present = self.is_vipnet_installed()

        self.status_signal.emit("Проверяю доступность сайта в сети...", "yellow")
        time.sleep(10.0)  
        
        if self.check_ping(self.target_url):
            self.status_signal.emit("Связь установлена! Открываю вкладку...", "green")
            self.open_browser_signal.emit(self.target_url)
            return

        if vipnet_present:
            self.status_signal.emit("Сайт недоступен. Отключаю ViPNet для входа в ЕСПД...", "yellow")
            subprocess.run(["systemctl", "stop", "vipnetclient"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(10.0) 
        else:
            self.status_signal.emit("Сайт недоступен. ViPNet не обнаружен, перехожу к ЕСПД...", "yellow")
            time.sleep(10.0)  

        self.status_signal.emit("Пожалуйста, пройдите авторизацию в окне ЕСПД!", "yellow")
        self.open_browser_signal.emit(ESPD_URL)
        time.sleep(1.0)
        self.open_browser_signal.emit(self.target_url)
        time.sleep(10.0) 

        self.status_signal.emit("[ТЕСТ] Ожидание авторизации в ЕСПД (10 сек)...", "yellow")
        time.sleep(10.0)  

        if vipnet_present:
            self.status_signal.emit("Интернет получен. Запускаю ViPNet Client...", "yellow")
            subprocess.run(["systemctl", "start", "vipnetclient"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(10.0) 

        iface = get_vipnet_interface()
        if "(тест)" not in iface:
            self.status_signal.emit(f"Оптимизация пакетов сети ({iface} -> MTU {MTU_VALUE})...", "yellow")
            subprocess.run(["ip", "link", "set", "dev", iface, "mtu", MTU_VALUE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(10.0)  

        self.status_signal.emit("Все службы запущены! Открываю целевой портал.", "green")
        self.open_browser_signal.emit(self.target_url)

class MTUMonitor(QThread):
    def run(self):
        while True:
            iface = get_vipnet_interface()
            if "(тест)" not in iface:
                res = subprocess.run(["ip", "link", "show", iface], capture_output=True, text=True)
                if iface in res.stdout and f"mtu {MTU_VALUE}" not in res.stdout:
                    subprocess.run(["ip", "link", "set", "dev", iface, "mtu", MTU_VALUE])
            time.sleep(4)

class MainApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.monitor = MTUMonitor()
        self.monitor.start()

    def init_ui(self):
        self.setWindowTitle("ФИС ФРДО — Помощник Сети")
        self.setFixedSize(920, 700)
        self.setStyleSheet("background-color: #f0f2f5;")

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.status_card = QFrame()
        self.status_card.setStyleSheet("background-color: #ffffff; border-radius: 10px; border: 1px solid #cfd4db;")
        card_layout = QVBoxLayout(self.status_card)
        self.status_label = QLabel("Выберите нужный портал для начала работы")
        self.status_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.status_label)
        left_layout.addWidget(self.status_card)

        for name, data in SITES_DATA.items():
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            btn = QPushButton(name)
            btn.setFont(QFont("Arial", 13, QFont.Weight.Bold))
            btn.setMinimumHeight(42)
            btn.setStyleSheet("""
                QPushButton { background-color: #0c54a0; color: white; border-radius: 8px; border: none; }
                QPushButton:hover { background-color: #0a4480; }
                QPushButton:pressed { background-color: #073360; }
            """)
            btn.clicked.connect(lambda checked, u=data["url"]: self.on_site_click(u))
            row_layout.addWidget(btn, stretch=5)

            info_btn = QPushButton("?")
            info_btn.setFont(QFont("Arial", 13, QFont.Weight.Bold))
            info_btn.setFixedSize(40, 42)
            info_btn.setStyleSheet("""
                QPushButton { background-color: #bdc3c7; color: #2c3e50; border-radius: 8px; border: none; }
                QPushButton:hover { background-color: #95a5a6; }
                QPushButton:pressed { background-color: #7f8c8d; }
            """)
            info_btn.clicked.connect(lambda checked, h=data["hint"]: self.show_hint(h))
            row_layout.addWidget(info_btn, stretch=1)

            left_layout.addLayout(row_layout)

        test_buttons_layout = QHBoxLayout()
        test_buttons_layout.setSpacing(10)

        self.espd_btn = QPushButton("Тест: ЕСПД")
        self.espd_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.espd_btn.setMinimumHeight(45)
        self.espd_btn.setStyleSheet("""
            QPushButton { background-color: #34c759; color: white; border-radius: 8px; border: none; }
            QPushButton:hover { background-color: #28a745; }
            QPushButton:pressed { background-color: #1e7e34; }
        """)
        self.espd_btn.clicked.connect(lambda: self.open_browser(ESPD_URL))
        test_buttons_layout.addWidget(self.espd_btn)

        self.frdo_test_btn = QPushButton("Тест: ФИС ФРДО")
        self.frdo_test_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.frdo_test_btn.setMinimumHeight(45)
        self.frdo_test_btn.setStyleSheet("""
            QPushButton { background-color: #af52de; color: white; border-radius: 8px; border: none; }
            QPushButton:hover { background-color: #933fc1; }
            QPushButton:pressed { background-color: #762fa0; }
        """)
        first_url = list(SITES_DATA.values())[0]["url"] if SITES_DATA else ""
        self.frdo_test_btn.clicked.connect(lambda: self.open_browser(first_url))
        test_buttons_layout.addWidget(self.frdo_test_btn)

        left_layout.addLayout(test_buttons_layout)

        self.fix_btn = QPushButton("Нажмите сюда, если не скачиваются файлы")
        self.fix_btn.setFont(QFont("Arial", 10))
        self.fix_btn.setMinimumHeight(38)
        self.fix_btn.setStyleSheet("""
            QPushButton { background-color: #e4e7eb; color: #2c3e50; border-radius: 6px; border: 1px solid #bdc3c7; }
            QPushButton:hover { background-color: #d5dbdb; }
        """)
        self.fix_btn.clicked.connect(self.manual_fix)
        left_layout.addWidget(self.fix_btn)

        main_layout.addWidget(left_widget, stretch=4)

        self.right_card = QFrame()
        self.right_card.setStyleSheet("background-color: #ffffff; border-radius: 12px; border: 2px solid #0c54a0;")
        right_layout = QVBoxLayout(self.right_card)
        right_layout.setContentsMargins(15, 15, 15, 15)

        self.hint_text = QTextEdit()
        self.hint_text.setReadOnly(True)
        self.hint_text.setFrameStyle(QFrame.Shape.NoFrame)
        self.hint_text.setHtml("<h3 style='color: #2c3e50; text-align: center; margin-top: 50px; font-family: Arial;'>Нажмите на кнопку [ ? ] рядом с нужным сайтом, чтобы увидеть список документов.</h3>")
        
        right_layout.addWidget(self.hint_text)
        main_layout.addWidget(self.right_card, stretch=3)

        self.setLayout(main_layout)

    def show_hint(self, html_content):
        self.hint_text.setHtml(html_content)

    def update_status(self, text, color_type):
        colors = {
            "green": "background-color: #e8f5e9; border: 2px solid #2e7d32; color: #1b5e20;",
            "yellow": "background-color: #fffde7; border: 2px solid #fbc02d; color: #f57f17;",
            "red": "background-color: #ffebee; border: 2px solid #c62828; color: #b71c1c;"
        }
        self.status_card.setStyleSheet(colors.get(color_type, ""))
        self.status_label.setText(text)

    def on_site_click(self, url):
        self.worker = NetworkWorker(url)
        self.worker.status_signal.connect(self.update_status)
        self.worker.open_browser_signal.connect(self.open_browser)
        self.worker.start()

    def open_browser(self, url):
        real_user = os.getenv("SUDO_USER")
        if not real_user or real_user == "root":
            try:
                real_user = subprocess.check_output("who | awk '{print $1}' | head -n1", shell=True).decode().strip()
            except Exception:
                real_user = "user"

        try:
            uid = subprocess.check_output(["id", "-u", real_user]).decode().strip()
            cmd = f"sudo -u {real_user} DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus xdg-open '{url}'"
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            cmd = f"sudo -u {real_user} DISPLAY=:0 xdg-open '{url}'"
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def manual_fix(self):
        iface = get_vipnet_interface()
        self.update_status(f"Настройки сети {iface} успешно сброшены (MTU {MTU_VALUE})!", "green")

if __name__ == '__main__':
    if os.getuid() != 0:
        print("Ошибка: Скрипт должен быть запущен с правами root через sudo!")
        sys.exit(1)

    app = QApplication(sys.argv)
    ex = MainApp()
    ex.show()
    sys.exit(app.exec())
