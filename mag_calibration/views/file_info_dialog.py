# mag_calibration/views/file_info_dialog.py
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt

class FileInfoDialog(QDialog):
    """Стартовое диалоговое окно для выбора режима работы с файлом сессии прибора."""

    def __init__(self, lang: str = "Russian", parent=None):
        super().__init__(parent)
        self.result_mode = "cancel"

        self.loc = {
            "Russian": {
                "title": "Выбор файла сессии калибровки",
                "label": "<b>Внимание!</b> Для фиксации результатов магнетометра требуется выбрать файл текущей сессии прибора или создать новый.",
                "btn_select": "Выбрать существующий файл",
                "btn_create": "Создать новый прибор"
            },
            "English": {
                "title": "Calibration Session Selection",
                "label": "<b>Attention!</b> To log magnetometer results, please select an existing device session file or create a new one.",
                "btn_select": "Select Existing File",
                "btn_create": "Create New Device"
            }
        }
        self.lp = self.loc.get(lang, self.loc["English"])
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(self.lp["title"])
        self.setModal(True)
        self.resize(460, 140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        lbl = QLabel(self.lp["label"])
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #2f3542;")
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        self.btn_select = QPushButton(self.lp["btn_select"])
        self.btn_select.setMinimumHeight(35)
        self.btn_select.clicked.connect(self._handle_select)
        btn_layout.addWidget(self.btn_select)

        self.btn_create = QPushButton(self.lp["btn_create"])
        self.btn_create.setMinimumHeight(35)
        self.btn_create.clicked.connect(self._handle_create)
        btn_layout.addWidget(self.btn_create)

        layout.addLayout(btn_layout)

    def _handle_select(self):
        self.result_mode = "select"
        self.accept()

    def _handle_create(self):
        self.result_mode = "create"
        self.accept()
