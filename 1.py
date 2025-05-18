import time
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt5.QtCore import Qt
import socket
import threading
import sys
import os
from PyQt5.QtGui import QPixmap
from io import BytesIO


class MainWindow(QMainWindow):
    update_image_signal = QtCore.pyqtSignal(bytes)
    send_input_signal = QtCore.pyqtSignal(str)

    def __init__(self):
        super(MainWindow, self).__init__()

        self.label = QLabel(self)
        self.setCentralWidget(self.label)

        # Настройка окна
        self.setWindowTitle("Remote Control Viewer")
        self.setFocusPolicy(Qt.StrongFocus)  # Для захвата клавиатуры

        # Инициализация сервера
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.settimeout(10)
        self.host = "localhost"
        self.port = 8080
        self.server.bind((self.host, self.port))
        self.server.listen(1)

        # Создаем поток для прослушивания соединений
        listen_thread = threading.Thread(target=self.listen)
        listen_thread.daemon = True
        listen_thread.start()

        # Подключаем сигналы
        self.update_image_signal.connect(self.update_image)
        self.send_input_signal.connect(self.send_input)

    def listen(self):
        try:
            self.conn, self.addr = self.server.accept()
            print(f"Connected - {self.addr}")
            self.conn.settimeout(5)
        except socket.timeout:
            print("Ошибка: время ожидания подключения истекло.")
            return

        while True:
            print("Ожидание данных от клиента...")
            img_data = bytearray()
            while True:
                try:
                    data = self.conn.recv(8192)
                    if data.endswith(b'END'):
                        img_data += data[:-3]
                        break
                    img_data += data
                except socket.timeout:
                    print("Ошибка: время ожидания данных истекло.")
                    break
                except Exception as e:
                    print(f"Ошибка при получении данных: {e}")
                    break

            if img_data:
                print(f"Получено изображение. Размер данных: {len(img_data)} байт.")
                self.update_image_signal.emit(bytes(img_data))
            else:
                print("Ошибка: изображение пустое.")

    @QtCore.pyqtSlot(bytes)
    def update_image(self, img_data):
        print("Обновление изображения...")
        pixmap = QPixmap()
        if pixmap.loadFromData(img_data, "JPEG"):
            self.label.setPixmap(pixmap)
            self.resize(pixmap.width(), pixmap.height())
            print("Изображение обновлено.")
        else:
            print("Ошибка загрузки изображения.")

    def mousePressEvent(self, event):
        """Обработка кликов мыши"""
        x = event.x()
        y = event.y()

        if event.button() == Qt.LeftButton:
            button = 'left'
        elif event.button() == Qt.RightButton:
            button = 'right'
        elif event.button() == Qt.MiddleButton:
            button = 'middle'
        else:
            button = 'unknown'

        self.send_input_signal.emit(f"mouse_click,{x},{y},{button}")

    def mouseDoubleClickEvent(self, event):
        """Обработка двойного клика"""
        x = event.x()
        y = event.y()
        self.send_input_signal.emit(f"mouse_double_click,{x},{y}")

    def mouseMoveEvent(self, event):
        """Обработка движения мыши"""
        if event.buttons() == Qt.LeftButton:
            x = event.x()
            y = event.y()
            self.send_input_signal.emit(f"mouse_drag,{x},{y}")

    def wheelEvent(self, event):
        """Обработка колесика мыши"""
        delta = event.angleDelta().y()
        self.send_input_signal.emit(f"mouse_wheel,{delta}")

    def keyPressEvent(self, event):
        """Обработка нажатия клавиш"""
        key_code = str(event.key())  # Преобразуем код в строку
        text = event.text()
        self.send_input_signal.emit(f"key_press,{key_code},{text}")

    def keyReleaseEvent(self, event):
        """Обработка отпускания клавиш"""
        key_code = str(event.key())  # Преобразуем код в строку
        self.send_input_signal.emit(f"key_release,{key_code}")

    @QtCore.pyqtSlot(str)
    def send_input(self, data):
        """Отправка входных данных на клиент"""
        if hasattr(self, 'conn'):
            try:
                self.conn.send(data.encode())
                print(f"Отправлено: {data}")
            except Exception as e:
                print(f"Ошибка отправки данных: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())