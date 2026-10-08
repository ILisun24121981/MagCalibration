import sys
import os
import gc
from typing import Optional
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QApplication, QWidget

_module_translator: Optional[QTranslator] = None

__all__ = ["calibrate"]


def calibrate(raw_data_dict: dict, parent_window: Optional[QWidget] = None) -> None:
    """Высокоуровневая фасадная точка входа хост-приложения для запуска калибровки магнетометра."""
    global _module_translator
    app = QApplication.instance()
    controller = None

    try:
        # ЛОКАЛЬНЫЙ (ЛЕНИВЫЙ) ИМПОРТ: Гарантирует чтение обновленного sys.modules
        from mag_calibration.controllers.calibration_controller import CalibrationController

        # 1. Аллокация ресурсов контроллера
        controller = CalibrationController(parent_window=parent_window)
        chosen_lang = controller.settings_manager.current_lang

        # 2. Локализация встроенных системных диалогов Qt
        if app:
            if _module_translator is None:
                _module_translator = QTranslator(app)

            module_dir = os.path.dirname(os.path.abspath(__file__))
            translation_file = os.path.join(
                module_dir, "translations",
                "qtbase_ru.qm" if chosen_lang == "Russian" else "qtbase_en.qm"
            )

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

        # Прокачиваем оконные циклы и принудительно чистим кэш импортов
        if app:
            app.processEvents()
            app.processEvents()

        # Выгружаем внутренние саб-пакеты самого плагина, чтобы они тоже пересоздавались с нуля
        try:
            for m in list(sys.modules.keys()):
                if m.startswith('mag_calibration.'):
                    del sys.modules[m]
        except Exception:
            pass

        gc.collect()
        print("✨ [Магнетометр - Фасад] ОЗУ полностью освобождена. Память стерильна.")
