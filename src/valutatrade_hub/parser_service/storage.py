"""Хранилище для исторических и текущих обменных курсов."""

from datetime import UTC, datetime

from valutatrade_hub.core.utils import parse_timestamp
from valutatrade_hub.infra.database import database
from valutatrade_hub.infra.settings import settings


class RatesStorage:
    """Сохраняет историю обменных курсов и снимок текущих курсов."""

    def __init__(self):
        self.history_filename = settings.get("history_file")
        self.rates_filename = settings.get("rates_file")

    def save_records(self, records: list[dict]) -> dict:
        """
        Добавляет уникальные записи в историю и обновляет текущий снимок.
        """
        def update_history(history):
            if not isinstance(history, dict):
                history = {"records": []}

            stored_records = history.setdefault("records", [])
            known_ids = {
                item.get("id")
                for item in stored_records
                if isinstance(item, dict)
            }

            added = 0

            for record in records:
                if record["id"] in known_ids:
                    continue

                stored_records.append(record)
                known_ids.add(record["id"])
                added += 1

            return {
                "records": stored_records,
            }, added

        history_result = {}

        def history_updater(history):
            updated_history, added_count = update_history(history)
            history_result["added"] = added_count
            return updated_history

        database.update_json(
            self.history_filename,
            history_updater,
            {"records": []},
        )

        def rates_updater(current):
            if not isinstance(current, dict):
                current = {}

            pairs = current.setdefault("pairs", {})
            updated_count = 0

            for record in records:
                pair_key = (
                    f"{record['from_currency']}_"
                    f"{record['to_currency']}"
                )

                new_entry = {
                    "rate": record["rate"],
                    "updated_at": record["timestamp"],
                    "source": record["source"],
                }

                old_entry = pairs.get(pair_key)

                should_replace = old_entry is None

                if isinstance(old_entry, dict):
                    try:
                        old_time = parse_timestamp(
                            old_entry["updated_at"]
                        )
                        new_time = parse_timestamp(
                            record["timestamp"]
                        )
                        should_replace = new_time > old_time
                    except (KeyError, TypeError, ValueError):
                        should_replace = True

                if should_replace:
                    pairs[pair_key] = new_entry
                    updated_count += 1

            current["pairs"] = pairs
            current["last_refresh"] = datetime.now(
                UTC
            ).isoformat().replace("+00:00", "Z")

            return current, updated_count

        rates_result = {}

        def rates_updater_wrapper(current):
            updated_data, updated_count = rates_updater(current)
            rates_result["updated"] = updated_count
            return updated_data

        database.update_json(
            self.rates_filename,
            rates_updater_wrapper,
            {"pairs": {}, "last_refresh": None},
        )

        return {
            "history_added": history_result.get("added", 0),
            "current_updated": rates_result.get("updated", 0),
        }

    def load_current_rates(self) -> dict:
        """Возвращает снимок текущих курсов."""
        data = database.read_json(
            self.rates_filename,
            {"pairs": {}, "last_refresh": None},
        )

        if not isinstance(data, dict):
            return {"pairs": {}, "last_refresh": None}

        data.setdefault("pairs", {})
        return data

    def load_history(self) -> dict:
        """Возвращает полный журнал исторических курсов."""
        data = database.read_json(
            self.history_filename,
            {"records": []},
        )

        if not isinstance(data, dict):
            return {"records": []}

        data.setdefault("records", [])
        return data