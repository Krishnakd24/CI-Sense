"""Evaluate saved B1 predictions without sending model requests."""
import csv
import json
from pathlib import Path

def compare_results(base, experiment):
    import pandas as pd
    from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, precision_recall_fscore_support
    base = Path(base)
    folder = base / 'b1_results' / experiment
    latest = {}
    for line in (folder / 'predictions.jsonl').read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        key = (r['run'], r['id'])
        if key not in latest or latest[key]['status'] != 'success':
            latest[key] = r
    frame = pd.DataFrame(latest.values())
    labels = pd.read_csv(base / 'sample_300_labels.csv', dtype={'id': str})[['id', 'fleaky']].rename(columns={'fleaky': 'actual'})
    frame = frame.merge(labels, on='id', how='left', validate='many_to_one')
    if frame.actual.isna().any():
        raise ValueError('Missing labels')
    if 'flaky_probability' not in frame:
        frame['flaky_probability'] = float('nan')
    frame['few_shot'] = frame.id.isin(['516', '404'])
    frame['predicted'] = frame.flaky_probability.ge(.5).astype('Int64')
    frame.loc[frame.status != 'success', 'predicted'] = pd.NA
    frame['correct'] = frame.predicted.eq(frame.actual)
    summaries = []
    for run, group in frame.groupby('run'):
        good = group[group.status == 'success']
        row = {'run': run, 'successful': len(good), 'failed': len(group)-len(good), 'not_attempted': len(labels)-len(group)}
        if len(good):
            y, pred = good.actual.astype(int), good.predicted.astype(int)
            precision, recall, f1, support = precision_recall_fscore_support(y, pred, labels=[0,1], zero_division=0)
            row.update(accuracy=accuracy_score(y,pred), brier=brier_score_loss(y,good.flaky_probability))
            for i,name in enumerate(('non_flaky','flaky')):
                row.update({name+'_precision': precision[i], name+'_recall': recall[i], name+'_f1': f1[i], name+'_support': int(support[i])})
            row.update(zip(('tn','fp','fn','tp'),confusion_matrix(y,pred,labels=[0,1]).ravel().tolist()))
        summaries.append(row)
    metrics = pd.DataFrame(summaries)
    frame.to_csv(folder / 'comparison.csv',index=False)
    metrics.to_csv(folder / 'metrics.csv',index=False)
    frame[frame.status=='success'].groupby('id').flaky_probability.agg(['count','mean','std','min','max']).to_csv(folder/'probability_variability.csv')
    return frame, metrics
