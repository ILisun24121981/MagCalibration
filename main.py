# main.py (Скрипт-загрузчик песочницы магнетометра)
import os
import sys
import csv
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QFileDialog, QLabel, QMessageBox, QDialog)
from PyQt6.QtCore import Qt

# Подключение нашего локального пакета магнетометра
from mag_calibration import calibrate


class ExternalAppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Внешний проект (Загрузчик данных Магнетометра)")
        self.resize(450, 150)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_filepath = os.path.join(base_dir, "main_config.json")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.label_info = QLabel("Выберите CSV файл магнитометра для отправки в модуль калибровки")
        layout.addWidget(self.label_info)

        self.btn_open = QPushButton("Выбрать файл и запустить калибровку")
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

    # main.py — Метод process_calibration — Часть 1 из 3
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
                required_headers = {'FLC_x', 'FLC_y', 'FLC_z'}
                if not required_headers.issubset(reader.fieldnames or []):
                    raise ValueError(f"В файле нет колонок FLC_x, FLC_y, FLC_z.\nНайдены: {reader.fieldnames}")

                for row in reader:
                    try:
                        x_data.append(float(row['FLC_x']))
                        y_data.append(float(row['FLC_y']))
                        z_data.append(float(row['FLC_z']))
                    except ValueError:
                        continue

            input_data_dict = {'x': x_data, 'y': y_data, 'z': z_data}
            total_input_points = len(x_data)

            print("[Хост]: Активация изолированного конвейера калибровки...")
            calibrate(input_data_dict, parent_window=self)
            print("[Хост]: Управление возвращено. Запуск тотальной проверки ОЗУ...")
# main.py — Метод process_calibration — Часть 2 из 3
            # 🧼 ИНИЦИАЛИЗАЦИЯ ЗАЧИСТКИ ОЧЕРЕДИ ПЕРЕД СКАНИРОВАНИЕМ
            import gc
            import numpy as np
            app = QApplication.instance()
            if app:
                app.processEvents()
            gc.collect()

            total_leaks = []
            for obj in gc.get_objects():
                obj_type = type(obj)
                type_name = obj_type.__name__

                # 1. Сканируем кастомные классы пакета магнетометра
                if hasattr(obj_type, '__module__'):
                    mod_name = obj_type.__module__
                    if isinstance(mod_name, str) and mod_name.startswith('mag_calibration'):
                        total_leaks.append(f"Класс пакета: {type_name}")
                        continue

                # 2. Проверяем тяжелые массивы NumPy, выделенные плагином
                if isinstance(obj, np.ndarray) and obj.base is None:
                    # Проверяем массивы, по длине совпадающие с переданным CSV-файлом
                    if obj.size == total_input_points:
                        total_leaks.append(f"Массив numpy.ndarray (Размер: {obj.size})")
                        continue
# main.py — Метод process_calibration — Часть 3 из 3
                # 3. Ищем скрытые текстовые следы в ОЗУ
                if isinstance(obj, str) and 'mag_calibration' in obj:
                    if 'total_leaks' not in obj and not obj.startswith('sys.modules'):
                        total_leaks.append(f"Строковый след в ОЗУ: '{obj[:30]}...'")

            print(f"\n📊 [ТОТАЛЬНЫЙ КОНТРОЛЬ ПАМЯТИ] Найдено остаточных следов проекта: {len(total_leaks)}")
            if total_leaks:
                print("📋 Список удержанных ресурсов:")
                for leak in total_leaks[:10]:
                    print(f"  • {leak}")
            else:
                print("🏆 ИДЕАЛЬНО! В ОЗУ хоста не осталось ни единого байта или следа от вашего модуля.")
            print()

        except TypeError as te:
            QMessageBox.critical(self, "Ошибка версии", f"Сбой вызова: {str(te)}\n\nВыполните: pip install -e .")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки", f"Произошел сбой:\n{str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ExternalAppWindow()
    window.show()
    sys.exit(app.exec())
