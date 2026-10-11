# mag_calibration/models/managers/mag_session_manager.py
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from mag_calibration.models.managers.settings_manager import SettingsManager
from mag_calibration.models.managers.mag_file_manager import MagFileManager


class MagSessionManager:
    """Управляет бизнес-логикой выполнения калибровочных сессий магнетометра."""

    def __init__(self, settings: SettingsManager, file_manager: MagFileManager):
        self.settings = settings
        self.io = file_manager

    def create_new_calibration_file(self, device_number: str, parent=None) -> Path:
        """Инициализирует чистый файл сессии для нового прибора."""
        folder_time = datetime.now().strftime('%Y_%m_%d_%H_%M')
        filename = f"{device_number}_calibration_{folder_time}.json"
        target_path = self.settings.save_result_dir / filename

        base_struct = {
            "fileInfo": {
                "device_number": str(device_number),
                "changeTimeStamp": folder_time,
                "calibrations_count": "5",
                "state": "Uncompleted"
            }
        }

        self.io.safe_write_json(target_path, base_struct, parent)
        self.settings.calibration_file_path = target_path
        self.settings.save_setting("Last Calibration File Path", target_path, parent)

        return target_path

    def update_session_file(self, data: Dict[str, Any], parent=None) -> None:
        """Обновляет файл текущей сессии с автогенерацией таймстемпа и переименованием."""
        new_timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M')
        if "fileInfo" in data:
            data["fileInfo"]["changeTimeStamp"] = new_timestamp

        dev_num = data.get("fileInfo", {}).get("device_number", "unknown")
        new_filename = f"{dev_num}_calibration_{new_timestamp}.json"
        new_file_path = self.settings.calibration_file_path.parent / new_filename

        if self.io.safe_write_json(new_file_path, data, parent):
            if self.settings.calibration_file_path != new_file_path:
                self.io.remove_file(self.settings.calibration_file_path, parent)

            self.settings.calibration_file_path = new_file_path
            self.settings.save_setting("Last Calibration File Path", new_file_path, parent)

    def save_final_mag_matrix(self, matrix_data: Dict[str, Any], parent=None) -> None:
        """Интегрирует калибровочную матрицу магнетометра в файл текущей сессии."""
        file_data = self.io.read_json(self.settings.calibration_file_path, parent)
        if not file_data:
            return

        file_data.setdefault("mag", {})
        file_data["mag"]["calibration"] = {
            "state": "Completed",
            "timestamp": datetime.now().isoformat(),
            "Result": matrix_data
        }

        self.update_session_file(file_data, parent)
        print(f"📊 Результаты калибровки магнетометра успешно внедрены в общую сессию.")
