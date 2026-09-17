# AI+X

2026학년도 2학기 AI+X 팀 프로젝트

Problem → Dataset / EDA → Baseline → Error Analysis → Model Improvement → Comparison → Prototype → Demo

## 현재 상태

주제, 팀원, 데이터셋 선정 전입니다.

## 권장 구성

아래는 향후 추가할 폴더 구성안입니다.

```text
docs/          # 문제 정의, 데이터 설명, 오류 분석, 팀원 기여
notebooks/     # EDA, Baseline, 분석 노트북
src/           # 전처리, 학습, 평가, 추론 코드
configs/       # 실험 설정과 seed
experiments/   # 실험 기록과 성능 비교표
data/          # 데이터 확보 방법 (원본 데이터는 별도 보관)
app/           # 시연용 사용자 화면
reports/       # 중간·최종 발표 자료
tests/         # 핵심 데이터 처리 및 추론 검증
```

## 진행 목표

- 8주차 중간발표: Problem + Dataset + Baseline + Initial Result
- 15주차 최종발표: Improvement + Comparison + Prototype + Demo
- 같은 데이터 분할과 평가 지표로 Baseline과 개선 결과 비교
- 실패 사례, 개선 가설, 실험 설정 및 개인 기여 기록
- 무료 Colab에서 재현 가능한 실행 방법 문서화

원본 데이터, 대용량 모델 가중치, API 키는 커밋하지 않습니다.
