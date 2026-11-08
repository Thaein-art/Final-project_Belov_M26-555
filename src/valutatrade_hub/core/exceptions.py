class ValutaTradeError(Exception):
    """Базовое исключение для всех ожидаемых ошибок приложения."""


class ValidationError(ValutaTradeError):
    """Вызывается, когда входные данные не соответствуют правилам валидации."""


class UserAlreadyExistsError(ValutaTradeError):
    """Вызывается, когда имя пользователя уже зарегистрировано."""


class UserNotFoundError(ValutaTradeError):
    """Вызывается, когда пользователь не может быть найден."""


class AuthenticationError(ValutaTradeError):
    """Вызывается, когда аутентификация не удалась или требуется."""


class WalletNotFoundError(ValutaTradeError):
    """Вызывается, когда запрашиваемый кошелек не существует."""


class InvalidAmountError(ValidationError):
    """Вызывается, когда сумма не является положительным конечным числом."""


class UnsupportedCurrencyError(ValidationError):
    """Вызывается, когда код валюты имеет недопустимый формат."""


class CurrencyNotFoundError(ValutaTradeError):
    """Вызывается, когда синтаксически правильная валюта отсутствует в реестре."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class InsufficientFundsError(ValutaTradeError):
    """Вызывается при недостатке средств в кошельке."""

    def __init__(
        self,
        available: float,
        required: float,
        code: str,
    ):
        self.available = available
        self.required = required
        self.code = code

        message = (
            f"Недостаточно средств: доступно {available:.4f} {code}, "
            f"требуется {required:.4f} {code}"
        )
        super().__init__(message)


class ApiRequestError(ValutaTradeError):
    """Вызывается при невозможности получить данные от API."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(
            f"Ошибка при обращении к внешнему API: {reason}"
        )