import math
import time
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    """Абстрактный интерфейс для клиентов внешних API обменных курсов."""

    source_name = "unknown"

    def __init__(self, config: ParserConfig):
        self.config = config
        self.last_metadata: dict[str, dict] = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Возвращает курсы в унифицированном формате ПАРА -> курс."""
        raise NotImplementedError


class CoinGeckoClient(BaseApiClient):
    """Получает цены криптовалют из CoinGecko."""

    source_name = "CoinGecko"

    def fetch_rates(self) -> dict[str, float]:
        ids = [
            self.config.crypto_id_map[code]
            for code in self.config.crypto_currencies
            if code in self.config.crypto_id_map
        ]

        if not ids:
            raise ApiRequestError(
                "список криптовалют для CoinGecko пуст."
            )

        params = {
            "ids": ",".join(ids),
            "vs_currencies": self.config.base_currency.lower(),
        }

        started_at = time.perf_counter()

        try:
            response = requests.get(
                self.config.coingecko_url,
                params=params,
                timeout=self.config.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as error:
            raise ApiRequestError(
                f"CoinGecko недоступен: {error}"
            ) from error
        except ValueError as error:
            raise ApiRequestError(
                "CoinGecko вернул некорректный JSON."
            ) from error

        request_ms = int(
            (time.perf_counter() - started_at) * 1000
        )

        if not isinstance(payload, dict):
            raise ApiRequestError(
                "CoinGecko вернул данные неожиданного формата."
            )

        rates = {}
        self.last_metadata = {}

        for code, raw_id in self.config.crypto_id_map.items():
            if code not in self.config.crypto_currencies:
                continue

            coin_data = payload.get(raw_id, {})
            raw_rate = coin_data.get(
                self.config.base_currency.lower()
            )

            if (
                isinstance(raw_rate, bool)
                or not isinstance(raw_rate, (int, float))
                or not math.isfinite(raw_rate)
                or raw_rate <= 0
            ):
                continue

            pair = f"{code}_{self.config.base_currency}"
            rates[pair] = float(raw_rate)

            self.last_metadata[pair] = {
                "raw_id": raw_id,
                "request_ms": request_ms,
                "status_code": response.status_code,
                "etag": response.headers.get("ETag"),
            }

        if not rates:
            raise ApiRequestError(
                "CoinGecko не вернул ни одного корректного курса."
            )

        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Получает курсы фиатных валют из ExchangeRate-API."""

    source_name = "ExchangeRate-API"

    def fetch_rates(self) -> dict[str, float]:
        api_key = self.config.exchangerate_api_key

        if not api_key:
            raise ApiRequestError(
                "не задана переменная окружения EXCHANGERATE_API_KEY."
            )

        url = (
            f"{self.config.exchangerate_api_url}/"
            f"{api_key}/latest/{self.config.base_currency}"
        )

        started_at = time.perf_counter()

        try:
            response = requests.get(
                url,
                timeout=self.config.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as error:
            raise ApiRequestError(
                f"ExchangeRate-API недоступен: {error}"
            ) from error
        except ValueError as error:
            raise ApiRequestError(
                "ExchangeRate-API вернул некорректный JSON."
            ) from error

        request_ms = int(
            (time.perf_counter() - started_at) * 1000
        )

        if not isinstance(payload, dict):
            raise ApiRequestError(
                "ExchangeRate-API вернул данные неожиданного формата."
            )

        if payload.get("result") != "success":
            raise ApiRequestError(
                f"ExchangeRate-API сообщил ошибку: "
                f"{payload.get('error-type', 'unknown error')}."
            )

        raw_rates = payload.get("rates")
        if not isinstance(raw_rates, dict):
            raise ApiRequestError(
                "В ответе ExchangeRate-API отсутствует словарь rates."
            )

        rates = {}
        self.last_metadata = {}

        for code in self.config.fiat_currencies:
            if code == self.config.base_currency:
                continue

            raw_rate = raw_rates.get(code)

            if (
                isinstance(raw_rate, bool)
                or not isinstance(raw_rate, (int, float))
                or not math.isfinite(raw_rate)
                or raw_rate <= 0
            ):
                continue

            # API returns foreign currency units per one USD.
            # Our internal format stores USD value of one foreign unit.
            normalized_rate = 1 / float(raw_rate)
            pair = f"{code}_{self.config.base_currency}"

            rates[pair] = normalized_rate

            self.last_metadata[pair] = {
                "raw_id": code,
                "request_ms": request_ms,
                "status_code": response.status_code,
                "etag": response.headers.get("ETag"),
            }

        if not rates:
            raise ApiRequestError(
                "ExchangeRate-API не вернул ни одного корректного курса."
            )

        return rates