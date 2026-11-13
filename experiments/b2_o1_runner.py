"""Construct B2_o1 target prompts; examples are already embedded in the template."""
import json

def build_prompt(data, template, target_id):
    records = {r['id']: r for r in data}
    if len(records) != len(data):
        raise ValueError('Duplicate B2_o1 IDs')
    if template.count('{{TARGET_B2_O1_JSON}}') != 1:
        raise ValueError('Expected one target placeholder')
    if template.count('LABELED EXAMPLE ') != 2:
        raise ValueError('Expected two fixed labeled examples')
    row = records[str(target_id)]
    payload = {key: value for key, value in row.items() if key != 'id'}
    return template.replace('{{TARGET_B2_O1_JSON}}',
                            json.dumps(payload, ensure_ascii=False, indent=2), 1)
