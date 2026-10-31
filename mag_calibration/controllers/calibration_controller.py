# mag_calibration/controllers/calibration_controller.py — Часть 1 из 4
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QLineEdit, QMessageBox, QWidget

from mag_calibration.models.calibration_model import CalibrationModel
from mag_calibration.views.calibration_view import CalibrationView
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
        self.current_stage = 1

        self.settings_manager = SettingsManager(parent=self._parent_window)
        self.file_manager = MagFileManager()
        self.session_manager = MagSessionManager(self.settings_manager, self.file_manager)

        self.model = CalibrationModel()
        self.fallback_defaults = self.settings_manager.load_calibration_settings()
        self.last_executed_parameters = self.fallback_defaults.copy()
        self.model.algo_settings.update(self.fallback_defaults)

        self.view = CalibrationView(parent=self._parent_window)
        self.model.logger = self.view.display_message
        self.view.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.view.start_clicked.connect(self._on_start_clicked)
        self.view.save_clicked.connect(self._on_save_clicked)
        self.view.reset_clicked.connect(self._on_reset_clicked)
        self.view.default_clicked.connect(self._on_default_clicked)

# mag_calibration/controllers/calibration_controller.py — Часть 2 из 4
    def handle_startup_session(self, force_settings: bool = False) -> bool:
        """Инициализирует сессию модуля."""
        if force_settings or not self.settings_manager.validate_environment():
            self.settings_manager.ensure_default_files()
            self.settings_manager.load_settings()

        c_path = self.settings_manager.calibration_file_path
        if c_path and c_path.is_file():
            print(f"[Магнетометр] Сессия подхвачена автоматически: {c_path.name}")
            return self._process_file_and_override_check(is_new_file=False)
        return self._run_interactive_file_selection()

    def _run_interactive_file_selection(self) -> bool:
        """Показывает стартовое окно выбора режима работы с файлом сессии."""
        init_dlg = FileInfoDialog(lang=self.settings_manager.current_lang, parent=self.view or self._parent_window)
        init_dlg.exec()

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
                return self._process_file_and_override_check(is_new_file=False)
            return self._run_interactive_file_selection()

        elif init_dlg.result_mode == 'create':
            prompt = "Введите номер прибора:" if self.settings_manager.current_lang == "Russian" else "Enter device number:"
            title = "Новая калибровка" if self.settings_manager.current_lang == "Russian" else "New Calibration"
            dev_num, ok = QInputDialog.getText(self.view, title, prompt, QLineEdit.EchoMode.Normal)
            if ok and dev_num.strip():
                self.session_manager.create_new_calibration_file(dev_num.strip(), parent=self.view)
                return self._process_file_and_override_check(is_new_file=True)
            return self._run_interactive_file_selection()
        return False

    def _process_file_and_override_check(self, is_new_file=False) -> bool:
        file_data = self.file_manager.read_json(self.settings_manager.calibration_file_path, parent=self.view)
        if not file_data or is_new_file:
            return True if is_new_file else False

        mag_section = file_data.get("mag", {}) if isinstance(file_data, dict) else {}
        calib_section = mag_section.get("calibration", {}) if isinstance(mag_section, dict) else {}
        is_completed = calib_section.get("state") == "Completed"
        current_dev_num = file_data.get("fileInfo", {}).get("device_number", "unknown")

        warn_dlg = CalibrationOverrideDialog(
            device_number=current_dev_num, result_path=self.settings_manager.calibration_file_path,
            lang=self.settings_manager.current_lang, is_completed=is_completed, parent=self.view
        )
        if warn_dlg.exec() == QDialog.DialogCode.Accepted:
            if is_completed and "mag" in file_data:
                del file_data["mag"]
                self.session_manager.update_session_file(file_data, parent=self.view)
            return True
        else:
            self.settings_manager.save_setting("Last Calibration File Path", "", parent=self.view)
            self.settings_manager.calibration_file_path = Path("")
            return self._run_interactive_file_selection()

    # mag_calibration/controllers/calibration_controller.py — Часть 3 из 4
    def _save_calibration_config(self):
        try:
            self.settings_manager.save_calibration_settings(self.model.algo_settings, parent=self.view)
            self.view.display_message(
                "Новые параметры успешно сохранены." if self.settings_manager.current_lang == "Russian" else "New parameters successfully saved.")
        except Exception as e:
            self.view.display_error(f"Не удалось сохранить конфигурацию ({e}).")

    def _load_raw_file_config_only(self) -> dict:
        disk_config = self.settings_manager.load_calibration_settings()
        return disk_config if disk_config else self.fallback_defaults

    def start_application(self, raw_data_dict: dict):
        self.model.load_data(raw_data_dict)
        file_data = self.file_manager.read_json(self.settings_manager.calibration_file_path, self.view)
        device_number = file_data.get("fileInfo", {}).get("device_number",
                                                          "unknown").strip() if file_data else "unknown"

        self.current_stage = 1
        active_lang = self.settings_manager.current_lang
        is_ru = active_lang == "Russian"
        msg_ready = "Приложение готово к фильтрации (Этап 1)." if is_ru else "Application ready for filtering (Stage 1)."

        self.view.set_calibration_mode_ui(self.model.algo_settings.get("calibration_type", "auto"))

        # ЖЕСТКАЯ СИНХРОНИЗАЦИЯ: Переключаем локализацию графического окна на системный язык сессии
        self.view.setup_ui_language(active_lang)
        self.view.update_file_context(device_number=device_number,
                                      result_path=self.settings_manager.calibration_file_path)

        self.view.generate_parameter_fields(self.model.algo_settings, stage=1)
        self.view.display_3d_plots(raw_data=self.model.raw_data, calibrated_data=None)

        self.view.save_result_clicked.connect(self._on_save_result_clicked)
        self.view.continue_clicked.connect(self._on_continue_clicked)
        self.view.btn_start.setEnabled(True)
        self.view.display_message(msg_ready)

    def _on_start_clicked(self):
        if not self.view.validate_fields():
            self.view.display_error(
                "Действие отклонено! Заполните пустые поля:" if self.settings_manager.current_lang == "Russian" else "Action rejected! Fill in empty fields:")
            return
        current_ui_mode = self.view.get_selected_calibration_mode()
        self.model.algo_settings["calibration_type"] = current_ui_mode
        if current_ui_mode == "manual":
            custom_params = self.view.get_custom_parameters()
            self.model.algo_settings.update(custom_params)
            self.last_executed_parameters.update(custom_params)

        if self.current_stage == 1:
            self.run_ransac_filtering_stage()
        else:
            self.run_gauss_newton_computation_stage()

    def run_ransac_filtering_stage(self):
        self.view.btn_start.setEnabled(False)
        is_ru = self.settings_manager.current_lang == "Russian"
        self.view.display_message(
            "Запуск RANSAC-экспертизы аномалий..." if is_ru else "Running RANSAC anomaly filtering...")
        QApplication.processEvents()

        filtered_plots_data = self.model.run_pass1_ransac()
        if not filtered_plots_data:
            self.view.btn_start.setEnabled(True)
            return

        self.view.display_filtered_ransac_plots(inliers=filtered_plots_data["inliers"],
                                                outliers=filtered_plots_data["outliers"])
        self.view.btn_start.setEnabled(True)
        self.view.btn_continue.setVisible(True)
        self.view.display_message(
            "Фильтрация завершена. Нажмите 'Продолжить' для перехода к расчету МНК." if is_ru else "Filtering completed. Click 'Continue' to proceed to GN-LSM.")

    # controllers/calibration_controller.py — Дополнение в Часть 3
    def show_settings_dialog(self) -> None:
        """Отображает изолированное окно конфигурации параметров среды магнетометра."""
        from mag_calibration.views.settings_dialog import SettingsDialog
        current_data = {
            "Language": self.settings_manager.current_lang,
            "Calibration result folder": str(self.settings_manager.save_result_dir)
        }

        # ОПТИМИЗИРОВАНО: parent=None для защиты С++ от удержания хостом
        dialog = SettingsDialog(current_settings=current_data, parent=None)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_settings = dialog.get_configured_settings()
            raw_lang = new_settings["Language"].strip()

            if raw_lang.startswith(("Rus", "rus")):
                raw_lang = "Russian"
            elif raw_lang.startswith(("Eng", "eng")):
                raw_lang = "English"

            self.settings_manager.current_lang = raw_lang
            self.settings_manager.save_result_dir = Path(new_settings["Calibration result folder"])

            # Сохраняем измененные параметры на жесткий диск
            self.settings_manager.save_setting("Language", self.settings_manager.current_lang, parent=None)
            self.settings_manager.save_setting("Calibration result folder",
                                               str(self.settings_manager.save_result_dir), parent=None)

    # mag_calibration/controllers/calibration_controller.py — Часть 4 из 4
    def _on_continue_clicked(self):
        self.current_stage = 2
        self.view.btn_continue.setVisible(False)
        self.view.generate_parameter_fields(self.model.algo_settings, stage=2)
        self.view.setup_stage2_buttons_ui()
        self.view.display_message(
            "Интерфейс переведен на Этап 2 (МНК Гаусса-Ньютона)." if self.settings_manager.current_lang == "Russian" else "Interface switched to Stage 2 (Gauss-Newton).")

    def run_gauss_newton_computation_stage(self):
        self.view.btn_start.setEnabled(False)
        is_ru = self.settings_manager.current_lang == "Russian"
        self.view.display_message("Запуск конвейера МНК..." if is_ru else "Starting GN-LSM pipeline...")
        QApplication.processEvents()

        offsets, coefficients, rmse = self.model.run_pass2_gauss_newton()
        if rmse == -1.0:
            self.view.display_error("[ОШИБКА]: Вычисления сорваны." if is_ru else "[ERROR]: Computation aborted.")
            self.view.btn_start.setEnabled(True)
            return

        self.model.calibration_offsets = offsets
        self.model.calibration_coefficients = coefficients
        self.model.calibrated_data = self.model.apply_calibration(self.model.raw_data, offsets, coefficients)

        lbl_res = "Смещения осей (Hard-Iron)" if is_ru else "Axis Offsets (Hard-Iron)"
        lbl_mat = "Матрица коэффициентов (Soft-Iron)" if is_ru else "Coefficients Matrix (Soft-Iron)"
        self.view.display_results({lbl_res: offsets.tolist(), lbl_mat: coefficients.tolist()})
        self.view.display_3d_plots(raw_data=self.model.raw_data, calibrated_data=self.model.calibrated_data)

        self.view.btn_start.setEnabled(True)
        self.view.btn_save_result.setVisible(True)
        self.view.display_message(
            "Результаты готовы. Нажмите 'Сохранить результат'." if is_ru else "Results ready. Click 'Save Result'.")

    def _on_save_clicked(self):
        if not self.view.validate_fields(): return
        self.model.algo_settings.update(self.view.get_custom_parameters())
        self._save_calibration_config()
        self.view.reset_modification_state()

    def _on_reset_clicked(self):
        self.settings_manager.ensure_default_files()
        self.settings_manager.load_settings()
        fresh_disk_config = self._load_raw_file_config_only()

        self.model.algo_settings.update(fresh_disk_config)
        self.last_executed_parameters = fresh_disk_config.copy()

        self.view.reset_to_values(fresh_disk_config)
        self.view.generate_parameter_fields(fresh_disk_config, stage=self.current_stage)

        if self.current_stage == 1:
            self.view.setup_stage1_buttons_ui()
            self.view.btn_continue.setVisible(False)
            self.view.display_3d_plots(raw_data=self.model.raw_data, calibrated_data=None)
        else:
            self.view.setup_stage2_buttons_ui()

        self.view.btn_save_result.setVisible(False)

        is_ru = self.settings_manager.current_lang == "Russian"
        self.view.display_message(
            f"Параметры Этапа {self.current_stage} восстановлены из конфигурации на диске." if is_ru else f"Stage {self.current_stage} parameters restored from disk.")

    def _on_default_clicked(self):
        factory_defaults = {"calibration_type": "auto", "ransac_iterations": 800, "ransac_threshold": 0.05,
                            "f_scale": 0.1, "iqr_multiplier": 1.5, "loss_type": "linear", "tolerance": 1e-12,
                            "max_iterations": 5000}
        self.view.reset_to_values(factory_defaults)

        is_ru = self.settings_manager.current_lang == "Russian"
        self.view.display_message(
            f"Поля Этапа {self.current_stage} заполнены заводскими значениями по умолчанию. Файл конфигурации не изменен." if is_ru else f"Stage {self.current_stage} fields populated with factory defaults. Configuration file not modified.")

    def _execute_json_save(self, offsets, coefficients, rmse):
        try:
            file_data = self.file_manager.read_json(self.settings_manager.calibration_file_path, self.view)
            device_number = file_data.get("fileInfo", {}).get("device_number",
                                                              "unknown").strip() if file_data else "unknown"
            save_structure = {"rmse": float(rmse), "hard_iron_offsets": offsets.tolist(),
                              "soft_iron_matrix": coefficients.tolist(),
                              "applied_algorithm_settings": self.model.algo_settings}
            self.session_manager.save_final_mag_matrix(save_structure, parent=self.view)
            current_timestamp = file_data.get("fileInfo", {}).get("changeTimeStamp", datetime.now().strftime(
                '%Y_%m_%d_%H_%M')) if file_data else "now"

            if self.view: self.view.accept()
            from mag_calibration.views.save_success_dialog import SaveSuccessDialog
            success_dlg = SaveSuccessDialog(filename=f"{device_number}_calibration_{current_timestamp}.json",
                                            folder_path=str(self.settings_manager.save_result_dir),
                                            lang=self.settings_manager.current_lang, parent=self._parent_window)
            success_dlg.exec()
        except Exception as e:
            if self.view: self.view.display_error(f"Критическая ошибка сохранения: {e}")

    def shutdown_session(self) -> None:
        if self.view: self.view.cleanup_resources(); self.view = None
        if self.model: self.model.logger = None; self.model = None
        print("✨ [Изоляция ОЗУ] Сессия полностью деаллоцирована.")

    def _on_save_result_clicked(self):
        if self.model.calibration_offsets is not None and self.model.calibration_coefficients is not None:
            self._execute_json_save(self.model.calibration_offsets, self.model.calibration_coefficients,
                                    self.model.algo_settings.get("rmse", 0.0))
