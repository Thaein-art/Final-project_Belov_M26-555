import logging
import threading

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.updater import RatesUpdater

logger = logging.getLogger("valutatrade.parser")


class RatesScheduler:
    """Периодически запускает RatesUpdater в фоновом потоке."""

    def __init__(
        self,
        updater: RatesUpdater,
        interval_seconds: int = 3600,
    ):
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, int)
            or interval_seconds <= 0
        ):
            raise ValueError(
                "Интервал обновления должен быть положительным целым числом."
            )

        self.updater = updater
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread = None

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.updater.run_update()
            except ApiRequestError:
                logger.exception(
                    "Scheduled rates update failed"
                )

            self._stop_event.wait(self.interval_seconds)

    def start(self):
        """Запускает планировщик в демоническом потоке."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="rates-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Запрашивает остановку планировщика."""
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join()