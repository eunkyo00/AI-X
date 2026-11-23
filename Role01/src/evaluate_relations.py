from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
K = 5
truth = pd.read_csv(BASE / 'relations_ground_truth.csv', dtype=str).fillna('')
truth = truth[truth['status'].eq('confirmed')]
if truth.empty:
    raise SystemExit('정답 CSV의 status를 검토 후 confirmed로 변경하세요.')
metadata = pd.read_csv(BASE / 'metadata.csv', dtype=str)
valid = set(metadata['file_id'])
assert set(truth.source_file_id) | set(truth.target_file_id) <= valid
assert not (truth.source_file_id == truth.target_file_id).any()
results = []
for version in (3, 4, 5):
    df = pd.read_csv(BASE / f'file_relations_v{version}.csv', dtype=str)
    # CSV 저장 순서가 추천 순위 (직접 참조 우선 포함)
    predictions = df.groupby('source_file_id', sort=False)['target_file_id'].apply(lambda x: list(dict.fromkeys(x))[:K]).to_dict()
    for (split, source), rows in truth.groupby(['split', 'source_file_id']):
        expected = set(rows.target_file_id)
        ranked = predictions.get(source, [])
        ranks = [i for i, target in enumerate(ranked, 1) if target in expected]
        results.append(dict(version=f'V{version}', split=split, source_file_id=source, hit=int(bool(ranks)), recall=len(ranks)/len(expected), mrr=1/min(ranks) if ranks else 0))
result = pd.DataFrame(results)
summary = result.groupby(['split','version']).agg(queries=('hit','size'), hit_at_5=('hit','mean'), recall_at_5=('recall','mean'), mrr_at_5=('mrr','mean')).reset_index()
print(summary.round(4).to_string(index=False))
result.to_csv(BASE / 'relations_evaluation_details.csv', index=False, encoding='utf-8-sig')
summary.to_csv(BASE / 'relations_evaluation_summary.csv', index=False, encoding='utf-8-sig')
