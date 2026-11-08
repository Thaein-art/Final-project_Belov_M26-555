import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    InsufficientFundsError,
    ValidationError,
    WalletNotFoundError,
)
from valutatrade_hub.core.utils import validate_amount


class User:
    """Зарегистрированный пользователь ValutaTrade Hub."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
            or user_id <= 0
        ):
            raise ValidationError(
                "ID пользователя должен быть положительным целым числом."
            )

        self._user_id = user_id
        self.username = username
        self._salt = self._validate_nonempty(salt, "Соль")
        self._hashed_password = self._validate_nonempty(
            hashed_password,
            "Хеш пароля",
        )
        self.registration_date = registration_date

    @staticmethod
    def _validate_nonempty(value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(
                f"{field_name} не может быть пустым."
            )
        return value.strip()

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        """Создает SHA-256 хеш пароля вместе с солью."""
        if not isinstance(password, str):
            raise ValidationError("Пароль должен быть строкой.")

        return hashlib.sha256(
            (password + salt).encode("utf-8")
        ).hexdigest()

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str):
        self._username = self._validate_nonempty(
            value,
            "Имя пользователя",
        )

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    @registration_date.setter
    def registration_date(self, value: datetime):
        if not isinstance(value, datetime):
            raise ValidationError(
                "Дата регистрации должна иметь тип datetime."
            )
        self._registration_date = value

    def change_password(self, new_password: str) -> None:
        """Изменяет пароль и генерирует новую соль."""
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValidationError(
                "Пароль должен быть не короче 4 символов."
            )

        self._salt = secrets.token_hex(16)
        self._hashed_password = self.hash_password(
            new_password,
            self._salt,
        )

    def verify_password(self, password: str) -> bool:
        """Сравнивает переданный пароль с сохраненным хешем пароля."""
        if not isinstance(password, str):
            return False

        candidate = self.hash_password(password, self._salt)
        return hmac.compare_digest(
            candidate,
            self._hashed_password,
        )

    def get_user_info(self) -> dict:
        """Возвращает публичную информацию о пользователе без секретов аутентификации."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def create(
        cls,
        user_id: int,
        username: str,
        password: str,
    ) -> "User":
        """Создает нового пользователя со сгенерированной солью."""
        if not isinstance(password, str) or len(password) < 4:
            raise ValidationError(
                "Пароль должен быть не короче 4 символов."
            )

        salt = secrets.token_hex(16)
        password_hash = cls.hash_password(password, salt)

        return cls(
            user_id=user_id,
            username=username,
            hashed_password=password_hash,
            salt=salt,
            registration_date=datetime.now(UTC),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Восстанавливает пользователя из данных, совместимых с JSON."""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(
                data["registration_date"]
            ),
        )

    def to_dict(self) -> dict:
        """Преобразует пользователя в данные, совместимые с JSON."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    def __str__(self) -> str:
        return f"Пользователь {self._username} (id={self._user_id})"

    def __repr__(self) -> str:
        return (
            f"User(user_id={self._user_id}, "
            f"username={self._username!r})"
        )


class Wallet:
    """Кошелек, хранящий баланс одной зарегистрированной валюты."""

    def __init__(
        self,
        currency_code: str,
        balance: float = 0.0,
    ):
        self.currency_code = currency_code
        self.balance = balance

    @property
    def currency_code(self) -> str:
        return self._currency_code

    @currency_code.setter
    def currency_code(self, value: str):
        currency = get_currency(value)
        self._currency_code = currency.code

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not float("-inf") < float(value) < float("inf")
            or value < 0
        ):
            raise ValidationError(
                "Баланс должен быть неотрицательным конечным числом."
            )

        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Добавляет положительную сумму на кошелек."""
        numeric_amount = validate_amount(amount)
        self.balance = self._balance + numeric_amount

    def withdraw(self, amount: float) -> None:
        """Снимает деньги или вызывает InsufficientFundsError."""
        numeric_amount = validate_amount(amount)

        if numeric_amount > self._balance:
            raise InsufficientFundsError(
                available=self._balance,
                required=numeric_amount,
                code=self.currency_code,
            )

        self.balance = self._balance - numeric_amount

    def get_balance_info(self) -> dict:
        return {
            "currency_code": self.currency_code,
            "balance": self.balance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(
            currency_code=data["currency_code"],
            balance=data.get("balance", 0.0),
        )

    def to_dict(self) -> dict:
        return {
            "currency_code": self._currency_code,
            "balance": self._balance,
        }

    def __str__(self) -> str:
        return f"{self._balance:.4f} {self._currency_code}"

    def __repr__(self) -> str:
        return (
            f"Wallet(currency_code={self._currency_code!r}, "
            f"balance={self._balance!r})"
        )


class Portfolio:
    """Набор валютных кошельков пользователя."""

    def __init__(
        self,
        user: User,
        wallets: dict[str, Wallet] | None = None,
    ):
        if not isinstance(user, User):
            raise ValidationError(
                "Портфель должен быть связан с объектом User."
            )

        self._user = user
        self._user_id = user.user_id
        self._wallets: dict[str, Wallet] = {}

        for code, wallet in (wallets or {}).items():
            if not isinstance(wallet, Wallet):
                raise ValidationError(
                    "Портфель может содержать только объекты Wallet."
                )

            normalized_code = get_currency(code).code
            if normalized_code != wallet.currency_code:
                raise ValidationError(
                    "Код словаря не совпадает с кодом кошелька."
                )

            self._wallets[normalized_code] = wallet

    @property
    def user(self) -> User:
        return self._user

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Возвращает поверхностную копию для защиты внутреннего словаря."""
        return self._wallets.copy()

    @staticmethod
    def validate_currency_code(currency_code: str) -> str:
        return get_currency(currency_code).code

    def add_currency(self, currency_code: str) -> Wallet:
        """Создает кошелек, если он не существует."""
        code = get_currency(currency_code).code

        if code in self._wallets:
            raise ValidationError(
                f"Кошелёк {code} уже существует."
            )

        wallet = Wallet(code)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet:
        """Возвращает кошелек по коду валюты."""
        code = get_currency(currency_code).code

        try:
            return self._wallets[code]
        except KeyError as error:
            raise WalletNotFoundError(
                f"Кошелёк {code} не найден."
            ) from error

    def get_total_value(
        self,
        base_currency: str,
        rates_to_usd: dict[str, float],
    ) -> float:
        """
        Рассчитывает общую стоимость портфеля в выбранной базовой валюте.

        rates_to_usd содержит стоимость в USD одной единицы каждой валюты.
        """
        base = get_currency(base_currency).code

        if not self._wallets:
            return 0.0

        if base not in rates_to_usd:
            raise ValidationError(
                f"Курс базовой валюты {base} недоступен."
            )

        base_rate = float(rates_to_usd[base])
        if base_rate <= 0:
            raise ValidationError(
                f"Некорректный курс для {base}."
            )

        total_usd = 0.0

        for code, wallet in self._wallets.items():
            if code not in rates_to_usd:
                raise ValidationError(
                    f"Курс валюты {code} недоступен."
                )

            rate = float(rates_to_usd[code])
            if rate <= 0:
                raise ValidationError(
                    f"Некорректный курс для {code}."
                )

            total_usd += wallet.balance * rate

        return total_usd / base_rate

    @classmethod
    def from_dict(
        cls,
        user: User,
        data: dict,
    ) -> "Portfolio":
        """Восстанавливает портфель и его кошельки из данных JSON."""
        if data["user_id"] != user.user_id:
            raise ValidationError(
                "Портфель принадлежит другому пользователю."
            )

        wallets = {}

        for code, wallet_data in data.get("wallets", {}).items():
            complete_data = {
                "currency_code": code,
                **wallet_data,
            }
            wallets[code] = Wallet.from_dict(complete_data)

        return cls(user=user, wallets=wallets)

    def to_dict(self) -> dict:
        """Преобразует портфель в данные, совместимые с JSON."""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: wallet.to_dict()
                for code, wallet in self._wallets.items()
            },
        }

    def __str__(self) -> str:
        return (
            f"Portfolio(user={self._user.username!r}, "
            f"wallets={len(self._wallets)})"
        )

    def __repr__(self) -> str:
        return (
            f"Portfolio(user_id={self._user_id}, "
            f"wallets={self._wallets!r})"
        )