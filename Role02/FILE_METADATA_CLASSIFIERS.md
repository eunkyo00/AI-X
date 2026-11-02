# 시간 분류기·자료 유형 분류기

## 시간 분류

몇 주차인지 정답을 만들 수 없으므로 주차는 분류하지 않습니다. 사용자가
`3월에 작업한 파일`처럼 검색할 수 있도록 수정 시각을 우선 사용해
연도·월·분기·상반기/하반기·계절 정보를 만듭니다. 수정 시각이 없을 때만
생성 시각을 사용합니다.

```bash
cd Role02
python time_classifier.py --modified-at "2026-03-16 14:30:00"
python evaluate_time_classifier.py
```

## 자료 유형 분류

기존 세부 role은 검색에 사용하기 쉬운 다음 6종으로 통일합니다.

- 강의자료
- 실습자료
- 코드
- 과제
- 데이터
- 안내자료

수동 description에 `강의 자료`, `실습 코드`처럼 정답이 직접 들어 있는
경우가 많으므로 학습과 평가에는 description을 사용하지 않습니다. 파일명,
확장자, 추출 본문의 E5 임베딩으로 로지스틱 회귀를 학습합니다.
파일명에 `과제·assignment·강의자료`가 있거나 확장자가 코드·데이터 유형을
명확히 나타내면 규칙으로 먼저 확정하고, 애매한 파일만 임베딩 분류기로
보냅니다.

```bash
cd Role02
python train_role_classifier.py
python classify_role.py --file-id F001
python classify_role.py --filename new.pdf --text-file new.txt
python classify_file_metadata.py --filename lecture.pdf --text-file new.txt \
  --modified-at "2026-03-16 14:30:00"
```

학습 결과는 `role_classifier_artifacts/`에 저장됩니다.

- `role_classifier.joblib`: 예측 모델
- `role_classifier_metrics.json`: 교차검증 성능
- `role_classifier_evaluation.csv`: 파일별 검증 결과
- `role_classifier_confusion_matrix.csv`: 혼동행렬

신뢰도가 학습 때 정한 확인 기준보다 낮으면 `미분류`로 반환하고 사용자에게
자료 유형 확인을 요청합니다.
