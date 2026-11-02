# 프로젝트 분류기

`../Role01/extracted_text.csv`의 파일명, 설명, 추출 본문으로 과목(`project`)을 예측한다.
정답 라벨인 `project` 값이나 프로젝트 폴더 경로는 모델 입력에 포함하지 않는다.

## 1. 학습 및 평가

```bash
cd Role02
python train_project_classifier.py
```

실행 결과는 `project_classifier_artifacts/`에 저장된다.

- `project_classifier.joblib`: 실제 예측에 사용하는 모델
- `project_classifier_metrics.json`: 정확도, Macro F1 등
- `project_classifier_evaluation.csv`: 파일별 교차검증 결과
- `project_classifier_confusion_matrix.csv`: 혼동행렬

현재 평가는 파일 단위 5겹 교차검증이다. 같은 파일에서 나온 여러 텍스트 조각이
학습용과 검증용으로 나뉘지 않도록, 먼저 파일별 임베딩 하나를 만든 뒤 분할한다.

## 2. 기존 CSV 파일로 예측 시험

```bash
cd Role02
python classify_new_file.py --file-id F001
```

## 3. 새 파일의 추출 텍스트로 예측

```bash
python classify_new_file.py \
  --filename "새강의자료.pdf" \
  --description "파일 설명" \
  --text-file "새강의자료.txt"
```

프로그램 연결용 JSON 출력:

```bash
python classify_new_file.py --file-id F001 --json
```

최고 예측 신뢰도가 모델에 저장된 기준보다 낮으면 프로젝트를 `새 과목`으로
반환하고 `needs_confirmation`을 `true`로 표시한다. 현재 데이터에는 실제 새 과목
검증 표본이 없으므로 이 기준은 초기값이다. 새 과목 파일을 따로 모아 평가한 뒤
조정해야 한다.

