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
    """Пассивный графический интерфейс для визуализации калибровки магнетометра in 3D."""

    start_clicked = pyqtSignal()
    save_clicked = pyqtSignal()
    reset_clicked = pyqtSignal()
    save_result_clicked = pyqtSignal()
    continue_clicked = pyqtSignal()
    default_clicked = pyqtSignal()

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
                "btn_filter": "Отфильтровать",
                "btn_start_calib": "Старт калибровки",
                "btn_continue": "Продолжить",
                "btn_save_res": "Сохранить результат",
                "lbl_algo": "Настройки алгоритма",
                "mode_auto": "Автоматический",
                "mode_manual": "Ручной режим",
                "btn_save": "Сохранить профиль",
                "btn_reset": "Восстановить профиль",
                "btn_default": "Профиль по умолчанию",
                "res_title": "\n📌 [РЕЗУЛЬТАТЫ РАСЧЕТА RANSAC / МНК]:"
            },
            "English": {
                "title": "Interactive 3D Magnetometer Calibration Module",
                "device_lbl": "Device Number:",
                "file_lbl": "Calibration File:",
                "btn_filter": "Filter Data",
                "btn_start_calib": "Start Calibration",
                "btn_continue": "Continue",
                "btn_save_res": "Save Calibration Result",
                "lbl_algo": "Algorithm Settings",
                "mode_auto": "Automatic Tuning",
                "mode_manual": "Manual Configuration",
                "btn_save": "Save Profile",
                "btn_reset": "Restore Profile",
                "btn_default": "Factory Defaults",
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

        self.info_bar = QWidget()
        self.info_bar.setObjectName("MagInfoBar")
        self.info_bar.setStyleSheet(
            "QWidget#MagInfoBar { background-color: #f8f9fa; border: 1px solid #ced4da; border-radius: 6px; } QLabel { color: #000000; font-size: 13px; }")
        info_layout = QHBoxLayout(self.info_bar)
        self.lbl_device = QLabel(
            f"<b>{self.lp['device_lbl']}</b> <span style='color: #1A237E; font-weight: bold;'>-</span>")
        info_layout.addWidget(self.lbl_device)
        info_layout.addSpacing(40)
        info_layout.addWidget(QLabel(f"<b>{self.lp['file_lbl']}</b>"))
        self.lbl_file_link = QLabel("-")
        self.lbl_file_link.linkActivated.connect(self._open_file_folder)
        info_layout.addWidget(self.lbl_file_link)
        info_layout.addStretch()
        main_layout.addWidget(self.info_bar)

        top_layout = QHBoxLayout()
        self.control_panel = QWidget()
        self.control_panel.setFixedWidth(240)
        self.control_panel.setObjectName("MagControlPanel")
        self.control_panel.setStyleSheet(
            "QWidget#MagControlPanel { background-color: #1e1e1e; border-radius: 6px; } QWidget#MagControlPanel QLabel { font-weight: bold; color: #ffffff; font-size: 12px; } QWidget#MagControlPanel QRadioButton { color: #ffffff; font-size: 12px; padding: 4px; } QWidget#MagControlPanel QRadioButton::indicator { width: 14px; height: 14px; border: 1px solid #ced4da; border-radius: 8px; background-color: #333333; } QWidget#MagControlPanel QRadioButton::indicator:checked { background-color: #2da44e; border: 1px solid #2da44e; }")

        panel_layout = QVBoxLayout(self.control_panel)
        self.btn_start = QPushButton(self.lp["btn_filter"])
        self.btn_start.setEnabled(False)
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(self.start_clicked.emit)
        panel_layout.addWidget(self.btn_start)

        modes_layout = QVBoxLayout()
        modes_layout.addWidget(QLabel(self.lp["lbl_algo"]))
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
        self.params_widget.setObjectName("MagParamsWidget")
        self.params_widget.setStyleSheet(
            "QFrame#MagParamsWidget { border: 1px solid #3c3c3c; border-radius: 6px; background-color: #252526; }")
        self.params_layout = QVBoxLayout(self.params_widget)

        self.btn_save = QPushButton(self.lp["btn_save"])
        self.btn_save.setVisible(False)
        self.btn_save.clicked.connect(self.save_clicked.emit)

        self.btn_reset = QPushButton(self.lp["btn_reset"])
        self.btn_reset.setVisible(False)
        self.btn_reset.setMinimumHeight(28)
        self.btn_reset.setStyleSheet(
            "background-color: #6c757d; color: white; font-weight: bold; font-size: 11px; border-radius: 4px;")
        self.btn_reset.clicked.connect(self.reset_clicked.emit)

        self.btn_default = QPushButton(self.lp["btn_default"])
        self.btn_default.setVisible(False)
        self.btn_default.setMinimumHeight(28)
        self.btn_default.setStyleSheet(
            "background-color: #bb2d3b; color: white; font-weight: bold; font-size: 11px; border-radius: 4px;")
        self.btn_default.clicked.connect(self.default_clicked.emit)

        panel_layout.addWidget(self.params_widget)

        self.btn_continue = QPushButton(self.lp["btn_continue"])
        self.btn_continue.setMinimumHeight(38);
        self.btn_continue.setVisible(False)
        self.btn_continue.setStyleSheet(
            "QPushButton { background-color: #0d6efd; color: white; font-weight: bold; font-size: 12px; border-radius: 6px; }")
        self.btn_continue.clicked.connect(self.continue_clicked.emit)
        panel_layout.addWidget(self.btn_continue)

        self.btn_save_result = QPushButton(self.lp["btn_save_res"])
        self.btn_save_result.setMinimumHeight(38);
        self.btn_save_result.setVisible(False)
        self.btn_save_result.setStyleSheet(
            "QPushButton { background-color: #e67e22; color: white; font-weight: bold; border-radius: 6px; }")
        self.btn_save_result.clicked.connect(self.save_result_clicked.emit)
        panel_layout.addWidget(self.btn_save_result)
        panel_layout.addStretch();
        top_layout.addWidget(self.control_panel)

        self.gl_widget = gl.GLViewWidget()
        self.gl_widget.setCameraPosition(distance=40)
        top_layout.addWidget(self.gl_widget, stretch=4);
        main_layout.addLayout(top_layout, stretch=4)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet(
            "QTextEdit { background-color: #000000; color: #00ff00; font-family: monospace; font-size: 12px; }")
        main_layout.addWidget(self.log_output, stretch=1)

# mag_calibration/views/calibration_view.py — Часть 3 из 4
    def update_file_context(self, device_number: str, result_path: Path):
        self._result_path = Path(result_path).resolve()
        self.lbl_device.setText(f"<b>{self.lp['device_lbl']}</b> <span style='color: #1A237E; font-weight: bold; font-size: 15px;'>{device_number}</span>")
        self.lbl_file_link.setText(f"<a href='#' style='color: #3498db; text-decoration: underline; font-weight: bold;'>{self._result_path.name}</a>")

    def _open_file_folder(self):
        if self._result_path and self._result_path.parent.exists():
            folder_path = self._result_path.parent
            import sys
            if sys.platform == "win32": os.startfile(folder_path)
            elif sys.platform == "darwin": subprocess.Popen(["open", folder_path])
            else: subprocess.Popen(["xdg-open", folder_path])

    def setup_ui_language(self, lang: str = "Russian"):
        self.lp = self.loc.get(lang, self.loc["English"])
        self.setWindowTitle(self.lp["title"])
        self.radio_auto.setText(self.lp["mode_auto"])
        self.radio_manual.setText(self.lp["mode_manual"])
        self.btn_save.setText(self.lp["btn_save"])
        self.btn_reset.setText(self.lp["btn_reset"])
        self.btn_default.setText(self.lp["btn_default"])
        self.btn_continue.setText(self.lp["btn_continue"])
        self.btn_save_result.setText(self.lp["btn_save_res"])

    def setup_stage1_buttons_ui(self):
        self.btn_start.setText(self.lp["btn_filter"])
        self.btn_start.setStyleSheet("QPushButton { background-color: #2da44e; color: white; font-weight: bold; font-size: 13px; border-radius: 6px; }")

    def setup_stage2_buttons_ui(self):
        self.btn_start.setText(self.lp["btn_start_calib"])
        self.btn_start.setStyleSheet("QPushButton { background-color: #e67e22; color: white; font-weight: bold; font-size: 13px; border-radius: 6px; }")

    def _toggle_params_visibility(self):
        is_manual = self.radio_manual.isChecked()
        self.params_widget.setVisible(is_manual)
        if is_manual:
            self._check_for_modifications()
        else:
            self.btn_save.setVisible(False)
            self.btn_reset.setVisible(False)
            self.btn_default.setVisible(False)

    def generate_parameter_fields(self, algo_settings: dict, stage: int = 1):
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            if item.widget() and item.widget() not in (self.btn_save, self.btn_reset, self.btn_default):
                item.widget().deleteLater()
        self.param_inputs.clear(); self.original_values.clear()

        target_keys = ("ransac_iterations", "ransac_threshold") if stage == 1 else ("f_scale", "iqr_multiplier", "loss_type", "tolerance")

        for key, value in algo_settings.items():
            if key not in target_keys: continue
            lbl = QLabel(self.param_labels.get(key, key))
            lbl.setStyleSheet("color: #d4d4d4; font-size: 11px; margin-top: 4px;")
            self.params_layout.addWidget(lbl)
            inp = QLineEdit(str(value))
            inp.setStyleSheet("QLineEdit { background: #ffffff; color: #000000; border: 1px solid #555555; border-radius: 4px; padding: 4px; font-size: 12px; }")
            self.params_layout.addWidget(inp)
            self.param_inputs[key] = inp; self.original_values[key] = str(value)
            inp.textChanged.connect(self._check_for_modifications)

        self.params_layout.addWidget(self.btn_save)
        self.params_layout.addWidget(self.btn_reset)
        self.params_layout.addWidget(self.btn_default)
        self._toggle_params_visibility()

    # mag_calibration/views/calibration_view.py — Часть 4 из 4
    def reset_modification_state(self):
        for key, inp in self.param_inputs.items(): self.original_values[key] = inp.text().strip()
        self._check_for_modifications()

    def _check_for_modifications(self):
        has_changes = False
        for key, inp in self.param_inputs.items():
            curr, orig = inp.text().strip(), self.original_values.get(key, "")
            if curr == "":
                inp.setStyleSheet(
                    "QLineEdit { background: #5c1d24; color: #ffffff; border: 1px solid #ff4d4d; }"); has_changes = True
            elif curr != orig:
                has_changes = True; inp.setStyleSheet(
                    "QLineEdit { background: #fff3cd; color: #000000; border: 1px solid #ffc107; }")
            else:
                inp.setStyleSheet("QLineEdit { background: #ffffff; color: #000000; border: 1px solid #555555; }")

        is_manual = self.radio_manual.isChecked()
        self.btn_save.setVisible(has_changes and is_manual)
        self.btn_reset.setVisible(has_changes and is_manual)
        self.btn_default.setVisible(has_changes and is_manual)

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
            try:
                res[key] = float(txt) if "." in txt or "e" in txt.lower() else int(txt)
            except ValueError:
                res[key] = txt
        return res

    def set_calibration_mode_ui(self, mode: str):
        self.radio_auto.setChecked(mode == "auto"); self.radio_manual.setChecked(
            mode != "auto"); self._toggle_params_visibility()

    def get_selected_calibration_mode(self) -> str:
        return "auto" if self.radio_auto.isChecked() else "manual"

    def display_message(self, text: str):
        self.log_output.append(f"ℹ️ {text}")

    def display_error(self, text: str):
        self.log_output.append(f'<span style="color:#ff4d4d; font-weight:bold;">⚠️ {text}</span>')

    def display_results(self, results: dict):
        self.log_output.append(self.lp.get("res_title", "\n📌 [РЕЗУЛЬТАТЫ РАСЧЕТА SVD]:"))
        for k, v in results.items():
            if isinstance(v, list) and any(isinstance(i, list) for i in v):
                self.log_output.append(f"   {k}:")
                for row in v: self.log_output.append("      " + ", ".join([f"{num:10.6f}" for num in row]))
            else:
                self.log_output.append(f"   {k}: {v}")

    def display_filtered_ransac_plots(self, inliers: dict, outliers: dict):
        for item in list(self.gl_widget.items):
            if isinstance(item, gl.GLScatterPlotItem): self.gl_widget.removeItem(item)
        in_pts, out_pts = np.vstack([inliers['x'], inliers['y'], inliers['z']]).T, np.vstack(
            [outliers['x'], outliers['y'], outliers['z']]).T
        if len(in_pts) > 0:
            scaled_in = in_pts * self.scale_factor;
            c_in = np.zeros((len(scaled_in), 4));
            c_in[:] = [0.2, 1.0, 0.2, 0.6]
            self.gl_widget.addItem(gl.GLScatterPlotItem(pos=scaled_in, color=c_in, size=3, pxMode=True))
        if len(out_pts) > 0:
            scaled_out = out_pts * self.scale_factor;
            c_out = np.zeros((len(scaled_out), 4));
            c_out[:] = [1.0, 0.2, 0.2, 0.4]
            self.gl_widget.addItem(gl.GLScatterPlotItem(pos=scaled_out, color=c_out, size=3, pxMode=True))

        if len(in_pts) > 0:
            center = np.mean(scaled_in, axis=0)
            self.gl_widget.opts['center'] = QVector3D(float(center[0]), float(center[1]), float(center[2]))

    def display_3d_plots(self, raw_data, calibrated_data=None):
        """Отрисовывает 3D графики магнитной среды с жестко выровненной сеткой строго по осям (0,0,0)."""
        for item in list(self.gl_widget.items):
            if isinstance(item, (gl.GLScatterPlotItem, gl.GLGridItem, gl.GLTextItem, gl.GLLinePlotItem)):
                self.gl_widget.removeItem(item)

        raw_pts = np.vstack([raw_data['x'], raw_data['y'], raw_data['z']]).T

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

        # Вычисляем центр масс облака точек для фокуса камеры
        if calibrated_data and ("inliers" in calibrated_data):
            in_pts = np.vstack(
                [calibrated_data['inliers']['x'], calibrated_data['inliers']['y'], calibrated_data['inliers']['z']]).T
            out_pts = np.vstack([calibrated_data['outliers']['x'], calibrated_data['outliers']['y'],
                                 calibrated_data['outliers']['z']]).T
            all_displayed_pts = np.vstack([in_pts, out_pts]) * self.scale_factor if len(
                out_pts) > 0 else in_pts * self.scale_factor
            center = np.mean(in_pts * self.scale_factor, axis=0) if len(in_pts) > 0 else np.zeros(3)
        else:
            in_pts, out_pts = None, None
            all_displayed_pts = scaled_raw
            center = np.mean(scaled_raw, axis=0)

        # Расчет длины осей с запасом 15%
        max_coord_val = np.max(np.abs(all_displayed_pts)) if len(all_displayed_pts) > 0 else 15.0
        axis_len = float(max_coord_val * 1.15)

        # Чтобы сетка GLGridItem была кратна шагу и центрировалась по осям,
        # задаем нечетное количество ячеек или явно компенсируем сдвиг.
        # ИСПРАВЛЕНО: Задаем размер сетки, строго кратный шагу, делая количество линий нечетным.
        grid_size = int(math.ceil(axis_len * 2 / s_step))
        if grid_size % 2 == 0:
            grid_size += 1
        total_size = grid_size * s_step

        grid_xy = gl.GLGridItem()
        grid_xy.setSize(total_size, total_size, 0)
        grid_xy.setSpacing(spacing=grid_spacing_vector)
        self.gl_widget.addItem(grid_xy)

        grid_xz = gl.GLGridItem()
        grid_xz.setSize(x=total_size, y=total_size, z=0)
        grid_xz.setSpacing(spacing=grid_spacing_vector)
        grid_xz.rotate(90, 1, 0, 0)
        self.gl_widget.addItem(grid_xz)

        grid_yz = gl.GLGridItem()
        grid_yz.setSize(x=total_size, y=total_size, z=0)
        grid_yz.setSpacing(spacing=grid_spacing_vector)
        grid_yz.rotate(90, 0, 1, 0)
        self.gl_widget.addItem(grid_yz)

        # Отрисовка сплошных цветных осей координат (проходят строго через ноль)
        self.gl_widget.addItem(
            gl.GLLinePlotItem(pos=np.array([[-axis_len, 0, 0], [axis_len, 0, 0]]), color=(1.0, 0.2, 0.2, 0.9),
                              width=6.0, antialias=True))
        self.gl_widget.addItem(
            gl.GLLinePlotItem(pos=np.array([[0, -axis_len, 0], [0, axis_len, 0]]), color=(0.2, 1.0, 0.2, 0.9),
                              width=6.0, antialias=True))
        self.gl_widget.addItem(
            gl.GLLinePlotItem(pos=np.array([[0, 0, -axis_len], [0, 0, axis_len]]), color=(0.2, 0.2, 1.0, 0.9),
                              width=6.0, antialias=True))

        # Вывод точек
        if in_pts is not None:
            s_in = in_pts * self.scale_factor
            c_in = np.zeros((len(s_in), 4));
            c_in[:] = [0.2, 1.0, 0.2, 0.6]
            self.scatter_calibrated = gl.GLScatterPlotItem(pos=s_in, color=c_in, size=3, pxMode=True)
            self.gl_widget.addItem(self.scatter_calibrated)

            if len(out_pts) > 0:
                s_out = out_pts * self.scale_factor
                c_out = np.zeros((len(s_out), 4));
                c_out[:] = [1.0, 0.2, 0.2, 0.4]
                scatter_cal_outliers = gl.GLScatterPlotItem(pos=s_out, color=c_out, size=3, pxMode=True)
                self.gl_widget.addItem(scatter_cal_outliers)
        else:
            c_raw = np.zeros((len(scaled_raw), 4));
            c_raw[:] = [1.0, 0.0, 0.0, 0.5]
            self.scatter_raw = gl.GLScatterPlotItem(pos=scaled_raw, color=c_raw, size=3, pxMode=True)
            self.gl_widget.addItem(self.scatter_raw)

        # Наведение фокуса камеры на центр облака точек
        if len(center) >= 3:
            self.gl_widget.opts['center'] = QVector3D(float(center[0]), float(center[1]), float(center[2]))
        else:
            self.gl_widget.opts['center'] = QVector3D(0.0, 0.0, 0.0)

    def cleanup_resources(self):
        try:
            self.start_clicked.disconnect();
            self.save_clicked.disconnect();
            self.reset_clicked.disconnect()
            if hasattr(self, 'save_result_clicked'): self.save_result_clicked.disconnect()
            if hasattr(self, 'continue_clicked'): self.continue_clicked.disconnect()
            if hasattr(self, 'default_clicked'): self.default_clicked.disconnect()
        except Exception:
            pass
        if self.gl_widget:
            for item in list(self.gl_widget.items):
                try:
                    if hasattr(item, 'shader'): item.shader = None
                    if hasattr(item, 'program'): item.program = None
                    self.gl_widget.removeItem(item)
                except Exception:
                    pass
        self.scatter_raw = None;
        self.scatter_calibrated = None
        if self.gl_widget:
            try:
                self.gl_widget.setParent(None);
                self.gl_widget.clear()
                from PyQt6 import sip;
                sip.delete(self.gl_widget)
            except Exception:
                pass
            self.gl_widget = None
        try:
            import sys
            modules_to_unload = [m for m in list(sys.modules.keys()) if
                                 m.startswith('pyqtgraph') or m.startswith('OpenGL')]
            for module_name in modules_to_unload: del sys.modules[module_name]
        except Exception:
            pass
        self.deleteLater()

    def closeEvent(self, event):
        self.cleanup_resources(); super().closeEvent(event)
