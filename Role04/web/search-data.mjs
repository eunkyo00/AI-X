/** UI fixtures, never real filesystem records or search scores. */
const fact = text => ({ text, certainty: 'confirmed' });
const guess = text => ({ text, certainty: 'inferred' });
const file = (id, name, type, role, task, date, size, summary, evidence) => ({
  id, name, type, role, task, modified: date, size, summary, evidence,
  path: `${task === 'r' ? 'R_project' : task === 'python' ? 'Python_practice' : 'Presentation'}/${name}`,
});
export const taskNames = { r: 'R 데이터 분석 과제', python: 'Python 실습', presentation: '딥러닝 발표 준비' };
export const files = [
  file('r-data', 'student_data.csv', 'data', '입력 데이터', 'r', '2026-10-15', '2.4 MB', 'analysis.R에서 읽는 데이터입니다. 과제 설명 문서와 코드의 참조를 함께 확인할 수 있습니다.', [fact('analysis.R에 student_data.csv를 읽는 구문이 있습니다.'), fact('과제 설명 PDF에 학생 데이터 분석 과제가 명시되어 있습니다.'), guess('코드 참조와 문서 내용을 바탕으로 이 과제의 입력 데이터로 추정합니다.'), guess('수정 날짜가 과제 자료의 수정 기간과 가깝습니다. 실제 사용 시각은 알 수 없습니다.')]),
  file('r-code', 'analysis.R', 'code', '분석 코드', 'r', '2026-10-16', '4.8 KB', 'student_data.csv를 읽고 result_plot.png를 저장하는 구문이 포함된 R 코드입니다.', [fact('student_data.csv 읽기 구문과 result_plot.png 저장 구문이 있습니다.'), guess('이 코드가 해당 분석 작업에 사용된 것으로 추정합니다. 실제 실행 여부는 확인하지 않았습니다.')]),
  file('r-guide', 'R_과제_설명.pdf', 'document', '과제 설명', 'r', '2026-10-10', '842 KB', 'R 데이터 분석 과제의 목표와 제출해야 할 그래프·보고서를 설명합니다.', [fact('문서에 R 분석 과제와 학생 데이터 활용 안내가 있습니다.'), guess('같은 경로의 분석 코드와 함께 사용된 참고 문서로 추정합니다.')]),
  file('r-plot', 'result_plot.png', 'image', '그래프', 'r', '2026-10-16', '186 KB', 'analysis.R에 동일한 파일명의 그래프 저장 구문이 있습니다.', [fact('analysis.R에서 result_plot.png라는 경로를 저장 대상으로 참조합니다.'), guess('코드의 결과 그래프로 추정합니다. 저장 구문만으로 실제 생성 여부를 확정할 수 없습니다.')]),
  file('r-report', '분석_보고서.docx', 'document', '결과 문서', 'r', '2026-10-18', '1.1 MB', '데이터 분석 과정과 그래프를 정리한 예시 보고서입니다.', [fact('보고서에 학생 데이터 분석 결과와 그래프 설명이 있습니다.'), guess('주제와 수정 시점을 바탕으로 같은 과제의 결과 문서로 추정합니다.')]),
  file('p-slides', '딥러닝_발표.pptx', 'presentation', '발표자료', 'presentation', '2026-09-24', '8.2 MB', '딥러닝 논문의 핵심 아이디어와 비교 결과를 정리한 발표자료입니다.', [fact('발표자료에 참고 논문의 제목과 출처가 적혀 있습니다.'), guess('발표 메모와 같은 발표 준비 작업에 속하는 것으로 추정합니다.')]),
  file('p-paper', '강화학습_논문.pdf', 'document', '참고 논문', 'presentation', '2025-11-08', '3.6 MB', '딥러닝 발표에서 참고 문헌으로 인용한 강화학습 논문입니다.', [fact('딥러닝_발표.pptx의 참고 문헌에서 이 논문의 제목을 확인할 수 있습니다.'), guess('이 문서의 수정 시각은 실제 읽은 시각과 다를 수 있습니다.')]),
  file('p-note', '발표_메모.txt', 'document', '작업 노트', 'presentation', '2026-09-22', '3.2 KB', '참고 논문 내용과 발표 순서를 정리한 메모입니다.', [fact('메모에 참고 논문의 제목과 발표 목차가 있습니다.'), guess('내용이 일치하는 발표자료와 같은 작업에 속하는 것으로 추정합니다.')]),
  file('py-code', 'process.py', 'code', '처리 코드', 'python', '2026-09-19', '5.6 KB', 'raw_data.csv를 읽어 처리하고 output.csv를 저장하는 구문이 있는 코드입니다.', [fact('raw_data.csv 읽기와 output.csv 저장 경로가 코드에 명시되어 있습니다.'), guess('실습 안내와 함께 사용된 코드로 추정합니다. 실행 여부는 확인하지 않았습니다.')]),
  file('py-output', 'output.csv', 'data', '결과 데이터', 'python', '2026-09-19', '632 KB', 'process.py의 저장 구문에서 참조하는 결과 데이터입니다.', [fact('process.py에 output.csv 저장 구문이 있습니다.'), guess('해당 실습에서 생성한 데이터로 추정합니다. 코드 실행 이력은 없습니다.')]),
  file('py-raw', 'raw_data.csv', 'data', '입력 데이터', 'python', '2026-09-17', '1.8 MB', 'process.py에서 입력 파일로 참조하는 원본 데이터입니다.', [fact('process.py에서 raw_data.csv를 읽는 구문이 있습니다.'), guess('실습 작업의 입력 자료로 추정합니다.')]),
  file('py-guide', 'Python_실습_안내.pdf', 'document', '실습 안내', 'python', '2026-09-15', '420 KB', '원본 데이터를 가공해 CSV 결과를 제출하는 실습의 안내 문서입니다.', [fact('문서에 Python 데이터 처리 실습과 제출 형식이 명시되어 있습니다.'), guess('코드의 입출력 구성과 일치하는 실습 안내로 추정합니다.')]),
];
export const relations = [
  { from: 'r-code', to: 'r-data', label: '코드에서 읽기 참조', certainty: 'confirmed' },
  { from: 'r-code', to: 'r-plot', label: '코드에서 저장 경로 참조', certainty: 'confirmed' },
  { from: 'r-data', to: 'r-guide', label: '같은 과제의 자료로 추정', certainty: 'inferred' },
  { from: 'r-plot', to: 'r-report', label: '보고서의 결과 그림으로 추정', certainty: 'inferred' },
  { from: 'p-slides', to: 'p-paper', label: '발표자료에서 문헌 인용', certainty: 'confirmed' },
  { from: 'p-slides', to: 'p-note', label: '같은 발표 작업으로 추정', certainty: 'inferred' },
  { from: 'py-code', to: 'py-raw', label: '코드에서 읽기 참조', certainty: 'confirmed' },
  { from: 'py-code', to: 'py-output', label: '코드에서 저장 경로 참조', certainty: 'confirmed' },
  { from: 'py-code', to: 'py-guide', label: '같은 실습으로 추정', certainty: 'inferred' },
];
export function getRelated(id) {
  return relations.filter(link => link.from === id || link.to === id).map(link => ({
    file: files.find(item => item.id === (link.from === id ? link.to : link.from)), relation: link,
  }));
}
export function mockSearch(query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  let task;
  if (/python|파이썬|실습|process|output|raw_data/.test(q)) task = 'python';
  else if (/논문|발표|딥러닝|강화학습|ppt|메모/.test(q)) task = 'presentation';
  else if (/(^|[^a-z])r([^a-z]|$)|과제|학생|student|analysis|그래프|보고서/.test(q)) task = 'r';
  const matched = task ? files.filter(item => item.task === task) : files.filter(item => q.includes(item.name.toLowerCase()));
  const preferred = /논문|pdf/.test(q) ? 'document' : /발표|ppt/.test(q) ? 'presentation' : /데이터|csv/.test(q) && !/코드/.test(q) ? 'data' : /코드/.test(q) ? 'code' : null;
  return [...matched].sort((a, b) => Number(b.type === preferred) - Number(a.type === preferred)).map((item, index) => ({ ...item, rank: index + 1 }));
}
export function filterResults(results, { type = 'all', period = 'all', sort = 'relevance' } = {}) {
  const filtered = results.filter(item => (type === 'all' || item.type === type) && (period === 'all' || item.modified.startsWith(period)));
  if (sort === 'date') {
    const time = value => {const timestamp=Date.parse(value);return Number.isFinite(timestamp)?timestamp:-Infinity;};
    filtered.sort((a,b)=>time(b.modified)-time(a.modified)||a.rank-b.rank);
  }
  else if (sort === 'name') filtered.sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  else filtered.sort((a, b) => a.rank - b.rank);
  return filtered;
}
