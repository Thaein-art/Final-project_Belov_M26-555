import os
from dataclasses import dataclass, field

from valutatrade_hub.infra.settings import settings


@dataclass(frozen=True)
class ParserConfig:
    """Конечные точки API, списки валют и параметры парсера."""

    exchangerate_api_key: str | None = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY")
    )

    coingecko_url: str = (
        "https://api.coingecko.com/api/v3/simple/price"
    )
    exchangerate_api_url: str = (
        "https://v6.exchangerate-api.com/v6"
    )

    base_currency: str = "USD"
    fiat_currencies: tuple[str, ...] = (
        "EUR",
        "GBP",
        "RUB",
    )
    crypto_currencies: tuple[str, ...] = (
        "BTC",
        "ETH",
        "SOL",
    )

    crypto_id_map: dict[str, str] = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    request_timeout: int = 10

    @property
    def rates_file_path(self):
        return settings.get("rates_path")

    @property
    def history_file_path(self):
        return settings.get("history_path")