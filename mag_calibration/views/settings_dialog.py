import os
from typing import Dict, Any
from PyQt6 import QtCore
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog, \
    QApplication


class SettingsDialog(QDialog):
    """Окно конфигурации параметров среды акселерометра (Язык, Путь сохранения).
    Синхронизировано по стилю и логике с модулем магнетометра.
    """

    def __init__(self, current_settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        # ОПТИМИЗИРОВАНО: Мгновенное С++ удаление окна из ОЗУ сразу после закрытия
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)

        self.loc = {
            "Russian": {
                "title": "Настройки модуля калибровки", "lbl_lang": "Язык интерфейса:",
                "lbl_path": "Папка сохранения результатов:", "btn_browse": "Обзор...",
                "btn_save": "Сохранить", "btn_cancel": "Отмена"
            },
            "English": {
                "title": "Calibration Module Settings", "lbl_lang": "Interface Language:",
                "lbl_path": "Result Storage Directory:", "btn_browse": "Browse...",
                "btn_save": "Save Settings", "btn_cancel": "Cancel"
            }
        }

        raw_lang = str(current_settings.get("Language", "English")).strip()
        self.lang = "Russian" if raw_lang.startswith(("Rus", "rus")) else "English"
        self.user_decision = "reject"

        # Кэш для безопасного сохранения параметров до уничтожения C++ виджетов
        self.final_configured_data = {}

        self.resize(520, 180)
        self.setModal(True)
        layout = QVBoxLayout(self)

        # 1. Выбор Языка
        self.lbl_lang = QLabel()
        layout.addWidget(self.lbl_lang)

        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["English", "Russian"])
        self.combo_lang.setCurrentText("Russian" if self.lang == "Russian" else "English")
        self.combo_lang.currentTextChanged.connect(self._handle_language_change)
        layout.addWidget(self.combo_lang)

        # 2. Выбор Папки (Текстовое поле + кнопка Обзор)
        self.lbl_path = QLabel()
        layout.addWidget(self.lbl_path)

        path_layout = QHBoxLayout()
        self.le_path = QLineEdit(str(current_settings.get("Calibration result folder", "")))
        self.btn_browse = QPushButton()
        self.btn_browse.clicked.connect(self._handle_browse)
        path_layout.addWidget(self.le_path)
        path_layout.addWidget(self.btn_browse)
        layout.addLayout(path_layout)

        layout.addStretch()
        # Кнопки Управления
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton()
        self.btn_save.setStyleSheet("background-color: lightgreen; font-weight: bold; height: 30px; color: black;")
        self.btn_save.clicked.connect(self._handle_save)

        self.btn_cancel = QPushButton()
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self._retranslate_ui()

        app = QApplication.instance()
        screen = app.primaryScreen().geometry() if app else None
        if screen:
            self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

    def _retranslate_ui(self) -> None:
        lp = self.loc.get(self.lang, self.loc["English"])
        self.setWindowTitle(lp["title"])
        self.lbl_lang.setText(f"<b>{lp['lbl_lang']}</b>")
        self.lbl_path.setText(f"<b>{lp['lbl_path']}</b>")
        self.btn_browse.setText(lp["btn_browse"])
        self.btn_save.setText(lp["btn_save"])
        self.btn_cancel.setText(lp["btn_cancel"])

    def _handle_language_change(self, selected_text: str) -> None:
        self.lang = selected_text
        self._retranslate_ui()

    def _handle_browse(self) -> None:
        lp = self.loc.get(self.lang, self.loc["English"])
        start_dir = self.le_path.text() if os.path.exists(self.le_path.text()) else os.getcwd()
        selected_dir = QFileDialog.getExistingDirectory(self, lp["lbl_path"], start_dir)
        if selected_dir:
            self.le_path.setText(os.path.abspath(selected_dir))

    def _handle_save(self) -> None:
        """Слот сохранения данных ПЕРЕД деструкцией C++ виджетов."""
        self.user_decision = "accept"

        # ОПТИМИЗИРОВАНО: Сохраняем только чистые инфраструктурные параметры среды среды
        self.final_configured_data = {
            "Language": self.combo_lang.currentText(),
            "Calibration result folder": os.path.abspath(self.le_path.text().strip())
        }
        self.accept()

    def get_configured_settings(self) -> Dict[str, Any]:
        """Возвращает предварительно закэшированный Python-словарь настроек."""
        return self.final_configured_data
