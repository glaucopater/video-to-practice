import json
import sys

path = sys.argv[1]
records = []

with open(path, "r", encoding="utf-8") as file:
    for line in file:
        if line.strip():
            records.append(json.loads(line))

records.sort(
    key=lambda record: int(
        record["frame"].rsplit("_", 1)[1].rsplit(".", 1)[0]
    )
)

with open(path, "w", encoding="utf-8") as file:
    for record in records:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")