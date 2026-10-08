# mag_calibration/controllers/calibration_controller.py — Часть 1 из 2
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QLineEdit, QMessageBox, QWidget

# Прямые импорты математического движка и графического интерфейса
from mag_calibration.models.calibration_model import CalibrationModel
from mag_calibration.views.calibration_view import CalibrationView

# Импорты новой отказоустойчивой экосистемы менеджеров и окон сессий
from mag_calibration.models.managers.settings_manager import SettingsManager
from mag_calibration.models.managers.mag_file_manager import MagFileManager
from mag_calibration.models.managers.mag_session_manager import MagSessionManager

from mag_calibration.views.file_info_dialog import FileInfoDialog
from mag_calibration.views.calibration_override_dialog import CalibrationOverrideDialog


class CalibrationController(QObject):
    """Центральный контроллер-дирижер модуля калибровки магнетометра."""

    def __init__(self, parent_window: Optional[QWidget] = None):
        super().__init__()
        self._parent_window = parent_window

        # Инициализация менеджеров среды и математического ядра
        self.settings_manager = SettingsManager(parent=self._parent_window)
        self.file_manager = MagFileManager()
        self.session_manager = MagSessionManager(self.settings_manager, self.file_manager)

        self.model = CalibrationModel()
        self.fallback_defaults = self.settings_manager.load_calibration_settings()
        self.last_executed_parameters = self.fallback_defaults.copy()
        self.model.algo_settings.update(self.fallback_defaults)

        # Конструируем пассивный View-интерфейс, жестко привязывая его к родителю-хосту
        self.view = CalibrationView(parent=self._parent_window)
        self.model.logger = self.view.display_message

        # ВАЖНО: Убираем WA_DeleteOnClose, удалением будем управлять вручную принудительно
        self.view.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        # Подписка на изолированные Qt сигналы View
        self.view.start_clicked.connect(self._on_start_clicked)
        self.view.save_clicked.connect(self._on_save_clicked)
        self.view.reset_clicked.connect(self._on_reset_clicked)

    def handle_startup_session(self, force_settings: bool = False) -> bool:
        """Инициализирует сессию модуля.

        Линейно разделяет потоки: создание нового прибора или выбор старого.
        """
        if force_settings or not self.settings_manager.validate_environment():
            self.settings_manager.ensure_default_files()
            self.settings_manager.load_settings()

        c_path = self.settings_manager.calibration_file_path

        # Если путь изначально передан/существует (автоподхват сессии из хоста)
        if c_path and c_path.is_file():
            print(f"[Магнетометр] Сессия подхвачена автоматически: {c_path.name}")
            return self._process_file_and_override_check(is_new_file=False)

        # Если пустой — запускаем прямое диалоговое окно выбора/создания
        return self._run_interactive_file_selection()

    def _run_interactive_file_selection(self) -> bool:
        """Показывает стартовое окно выбора режима работы с файлом сессии."""
        init_dlg = FileInfoDialog(lang=self.settings_manager.current_lang, parent=self.view or self._parent_window)
        init_dlg.exec()

        # СЦЕНАРИЙ А: Выбор существующего файла через проводник
        if init_dlg.result_mode == 'select':
            file_filter = "JSON Files (*.json)"
            caption = "Выберите файл калибровочной сессии" if self.settings_manager.current_lang == "Russian" else "Select Calibration Session File"
            selected_file, _ = QFileDialog.getOpenFileName(
                self.view, caption, str(self.settings_manager.save_result_dir), file_filter,
                options=QFileDialog.Option.DontUseNativeDialog
            )
            if selected_file:
                self.settings_manager.calibration_file_path = Path(selected_file).resolve()
                self.settings_manager.save_setting("Last Calibration File Path", selected_file, parent=self.view)

                # Файл выбран из существующих -> отправляем на проверку перезаписи (окно покажется, если там уже есть mag)
                return self._process_file_and_override_check(is_new_file=False)

            # Если в проводнике нажали "Отмена" — возвращаем пользователя на стартовый выбор
            return self._run_interactive_file_selection()

        # СЦЕНАРИЙ Б: Создание нового файла прибора с нуля
        elif init_dlg.result_mode == 'create':
            prompt = "Введите номер прибора:" if self.settings_manager.current_lang == "Russian" else "Enter device number:"
            title = "Новая калибровка" if self.settings_manager.current_lang == "Russian" else "New Calibration"
            dev_num, ok = QInputDialog.getText(self.view, title, prompt, QLineEdit.EchoMode.Normal)
            if ok and dev_num.strip():
                # Менеджер сессий создает пустой файл структуры и прописывает его в settings_manager
                self.session_manager.create_new_calibration_file(dev_num.strip(), parent=self.view)

                print("[Магнетометр] Создан новый файл прибора. Окно предупреждения заблокировано.")
                # Файл абсолютно чистый и новый -> передаем is_new_file=True, чтобы гарантированно пропустить диалог
                return self._process_file_and_override_check(is_new_file=True)

            # Если отменили ввод номера прибора — возвращаем на стартовый выбор
            return self._run_interactive_file_selection()

        return False  # Нажат крестик закрытия стартового окнаFileInfoDialog

    def _process_file_and_override_check(self, is_new_file: bool) -> bool:
        """Считывает JSON-структуру файла и управляет выводом окна верификации перезаписи."""
        file_data = self.file_manager.read_json(self.settings_manager.calibration_file_path, parent=self.view)
        if not file_data:
            return False

        # ИСПРАВЛЕНО: Если файл только что создан — мгновенно выходим в главное окно без предупреждений!
        if is_new_file:
            return True

        # Валидация секций для старых файлов
        mag_section = file_data.get("mag", {}) if isinstance(file_data, dict) else {}
        if not isinstance(mag_section, dict): mag_section = {}

        calib_section = mag_section.get("calibration", {}) if isinstance(mag_section, dict) else {}
        if not isinstance(calib_section, dict): calib_section = {}

        is_completed = calib_section.get("state") == "Completed"
        current_dev_num = file_data.get("fileInfo", {}).get("device_number", "unknown")

        # Окно верификации выводится только для старых файлов сессий
        warn_dlg = CalibrationOverrideDialog(
            device_number=current_dev_num,
            result_path=self.settings_manager.calibration_file_path,
            lang=self.settings_manager.current_lang,
            is_completed=is_completed,
            parent=self.view
        )

        if warn_dlg.exec() == QDialog.DialogCode.Accepted:
            if is_completed:
                print("[Магнетометр] Повторный запуск. Предыдущая секция 'mag' очищена.")
                if "mag" in file_data:
                    del file_data["mag"]
                self.session_manager.update_session_file(file_data, parent=self.view)
            return True
        else:
            # Нажали "Сменить файл калибровки" -> обнуляем пути и уводим на чистый выбор
            self.settings_manager.save_setting("Last Calibration File Path", "", parent=self.view)
            self.settings_manager.calibration_file_path = Path("")
            return self._run_interactive_file_selection()

# mag_calibration/controllers/calibration_controller.py — Часть 2 из 2

    def _save_calibration_config(self):
        """Сохраняет измененные параметры алгоритма на диск."""
        try:
            self.settings_manager.save_calibration_settings(self.model.algo_settings, parent=self.view)
            self.view.display_message(
                "Новые параметры ручного режима успешно сохранены." if self.settings_manager.current_lang == "Russian" else "New manual mode parameters successfully saved.")
        except Exception as e:
            self.view.display_error(f"Не удалось сохранить конфигурацию ({e}).")

    def _load_raw_file_config_only(self) -> dict:
        disk_config = self.settings_manager.load_calibration_settings()
        return disk_config if disk_config else self.fallback_defaults

    def start_application(self, raw_data_dict: dict):
        """Инициализирует UI-компоненты и выводит исходное 3D облако точек."""
        self.model.load_data(raw_data_dict)

        file_data = self.file_manager.read_json(self.settings_manager.calibration_file_path, self.view)
        device_number = file_data.get("fileInfo", {}).get("device_number", "unknown").strip() if file_data else "unknown"

        self.view.update_file_context(device_number=device_number, result_path=self.settings_manager.calibration_file_path)

        is_ru = self.settings_manager.current_lang == "Russian"
        msg_check = "Проверка настроек алгоритма калибровки..." if is_ru else "Checking calibration algorithm settings..."
        msg_ready = "Приложение готово к расчету." if is_ru else "Application is ready for computation."

        self.view.display_message(msg_check)
        calib_type = self.model.algo_settings.get("calibration_type", "auto")
        self.view.set_calibration_mode_ui(calib_type)
        self.view.generate_parameter_fields(self.model.algo_settings)
        self.view.display_3d_plots(raw_data=self.model.raw_data, calibrated_data=None)

        # Подвязываем новый сигнал кнопки сохранения финального результата
        self.view.save_result_clicked.connect(self._on_save_result_clicked)

        self.view.btn_start.setEnabled(True)
        self.view.display_message(msg_ready)


    def _log_empty_fields_report(self, prefix_msg):
        self.view.display_error(prefix_msg)
        for key, inp in self.view.param_inputs.items():
            if inp.text().strip() == "":
                lbl = self.view.param_labels.get(key, key)
                in_model = self.last_executed_parameters.get(key, 'Не задано')
                in_default = self.fallback_defaults.get(key, 'Нет')
                self.view.display_error(f"   • {lbl} → В модели: {in_model} | Дефолт: {in_default}")

    def _on_start_clicked(self):
        if not self.view.validate_fields():
            is_ru = self.settings_manager.current_lang == "Russian"
            err_msg = "Калибровка отклонена! Заполните пустые поля:" if is_ru else "Calibration rejected! Fill in empty fields:"
            self._log_empty_fields_report(err_msg)
            return
        current_ui_mode = self.view.get_selected_calibration_mode()
        self.model.algo_settings["calibration_type"] = current_ui_mode
        if current_ui_mode == "manual":
            custom_params = self.view.get_custom_parameters()
            self.model.algo_settings.update(custom_params)
            self.last_executed_parameters.update(custom_params)
            self.run_calibration_process()
        else:
            self.run_auto_tuning()

    def _on_save_clicked(self):
        if not self.view.validate_fields():
            is_ru = self.settings_manager.current_lang == "Russian"
            err_msg = "Сохранение заблокировано! Заполните пустые поля:" if is_ru else "Saving blocked! Fill in empty fields:"
            self._log_empty_fields_report(err_msg)
            return
        custom_params = self.view.get_custom_parameters()
        self.model.algo_settings.update(custom_params)
        self._save_calibration_config()
        self.view.reset_modification_state()

    def _on_reset_clicked(self):
        fresh_disk_config = self._load_raw_file_config_only()
        self.view.reset_to_values(fresh_disk_config)
        is_ru = self.settings_manager.current_lang == "Russian"
        msg = ("Интерфейс сброшен к сохраненному файлу на диске. Параметры модели не изменялись." if is_ru else
               "Interface reset to saved disk file. Model parameters were not modified.")
        self.view.display_message(msg)

    def run_auto_tuning(self):
        self.view.btn_start.setEnabled(False)
        success, _ = self.model.optimize_and_save_algorithm_settings()
        if success:
            self.last_executed_parameters.update(self.model.algo_settings)
            self.run_calibration_process()
        else:
            is_ru = self.settings_manager.current_lang == "Russian"
            msg = "[ОШИБКА AUTO]: Сбой авто-калибровки." if is_ru else "[AUTO ERROR]: Auto-calibration failed."
            self.view.display_message(msg)
            self.view.btn_start.setEnabled(True)

    def run_calibration_process(self):
        self.view.btn_start.setEnabled(False)
        self.view.btn_save_result.setVisible(False)  # Скрываем кнопку на время нового расчета

        is_ru = self.settings_manager.current_lang == "Russian"
        msg_start = "Запуск математического конвейера вычислений..." if is_ru else "Starting mathematical computation pipeline..."
        self.view.display_message(msg_start)
        QApplication.processEvents()

        offsets, coefficients, rmse = self.model.calculate_calibration_parameters_combined()

        if rmse == -1.0:
            msg = "[ОШИБКА]: Калибровка сорвана." if is_ru else "[ERROR]: Calibration aborted."
            self.view.display_message(msg)
            self.view.btn_start.setEnabled(True)
            return

        msg_done = f"Калибровка успешно завершена. Результирующий RMSE: {rmse:.6f}" if is_ru else f"Calibration successfully completed. Resulting RMSE: {rmse:.6f}"
        self.view.display_message(msg_done)

        self.model.calibration_offsets = offsets
        self.model.calibration_coefficients = coefficients
        self.model.calibrated_data = self.model.apply_calibration(self.model.raw_data, offsets, coefficients)

        lbl_res = "Смещения осей (Hard-Iron)" if is_ru else "Axis Offsets (Hard-Iron)"
        lbl_mat = "Матрица коэффициентов (Soft-Iron)" if is_ru else "Coefficients Matrix (Soft-Iron)"

        self.view.display_results({lbl_res: offsets.tolist(), lbl_mat: coefficients.tolist()})
        self.view.display_3d_plots(raw_data=self.model.raw_data, calibrated_data=self.model.calibrated_data)

        self.view.btn_start.setEnabled(True)

        # ИСПРАВЛЕНО: Вместо автосохранения делаем видимой большую зеленую кнопку под блоком настроек
        self.view.btn_save_result.setVisible(True)
        self.view.display_message(
            "Результаты готовы к фиксации. Нажмите кнопку 'Сохранить результат' слева." if is_ru else "Results ready. Click 'Save Result' on the left panel.")
    def _execute_json_save(self, offsets, coefficients, rmse):
        """Автоматически считывает device_number из сессии и фиксирует результаты."""
        try:
            file_data = self.file_manager.read_json(self.settings_manager.calibration_file_path, self.view)
            if not file_data:
                raise ValueError("Не удалось получить текущую сессию прибора.")

            device_number = file_data.get("fileInfo", {}).get("device_number", "unknown").strip()

            save_structure = {
                "rmse": float(rmse),
                "hard_iron_offsets": offsets.tolist(),
                "soft_iron_matrix": coefficients.tolist(),
                "applied_algorithm_settings": self.model.algo_settings
            }

            self.session_manager.save_final_mag_matrix(save_structure, parent=self.view)

            current_timestamp = file_data.get("fileInfo", {}).get("changeTimeStamp",
                                                                  datetime.now().strftime('%Y_%m_%d_%H_%M'))
            filename = f"{device_number}_calibration_{current_timestamp}.json"

            # Модуль завершил логику. Закрываем диалог.
            if self.view:
                self.view.accept()

            # Вызываем диалог успешного сохранения из НАШЕГО пакета, а не из хоста
            from mag_calibration.views.save_success_dialog import SaveSuccessDialog
            success_dlg = SaveSuccessDialog(
                filename=filename,
                folder_path=str(self.settings_manager.save_result_dir),
                lang=self.settings_manager.current_lang,
                parent=self._parent_window
            )
            success_dlg.exec()

        except Exception as e:
            if self.view:
                self.view.display_error(f"Критическая ошибка сохранения файла данных ({e})")
            else:
                print(f"[Магнетометр] Ошибка сохранения данных: {e}")

    def shutdown_session(self) -> None:
        """Безопасная деструкция ресурсов модуля для полного предотвращения утечек памяти."""
        if self.view:
            try:
                self.view.cleanup_resources()
            except Exception as e:
                print(f"[Магнетометр] Ошибка деаллокации View: {e}")
            self.view = None

        if self.model:
            self.model.logger = None  # Уничтожаем циклическую ссылку метода-колбэка!
            self.model = None

        self.settings_manager = None
        self.file_manager = None
        self.session_manager = None
        self.fallback_defaults = None
        self.last_executed_parameters = None
        self._parent_window = None
        print("✨ [Изоляция ОЗУ] Сессия калибровки магнетометра полностью деаллоцирована.")

    def _on_save_result_clicked(self):
        """Вызывается строго по физическому нажатию кнопки пользователем после расчета."""
        # Проверяем, что расчет действительно был выполнен
        if self.model.calibration_offsets is None or self.model.calibration_coefficients is None:
            return

        # Делегируем выполнение сохранения в JSON
        self._execute_json_save(
            self.model.calibration_offsets,
            self.model.calibration_coefficients,
            self.model.algo_settings.get("rmse", 0.0)
        )