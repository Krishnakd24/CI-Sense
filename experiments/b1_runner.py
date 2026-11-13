"""B1 pilot: model calls are made only when run_pilot is invoked."""
import csv
import json
import shutil
import time
from pathlib import Path
from b0_parallel import request_one
from b0_runner import digest

ROOT = Path(__file__).resolve().parent
MODEL = 'Gemini 3.8 Flash (Medium)'
EXAMPLES = ('516', '404')

def build_prompt(data, template, target_id):
    records = {r['id']: r for r in data}
    def model_data(ident):
        r = records[ident]
        return json.dumps({'test_code': r['test_code'], 'failure_reports': r['failure_reports']}, ensure_ascii=False, indent=2)
    for token, ident in zip(('{{EXAMPLE_NON_FLAKY_JSON}}', '{{EXAMPLE_FLAKY_JSON}}', '{{TARGET_B1_JSON}}'), (*EXAMPLES, str(target_id))):
        if template.count(token) != 1:
            raise ValueError('Prompt placeholder missing or duplicated: ' + token)
        template = template.replace(token, model_data(ident), 1)
    return template

def run_pilot(target_id='198', root=ROOT):
    root = Path(root)
    data = json.loads((root / 'b1_data_v1.json').read_text(encoding='utf-8'))
    template = (root / 'prompt_b1.txt').read_text(encoding='utf-8')
    prompt = build_prompt(data, template, target_id)
    cli = shutil.which('agy') or str(Path.home() / 'AppData/Local/agy/bin/agy.exe')
    result = request_one(cli, prompt, MODEL, 'medium', 300)
    result.update(id=str(target_id), model=MODEL, prompt_sha256=digest(prompt),
                  timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    folder = root / 'b1_results' / 'pilot_v1'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'predictions.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False) + '\n')
    return result

def compare(result, root=ROOT):
    with (Path(root) / 'sample_300_labels.csv').open(encoding='utf-8-sig', newline='') as f:
        labels = {r['id']: int(r['fleaky']) for r in csv.DictReader(f)}
    if result['status'] != 'success':
        return {'id': result['id'], 'status': result['status'], 'error': result.get('error')}
    p = result['flaky_probability']
    return {'id': result['id'], 'probability': p, 'predicted': int(p >= .5), 'actual': labels[result['id']],
            'correct': int(p >= .5) == labels[result['id']]}
