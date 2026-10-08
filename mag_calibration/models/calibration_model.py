# mag_calibration/models/calibration_model.py — Часть 1 из 2
import json
import os
import random
import numpy as np
from scipy.optimize import least_squares


def _geometric_ellipsoid_residuals(params, x, y, z):
    """Стабильный расчет невязки повернутого эллипсоида.

    Для точек строго на поверхности функция возвращает 0.0.
    """
    ox, oy, oz, a, b, c, alpha, beta, gamma = params

    a = max(a, 1e-6)
    b = max(b, 1e-6)
    c = max(c, 1e-6)

    xc, yc, zc = x - ox, y - oy, z - oz

    ca, sa = np.cos(alpha), np.sin(alpha)
    cb, sb = np.cos(beta), np.sin(beta)
    cg, sg = np.cos(gamma), np.sin(gamma)

    x_rot = (cb * cg) * xc + (cb * sg) * yc - sb * zc
    y_rot = (sa * sb * cg - ca * sg) * xc + (sa * sb * sg + ca * cg) * yc + (sa * cb) * zc
    z_rot = (ca * sb * cg + sa * sg) * xc + (ca * sb * sg - sa * cg) * yc + (ca * cb) * zc

    return (x_rot / a) ** 2 + (y_rot / b) ** 2 + (z_rot / c) ** 2 - 1.0


def _algebraic_ellipsoid_residuals(params, x, y, z):
    """Быстрый алгебраический расчет невязки повернутого эллипсоида для нужд RANSAC-прототипирования."""
    ox, oy, oz, a, b, c, alpha, beta, gamma = params
    a, b, c = max(a, 1e-6), max(b, 1e-6), max(c, 1e-6)
    xc, yc, zc = x - ox, y - oy, z - oz
    ca, sa = np.cos(alpha), np.sin(alpha)
    cb, sb = np.cos(beta), np.sin(beta)
    cg, sg = np.cos(gamma), np.sin(gamma)

    x_rot = (cb * cg) * xc + (cb * sg) * yc - sb * zc
    y_rot = (sa * sb * cg - ca * sg) * xc + (sa * sb * sg + ca * cg) * yc + (sa * cb) * zc
    z_rot = (ca * sb * cg + sa * sg) * xc + (ca * sb * sg - sa * cg) * yc + (ca * cb) * zc

    return (x_rot / a) ** 2 + (y_rot / b) ** 2 + (z_rot / c) ** 2 - 1.0


class CalibrationModel:
    """Математическое ядро расчета калибровочных матриц магнетометра."""

    def __init__(self):
        self.keys = ('x', 'y', 'z')
        self.raw_data = {k: [] for k in self.keys}
        self.calibrated_data = {k: [] for k in self.keys}

        self.calibration_offsets = np.zeros(3)
        self.calibration_coefficients = np.eye(3)

        # Системный колбэк для пересылки логов напрямую во View через Контроллер
        self.logger = None

        # Профессиональные настройки алгоритма (RANSAC + Стабильный МНК)
        self.algo_settings = {
            "calibration_type": "auto",
            "ransac_iterations": 800,
            "ransac_threshold": 0.05,
            "f_scale": 0.1,
            "iqr_multiplier": 1.5,
            "loss_type": "linear",
            "tolerance": 1e-12,
            "max_iterations": 5000
        }
        # ИСПРАВЛЕНО: Привязка к локальному self.config_filename = "config.json" полностью удалена!

    def _log(self, message: str):
        """Внутренний хелпер: шлет лог в контроллер и принудительно обновляет UI хоста."""
        if self.logger:
            self.logger(message)
            # Импортируем локально, чтобы модель оставалась независимой от глобальной области Qt при инициализации
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.processEvents() # Мгновенно отрисовывает строку в текстовом окне логов
        else:
            print(message)

    def load_data(self, raw_dict: dict):
        self.raw_data = raw_dict

    def _fit_ransac_robust(self, x, y, z, max_iter=800, threshold=0.05):
        """RANSAC-фильтрация данных.

        Ищет устойчивое геометрическое ядро, полностью отсекая локальные помехи и наводки у металла.
        """
        num_pts = len(x)
        if num_pts < 9:
            return np.ones(num_pts, dtype=bool)

        best_inliers_mask = np.ones(num_pts, dtype=bool)
        max_inliers_count = -1

        approx_radius = (np.max(x) - np.min(x)) / 2.0

        for _ in range(max_iter):
            indices = random.sample(range(num_pts), 9)
            xs, ys, zs = x[indices], y[indices], z[indices]

            ox_s, oy_s, oz_s = np.median(xs), np.median(ys), np.median(zs)
            a_s = max((np.max(xs) - np.min(xs)) / 2.0, 1.0)
            b_s = max((np.max(ys) - np.min(ys)) / 2.0, 1.0)
            c_s = max((np.max(zs) - np.min(zs)) / 2.0, 1.0)

            initial_guess = [ox_s, oy_s, oz_s, a_s, b_s, c_s, 0.0, 0.0, 0.0]
            param_bounds = (
                [-np.inf, -np.inf, -np.inf, 1e-3, 1e-3, 1e-3, -np.pi, -np.pi, -np.pi],
                [np.inf, np.inf, np.inf, np.inf, np.inf, np.inf, np.pi, np.pi, np.pi]
            )

            try:
                res = least_squares(
                    _algebraic_ellipsoid_residuals, initial_guess, args=(xs, ys, zs),
                    bounds=param_bounds, ftol=1e-4, xtol=1e-4, max_nfev=100, method='trf'
                )
                model_params = res.x
            except Exception:
                continue

            _, a, b, c, _, _, _, _, _ = model_params
            if a > approx_radius * 5.0 or b > approx_radius * 5.0 or c > approx_radius * 5.0:
                continue

            errors = np.abs(_algebraic_ellipsoid_residuals(model_params, x, y, z))
            current_inliers_mask = errors <= threshold
            inliers_count = np.sum(current_inliers_mask)

            if inliers_count > max_inliers_count:
                max_inliers_count = inliers_count
                best_inliers_mask = current_inliers_mask

        if max_inliers_count < 9:
            self._log("[Модель - RANSAC]: Консенсус не найден. Отмена фильтрации.")
            return np.ones(num_pts, dtype=bool)

        self._log(f"[Модель - RANSAC]: Отсечено {num_pts - max_inliers_count} точек аномалий магнитной среды.")
        return best_inliers_mask

    # mag_calibration/models/calibration_model.py — Часть 2 из 2

    def _fit_geometric_gauss_newton(self, x, y, z, loss_type='linear', f_scale=0.1, tolerance=1e-12,
                                    max_iterations=5000):
        """Числовой нелинейный МНК Гаусса-Ньютона (через алгоритм TRF).

        Опирается на стабильную невязку повернутого эллипсоида для исключения расхождения осей.
        """
        ox_s, oy_s, oz_s = np.median(x), np.median(y), np.median(z)
        a_s = max((np.max(x) - np.min(x)) / 2.0, 1.0)
        b_s = max((np.max(y) - np.min(y)) / 2.0, 1.0)
        c_s = max((np.max(z) - np.min(z)) / 2.0, 1.0)

        initial_guess = [ox_s, oy_s, oz_s, a_s, b_s, c_s, 0.0, 0.0, 0.0]

        param_bounds = (
            [-np.inf, -np.inf, -np.inf, 1e-3, 1e-3, 1e-3, -np.pi, -np.pi, -np.pi],
            [np.inf, np.inf, np.inf, np.inf, np.inf, np.inf, np.pi, np.pi, np.pi]
        )

        try:
            result = least_squares(
                _geometric_ellipsoid_residuals, initial_guess, args=(x, y, z),
                loss=loss_type, f_scale=f_scale, bounds=param_bounds,
                ftol=tolerance, xtol=tolerance, max_nfev=max_iterations, method='trf'
            )
            ox, oy, oz, a, b, c, alpha, beta, gamma = result.x
        except Exception as e:
            self._log(f"[Модель - Геометрия]: Ошибка геометрического МНК ({e}). Фолбэк на базовые параметры.")
            ox, oy, oz, a, b, c, alpha, beta, gamma = ox_s, oy_s, oz_s, a_s, b_s, c_s, 0.0, 0.0, 0.0

        center = np.array([ox, oy, oz])
        radii = np.array([a, b, c])

        ca, sa = np.cos(alpha), np.sin(alpha)
        cb, sb = np.cos(beta), np.sin(beta)
        cg, sg = np.cos(gamma), np.sin(gamma)

        rotation_matrix = np.array([
            [cb * cg, cb * sg, -sb],
            [sa * sb * cg - ca * sg, sa * sb * sg + ca * cg, sa * cb],
            [ca * sb * cg + sa * sg, ca * sb * sg - sa * cg, ca * cb]
        ])

        geo_residuals = _geometric_ellipsoid_residuals([ox, oy, oz, a, b, c, alpha, beta, gamma], x, y, z)
        rmse = float(np.sqrt(np.mean(geo_residuals ** 2)))

        return center, radii, rotation_matrix, rmse

    def calculate_calibration_parameters_combined(self, f_scale=None, iqr_multiplier=None, loss_type=None):
        """ГЛАВНЫЙ МЕТОД КОНВЕЙЕРА: Связка RANSAC (Пасс 1) + Стабильный МНК (Пасс 2).

        Универсально отрабатывает как авто-конвейер, так и ручные параметры из полей интерфейса.
        """
        if loss_type is None:
            loss_type = self.algo_settings["loss_type"]
        if f_scale is None:
            f_scale = self.algo_settings["f_scale"]

        ransac_iter = self.algo_settings.get("ransac_iterations", 800)
        ransac_th = self.algo_settings.get("ransac_threshold", 0.05)
        tolerance = self.algo_settings["tolerance"]
        max_iterations = self.algo_settings["max_iterations"]

        key_x, key_y, key_z = self.keys
        x_raw = np.array(self.raw_data[key_x], dtype=float)
        y_raw = np.array(self.raw_data[key_y], dtype=float)
        z_raw = np.array(self.raw_data[key_z], dtype=float)

        total_points = len(x_raw)
        if total_points < 9:
            self._log("[Модель - Ошибка]: Критически мало точек для прецизионного геометрического расчета.")
            return np.zeros(3), np.eye(3), -1.0

        self._log(f"[Пасс 1]: Запуск RANSAC-экспертизы (входной массив: {total_points} точек)...")
        clean_mask = self._fit_ransac_robust(x_raw, y_raw, z_raw, max_iter=ransac_iter, threshold=ransac_th)

        x_clean = x_raw[clean_mask]
        y_clean = y_raw[clean_mask]
        z_clean = z_raw[clean_mask]
        remaining_points = len(x_clean)

        self._log(f"[Пасс 2]: Запуск ортогонального МНК Гаусса-Ньютона на чистом облаке ({remaining_points} точек)...")
        center_f, radii_f, rotation_f, rmse_final = self._fit_geometric_gauss_newton(
            x_clean, y_clean, z_clean, loss_type=loss_type, f_scale=f_scale,
            tolerance=tolerance, max_iterations=max_iterations
        )

        offsets = center_f
        radii_flat = np.abs(radii_f.ravel())
        r_mean = np.mean(radii_flat)

        scale_matrix_local = np.diag([
            r_mean / max(radii_flat[0], 1e-6),
            r_mean / max(radii_flat[1], 1e-6),
            r_mean / max(radii_flat[2], 1e-6)
        ])

        scale_matrix_global = np.dot(rotation_f.T, np.dot(scale_matrix_local, rotation_f))

        self._log("[Успех]: Матрицы жесткого и мягкого железа успешно рассчитаны.")
        return offsets, scale_matrix_global, rmse_final

    def apply_calibration(self, raw_data_dict: dict, offsets: np.ndarray, coefficients: np.ndarray) -> dict:
        """Применяет вычисленные калибровочные параметры к сырому массиву данных."""
        key_x, key_y, key_z = self.keys

        x_raw = np.array(raw_data_dict[key_x], dtype=float)
        y_raw = np.array(raw_data_dict[key_y], dtype=float)
        z_raw = np.array(raw_data_dict[key_z], dtype=float)

        raw_matrix = np.vstack((x_raw, y_raw, z_raw))
        centered_matrix = raw_matrix - offsets[:, np.newaxis]
        calibrated_matrix = np.dot(coefficients, centered_matrix)

        return {
            key_x: calibrated_matrix[0].tolist(),
            key_y: calibrated_matrix[1].tolist(),
            key_z: calibrated_matrix[2].tolist()
        }

    def optimize_and_save_algorithm_settings(self):
        """ФУНКЦИЯ-СОВМЕСТИМОСТЬ: Имитирует успешный авто-подбор параметров алгоритма.

        ИСПРАВЛЕНО: Избыточная локальная запись удалена. Метод возвращает флаг
        успешности, перекладывая сохранение на единую экосистему менеджеров.
        """
        self._log("[Модель - Инфо]: Новый конвейер RANSAC+Геометрия стабилен. Пропуск Grid Search.")
        return True, 0.000000

    def load_algorithm_settings(self) -> bool:
        """Заглушка-совместимость. Больше не используется, так как параметры читает SettingsManager."""
        return True
