# mag_calibration/models/managers/mag_file_manager.py
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class MagFileManager:
    """Обеспечивает атомарные операции чтения и записи файлов сессий."""

    def read_json(self, path: Path, parent=None) -> Optional[Dict[str, Any]]:
        if not path or not path.is_file():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Магнетометр] Ошибка чтения JSON: {e}")
            return None

        return None

    def safe_write_json(self, path: Path, data: Dict[str, Any], parent=None) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix('.json.tmp')

            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            tmp_path.replace(path)
            return True
        except Exception as e:
            print(f"[Магнетометр] Критическая ошибка записи JSON: {e}")
            if tmp_path.is_file():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return False

    def remove_file(self, path: Path, parent=None) -> None:
        if path and path.is_file():
            try:
                path.unlink()
            except Exception as e:
                print(f"[Магнетометр] Не удалось удалить файл: {e}")
