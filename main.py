# main.py — Часть 1 из 3
import os
import sys
import csv
import json
import gc
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QFileDialog, QLabel, QMessageBox, QDialog)
from PyQt6.QtCore import Qt

# Подключение локального пакета магнетометра
from mag_calibration import calibrate, open_settings_window


class ExternalAppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Внешний проект (Загрузчик данных Магнетометра)")
        self.resize(450, 180)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_filepath = os.path.join(base_dir, "main_config.json")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.label_info = QLabel("Управление изолированным модулем магнетометра:")
        layout.addWidget(self.label_info)
# main.py — Часть 2 из 3
        # ДОБАВЛЕНО: Кнопка вызова глобальных настроек среды модуля
        self.btn_settings = QPushButton("⚙️ Открыть настройки среды")
        self.btn_settings.setStyleSheet("height: 30px;")
        self.btn_settings.clicked.connect(self.run_settings)
        layout.addWidget(self.btn_settings)

        self.btn_open = QPushButton("📊 Выбрать файл и запустить калибровку")
        self.btn_open.setStyleSheet("height: 35px; font-weight: bold;")
        self.btn_open.clicked.connect(self.process_calibration)
        layout.addWidget(self.btn_open)

    def _load_last_directory(self) -> str:
        if os.path.exists(self.config_filepath):
            try:
                with open(self.config_filepath, 'r', encoding='utf-8') as f:
                    return json.load(f).get("last_opened_directory", "")
            except Exception:
                pass
        return ""

    def _save_last_directory(self, directory_path: str):
        try:
            with open(self.config_filepath, 'w', encoding='utf-8') as f:
                json.dump({"last_opened_directory": directory_path}, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def run_settings(self):
        """Слот хоста: Вызов окна настроек пакета с последующим тотальным контролем ОЗУ."""
        print("\n🔧 [Хост]: Запрос на открытие окна настроек магнетометра...")
        open_settings_window(parent_window=self)
        self.check_memory_leaks(total_input_points=0)
# main.py — Часть 3 из 3
    def process_calibration(self):
        last_dir = self._load_last_directory()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Открыть файл данных магнитометра", last_dir, "CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        current_dir = os.path.dirname(file_path)
        self._save_last_directory(current_dir)

        try:
            x_data, y_data, z_data = [], [], []
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        x_data.append(float(row['FLC_x']))
                        y_data.append(float(row['FLC_y']))
                        z_data.append(float(row['FLC_z']))
                    except (ValueError, KeyError):
                        continue

            input_data_dict = {'x': x_data, 'y': y_data, 'z': z_data}
            total_input_points = len(x_data)

            print("[Хост]: Активация конвейера калибровки...")
            calibrate(input_data_dict, parent_window=self)
            self.check_memory_leaks(total_input_points)

        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки", f"Произошел сбой:\n{str(e)}")

    def check_memory_leaks(self, total_input_points: int):
        """Тотальный рентген-сканер остаточных ресурсов модуля в памяти."""
        print("[Хост]: Управление возвращено. Запуск проверки ОЗУ...")
        app = QApplication.instance()
        if app:
            app.processEvents()
        gc.collect()

        total_leaks = []
        for obj in gc.get_objects():
            obj_type = type(obj)
            if hasattr(obj_type, '__module__') and isinstance(obj_type.__module__, str) and obj_type.__module__.startswith('mag_calibration'):
                total_leaks.append(f"Класс пакета: {obj_type.__name__}")
                continue
            if total_input_points > 0 and isinstance(obj, np.ndarray) and obj.base is None:
                if obj.size == total_input_points:
                    total_leaks.append(f"Массив numpy.ndarray (Размер: {obj.size})")
                    continue
            if isinstance(obj, str) and 'mag_calibration' in obj:
                if 'total_leaks' not in obj and not obj.startswith('sys.modules'):
                    total_leaks.append(f"Строковый след в ОЗУ: '{obj[:30]}...'")

        print(f"📊 [ТОТАЛЬНЫЙ КОНТРОЛЬ ПАМЯТИ] Найдено остаточных следов проекта: {len(total_leaks)}")
        if total_leaks:
            print("📋 Список удержанных ресурсов:")
            for leak in total_leaks[:10]:
                print(f"  • {leak}")
        else:
            print("🏆 ИДЕАЛЬНО! В ОЗУ хоста не осталось ни единого байта от вашего модуля.")
        print()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ExternalAppWindow()
    window.show()
    sys.exit(app.exec())
