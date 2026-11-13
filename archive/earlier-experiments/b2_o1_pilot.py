"""Three independent B2_o1 predictions for one selected test."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import time
from b0_parallel import request_one
from b0_runner import digest

ROOT = Path(__file__).resolve().parent
MODEL = 'Gemini 3.8 Flash (Medium)'

def run_pilot(test_id='198', n_runs=3, root=ROOT):
    root = Path(root)
    data = {r['id']: r for r in json.loads((root/'b2_o1_data_v1.json').read_text(encoding='utf-8'))}
    row = data[str(test_id)]
    template = (root/'prompt_b2_o1.txt').read_text(encoding='utf-8')
    if template.count('{{TARGET_B2_O1_JSON}}') != 1:
        raise ValueError('Expected exactly one target placeholder')
    payload = {k:v for k,v in row.items() if k != 'id'}
    prompt = template.replace('{{TARGET_B2_O1_JSON}}', json.dumps(payload,ensure_ascii=False,indent=2))
    folder = root/'b2_o1_results'/'pilot_v1'
    folder.mkdir(parents=True,exist_ok=True)
    log = folder/'predictions.jsonl'
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()] if log.exists() else []
    done = {r['run'] for r in records if r['status']=='success' and r['id']==str(test_id) and r['prompt_sha256']==digest(prompt)}
    cli = shutil.which('agy') or str(Path.home()/'AppData/Local/agy/bin/agy.exe')
    with (root/'sample_300_labels.csv').open(encoding='utf-8-sig',newline='') as f:
        actual = {r['id']:int(r['fleaky']) for r in csv.DictReader(f)}[str(test_id)]
    for run in range(1,n_runs+1):
        if run in done:
            print(f'Run {run}: previously saved; skipping',flush=True)
            continue
        result = request_one(cli,prompt,MODEL,'medium',300)
        result.update(run=run,id=str(test_id),model=MODEL,prompt_sha256=digest(prompt),
                      timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        with log.open('a',encoding='utf-8') as f:
            f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
        print(f'Run {run}: {result["status"]}, probability={result.get("flaky_probability")}, actual={actual}',flush=True)
        if result['status']=='blocked':
            print('Authentication or quota requires sign-in; rerun to resume.',flush=True)
            break
    return log

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--id',default='198')
    args=parser.parse_args()
    while True:
        log = run_pilot(args.id)
        records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
        successful = {r['run'] for r in records if r['id']==args.id and r['status']=='success'}
        if len(successful) == 3:
            print('Three valid predictions saved.', flush=True)
            break
        if records[-1]['status'] == 'blocked':
            break
        print('Retrying missing valid predictions in 5 seconds.', flush=True)
        time.sleep(5)
