
import shlex

from valutatrade_hub.core import usecases
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValutaTradeError,
)
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.scheduler import RatesScheduler
from valutatrade_hub.parser_service.updater import build_default_updater


def print_help():
    """Выводит доступные команды и примеры."""
    print(
        """
ValutaTrade Hub

Пользователи:
  register --username <имя> --password <пароль>
  login --username <имя> --password <пароль>
  logout

Портфель:
  show-portfolio [--base USD]
  deposit --currency USD --amount 10000

Операции:
  buy --currency BTC --amount 0.05
  sell --currency BTC --amount 0.01

Курсы:
  get-rate --from BTC --to USD
  show-rates
  show-rates --currency BTC
  show-rates --top 2
  show-rates --base EUR
  update-rates
  update-rates --source coingecko
  update-rates --source exchangerate

Планировщик:
  schedule-rates --interval 3600
  stop-scheduler

Прочее:
  help
  exit

Строковые аргументы с пробелами заключайте в кавычки.

Команда deposit добавлена для демонстрации виртуального баланса.
Она не выполняет реальных платежей.
"""
    )


def _parse_options(tokens: list[str]) -> dict:
    """Разбирает опции команды в формате --ключ значение."""
    if len(tokens) % 2:
        raise ValueError(
            "Для каждого параметра необходимо указать значение."
        )

    options = {}

    for index in range(0, len(tokens), 2):
        key = tokens[index]
        value = tokens[index + 1]

        if not key.startswith("--"):
            raise ValueError(
                f"Ожидался именованный параметр, получено {key!r}."
            )

        normalized_key = key[2:]

        if normalized_key in options:
            raise ValueError(
                f"Параметр {key} указан несколько раз."
            )

        options[normalized_key] = value

    return options


def _required(options: dict, *names: str) -> list[str]:
    """Возвращает обязательные опции или вызывает информативную ошибку."""
    missing = [
        name
        for name in names
        if name not in options
    ]

    if missing:
        formatted = ", ".join(
            f"--{name}"
            for name in missing
        )
        raise ValueError(
            f"Не указаны обязательные параметры: {formatted}."
        )

    return [
        options[name]
        for name in names
    ]


def _require_login(current_user):
    """Проверяет, что пользователь аутентифицирован."""
    if current_user is None:
        raise ValueError("Сначала выполните login.")

    return current_user


def _print_portfolio(report: dict) -> None:
    """Выводит отчет по портфелю."""
    print(
        f"Портфель пользователя '{report['username']}' "
        f"(база: {report['base_currency']}):"
    )

    if not report["wallets"]:
        print("Портфель пока пуст.")
    else:
        for wallet in report["wallets"]:
            code = wallet["currency_code"]
            balance = wallet["balance"]
            converted = wallet["converted_value"]

            print(
                f"- {code}: {balance:.4f} "
                f"→ {converted:,.2f} {report['base_currency']}"
            )

    print("---------------------------------")
    print(
        f"ИТОГО: {report['total']:,.2f} "
        f"{report['base_currency']}"
    )


def _print_rates(report: dict) -> None:
    """Выводит кэшированные обменные курсы."""
    print(
        f"Курсы из локального кеша "
        f"(база: {report['base_currency']})."
    )
    print(
        f"Последнее обновление кеша: "
        f"{report['last_refresh'] or 'неизвестно'}"
    )

    if not report["rates"]:
        print("Подходящие курсы в кеше не найдены.")
        return

    for item in report["rates"]:
        print(
            f"- {item['pair']}: {item['rate']:.8f} "
            f"| updated_at={item['updated_at']} "
            f"| source={item['source']}"
        )


def run():
    """Запускает интерактивный цикл CLI."""
    setup_logging()

    current_user = None
    scheduler = None

    print("Добро пожаловать в ValutaTrade Hub!")
    print("Введите help для просмотра команд.")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            if scheduler is not None:
                scheduler.stop()

            print("\nДо свидания!")
            break

        if not user_input:
            continue

        try:
            tokens = shlex.split(user_input)

            if not tokens:
                continue

            command = tokens[0].lower()
            arguments = tokens[1:]

            if command == "help":
                print_help()

            elif command == "register":
                options = _parse_options(arguments)
                username, password = _required(
                    options,
                    "username",
                    "password",
                )

                user = usecases.register_user(
                    username,
                    password,
                )

                print(
                    f"Пользователь '{user.username}' зарегистрирован "
                    f"(id={user.user_id})."
                )

            elif command == "login":
                options = _parse_options(arguments)
                username, password = _required(
                    options,
                    "username",
                    "password",
                )

                current_user = usecases.login_user(
                    username,
                    password,
                )

                print(
                    f"Вы вошли как '{current_user.username}'."
                )

            elif command == "logout":
                if arguments:
                    raise ValueError(
                        "Команда logout не принимает аргументы."
                    )

                if current_user is None:
                    print("Вы не авторизованы.")
                else:
                    print(
                        f"Пользователь '{current_user.username}' вышел."
                    )
                    current_user = None

            elif command == "show-portfolio":
                options = _parse_options(arguments)
                user = _require_login(current_user)

                report = usecases.show_portfolio(
                    user,
                    options.get("base", "USD"),
                )

                _print_portfolio(report)

            elif command == "deposit":
                options = _parse_options(arguments)
                user = _require_login(current_user)

                currency, amount = _required(
                    options,
                    "currency",
                    "amount",
                )

                result = usecases.deposit_funds(
                    user,
                    currency,
                    amount,
                )

                print(
                    f"Баланс {result['currency']} пополнен на "
                    f"{result['amount']:.4f}."
                )
                print(
                    f"Новый баланс: {result['new_balance']:.4f}."
                )

            elif command == "buy":
                options = _parse_options(arguments)
                user = _require_login(current_user)

                currency, amount = _required(
                    options,
                    "currency",
                    "amount",
                )

                result = usecases.buy(
                    user,
                    currency,
                    amount,
                )

                print(
                    f"Покупка выполнена: {result['amount']:.4f} "
                    f"{result['currency']}."
                )
                print(
                    f"Курс: {result['rate']:.8f} "
                    f"USD/{result['currency']}."
                )
                print(
                    f"Стоимость покупки: "
                    f"{result['cost_usd']:,.2f} USD."
                )
                print(
                    f"Баланс {result['currency']}: "
                    f"{result['old_balance']:.4f} → "
                    f"{result['new_balance']:.4f}."
                )
                print(
                    f"Остаток USD: {result['usd_balance']:.4f}."
                )

            elif command == "sell":
                options = _parse_options(arguments)
                user = _require_login(current_user)

                currency, amount = _required(
                    options,
                    "currency",
                    "amount",
                )

                result = usecases.sell(
                    user,
                    currency,
                    amount,
                )

                print(
                    f"Продажа выполнена: {result['amount']:.4f} "
                    f"{result['currency']}."
                )
                print(
                    f"Курс: {result['rate']:.8f} "
                    f"USD/{result['currency']}."
                )
                print(
                    f"Выручка: {result['proceeds_usd']:,.2f} USD."
                )
                print(
                    f"Баланс {result['currency']}: "
                    f"{result['old_balance']:.4f} → "
                    f"{result['new_balance']:.4f}."
                )
                print(
                    f"Новый баланс USD: {result['usd_balance']:.4f}."
                )

            elif command == "get-rate":
                options = _parse_options(arguments)

                from_currency, to_currency = _required(
                    options,
                    "from",
                    "to",
                )

                result = usecases.get_rate(
                    from_currency,
                    to_currency,
                )

                print(
                    f"Курс {result['from']}→{result['to']}: "
                    f"{result['rate']:.8f}"
                )
                print(
                    f"Обратный курс: "
                    f"{result['reverse_rate']:.8f}"
                )
                print(
                    f"Обновлено: {result['updated_at']} "
                    f"(источник: {result['source']})"
                )

            elif command == "update-rates":
                options = _parse_options(arguments)
                source = options.get("source")

                result = build_default_updater().run_update(
                    source=source,
                )

                if result["errors"]:
                    print(
                        "Обновление завершено с ошибками. "
                        "Проверьте logs/actions.log."
                    )
                    for error in result["errors"]:
                        print(f"- {error}")
                else:
                    print("Обновление курсов успешно завершено.")

                print(
                    f"Получено записей: {result['updated_count']}."
                )
                print(
                    f"Добавлено в историю: {result['history_added']}."
                )
                print(
                    f"Обновлено пар в кеше: "
                    f"{result['current_updated']}."
                )
                print(
                    f"Время: {result['last_refresh']}."
                )

            elif command == "show-rates":
                options = _parse_options(arguments)

                top = options.get("top")
                if top is not None:
                    try:
                        top = int(top)
                    except ValueError as error:
                        raise ValueError(
                            "--top должен быть целым числом."
                        ) from error

                report = usecases.show_rates(
                    currency=options.get("currency"),
                    top=top,
                    base_currency=options.get("base", "USD"),
                )

                _print_rates(report)

            elif command == "schedule-rates":
                options = _parse_options(arguments)
                interval = int(options.get("interval", "3600"))

                if scheduler is not None:
                    scheduler.stop()

                scheduler = RatesScheduler(
                    updater=build_default_updater(),
                    interval_seconds=interval,
                )
                scheduler.start()

                print(
                    f"Планировщик запущен. "
                    f"Интервал: {interval} секунд."
                )

            elif command == "stop-scheduler":
                if scheduler is None:
                    print("Планировщик не запущен.")
                else:
                    scheduler.stop()
                    scheduler = None
                    print("Планировщик остановлен.")

            elif command == "exit":
                if arguments:
                    raise ValueError(
                        "Команда exit не принимает аргументы."
                    )

                if scheduler is not None:
                    scheduler.stop()

                print("До свидания!")
                break

            else:
                print(
                    f"Неизвестная команда: {command}. "
                    "Введите help."
                )

        except InsufficientFundsError as error:
            print(error)

        except CurrencyNotFoundError as error:
            print(error)
            print(
                "Проверьте код валюты. "
                "Введите help для примеров команды get-rate."
            )

        except ApiRequestError as error:
            print(error)
            print(
                "Повторите попытку позже или проверьте подключение к сети. "
                "Для ручного обновления используйте update-rates."
            )

        except (ValutaTradeError, ValueError, OSError) as error:
            print(error)