# mag_calibration/views/save_success_dialog.py
import os
import sys
import subprocess
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

class SaveSuccessDialog(QDialog):
    """Кастомное окно успешного завершения калибровки магнетометра."""

    def __init__(self, filename: str, folder_path: str, lang: str = "Russian", parent=None):
        super().__init__(parent)
        self.folder_path = os.path.abspath(folder_path)

        if lang == "Russian":
            self.setWindowTitle("Внимание")
            self.msg_text = f"Результаты калибровки магнетометра успешно сохранены в общую сессию прибора:\n\n{filename}"
            self.btn_open_text = "Открыть папку с результатом"
            self.btn_ok_text = "ОК"
        else:
            self.setWindowTitle("Attention")
            self.msg_text = f"Magnetometer results successfully saved to device session:\n\n{filename}"
            self.btn_open_text = "Open Containing Folder"
            self.btn_ok_text = "OK"

        self.init_ui()

    def init_ui(self):
        self.resize(440, 140)
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl = QLabel(self.msg_text)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton(self.btn_open_text)
        self.btn_ok = QPushButton(self.btn_ok_text)

        self.btn_open.setMinimumHeight(30)
        self.btn_ok.setMinimumHeight(30)
        self.btn_ok.setFixedWidth(80)

        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_open.clicked.connect(self.handle_open_folder)

    def handle_open_folder(self):
        try:
            if os.path.exists(self.folder_path):
                if os.name == 'nt':
                    os.startfile(self.folder_path)
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', self.folder_path])
                else:
                    subprocess.Popen(['xdg-open', self.folder_path])
        except Exception as e:
            print(f"[Магнетометр] Не удалось открыть директорию: {e}")
        self.accept()
