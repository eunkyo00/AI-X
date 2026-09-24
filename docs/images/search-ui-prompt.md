# 검색 화면 이미지 생성 기록

- 생성 방식: 내장 image_gen 도구
- 이미지: `search-ui-concept.png`
- 용도: README 검색 예시의 앱 화면 구상

## 최종 프롬프트

```text
Use case: ui-mockup
Asset type: README image for Context-based Personal Search, a Korean desktop personal file search concept.
Create a polished high-fidelity front-on flat desktop app screenshot, landscape 1536x1024, no device or perspective. Restrained off-white background, white cards, slate text, teal accents, subtle borders, generous spacing, clear large Korean typography. Realistic usable productivity app, not a landing page, no marketing artwork.
Header: small search icon then "Context-based Personal Search", small badge "화면 구상".
Prominent search field exact Korean text "지난달 R 과제할 때 사용했던 데이터" and button "검색".
Below two-column layout: left roughly 60% primary result, right 40% related task. Left title "가장 관련 있는 파일". Main selected file card with green CSV icon, filename "student_data.csv", metadata "CSV · 지난달 수정", buttons "파일 열기" and "저장 위치". Below a clear section "이 파일을 찾은 근거" with three short readable rows: "analysis.R에서 이 CSV를 불러옵니다", "과제 설명에 R 데이터 분석이 포함됩니다", "관련 파일이 지난달에 수정되었습니다". Add a tasteful tiny preview table with headers student_id, study_hours, score and 3 sample numeric rows; label "데이터 미리보기".
Right panel heading "관련 작업", title "R 데이터 분석 과제", small badge "추정". Then heading "함께 확인할 파일". Four spacious rows with restrained file icons and filename and subtitle: "assignment.pdf" / "과제 설명"; "analysis.R" / "분석 코드"; "result_plot.png" / "관련 그래프로 추정"; "report.pdf" / "관련 보고서로 추정". Each row has a small open icon. Bottom of right panel small note "파일 내용과 시간 정보를 바탕으로 연결".
Everything must fit inside app window, excellent text legibility, avoid invented confidence percentages, folder organization controls, chatbot bubbles, code implementation details, excessive text, gradients, and decorative charts. The primary message is context-based rediscovery and related task files, not generic document search. Render Korean text accurately.
```
