# 검색 화면 시안 수정 기록

- 도구: 내장 image_gen 이미지 편집
- 원본: `search-ui-concept.png`
- 결과: `search-ui-concept-v2.png`
- 변경: 데이터 미리보기를 파일 관계 흐름으로 교체하고 확인·추정을 구분

## 최종 프롬프트

```text
Edit this Korean desktop app concept screenshot. Preserve its clean off-white, white and teal professional design, readable Korean typography, header "Context-based Personal Search", badge "화면 구상", exact search query "지난달 R 과제할 때 사용했던 데이터", left primary result student_data.csv and file-open/location buttons, the three search evidence rows, and right related-task panel with all four related files assignment.pdf, analysis.R, result_plot.png, report.pdf. Landscape front-facing app screenshot. You may increase canvas height to keep all text readable.
Critical change: REMOVE the bottom-left sample data preview table entirely. Instead ADD a full-width bottom section below both upper columns titled "파일 간 작업 흐름". Show a spacious horizontal relationship graph with four clear file nodes:
"student_data.csv" subtitle "입력 데이터" → "analysis.R" subtitle "분석 코드" ⇢ "result_plot.png" subtitle "결과 그래프" ⇢ "report.pdf" subtitle "보고서".
First edge solid teal line with arrowhead pointing from CSV to R labeled "코드 참조 확인". Next edge from R to PNG dashed with arrowhead labeled "생성 관계 추정". Last edge from PNG to PDF dashed with arrowhead labeled "포함 관계 추정". Add small readable legend beneath "실선: 확인된 참조 · 점선: 추정 관계". No arrows connecting unrelated files. Keep assignment.pdf as task description in right file list, not as a producer of the CSV. The upper left evidence third row still mentions files modified last month. Retain task badge "추정". Do not add fake confidence percentages. Design must emphasize file relationships beyond a flat list without becoming crowded. Accurate Korean, no text clipping.
```
