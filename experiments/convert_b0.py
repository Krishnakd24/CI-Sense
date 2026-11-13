"""Standalone B0 CSV -> JSON conversion; no model calls."""
import argparse
import csv
import json
from pathlib import Path


def convert(source, destination):
    with Path(source).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    records = [{"id": r["id"], "test_code": r["Test_code"]} for r in rows]
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Duplicate IDs")
    if any(not r["id"] or not r["test_code"].strip() or r["test_code"] == "NA" for r in records):
        raise ValueError("Missing ID or test code")
    with Path(destination).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).with_name("b0_data.csv"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("b0_data_v1.json"))
    args = parser.parse_args()
    print(f"Converted {len(convert(args.source, args.output))} rows to {args.output}")
