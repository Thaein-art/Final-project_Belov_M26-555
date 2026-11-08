import logging
import math
from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage

logger = logging.getLogger("valutatrade.parser")


class RatesUpdater:
    """Получает курсы от настроенных клиентов и сохраняет их результаты."""

    def __init__(self, clients: list, storage: RatesStorage):
        self.clients = clients
        self.storage = storage

    def run_update(self, source: str | None = None) -> dict:
        """
        Получает данные от всех выбранных API-клиентов.

        Сбой одного клиента не мешает успешным клиентам сохранять данные.
        """
        logger.info("Starting rates update")

        selected_clients = self.clients

        if source is not None:
            normalized_source = source.strip().lower()
            selected_clients = [
                client
                for client in self.clients
                if (
                    client.source_name.lower().replace("-api", "")
                    == normalized_source.replace("-api", "")
                )
            ]

            if not selected_clients:
                raise ValueError(
                    f"Неизвестный источник курсов: {source}."
                )

        records = []
        errors = []

        for client in selected_clients:
            logger.info(
                "Fetching from %s",
                client.source_name,
            )

            try:
                rates = client.fetch_rates()
            except ApiRequestError as error:
                message = (
                    f"Failed to fetch from {client.source_name}: {error}"
                )
                logger.error(message)
                errors.append(message)
                continue

            timestamp = (
                datetime.now(UTC)
                .isoformat()
                .replace("+00:00", "Z")
            )

            client_count = 0

            for pair, rate in rates.items():
                parts = pair.split("_")

                if len(parts) != 2:
                    logger.warning(
                        "Skipping invalid pair key: %s",
                        pair,
                    )
                    continue

                from_code, to_code = parts

                if (
                    not from_code.isalnum()
                    or not to_code.isalnum()
                    or not 2 <= len(from_code) <= 5
                    or not 2 <= len(to_code) <= 5
                    or from_code != from_code.upper()
                    or to_code != to_code.upper()
                ):
                    logger.warning(
                        "Skipping invalid currency pair: %s",
                        pair,
                    )
                    continue

                if (
                    isinstance(rate, bool)
                    or not isinstance(rate, (int, float))
                    or not math.isfinite(rate)
                    or rate <= 0
                ):
                    logger.warning(
                        "Skipping invalid rate for %s",
                        pair,
                    )
                    continue

                meta = client.last_metadata.get(pair, {})
                record_id = f"{from_code}_{to_code}_{timestamp}"

                records.append({
                    "id": record_id,
                    "from_currency": from_code,
                    "to_currency": to_code,
                    "rate": float(rate),
                    "timestamp": timestamp,
                    "source": client.source_name,
                    "meta": meta,
                })
                client_count += 1

            logger.info(
                "Fetching from %s... OK (%s rates)",
                client.source_name,
                client_count,
            )

        if not records:
            reason = "; ".join(errors) if errors else (
                "API-клиенты не вернули курсы."
            )
            raise ApiRequestError(reason)

        logger.info("Writing %s rates to local storage", len(records))

        try:
            storage_result = self.storage.save_records(records)
        except (OSError, ValueError) as error:
            logger.exception("Failed to save exchange rates")
            raise ApiRequestError(
                f"не удалось сохранить курсы: {error}"
            ) from error

        result = {
            "updated_count": len(records),
            "history_added": storage_result["history_added"],
            "current_updated": storage_result["current_updated"],
            "last_refresh": timestamp,
            "errors": errors,
        }

        if errors:
            logger.warning(
                "Rates update completed with errors: %s",
                "; ".join(errors),
            )
        else:
            logger.info(
                "Rates update completed successfully: %s rates",
                len(records),
            )

        return result


def build_default_updater() -> RatesUpdater:
    """Создает стандартный обновлятор с обоими настроенными API-клиентами."""
    config = ParserConfig()

    clients = [
        CoinGeckoClient(config),
        ExchangeRateApiClient(config),
    ]

    return RatesUpdater(
        clients=clients,
        storage=RatesStorage(),
    )