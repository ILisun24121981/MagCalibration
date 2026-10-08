# mag_calibration/views/calibration_view.py — Часть 1 из 4
import sys
import math
import os
import subprocess
from pathlib import Path
import numpy as np
from PyQt6 import QtCore
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QTextEdit, QApplication, QPushButton,
                             QRadioButton, QButtonGroup, QLineEdit, QFrame)
from PyQt6.QtGui import QVector3D
from PyQt6.QtCore import pyqtSignal
import pyqtgraph.opengl as gl


class CalibrationView(QDialog):
    """Пассивный графический интерфейс для визуализации калибровки магнетометра в 3D."""

    start_clicked = pyqtSignal()
    save_clicked = pyqtSignal()
    reset_clicked = pyqtSignal()

    # Изолированный сигнал для кнопки фиксации результатов расчета
    save_result_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MagCalibrationMainDialog")

        self.resize(1150, 820)

        self.param_inputs = {}
        self.original_values = {}
        self.scatter_raw = None
        self.scatter_calibrated = None
        self._result_path = None

        self._init_localization_dictionaries()
        self._build_ui_layout()

    def _init_localization_dictionaries(self):
        self.param_labels = {
            "f_scale": "Масштаб функции (f_scale)",
            "iqr_multiplier": "Множитель IQR",
            "loss_type": "Тип функции потерь",
            "tolerance": "Порог сходимости (ftol)",
            "ransac_iterations": "Итерации RANSAC",
            "ransac_threshold": "Порог RANSAC"
        }

        self.loc = {
            "Russian": {
                "title": "Интерактивный модуль 3D-калибровки Магнетометра",
                "device_lbl": "Номер прибора:",
                "file_lbl": "Файл калибровки:",
                "btn_start": "Старт калибровки",
                "btn_save_res": "Сохранить результат",
                "lbl_algo": "Настройки алгоритма",
                "mode_auto": "Автоматический",
                "mode_manual": "Ручной режим",
                "btn_save": "Сохранить профиль",
                "btn_reset": "Сбросить поля",
                "res_title": "\n📌 [РЕЗУЛЬТАТЫ РАСЧЕТА RANSAC / МНК]:"
            },
            "English": {
                "title": "Interactive 3D Magnetometer Calibration Module",
                "device_lbl": "Device Number:",
                "file_lbl": "Calibration File:",
                "btn_start": "Start Calibration",
                "btn_save_res": "Save Calibration Result",
                "lbl_algo": "Algorithm Settings",
                "mode_auto": "Automatic Tuning",
                "mode_manual": "Manual Configuration",
                "btn_save": "Save Profile",
                "btn_reset": "Reset Fields",
                "res_title": "\n📌 [RANSAC / LSQ CALIBRATION RESULTS]:"
            }
        }

    # mag_calibration/views/calibration_view.py — Часть 2 из 4

    def _build_ui_layout(self):
        self.lp = self.loc["Russian"]
        self.setWindowTitle(self.lp["title"])

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # --- ВЕРХНИЙ ГОРИЗОНТАЛЬНЫЙ ИНФО-БАР ---
        self.info_bar = QWidget()
        self.info_bar.setObjectName("MagInfoBar")
        self.info_bar.setStyleSheet("""
            QWidget#MagInfoBar { 
                background-color: #f8f9fa; 
                border: 1px solid #ced4da; 
                border-radius: 6px; 
            }
            QLabel { color: #000000; font-size: 13px; }
        """)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(20, 10, 20, 10)

        self.lbl_device = QLabel(
            f"<b>{self.lp['device_lbl']}</b> <span style='color: #1A237E; font-weight: bold;'>-</span>")
        self.lbl_device.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(self.lbl_device)

        info_layout.addSpacing(40)

        self.lbl_file_title = QLabel(f"<b>{self.lp['file_lbl']}</b>")
        info_layout.addWidget(self.lbl_file_title)

        self.lbl_file_link = QLabel("-")
        self.lbl_file_link.setOpenExternalLinks(False)
        self.lbl_file_link.linkActivated.connect(self._open_file_folder)
        info_layout.addWidget(self.lbl_file_link)

        info_layout.addStretch()
        main_layout.addWidget(self.info_bar)

        # --- ОСНОВНОЙ КОНТЕНТ (Сайдбар + График) ---
        top_layout = QHBoxLayout()

        self.control_panel = QWidget()
        self.control_panel.setFixedWidth(240)
        self.control_panel.setObjectName("MagControlPanel")

        self.control_panel.setStyleSheet("""
            QWidget#MagControlPanel { background-color: #1e1e1e; border-radius: 6px; }
            QWidget#MagControlPanel QLabel { font-weight: bold; color: #ffffff; font-size: 12px; background: transparent; border: none; }

            QWidget#MagControlPanel QRadioButton { 
                color: #ffffff; 
                font-size: 12px; 
                padding: 4px; 
                background: transparent; 
            }
            QWidget#MagControlPanel QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #ced4da;
                border-radius: 8px;
                background-color: #333333;
            }
            QWidget#MagControlPanel QRadioButton::indicator:checked {
                background-color: #2da44e;
                border: 1px solid #2da44e;
            }
            QWidget#MagControlPanel QRadioButton::indicator:hover {
                border: 1px solid #ffffff;
            }
        """)

        panel_layout = QVBoxLayout(self.control_panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        self.btn_start = QPushButton(self.lp["btn_start"])
        self.btn_start.setEnabled(False)
        self.btn_start.setMinimumHeight(40)
        self.btn_start.setStyleSheet("""
            QPushButton { background-color: #2da44e; color: white; font-weight: bold; font-size: 13px; border-radius: 6px; }
            QPushButton:hover { background-color: #2c974b; }
            QPushButton:disabled { background-color: #343a40; color: #6c757d; }
        """)
        self.btn_start.clicked.connect(self.start_clicked.emit)
        panel_layout.addWidget(self.btn_start)

        modes_layout = QVBoxLayout()
        modes_layout.setContentsMargins(5, 15, 0, 0)
        lbl_title = QLabel(self.lp["lbl_algo"])
        modes_layout.addWidget(lbl_title)

        self.radio_auto = QRadioButton(self.lp["mode_auto"])
        self.radio_manual = QRadioButton(self.lp["mode_manual"])
        modes_layout.addWidget(self.radio_auto)
        modes_layout.addWidget(self.radio_manual)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_auto, 0)
        self.mode_group.addButton(self.radio_manual, 1)
        self.mode_group.idClicked.connect(self._toggle_params_visibility)
        panel_layout.addLayout(modes_layout)

        self.params_widget = QFrame()
        self.params_widget.setFrameShape(QFrame.Shape.StyledPanel)
        self.params_widget.setObjectName("MagParamsWidget")
        self.params_widget.setStyleSheet("""
            QFrame#MagParamsWidget { border: 1px solid #3c3c3c; border-radius: 6px; background-color: #252526; }
            QFrame#MagParamsWidget QLabel { border: none; background: transparent; color: #ffffff; }
        """)

        self.params_layout = QVBoxLayout(self.params_widget)
        self.params_layout.setContentsMargins(10, 10, 10, 10)
        self.params_layout.setSpacing(6)

        self.btn_save = QPushButton(self.lp["btn_save"])
        self.btn_save.setVisible(False)
        self.btn_save.setMinimumHeight(28)
        self.btn_save.setStyleSheet(
            "background-color: #0d6efd; color: white; font-weight: bold; font-size: 11px; border-radius: 4px;")
        self.btn_save.clicked.connect(self.save_clicked.emit)

        self.btn_reset = QPushButton(self.lp["btn_reset"])
        self.btn_reset.setVisible(False)
        self.btn_reset.setMinimumHeight(28)
        self.btn_reset.setStyleSheet(
            "background-color: #6c757d; color: white; font-weight: bold; font-size: 11px; border-radius: 4px;")
        self.btn_reset.clicked.connect(self.reset_clicked.emit)

        panel_layout.addWidget(self.params_widget)

        self.btn_save_result = QPushButton(self.lp["btn_save_res"])
        self.btn_save_result.setMinimumHeight(38)
        self.btn_save_result.setVisible(False)
        self.btn_save_result.setStyleSheet("""
            QPushButton { 
                background-color: #e67e22; 
                color: white; 
                font-weight: bold; 
                font-size: 12px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: #d35400; }
        """)
        self.btn_save_result.clicked.connect(self.save_result_clicked.emit)
        panel_layout.addWidget(self.btn_save_result)

        panel_layout.addStretch()
        top_layout.addWidget(self.control_panel)

        # ВОЗВРАЩЕНО К СТАНДАРТУ: Полностью локальное создание виджета
        # При таком подходе принудительный sip.delete() в методе cleanup_resources сработает идеально
        self.gl_widget = gl.GLViewWidget()
        self.gl_widget.setCameraPosition(distance=40)
        top_layout.addWidget(self.gl_widget, stretch=4)
        main_layout.addLayout(top_layout, stretch=4)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet(
            "QTextEdit { background-color: #000000; color: #00ff00; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; }")
        main_layout.addWidget(self.log_output, stretch=1)

# mag_calibration/views/calibration_view.py — Часть 3 из 4

    def update_file_context(self, device_number: str, result_path: Path):
        """Обновляет заголовок инфо-бара актуальными данными сессии прибора."""
        self._result_path = Path(result_path).resolve()
        self.lbl_device.setText(f"<b>{self.lp['device_lbl']}</b> <span style='color: #1A237E; font-weight: bold; font-size: 15px;'>{device_number}</span>")
        self.lbl_file_link.setText(f"<a href='#' style='color: #3498db; text-decoration: underline; font-weight: bold;'>{self._result_path.name}</a>")

    def _open_file_folder(self):
        """Открывает папку с текущим сессионным файлом калибровки."""
        if self._result_path and self._result_path.parent.exists():
            folder_path = self._result_path.parent
            import sys
            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])

    def setup_ui_language(self, lang: str = "Russian"):
        self.lp = self.loc.get(lang, self.loc["English"])
        self.setWindowTitle(self.lp["title"])
        self.btn_start.setText(self.lp["btn_start"])
        self.radio_auto.setText(self.lp["mode_auto"])
        self.radio_manual.setText(self.lp["mode_manual"])
        self.btn_save.setText(self.lp["btn_save"])
        self.btn_reset.setText(self.lp["btn_reset"])
        self.btn_save_result.setText(self.lp["btn_save_res"])

    def _toggle_params_visibility(self):
        is_manual = self.radio_manual.isChecked()
        self.params_widget.setVisible(is_manual)
        self.btn_reset.setVisible(is_manual)
        if is_manual:
            self._check_for_modifications()
        else:
            self.btn_save.setVisible(False)

    def generate_parameter_fields(self, algo_settings: dict):
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            if item.widget() and item.widget() not in (self.btn_save, self.btn_reset):
                item.widget().deleteLater()
        self.param_inputs.clear()
        self.original_values.clear()

        for key, value in algo_settings.items():
            if key in ("calibration_type", "max_iterations"): continue

            lbl = QLabel(self.param_labels.get(key, key))
            lbl.setStyleSheet("color: #d4d4d4; font-size: 11px; margin-top: 4px;")
            self.params_layout.addWidget(lbl)

            inp = QLineEdit(str(value))
            inp.setStyleSheet("QLineEdit { background: #333333; color: #ffffff; border: 1px solid #555555; border-radius: 4px; padding: 4px; font-size: 12px; }")
            self.params_layout.addWidget(inp)

            self.param_inputs[key] = inp
            self.original_values[key] = str(value)
            inp.textChanged.connect(self._check_for_modifications)

        self.params_layout.addWidget(self.btn_save)
        self.params_layout.addWidget(self.btn_reset)
        self._toggle_params_visibility()

    def reset_modification_state(self):
        """Сбрасывает флаги изменений в интерфейсе после успешного сохранения настроек алгоритма на диск."""
        # Перезаписываем оригинальные значения текущими строками из полей ввода
        for key, inp in self.param_inputs.items():
            self.original_values[key] = inp.text().strip()

        # Принудительно вызываем внутренний перерасчет стилей полей, чтобы убрать красную/розовую подсветку
        self._check_for_modifications()

    def _check_for_modifications(self):
        has_changes = False
        for key, inp in self.param_inputs.items():
            curr = inp.text().strip()
            orig = self.original_values.get(key, "")

            if curr == "":
                inp.setStyleSheet("QLineEdit { background: #5c1d24; color: #ffffff; border: 1px solid #ff4d4d; border-radius: 4px; padding: 4px; font-size: 12px; }")
                has_changes = True
            elif curr != orig:
                has_changes = True
                inp.setStyleSheet("QLineEdit { background: #443135; color: #ffffff; border: 1px solid #f5c2c7; border-radius: 4px; padding: 4px; font-size: 12px; }")
            else:
                inp.setStyleSheet("QLineEdit { background: #333333; color: #ffffff; border: 1px solid #555555; border-radius: 4px; padding: 4px; font-size: 12px; }")
        self.btn_save.setVisible(has_changes and self.radio_manual.isChecked())

    def reset_to_values(self, settings_dict: dict):
        for key, inp in self.param_inputs.items():
            if key in settings_dict: inp.setText(str(settings_dict[key]))
        self._check_for_modifications()

    def validate_fields(self) -> bool:
        return len([k for k, inp in self.param_inputs.items() if inp.text().strip() == ""]) == 0

    def get_custom_parameters(self) -> dict:
        res = {}
        for key, inp in self.param_inputs.items():
            txt = inp.text().strip()
            try: res[key] = float(txt) if "." in txt or "e" in txt.lower() else int(txt)
            except ValueError: res[key] = txt
        return res

    def set_calibration_mode_ui(self, mode: str):
        self.radio_auto.setChecked(mode == "auto")
        self.radio_manual.setChecked(mode != "auto")
        self._toggle_params_visibility()

    def get_selected_calibration_mode(self) -> str:
        return "auto" if self.radio_auto.isChecked() else "manual"

    # mag_calibration/views/calibration_view.py — Часть 4 из 4

    def display_message(self, text: str):
        self.log_output.append(f"ℹ️ {text}")

    def display_error(self, text: str):
        self.log_output.append(f'<span style="color:#ff4d4d; font-weight:bold;">⚠️ {text}</span>')

    def display_results(self, results: dict):
        self.log_output.append(self.lp.get("res_title", "\n📌 [РЕЗУЛЬТАТЫ РАСЧЕТА SVD]:"))
        for k, v in results.items():
            if isinstance(v, list) and any(isinstance(i, list) for i in v):
                self.log_output.append(f"   {k}:")
                for row in v:
                    self.log_output.append("      " + ", ".join([f"{num:10.6f}" for num in row]))
            else:
                self.log_output.append(f"   {k}: {v}")

    def display_3d_plots(self, raw_data, calibrated_data=None):
        for item in list(self.gl_widget.items):
            if isinstance(item, (gl.GLScatterPlotItem, gl.GLGridItem, gl.GLTextItem, gl.GLLinePlotItem)):
                self.gl_widget.removeItem(item)

        raw_pts = np.vstack([raw_data['x'], raw_data['y'], raw_data['z']]).T
        cal_pts = np.vstack([calibrated_data['x'], calibrated_data['y'], calibrated_data['z']]).T if (
                calibrated_data and any(calibrated_data[k] for k in ('x', 'y', 'z'))) else None

        self.scale_factor = 15.0 / max(np.max(np.abs(raw_pts)), 1.0)
        scaled_raw = raw_pts * self.scale_factor
        mn_x, mx_x = np.min(raw_data['x']), np.max(raw_data['x'])
        mn_y, mx_y = np.min(raw_data['y']), np.max(raw_data['y'])
        mn_z, mx_z = np.min(raw_data['z']), np.max(raw_data['z'])
        span = max(mx_x - mn_x, mx_y - mn_y, mx_z - mn_z)

        grid_step = float((1.0 if (span / 6.0) / (10 ** math.floor(math.log10(span / 6.0))) < 1.5 else (
            2.0 if (span / 6.0) / (10 ** math.floor(math.log10(span / 6.0))) < 3.5 else (
                5.0 if (span / 6.0) / (10 ** math.floor(math.log10(span / 6.0))) < 7.5 else 10.0))) * (
                                  10 ** math.floor(math.log10(span / 6.0)))) if span > 0 else 1000.0
        s_step = max(0.1, min(grid_step * self.scale_factor, 30.0))
        grid_spacing_vector = QVector3D(s_step, s_step, s_step)

        grid_xy = gl.GLGridItem();
        grid_xy.setSize(40, 40, 0);
        grid_xy.setSpacing(spacing=grid_spacing_vector);
        self.gl_widget.addItem(grid_xy)
        grid_xz = gl.GLGridItem();
        grid_xz.setSize(x=40, y=40, z=0);
        grid_xz.setSpacing(spacing=grid_spacing_vector);
        grid_xz.rotate(90, 1, 0, 0);
        self.gl_widget.addItem(grid_xz)
        grid_yz = gl.GLGridItem();
        grid_yz.setSize(x=40, y=40, z=0);
        grid_yz.setSpacing(spacing=grid_spacing_vector);
        grid_yz.rotate(90, 0, 1, 0);
        self.gl_widget.addItem(grid_yz)

        st_x, end_x = min(0.0, mn_x * self.scale_factor - 2 * s_step), max(0.0,
                                                                           mx_x * self.scale_factor + 2 * s_step)
        st_y, end_y = min(0.0, mn_y * self.scale_factor - 2 * s_step), max(0.0,
                                                                           mx_y * self.scale_factor + 2 * s_step)
        st_z, end_z = min(0.0, mn_z * self.scale_factor - 2 * s_step), max(0.0,
                                                                           mx_z * self.scale_factor + 2 * s_step)

        self.gl_widget.addItem(
            gl.GLLinePlotItem(pos=np.array([[st_x, 0, 0], [end_x, 0, 0]]), color=(1.0, 0.2, 0.2, 0.9), width=6.0,
                              antialias=True))
        self.gl_widget.addItem(
            gl.GLLinePlotItem(pos=np.array([[0, st_y, 0], [0, end_y, 0]]), color=(0.2, 1.0, 0.2, 0.9), width=6.0,
                              antialias=True))
        self.gl_widget.addItem(
            gl.GLLinePlotItem(pos=np.array([[0, 0, st_z], [0, 0, end_z]]), color=(0.2, 0.2, 1.0, 0.9), width=6.0,
                              antialias=True))

        c_raw = np.zeros((len(scaled_raw), 4));
        c_raw[:] = [1, 0, 0, 0.5]
        self.scatter_raw = gl.GLScatterPlotItem(pos=scaled_raw, color=c_raw, size=3, pxMode=True)
        self.gl_widget.addItem(self.scatter_raw)

        # ИСПРАВЛЕНО: Пересчитываем фокус вращения камеры на центр калиброванных точек, если они переданы
        if cal_pts is not None:
            s_cal = cal_pts * self.scale_factor
            c_cal = np.zeros((len(s_cal), 4));
            c_cal[:] = [0, 1, 0, 0.6]
            self.scatter_calibrated = gl.GLScatterPlotItem(pos=s_cal, color=c_cal, size=3, pxMode=True)
            self.gl_widget.addItem(self.scatter_calibrated)

            # Фокусируемся на зеленой сфере (калиброванные данные)
            center = np.mean(s_cal, axis=0)
        else:
            # Стартовое состояние: фокусируемся на красной несбалансированной сфере
            center = np.mean(scaled_raw, axis=0)

        self.gl_widget.opts['center'] = QVector3D(float(center[0]), float(center[1]), float(center[2]))

    def cleanup_resources(self):
        """Полная, синхронная и изолированная зачистка всех OpenGL ресурсов модуля."""
        try:
            self.start_clicked.disconnect()
            self.save_clicked.disconnect()
            self.reset_clicked.disconnect()
            if hasattr(self, 'save_result_clicked'):
                self.save_result_clicked.disconnect()
        except Exception:
            pass

        # 1. Сброс программ у элементов сцены
        if self.gl_widget:
            for item in list(self.gl_widget.items):
                try:
                    if hasattr(item, 'shader'): item.shader = None
                    if hasattr(item, 'program'): item.program = None
                    self.gl_widget.removeItem(item)
                except Exception:
                    pass

        self.scatter_raw = None
        self.scatter_calibrated = None

        # 2. Жесткое удаление C++ виджета из памяти через PyQt6.sip
        if self.gl_widget:
            try:
                self.gl_widget.setParent(None)
                self.gl_widget.clear()
                from PyQt6 import sip
                sip.delete(self.gl_widget)
                print("🗑️ [Изоляция] Виджет GLViewWidget синхронно удален из C++ памяти.")
            except Exception as e:
                print(f"[Магнетометр] Ошибка жесткого удаления виджета: {e}")
            self.gl_widget = None

        # 3. ТОТАЛЬНАЯ ВЫГРУЗКА МОДУЛЕЙ ИЗ ОЗУ ПРОЦЕССА
        # Стираем pyqtgraph и OpenGL из sys.modules, чтобы гарантировать
        # их полную повторную инициализацию при следующем запуске плагина.
        try:
            import sys
            modules_to_unload = [
                m for m in list(sys.modules.keys())
                if m.startswith('pyqtgraph') or m.startswith('OpenGL')
            ]
            for module_name in modules_to_unload:
                del sys.modules[module_name]
            print(f"🧹 [Изоляция] Из ОЗУ выгружено {len(modules_to_unload)} модулей графического движка.")
        except Exception as e:
            print(f"[Магнетометр] Ошибка горячей выгрузки модулей: {e}")

        self.deleteLater()

    def closeEvent(self, event):
        self.cleanup_resources()
        super().closeEvent(event)
