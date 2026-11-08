"""Настройка логирования с ротацией файлов."""

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import settings


class ISOFormatter(logging.Formatter):
    """Форматировщик, записывающий ISO-метки времени с учетом часового пояса."""

    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(
            record.created
        ).astimezone().isoformat(timespec="seconds")


def setup_logging() -> logging.Logger:
    """Настраивает логирование приложения и возвращает корневой логгер."""
    logger = logging.getLogger("valutatrade")
    logger.setLevel(
        getattr(
            logging,
            str(settings.get("log_level", "INFO")).upper(),
            logging.INFO,
        )
    )
    logger.propagate = False

    if any(
        isinstance(handler, RotatingFileHandler)
        for handler in logger.handlers
    ):
        return logger

    log_path = settings.get("log_path")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = ISOFormatter(
        fmt="%(levelname)s %(asctime)s %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=int(settings.get("max_log_bytes", 1_048_576)),
        backupCount=int(settings.get("backup_count", 5)),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger