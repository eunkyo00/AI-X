"""프로젝트·자료유형·작업시각 자동 예측 결과를 별도 CSV에 저장한다.

실행: python Role02/classify_metadata.py
원본 extracted_text.csv의 수동 project/role 라벨은 변경하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
ROLE01 = ROOT / 'Role01'
DATA = ROLE01 / 'extracted_text.csv'
OUTPUT = BASE / 'metadata_classification_generated.csv'
PROJECT_MODEL = BASE / 'project_classifier_artifacts_v3' / 'project_classifier_v3.joblib'
ROLE_MODEL = BASE / 'role_classifier_artifacts' / 'role_classifier.joblib'
DESCRIPTIONS = BASE / 'metadata_description_generated.csv'

from project_classifier_v3 import row_to_file_text, encode_file_texts as project_encode, score_embeddings
from role_classifier import recognize_role_by_rule, row_to_role_file_text
from project_classifier import encode_file_texts as role_encode


def args_parse():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, default=DATA)
    p.add_argument('--output', type=Path, default=OUTPUT)
    p.add_argument('--force', action='store_true', help='기존 자동 예측도 다시 계산')
    return p.parse_args()


def main():
    args = args_parse()
    for file in (args.data, PROJECT_MODEL, ROLE_MODEL):
        if not file.is_file():
            raise FileNotFoundError(f'필요한 파일이 없습니다: {file}')

    df = pd.read_csv(args.data, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    if not {'file_id', 'filename', 'extracted_text'}.issubset(df.columns):
        raise ValueError('extracted_text.csv에 file_id, filename, extracted_text가 필요합니다')
    if df['file_id'].duplicated().any():
        raise ValueError('file_id 중복이 있습니다')
    for col in ('project', 'role', 'description', 'extension', 'modified_at', 'created_at', 'activity_at'):
        if col not in df:
            df[col] = ''

    if DESCRIPTIONS.is_file():
        desc = pd.read_csv(DESCRIPTIONS, dtype=str, keep_default_na=False, encoding='utf-8-sig')
        if {'file_id', 'description'}.issubset(desc.columns):
            desc_map = desc.drop_duplicates('file_id').set_index('file_id')['description']
            # 최신 자동 설명을 우선 사용. 수동 설명 우선 정책은 설명 생성기에서 처리해야 함.
            df['description'] = df['file_id'].map(desc_map).fillna('').where(
                df['file_id'].map(desc_map).fillna('').str.strip().ne(''), df['description']
            )

    previous = {}
    if args.output.is_file() and not args.force:
        old = pd.read_csv(args.output, dtype=str, keep_default_na=False, encoding='utf-8-sig')
        if 'file_id' in old:
            previous = {str(r['file_id']): r for r in old.to_dict('records')}

    project_artifact = joblib.load(PROJECT_MODEL)
    role_artifact = joblib.load(ROLE_MODEL)
    models = {}

    def get_model(name):
        if name not in models:
            from sentence_transformers import SentenceTransformer

            models[name] = SentenceTransformer(
                name,
                local_files_only=True
            )
        return models[name]

    results = []
    for row in df.to_dict('records'):
        fid = row['file_id'].strip()
        if not fid:
            continue
        old = previous.get(fid, {})
        result = {
            'file_id': fid, 'filename': row['filename'],
            'manual_project': row['project'], 'manual_role': row['role'],
            'predicted_project': '', 'project_needs_confirmation': '',
            'project_confidence': '', 'closest_existing_project': '',
            'predicted_role': '', 'role_needs_confirmation': '',
            'role_confidence': '', 'role_method': '',
            'activity_at': '', 'time_source': '', 'year_month': '',
            'quarter': '', 'half_year': '', 'season': '',
        }
        # 파일이 바뀌지 않았더라도 자동 예측을 보존. 재계산은 --force 사용.
        if old:
            for key in result:
                if key not in ('manual_project', 'manual_role', 'filename', 'file_id'):
                    result[key] = old.get(key, '')

        if not row['project'].strip() and (args.force or not result['predicted_project']):
            embedding = project_encode(
                get_model(project_artifact['model_name']), [row_to_file_text(row)],
                chunk_chars=int(project_artifact['chunk_chars']),
                max_chunks=int(project_artifact['max_chunks']),
                view_weights=project_artifact['view_weights'], show_progress_bar=False,
            )
            scores = score_embeddings(project_artifact, embedding)
            result['predicted_project'] = str(scores['predicted_project'][0])
            result['closest_existing_project'] = str(scores['closest_existing_project'][0])
            result['project_confidence'] = round(float(scores['confidence'][0]), 4)
            result['project_needs_confirmation'] = not bool(scores['accepted_as_existing'][0])

        if not row['role'].strip() and (args.force or not result['predicted_role']):
            record = row_to_role_file_text(row)
            rule = recognize_role_by_rule(record)
            if rule is not None:
                predicted, method = rule
                confidence, needs_confirmation = 0.99, False
            else:
                embedding = role_encode(
                    get_model(role_artifact['model_name']), [record],
                    chunk_chars=int(role_artifact['chunk_chars']),
                    max_chunks=int(role_artifact['max_chunks']), show_progress_bar=False,
                )
                prob = role_artifact['classifier'].predict_proba(embedding)[0]
                idx = int(prob.argmax())
                confidence = float(prob[idx])
                needs_confirmation = confidence < float(role_artifact['confirmation_threshold'])
                predicted = '미분류' if needs_confirmation else str(role_artifact['classifier'].classes_[idx])
                method = 'embedding_classifier'
            result['predicted_role'] = predicted
            result['role_confidence'] = round(confidence, 4)
            result['role_needs_confirmation'] = needs_confirmation
            result['role_method'] = method

        # 시간 정보는 표준 라이브러리로 처리하므로 별도 학습 모델이 필요하지 않다.
        from datetime import datetime
        for source in ('activity_at', 'modified_at', 'created_at'):
            value = str(row.get(source, '')).strip()
            if not value:
                continue
            try:
                dt = datetime.fromisoformat(value.replace('/', '-').replace('.', '-'))
            except ValueError:
                continue
            m = dt.month
            result.update(activity_at=dt.isoformat(sep=' ', timespec='seconds'),
                          time_source=source, year_month=f'{dt.year:04d}-{m:02d}',
                          quarter=f'{(m-1)//3+1}분기',
                          half_year='상반기' if m <= 6 else '하반기',
                          season=('봄' if m in (3,4,5) else '여름' if m in (6,7,8)
                                  else '가을' if m in (9,10,11) else '겨울'))
            break
        results.append(result)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix('.tmp.csv')
    pd.DataFrame(results, columns=[
        'file_id','filename','manual_project','manual_role','predicted_project',
        'project_needs_confirmation','project_confidence','closest_existing_project',
        'predicted_role','role_needs_confirmation','role_confidence','role_method',
        'activity_at','time_source','year_month','quarter','half_year','season',
    ]).to_csv(tmp, index=False, encoding='utf-8-sig')
    tmp.replace(args.output)
    print(f'분류 결과 저장: {args.output} ({len(results)}개)')
    print('주의: 기존 검색 엔진에 예측 라벨을 적용하려면 별도 연결이 필요합니다.')


if __name__ == '__main__':
    main()
