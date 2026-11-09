"""Convert frozen B0/B1 CSVs to structured B1 JSON without modifying inputs."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ('execution_result', 'exception_type', 'failure_message', 'error_message',
          'stack_trace', 'source_file', 'line_number', 'expected_value', 'actual_value',
          'duration_seconds', 'test_stdout', 'test_stderr')

def convert(root=ROOT):
    with (root / 'b0_data.csv').open(encoding='utf-8-sig', newline='') as f:
        code = list(csv.DictReader(f))
    with (root / 'data_B1.csv').open(encoding='utf-8-sig', newline='') as f:
        reports = list(csv.DictReader(f))
    by_id = {r['id']: r for r in code}
    if len(by_id) != len(code) or len({r['id'] for r in reports}) != len(reports) or set(by_id) != {r['id'] for r in reports}:
        raise ValueError('B0 and B1 must contain the same unique IDs')
    result = []
    for row in reports:
        entries = []
        for suffix in ('', '_part_2'):
            entry = {name: row[name + suffix] for name in FIELDS
                     if row[name + suffix] not in ('', 'NA')}
            if entry:
                entries.append(entry)
        if not entries:
            raise ValueError('Missing report for ID ' + row['id'])
        result.append({'id': row['id'], 'test_code': by_id[row['id']]['Test_code'], 'failure_reports': entries})
    return result

if __name__ == '__main__':
    data = convert()
    with (ROOT / 'b1_data_v1.json').open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'Converted {len(data)} rows')
