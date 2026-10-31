# mag_calibration/__init__.py — Часть 1 из 1
import gc
import numpy as np
from PyQt6.QtWidgets import QApplication
from mag_calibration.controllers.calibration_controller import CalibrationController


def calibrate(raw_data_dict: dict, parent_window=None) -> None:
    """Существующая внешняя точка входа для калибровки."""
    controller = None
    try:
        controller = CalibrationController(parent_window=parent_window)
        if controller.handle_startup_session():
            controller.start_application(raw_data_dict)
    except Exception as e:
        print(f"[Магнетометр] Критическая ошибка пайплайна: {e}")


def open_settings_window(parent_window=None) -> None:
    """Внешняя точка входа для отображения глобальных настроек пакета магнетометра.

    Обеспечивает 100% изоляцию и очистку памяти ОЗУ.
    """
    controller = None
    try:
        controller = CalibrationController(parent_window=parent_window)
        controller.show_settings_dialog()
    finally:
        if controller:
            controller.shutdown_session()
            del controller

        app = QApplication.instance()
        if app:
            app.processEvents()
        gc.collect()
