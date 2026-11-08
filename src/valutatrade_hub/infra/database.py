
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from valutatrade_hub.infra.settings import settings


class DatabaseManager:
    """Обеспечивает синхронизированный и атомарный доступ к хранилищу JSON."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._lock = threading.RLock()
        self._data_dir = Path(settings.get("data_dir"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def _get_path(self, filename: str) -> Path:
        """Формирует путь к файлу внутри настроенной директории данных."""
        candidate = Path(filename)

        if candidate.is_absolute() or len(candidate.parts) != 1:
            raise ValueError("Допустимо указывать только имя JSON-файла.")

        return self._data_dir / candidate

    def read_json(self, filename: str, default: Any = None) -> Any:
        """Читает данные JSON или возвращает копию переданного значения по умолчанию."""
        path = self._get_path(filename)

        with self._lock:
            try:
                with path.open("r", encoding="utf-8") as file:
                    return json.load(file)
            except FileNotFoundError:
                if isinstance(default, (dict, list)):
                    return default.copy()
                return default
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Файл {filename} содержит некорректный JSON."
                ) from error

    def write_json(self, filename: str, data: Any) -> None:
        """Атомарно записывает JSON, используя временный файл и замену."""
        path = self._get_path(filename)
        temporary_path = path.with_suffix(path.suffix + ".tmp")

        with self._lock:
            self._data_dir.mkdir(parents=True, exist_ok=True)

            try:
                with temporary_path.open("w", encoding="utf-8") as file:
                    json.dump(
                        data,
                        file,
                        ensure_ascii=False,
                        indent=4,
                        allow_nan=False,
                    )
                    file.flush()

                temporary_path.replace(path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

    def update_json(
        self,
        filename: str,
        updater: Callable[[Any], Any],
        default: Any = None,
    ) -> Any:
        """Выполняет чтение-изменение-запись, удерживая блокировку базы данных."""
        path = self._get_path(filename)
        temporary_path = path.with_suffix(path.suffix + ".tmp")

        with self._lock:
            try:
                with path.open("r", encoding="utf-8") as file:
                    current_data = json.load(file)
            except FileNotFoundError:
                if isinstance(default, (dict, list)):
                    current_data = default.copy()
                else:
                    current_data = default
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Файл {filename} содержит некорректный JSON."
                ) from error

            new_data = updater(current_data)

            try:
                with temporary_path.open("w", encoding="utf-8") as file:
                    json.dump(
                        new_data,
                        file,
                        ensure_ascii=False,
                        indent=4,
                        allow_nan=False,
                    )
                    file.flush()

                temporary_path.replace(path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

            return new_data


database = DatabaseManager()