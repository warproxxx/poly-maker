import json

from tweet_engine.normalization import to_records


class RawEventRecorder:
    def __init__(self, output_path):
        self.output_path = output_path

    def record(self, event):
        self.record_many([event])

    def record_many(self, events):
        records = to_records(events)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True))
                handle.write("\n")

