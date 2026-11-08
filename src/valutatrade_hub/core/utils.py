import math
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    InvalidAmountError,
    ValidationError,
)


def validate_currency_code(code: str) -> str:
    """Проверяет валюту по реестру и возвращает её код."""
    return get_currency(code).code


def validate_amount(amount: float) -> float:
    """Преобразует сумму в float и проверяет, что она положительна и конечна."""
    try:
        numeric_amount = float(amount)
    except (TypeError, ValueError) as error:
        raise InvalidAmountError(
            "'amount' должен быть положительным числом."
        ) from error

    if not math.isfinite(numeric_amount) or numeric_amount <= 0:
        raise InvalidAmountError(
            "'amount' должен быть положительным числом."
        )

    return numeric_amount


def validate_rate(rate: float) -> float:
    """Проверяет, что курс обмена является положительным конечным числом."""
    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ValidationError("Курс должен быть положительным числом.")

    return float(rate)


def convert_amount(
    amount: float,
    from_code: str,
    to_code: str,
    rates_to_usd: dict[str, float],
) -> float:
    """
    Конвертирует сумму, используя курсы, выраженные как стоимость в USD
    за одну единицу валюты.

    Пример:
        BTC_USD = 60000
        EUR_USD = 1.08

        1 BTC -> EUR = 60000 / 1.08
    """
    numeric_amount = validate_amount(amount)
    source = validate_currency_code(from_code)
    target = validate_currency_code(to_code)

    if source == target:
        return numeric_amount

    try:
        source_rate = validate_rate(rates_to_usd[source])
        target_rate = validate_rate(rates_to_usd[target])
    except KeyError as error:
        missing_code = error.args[0]
        raise ValidationError(
            f"Нет курса для валюты {missing_code}."
        ) from error

    return numeric_amount * source_rate / target_rate


def parse_timestamp(value: str) -> datetime:
    """Разбирает метку времени ISO и проверяет, что она содержит часовой пояс."""
    if not isinstance(value, str):
        raise ValidationError("Время обновления должно быть строкой.")

    try:
        timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValidationError(
            f"Некорректная дата обновления: {value!r}."
        ) from error

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    return timestamp.astimezone(UTC)