import sys
import os
import gc
from typing import Optional
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QApplication, QWidget

_module_translator: Optional[QTranslator] = None

# Экспортируем обе фасадные функции для хост-приложения
__all__ = ["calibrate", "open_settings_window"]


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
        if app:
            # ИСПРАВЛЕНО: Даем Qt полностью закрыть стартовый диалог и освободить стек окон
            app.processEvents()

        controller.start_application(raw_data_dict)
        controller.view.exec()

    finally:
        # 5. Рубеж гарантированной деаллокации ОЗУ
        print("🧹 [Магнетометр - Фасад] Активация рубежа очистки памяти модуля калибровки...")
        if app and _module_translator:
            try:
                app.removeTranslator(_module_translator)
            except Exception:
                pass

        if controller:
            controller.shutdown_session()
            del controller

        # Прокачиваем оконные циклы Qt, давая полностью отработать методам deleteLater()
        if app:
            for _ in range(5):
                app.processEvents()

        # Выгружаем внутренние саб-пакеты самого плагина, чтобы они пересоздавались с нуля
        try:
            for m in list(sys.modules.keys()):
                if m.startswith('mag_calibration.'):
                    del sys.modules[m]
        except Exception:
            pass

        gc.collect()
        print("✨ [Магнетометр - Фасад] ОЗУ калибровки полностью освобождена. Память стерильна.")


def open_settings_window(parent_window: Optional[QWidget] = None) -> None:
    """Изолированная фасадная точка входа для настройки глобальных параметров среды (Язык, Пути)."""
    app = QApplication.instance()
    controller = None

    try:
        from mag_calibration.controllers.calibration_controller import CalibrationController

        # 1. Создаем временный контроллер исключительно ради доступа к settings_manager и диалогу настроек
        controller = CalibrationController(parent_window=parent_window)

        # 2. Передаем управление в диалог глобальных настроек среды
        controller.show_settings_dialog()

    finally:
        # 3. Гарантированный разрыв связей и зачистка ресурсов контроллера настроек
        print("🧹 [Магнетометр - Фасад] Очистка ОЗУ после закрытия окна настроек...")
        if controller:
            controller.shutdown_session()
            del controller

        # Даем Qt Event Loop полностью завершить удаление C++ виджетов (WA_DeleteOnClose)
        if app:
            for _ in range(5):
                app.processEvents()

        # Очищаем sys.modules для предотвращения накопления строковых следов метаданных
        try:
            for m in list(sys.modules.keys()):
                if m.startswith('mag_calibration.'):
                    del sys.modules[m]
        except Exception:
            pass

        gc.collect()
        print("✨ [Магнетометр - Фасад] ОЗУ настроек полностью освобождена. Память стерильна.")
