# mag_calibration/models/managers/settings_manager.py — Часть 1 из 2
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any


class SettingsManager:
    """Менеджер управления глобальными настройками среды модуля MagCalibration.

    Синхронизирован с общей папкой RssCalibrationSettings в AppData.
    """

    def __init__(self, parent=None):
        if os.name == 'nt':  # Windows
            base_app_data = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        else:  # Linux / macOS
            env_xdg = os.environ.get("XDG_CONFIG_HOME")
            base_app_data = Path(env_xdg) if env_xdg else Path.home() / ".config"

        # Единая папка настроек для всех модулей калибровки в системе
        self.root_module_dir = base_app_data / "RssCalibrationSettings"
        try:
            self.root_module_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[Магнетометр] Ошибка создания папки настроек: {e}")

        # Ссылаемся на один и тот же общий файл AppSettings.json
        self.app_settings_path = self.root_module_dir / "AppSettings.json"
        self.calibration_settings_path = self.root_module_dir / "MagCalibrationSettings.json"

        # Общая папка результатов RssCalibrationFiles напрямую в AppData
        self.default_save_dir = base_app_data / "RssCalibrationFiles"

        self.current_lang = "Russian"
        self.save_result_dir = self.default_save_dir
        self.calibration_file_path = Path("")

        self.ensure_default_files()
        self.load_settings()

    def validate_environment(self) -> bool:
        """Валидация стабильности среды модуля магнетометра."""
        return (self.app_settings_path.is_file() and self.app_settings_path.stat().st_size > 0 and
                self.calibration_settings_path.is_file() and self.calibration_settings_path.stat().st_size > 0)

# mag_calibration/models/managers/settings_manager.py — Часть 2 из 2

    def load_settings(self, parent=None) -> None:
        """Считывает актуальные настройки из общего AppSettings.json."""
        if not self.app_settings_path.is_file():
            return
        try:
            with open(self.app_settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.current_lang = data.get("Language", "Russian")
            res_dir = data.get("Calibration result folder", str(self.default_save_dir))
            self.save_result_dir = Path(res_dir).resolve()

            raw_path = data.get("Last Calibration File Path", "")
            if raw_path:
                abs_raw_path = Path(raw_path).resolve()
                if not abs_raw_path.is_file():
                    self.calibration_file_path = Path("")
                    self.save_setting("Last Calibration File Path", "", parent)
                else:
                    self.calibration_file_path = abs_raw_path
            else:
                self.calibration_file_path = Path("")

            if self.save_result_dir.is_absolute():
                self.save_result_dir.mkdir(parents=True, exist_ok=True)

            logging.info("⚙️ Параметры из общего AppSettings.json успешно применены к магнетометру.")
        except Exception as e:
            self.calibration_file_path = Path("")
            print(f"[Магнетометр] Ошибка при парсинге общего AppSettings.json: {e}")

    def save_setting(self, key: str, value: Any, parent=None) -> None:
        """Атомарно обновляет конкретный ключ в общем файле настроек."""
        try:
            data = {}
            if self.app_settings_path.is_file():
                with open(self.app_settings_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            data[key] = str(value) if isinstance(value, Path) else value

            tmp_path = self.app_settings_path.with_suffix('.json.tmp')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            tmp_path.replace(self.app_settings_path)
        except Exception as e:
            print(f"[Магнетометр] Не удалось обновить параметр '{key}': {e}")

    def load_calibration_settings(self) -> Dict[str, Any]:
        """Загружает профиль алгоритма калибровки RANSAC+МНК магнетометра."""
        if self.calibration_settings_path.is_file():
            try:
                with open(self.calibration_settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_calibration_settings(self, current_settings: Dict[str, Any], parent=None) -> None:
        """Сохраняет измененную конфигурацию алгоритма на диск."""
        try:
            tmp_path = self.calibration_settings_path.with_suffix('.json.tmp')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(current_settings, f, indent=4, ensure_ascii=False)
            tmp_path.replace(self.calibration_settings_path)
        except Exception as e:
            print(f"[Магнетометр] Ошибка сохранения алгоритма: {e}")

    def ensure_default_files(self) -> None:
        """Резервное создание папок и дефолтных JSON-файлов."""
        try:
            self.root_module_dir.mkdir(parents=True, exist_ok=True)
            self.default_save_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        if not self.app_settings_path.is_file() or self.app_settings_path.stat().st_size == 0:
            default_settings = {
                "Language": "Russian",
                "Calibration result folder": str(self.default_save_dir),
                "Last Calibration File Path": ""
            }
            try:
                with open(self.app_settings_path, 'w', encoding='utf-8') as f:
                    json.dump(default_settings, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

        if not self.calibration_settings_path.is_file() or self.calibration_settings_path.stat().st_size == 0:
            default_algo_settings = {
                "calibration_type": "auto",
                "ransac_iterations": 800,
                "ransac_threshold": 0.05,
                "f_scale": 0.1,
                "iqr_multiplier": 1.5,
                "loss_type": "linear",
                "tolerance": 1e-12,
                "max_iterations": 5000
            }
            try:
                with open(self.calibration_settings_path, 'w', encoding='utf-8') as f:
                    json.dump(default_algo_settings, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
