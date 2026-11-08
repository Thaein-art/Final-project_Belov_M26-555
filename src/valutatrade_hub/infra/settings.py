import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class SettingsLoader:
    """Загружает и кэширует настройки проекта в едином общем экземпляре."""

    _instance = None

    def __new__(cls):
        # __new__ управляет созданием экземпляра, поэтому повторные вызовы
        # возвращают тот же объект вместо создания новых объектов SettingsLoader.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._config: dict[str, Any] = {}
        self.reload()
        self._initialized = True

    def _load_defaults(self) -> dict[str, Any]:
        return {
            "data_dir": "data",
            "logs_dir": "logs",
            "users_file": "users.json",
            "portfolios_file": "portfolios.json",
            "rates_file": "rates.json",
            "history_file": "exchange_rates.json",
            "rates_ttl_seconds": 300,
            "base_currency": "USD",
            "log_level": "INFO",
            "log_file": "actions.log",
            "max_log_bytes": 1_048_576,
            "backup_count": 5,
        }

    def reload(self) -> None:
        """Перезагружает настройки из pyproject.toml и применяет значения по умолчанию."""
        config = self._load_defaults()
        pyproject_path = PROJECT_ROOT / "pyproject.toml"

        if pyproject_path.exists():
            with pyproject_path.open("rb") as file:
                pyproject_data = tomllib.load(file)

            project_config = (
                pyproject_data
                .get("tool", {})
                .get("valutatrade", {})
            )
            config.update(project_config)

        data_dir = Path(config["data_dir"])
        logs_dir = Path(config["logs_dir"])

        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir

        if not logs_dir.is_absolute():
            logs_dir = PROJECT_ROOT / logs_dir

        config["data_dir"] = data_dir
        config["logs_dir"] = logs_dir

        config["users_path"] = data_dir / config["users_file"]
        config["portfolios_path"] = data_dir / config["portfolios_file"]
        config["rates_path"] = data_dir / config["rates_file"]
        config["history_path"] = data_dir / config["history_file"]
        config["log_path"] = logs_dir / config["log_file"]

        self._config = config

    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает значение конфигурации или переданное значение по умолчанию."""
        return self._config.get(key, default)


# Импорт этого модуля не создает несколько объектов настроек.
settings = SettingsLoader()