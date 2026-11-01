# mag_calibration/views/calibration_override_dialog.py
from pathlib import Path
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
from PyQt6.QtCore import Qt


class CalibrationOverrideDialog(QDialog):
    """Модальное окно верификации сессии магнетометра."""

    def __init__(self, device_number: str, result_path: Path, lang: str = "Russian", is_completed: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("MagOverrideDialog")
        self.result_path = Path(result_path).resolve()
        self._is_completed = is_completed

        self.loc = {
            "Russian": {
                "title": "Предупреждение",
                "device_lbl": "Номер прибора:",
                "msg_blocked": "<br><b>Выбран файл сессии для проведения расчетов.</b><br><br>"
                               "Матрицы калибровки магнетометра будут автоматически рассчитаны и добавлены в этот файл сессии.",
                "msg_overwrite": "<br><b>В данной сессии калибровки уже выполнена калибровка магнетометра.</b><br><br>"
                                 "Повторный запуск процесса приведет к необходимости повторно произвести все калибровки, относящиеся к магнетометру.",
                "btn_change": "Сменить файл калибровки",
                "btn_ok": "ОК",
                "btn_overwrite": "Перезаписать"
            },
            "English": {
                "title": "Warning",
                "device_lbl": "Device Number:",
                "msg_blocked": "<br><b>Device session file selected for execution.</b><br><br>"
                               "Magnetometer calibration matrices will be computed and appended to this session file.",
                "msg_overwrite": "<br><b>Magnetometer calibration has already been completed in this calibration session.</b><br><br>"
                                 "Restarting the process will require recalculating all calibrations related to the magnetometer.",
                "btn_change": "Change Calibration File",
                "btn_ok": "OK",
                "btn_overwrite": "Overwrite"
            }
        }

        self.lp = self.loc.get(lang, self.loc["English"])
        self.init_ui(device_number, is_completed)
        self.is_closed_by_x = True

    def init_ui(self, device_number: str, is_completed: bool):
        self.setWindowTitle(self.lp["title"])
        self.setModal(True)
        self.resize(680, 245)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(12)

        # Безопасное изолированное оформление
        self.setStyleSheet("""
            QDialog#MagOverrideDialog QLabel { color: #000000; }
        """)

        dev_layout = QHBoxLayout()
        dev_layout.addStretch()
        lbl_device = QLabel(f"<h2>{self.lp['device_lbl']} <span style='color: #1A237E;'>{device_number}</span></h2>")
        lbl_device.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_layout.addWidget(lbl_device)
        dev_layout.addStretch()
        layout.addLayout(dev_layout)

        filename_only = self.result_path.name
        lbl_link = QLabel(
            f"<center><a href='#' style='color: #3498db; text-decoration: underline;'>{filename_only}</a></center>")
        lbl_link.setOpenExternalLinks(False)
        lbl_link.linkActivated.connect(self._open_folder)
        layout.addWidget(lbl_link)

        layout.addSpacing(5)

        msg_text = self.lp["msg_overwrite"] if is_completed else self.lp["msg_blocked"]
        lbl_msg = QLabel(msg_text)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 12px; color: #000000; font-weight: bold; background: transparent;")
        layout.addWidget(lbl_msg)

        layout.addSpacing(15)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)

        left_btn_text = self.lp["btn_overwrite"] if is_completed else self.lp["btn_ok"]
        self.btn_close = QPushButton(left_btn_text)
        self.btn_close.setMinimumHeight(40)

        if is_completed:
            self.btn_close.setStyleSheet("""
                QPushButton { background-color: #c0392b; color: white; font-weight: bold; font-size: 13px; border: 1px solid #a93226; border-radius: 6px; }
                QPushButton:hover { background-color: #b03a2e; }
            """)
        else:
            self.btn_close.setStyleSheet("""
                QPushButton { background-color: #ffffff; color: #000000; font-weight: bold; font-size: 13px; border: 1px solid #ced4da; border-radius: 6px; }
                QPushButton:hover { background-color: #f8f9fa; }
            """)

        btn_layout.addWidget(self.btn_close, stretch=1)

        self.btn_change = QPushButton(self.lp["btn_change"])
        self.btn_change.setMinimumHeight(40)
        self.btn_change.setStyleSheet("""
            QPushButton { background-color: #ffffff; color: #000000; font-weight: bold; font-size: 13px; border: 1px solid #ced4da; border-radius: 6px; }
            QPushButton:hover { background-color: #f8f9fa; }
        """)
        btn_layout.addWidget(self.btn_change, stretch=1)

        layout.addLayout(btn_layout)

        self.btn_close.clicked.connect(self._handle_ok_click)
        self.btn_change.clicked.connect(self._handle_change_click)

    def showEvent(self, event):
        super().showEvent(event)
        if self._is_completed:
            self.btn_change.setFocus()
            self.btn_change.setDefault(True)
        else:
            self.btn_close.setFocus()
            self.btn_close.setDefault(True)

    def _open_folder(self):
        folder_path = self.result_path.parent
        if folder_path.exists():
            import sys, subprocess, os
            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])

    def _handle_ok_click(self):
        self.is_closed_by_x = False
        self.accept()

    def _handle_change_click(self):
        self.is_closed_by_x = False
        self.reject()

    def closeEvent(self, event):
        # Если нажали крестик, self.is_closed_by_x останется True
        super().closeEvent(event)