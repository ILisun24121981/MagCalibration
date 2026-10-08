# mag_calibration/__init__.py
import sys
import os
import gc
from typing import Optional
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QApplication, QWidget

from mag_calibration.controllers.calibration_controller import CalibrationController

_module_translator: Optional[QTranslator] = None

__all__ = ["calibrate"]


def calibrate(raw_data_dict: dict, parent_window: Optional[QWidget] = None) -> None:
    """Высокоуровневая фасадная точка входа хост-приложения для запуска калибровки магнетометра.

    Принимает словарь с сырыми массивами осей {'x': [...], 'y': [...], 'z': [...]}.
    Гарантирует атомарную изоляцию ОЗУ хоста после закрытия окон.

    :param raw_data_dict: Словарь с сырыми данными осей X, Y, Z.
    :param parent_window: Ссылка на окно хост-приложения для обеспечения корректной иерархии окон.
    """
    global _module_translator
    app = QApplication.instance()
    controller = None

    try:
        # 1. Аллокация ресурсов контроллера с привязкой к окну хоста
        controller = CalibrationController(parent_window=parent_window)
        chosen_lang = controller.settings_manager.current_lang

        # 2. Локализация встроенных системных диалогов Qt (Проводник, ввод текста)
        if app:
            if _module_translator is None:
                _module_translator = QTranslator(app)

            module_dir = os.path.dirname(os.path.abspath(__file__))
            if chosen_lang == "Russian":
                translation_file = os.path.join(module_dir, "translations", "qtbase_ru.qm")
            else:
                translation_file = os.path.join(module_dir, "translations", "qtbase_en.qm")

            if os.path.exists(translation_file):
                if _module_translator.load(translation_file):
                    app.installTranslator(_module_translator)

        # 3. Запуск транзакции проверки и выбора сессионного файла прибора.
        if not controller.handle_startup_session(force_settings=False):
            print("[Магнетометр] Сессия аннулирована пользователем на этапе выбора файла.")
            return

        # 4. Передача управления в интерактивный 3D UI loop модуля
        controller.start_application(raw_data_dict)
        controller.view.exec()

    finally:
        # 5. Рубеж гарантированной деаллокации ОЗУ
        print("🧹 [Магнетометр - Фасад] Активация рубежа очистки памяти модуля...")
        if app and _module_translator:
            try:
                app.removeTranslator(_module_translator)
            except Exception:
                pass

        if controller:
            controller.shutdown_session()
            del controller

        # Очистка циклов событий Qt от удаленных C++ объектов (через deleteLater)
        if app:
            app.processEvents()

        # Принудительный вызов циклической сборки мусора Python
        gc.collect()
        print("✨ [Магнетометр - Фасад] ОЗУ полностью освобождена. Управление возвращено хост-приложению.")
