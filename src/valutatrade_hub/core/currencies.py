import math
import re
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    ValidationError,
)


class Currency(ABC):
    """Абстрактный базовый класс для всех поддерживаемых валют."""

    def __init__(self, name: str, code: str):
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("Название валюты не может быть пустым.")

        if not isinstance(code, str):
            raise ValidationError("Код валюты должен быть строкой.")

        normalized_code = code.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{2,5}", normalized_code):
            raise ValidationError(
                "Код валюты должен содержать от 2 до 5 символов "
                "в верхнем регистре."
            )

        self._name = name.strip()
        self._code = normalized_code

    @property
    def name(self) -> str:
        """Возвращает читаемое название валюты."""
        return self._name

    @property
    def code(self) -> str:
        """Возвращает нормализованный код валюты."""
        return self._code

    @abstractmethod
    def get_display_info(self) -> str:
        """Возвращает строковое представление, подходящее для интерфейса и логов."""
        raise NotImplementedError

    def __str__(self) -> str:
        return self.get_display_info()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(name={self.name!r}, code={self.code!r})"
        )


class FiatCurrency(Currency):
    """Фиатная валюта, выпускаемая страной или валютным союзом."""

    def __init__(
        self,
        name: str,
        code: str,
        issuing_country: str,
    ):
        super().__init__(name, code)

        if (
            not isinstance(issuing_country, str)
            or not issuing_country.strip()
        ):
            raise ValidationError(
                "Страна или зона эмиссии не может быть пустой."
            )

        self._issuing_country = issuing_country.strip()

    @property
    def issuing_country(self) -> str:
        return self._issuing_country

    def get_display_info(self) -> str:
        return (
            f"[FIAT] {self.code} — {self.name} "
            f"(Issuing: {self.issuing_country})"
        )


class CryptoCurrency(Currency):
    """Криптовалюта с метаданными об алгоритме и рыночной капитализации."""

    def __init__(
        self,
        name: str,
        code: str,
        algorithm: str,
        market_cap: float = 0.0,
    ):
        super().__init__(name, code)

        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValidationError(
                "Алгоритм криптовалюты не может быть пустым."
            )

        if (
            isinstance(market_cap, bool)
            or not isinstance(market_cap, (int, float))
            or not math.isfinite(market_cap)
            or market_cap < 0
        ):
            raise ValidationError(
                "Капитализация должна быть неотрицательным числом."
            )

        self._algorithm = algorithm.strip()
        self._market_cap = float(market_cap)

    @property
    def algorithm(self) -> str:
        return self._algorithm

    @property
    def market_cap(self) -> float:
        return self._market_cap

    @market_cap.setter
    def market_cap(self, value: float):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValidationError(
                "Капитализация должна быть неотрицательным числом."
            )
        self._market_cap = float(value)

    def get_display_info(self) -> str:
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {self.market_cap:.2e})"
        )


# Единый реестр используется всем приложением.
_CURRENCY_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("Pound Sterling", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency(
        "Bitcoin",
        "BTC",
        "SHA-256",
        1.12e12,
    ),
    "ETH": CryptoCurrency(
        "Ethereum",
        "ETH",
        "Ethash / Proof of Stake",
        4.45e11,
    ),
    "SOL": CryptoCurrency(
        "Solana",
        "SOL",
        "Proof of History / Proof of Stake",
        7.0e10,
    ),
}


def register_currency(currency: Currency) -> None:
    """Добавляет или заменяет валюту в реестре."""
    if not isinstance(currency, Currency):
        raise ValidationError(
            "В реестр можно добавлять только объекты Currency."
        )

    _CURRENCY_REGISTRY[currency.code] = currency


def get_currency(code: str) -> Currency:
    """Возвращает объект валюты по коду или вызывает CurrencyNotFoundError."""
    if not isinstance(code, str):
        raise CurrencyNotFoundError(str(code))

    normalized_code = code.strip().upper()
    currency = _CURRENCY_REGISTRY.get(normalized_code)

    if currency is None:
        raise CurrencyNotFoundError(normalized_code)

    return currency


def get_supported_currencies() -> dict[str, Currency]:
    """Возвращает копию реестра поддерживаемых валют."""
    return _CURRENCY_REGISTRY.copy()