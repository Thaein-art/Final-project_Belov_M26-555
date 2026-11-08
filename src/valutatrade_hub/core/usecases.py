from datetime import UTC, datetime, timedelta

from valutatrade_hub.core.currencies import (
    CryptoCurrency,
    get_currency,
)
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    AuthenticationError,
    CurrencyNotFoundError,
    UserAlreadyExistsError,
    UserNotFoundError,
    ValidationError,
    WalletNotFoundError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    parse_timestamp,
    validate_amount,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import database
from valutatrade_hub.infra.settings import settings


def _require_user(user: User) -> None:
    """Проверяет, что приватная операция выполняется аутентифицированным пользователем."""
    if not isinstance(user, User):
        raise AuthenticationError("Сначала выполните login.")


def _load_portfolios() -> list[dict]:
    data = database.read_json(
        settings.get("portfolios_file"),
        [],
    )

    if not isinstance(data, list):
        raise ValidationError(
            "Файл portfolios.json должен содержать список."
        )

    return data


def _load_portfolio_for_user(user: User) -> Portfolio:
    """Находит и восстанавливает портфель, принадлежащий указанному пользователю."""
    portfolios = _load_portfolios()

    for item in portfolios:
        if item.get("user_id") == user.user_id:
            return Portfolio.from_dict(user, item)

    raise ValidationError(
        f"Портфель пользователя '{user.username}' не найден."
    )


def _save_portfolio(portfolio: Portfolio) -> None:
    """Обновляет один портфель, не заменяя портфели других пользователей."""

    def updater(portfolios):
        if not isinstance(portfolios, list):
            raise ValidationError(
                "Файл portfolios.json должен содержать список."
            )

        for index, item in enumerate(portfolios):
            if item.get("user_id") == portfolio.user_id:
                portfolios[index] = portfolio.to_dict()
                return portfolios

        portfolios.append(portfolio.to_dict())
        return portfolios

    database.update_json(
        settings.get("portfolios_file"),
        updater,
        [],
    )


@log_action("REGISTER")
def register_user(username: str, password: str) -> User:
    """Регистрирует уникального пользователя и создает пустой портфель."""
    if not isinstance(username, str) or not username.strip():
        raise ValidationError(
            "Имя пользователя не может быть пустым."
        )

    if not isinstance(password, str) or len(password) < 4:
        raise ValidationError(
            "Пароль должен быть не короче 4 символов."
        )

    normalized_username = username.strip().casefold()
    created_user = {}

    def add_user(users):
        if not isinstance(users, list):
            raise ValidationError(
                "Файл users.json должен содержать список."
            )

        if any(
            item.get("username", "").casefold()
            == normalized_username
            for item in users
        ):
            raise UserAlreadyExistsError(
                f"Имя пользователя '{username}' уже занято."
            )

        user_id = max(
            (item.get("user_id", 0) for item in users),
            default=0,
        ) + 1

        user = User.create(
            user_id=user_id,
            username=username.strip(),
            password=password,
        )

        users.append(user.to_dict())
        created_user["user"] = user
        return users

    database.update_json(
        settings.get("users_file"),
        add_user,
        [],
    )

    user = created_user["user"]

    def add_portfolio(portfolios):
        if not isinstance(portfolios, list):
            raise ValidationError(
                "Файл portfolios.json должен содержать список."
            )

        portfolios.append({
            "user_id": user.user_id,
            "wallets": {},
        })
        return portfolios

    database.update_json(
        settings.get("portfolios_file"),
        add_portfolio,
        [],
    )

    return user


@log_action("LOGIN")
def login_user(username: str, password: str) -> User:
    """Аутентифицирует пользователя и возвращает восстановленный объект User."""
    users = database.read_json(
        settings.get("users_file"),
        [],
    )

    if not isinstance(users, list):
        raise ValidationError(
            "Файл users.json должен содержать список."
        )

    normalized_username = username.strip().casefold()

    for item in users:
        if (
            item.get("username", "").casefold()
            == normalized_username
        ):
            user = User.from_dict(item)

            if not user.verify_password(password):
                raise AuthenticationError("Неверный пароль.")

            return user

    raise UserNotFoundError(
        f"Пользователь '{username}' не найден."
    )


def _read_rate_pairs() -> dict:
    """Читает снимок текущих курсов."""
    rates_data = database.read_json(
        settings.get("rates_file"),
        {"pairs": {}, "last_refresh": None},
    )

    if not isinstance(rates_data, dict):
        raise ValidationError(
            "Файл rates.json содержит данные неверного формата."
        )

    pairs = rates_data.get("pairs", {})
    if not isinstance(pairs, dict):
        raise ValidationError(
            "Поле pairs в rates.json должно быть объектом."
        )

    return pairs


def _get_fresh_usd_rate(
    code: str,
    pairs: dict,
    now: datetime,
    ttl: timedelta,
) -> dict | None:
    """Возвращает свежий курс одной валюты к USD."""
    if code == "USD":
        return {
            "rate": 1.0,
            "updated_at": now,
            "source": "identity",
        }

    entry = pairs.get(f"{code}_USD")
    if not isinstance(entry, dict):
        return None

    try:
        updated_at = parse_timestamp(entry["updated_at"])
        rate = float(entry["rate"])
    except (KeyError, TypeError, ValueError):
        return None

    if rate <= 0:
        return None

    age = now - updated_at
    if age > ttl:
        return None

    return {
        "rate": rate,
        "updated_at": updated_at,
        "source": entry.get("source", "cache"),
    }


@log_action("GET_RATE")
def get_rate(
    from_currency: str,
    to_currency: str,
) -> dict:
    """
    Возвращает обменный курс, используя локальный кеш на основе USD.

    Если нужные записи кеша отсутствуют или устарели, вызывается Parser Service.
    Вымышленный запасной курс не генерируется.
    """
    source = get_currency(from_currency).code
    target = get_currency(to_currency).code

    now = datetime.now(UTC)

    if source == target:
        return {
            "from": source,
            "to": target,
            "rate": 1.0,
            "reverse_rate": 1.0,
            "updated_at": now.isoformat(),
            "source": "identity",
        }

    ttl_seconds = int(
        settings.get("rates_ttl_seconds", 300)
    )
    ttl = timedelta(seconds=ttl_seconds)

    pairs = _read_rate_pairs()

    source_data = _get_fresh_usd_rate(
        source,
        pairs,
        now,
        ttl,
    )
    target_data = _get_fresh_usd_rate(
        target,
        pairs,
        now,
        ttl,
    )

    update_error = None

    if source_data is None or target_data is None:
        from valutatrade_hub.parser_service.updater import (
            build_default_updater,
        )

        try:
            build_default_updater().run_update()
        except ApiRequestError as error:
            update_error = str(error)

        pairs = _read_rate_pairs()
        now = datetime.now(UTC)

        source_data = _get_fresh_usd_rate(
            source,
            pairs,
            now,
            ttl,
        )
        target_data = _get_fresh_usd_rate(
            target,
            pairs,
            now,
            ttl,
        )

    if source_data is None or target_data is None:
        missing = []

        if source_data is None:
            missing.append(f"{source}_USD")

        if target_data is None:
            missing.append(f"{target}_USD")

        reason = (
            "нет актуальных курсов для "
            + ", ".join(missing)
            + ". Выполните update-rates."
        )

        if update_error:
            reason += f" Последняя ошибка обновления: {update_error}"

        raise ApiRequestError(reason)

    # Both values express USD price of one unit of each currency.
    rate = source_data["rate"] / target_data["rate"]

    used_sources = sorted({
        source_data["source"],
        target_data["source"],
    })

    updated_at = min(
        source_data["updated_at"],
        target_data["updated_at"],
    )

    return {
        "from": source,
        "to": target,
        "rate": rate,
        "reverse_rate": 1 / rate,
        "updated_at": updated_at.isoformat(),
        "source": " + ".join(used_sources),
    }


def show_portfolio(
    user: User,
    base_currency: str = "USD",
) -> dict:
    """Формирует отчет по портфелю с пересчитанной стоимостью кошельков."""
    _require_user(user)

    base = get_currency(base_currency).code
    portfolio = _load_portfolio_for_user(user)

    wallet_rows = []
    rates_to_usd = {}

    if portfolio.wallets:
        for code, wallet in portfolio.wallets.items():
            rates_to_usd[code] = get_rate(code, "USD")["rate"]

            converted = wallet.balance * get_rate(
                code,
                base,
            )["rate"]

            wallet_rows.append({
                "currency_code": code,
                "balance": wallet.balance,
                "converted_value": converted,
            })

        rates_to_usd[base] = get_rate(base, "USD")["rate"]

    total = portfolio.get_total_value(
        base,
        rates_to_usd,
    )

    return {
        "username": user.username,
        "base_currency": base,
        "wallets": wallet_rows,
        "total": total,
    }


def deposit_funds(
    user: User,
    currency_code: str,
    amount: float,
) -> dict:
    """
    Пополняет виртуальными средствами кошелек.

    Это дополнительная демонстрационная команда, а не реальная платежная операция.
    """
    _require_user(user)

    code = get_currency(currency_code).code
    numeric_amount = validate_amount(amount)

    portfolio = _load_portfolio_for_user(user)

    try:
        wallet = portfolio.get_wallet(code)
    except WalletNotFoundError:
        wallet = portfolio.add_currency(code)

    old_balance = wallet.balance
    wallet.deposit(numeric_amount)

    _save_portfolio(portfolio)

    return {
        "currency": code,
        "amount": numeric_amount,
        "old_balance": old_balance,
        "new_balance": wallet.balance,
    }


@log_action("BUY", verbose=True)
def buy(
    user: User,
    currency_code: str,
    amount: float,
) -> dict:
    """Покупает валюту, тратя соответствующую сумму USD."""
    _require_user(user)

    code = get_currency(currency_code).code
    numeric_amount = validate_amount(amount)

    if code == "USD":
        raise ValidationError(
            "Покупать USD за USD нельзя."
        )

    portfolio = _load_portfolio_for_user(user)

    usd_wallet = portfolio.get_wallet("USD")
    rate_info = get_rate(code, "USD")
    cost_usd = numeric_amount * rate_info["rate"]

    try:
        target_wallet = portfolio.get_wallet(code)
    except WalletNotFoundError:
        target_wallet = portfolio.add_currency(code)

    old_balance = target_wallet.balance

    # withdraw() itself checks available funds and raises
    # InsufficientFundsError with the required formatted message.
    usd_wallet.withdraw(cost_usd)
    target_wallet.deposit(numeric_amount)

    _save_portfolio(portfolio)

    return {
        "currency": code,
        "amount": numeric_amount,
        "rate": rate_info["rate"],
        "cost_usd": cost_usd,
        "old_balance": old_balance,
        "new_balance": target_wallet.balance,
        "usd_balance": usd_wallet.balance,
    }


@log_action("SELL", verbose=True)
def sell(
    user: User,
    currency_code: str,
    amount: float,
) -> dict:
    """Продает валюту и зачисляет выручку на кошелек USD."""
    _require_user(user)

    code = get_currency(currency_code).code
    numeric_amount = validate_amount(amount)

    if code == "USD":
        raise ValidationError(
            "Нельзя продавать USD за USD."
        )

    portfolio = _load_portfolio_for_user(user)
    source_wallet = portfolio.get_wallet(code)

    rate_info = get_rate(code, "USD")
    proceeds_usd = numeric_amount * rate_info["rate"]

    try:
        usd_wallet = portfolio.get_wallet("USD")
    except WalletNotFoundError:
        usd_wallet = portfolio.add_currency("USD")

    old_balance = source_wallet.balance

    source_wallet.withdraw(numeric_amount)
    usd_wallet.deposit(proceeds_usd)

    _save_portfolio(portfolio)

    return {
        "currency": code,
        "amount": numeric_amount,
        "rate": rate_info["rate"],
        "proceeds_usd": proceeds_usd,
        "old_balance": old_balance,
        "new_balance": source_wallet.balance,
        "usd_balance": usd_wallet.balance,
    }


# Compatibility names for code that used the previous function names.
buy_currency = buy
sell_currency = sell


def show_rates(
    currency: str | None = None,
    top: int | None = None,
    base_currency: str = "USD",
) -> dict:
    """
    Возвращает курсы из локального кеша, не вызывая принудительное обновление через API.

    Фильтр --top включает только зарегистрированные криптовалюты.
    """
    base = get_currency(base_currency).code
    pairs = _read_rate_pairs()

    if not pairs:
        raise ValidationError(
            "Локальный кеш курсов пуст. "
            "Выполните 'update-rates', чтобы загрузить данные."
        )

    if currency is not None:
        requested_currency = get_currency(currency).code
        requested_pair = f"{requested_currency}_USD"

        if requested_currency != "USD" and requested_pair not in pairs:
            raise ValidationError(
                f"Курс для '{requested_currency}' не найден в кеше."
            )

        currency_filter = requested_currency
    else:
        currency_filter = None

    if top is not None:
        if isinstance(top, bool) or top <= 0:
            raise ValidationError(
                "Параметр --top должен быть положительным числом."
            )

    base_rate = 1.0
    base_timestamp = None

    if base != "USD":
        base_entry = pairs.get(f"{base}_USD")

        if not isinstance(base_entry, dict):
            raise ValidationError(
                f"Курс базовой валюты {base} отсутствует в кеше."
            )

        base_rate = float(base_entry["rate"])
        base_timestamp = parse_timestamp(
            base_entry["updated_at"]
        )

    rows = []

    for pair_key, entry in pairs.items():
        if not pair_key.endswith("_USD"):
            continue

        code = pair_key[:-4]

        if code == "USD":
            continue

        try:
            currency_object = get_currency(code)
        except CurrencyNotFoundError:
            continue

        if currency_filter and code != currency_filter:
            continue

        if top is not None and not isinstance(
            currency_object,
            CryptoCurrency,
        ):
            continue

        rate_usd = float(entry["rate"])
        display_rate = rate_usd / base_rate

        updated_at = parse_timestamp(entry["updated_at"])

        if base_timestamp is not None:
            updated_at = min(updated_at, base_timestamp)

        rows.append({
            "pair": f"{code}_{base}",
            "currency": code,
            "rate": display_rate,
            "updated_at": updated_at.isoformat(),
            "source": entry.get("source", "cache"),
        })

    rows.sort(
        key=lambda item: item["rate"],
        reverse=top is not None,
    )

    if top is not None:
        rows = rows[:top]

    if currency_filter and not rows and currency_filter != "USD":
        raise ValidationError(
            f"Курс для '{currency_filter}' не найден в кеше."
        )

    return {
        "base_currency": base,
        "last_refresh": database.read_json(
            settings.get("rates_file"),
            {},
        ).get("last_refresh"),
        "rates": rows,
    }