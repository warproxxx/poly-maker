from dataclasses import asdict, is_dataclass
from datetime import datetime

from tweet_engine.models import EVENT_TYPE_TO_CLASS


EVENT_PRIORITY = {
    "metadata": 0,
    "tweet_count": 1,
    "quote": 2,
    "trade": 3,
}


def sort_events(events):
    return sorted(
        events,
        key=lambda event: (
            getattr(event, "timestamp", None),
            EVENT_PRIORITY.get(getattr(event, "event_type", ""), 99),
        ),
    )


def to_records(events):
    records = []
    for event in sort_events(events):
        if is_dataclass(event):
            record = asdict(event)
        else:
            record = dict(event)

        for key, value in list(record.items()):
            if isinstance(value, datetime):
                record[key] = value.isoformat()

        records.append(record)

    return records


def from_records(records):
    events = []
    for record in records:
        event_type = record["event_type"]
        event_class = EVENT_TYPE_TO_CLASS[event_type]
        hydrated = {}
        for key, value in record.items():
            if key == "event_type":
                continue
            if isinstance(value, str) and _looks_like_timestamp(value):
                hydrated[key] = datetime.fromisoformat(value)
            else:
                hydrated[key] = value
        events.append(event_class(**hydrated))
    return sort_events(events)


def _looks_like_timestamp(value):
    return "T" in value and ("+" in value or value.endswith("Z"))
