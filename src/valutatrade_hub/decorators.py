"""Декораторы для логирования доменных операций."""

import inspect
import logging
from functools import wraps

logger = logging.getLogger("valutatrade.actions")


def log_action(action: str, verbose: bool = False):
    """Логирует операцию, не подавляя исключения."""

    def decorator(function):
        signature = inspect.signature(function)

        @wraps(function)
        def wrapper(*args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            values = bound.arguments

            user = values.get("user")
            username = getattr(user, "username", None)

            if username is None:
                username = values.get("username")

            if username is None:
                username = values.get("user_id", "anonymous")

            currency_code = (
                values.get("currency_code")
                or values.get("from_currency")
                or values.get("currency")
                or "-"
            )

            amount = values.get("amount")
            amount_text = (
                f"{float(amount):.4f}"
                if isinstance(amount, (int, float))
                else "-"
            )

            base = values.get("to_currency", "USD")
            rate_text = "-"
            context = (
                f"{action} user={username!r} "
                f"currency={currency_code!r} "
                f"amount={amount_text} base={base!r}"
            )

            try:
                result = function(*args, **kwargs)

                if isinstance(result, dict):
                    rate = result.get("rate")
                    if isinstance(rate, (int, float)):
                        rate_text = f"{rate:.8f}"

                    if verbose:
                        old_balance = result.get("old_balance")
                        new_balance = result.get("new_balance")

                        if (
                            isinstance(old_balance, (int, float))
                            and isinstance(new_balance, (int, float))
                        ):
                            context += (
                                f" balance={old_balance:.4f}"
                                f"->{new_balance:.4f}"
                            )

                logger.info(
                    "%s rate=%s result=OK",
                    context,
                    rate_text,
                )
                return result

            except Exception as error:
                logger.info(
                    "%s rate=%s result=ERROR "
                    "error_type=%s error_message=%r",
                    context,
                    rate_text,
                    type(error).__name__,
                    str(error),
                )
                raise

        return wrapper

    return decorator