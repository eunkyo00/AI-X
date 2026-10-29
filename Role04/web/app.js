import { WorkspaceUI } from './workspace-ui.mjs';
import { MockSearchService, SearchController } from './search-service.mjs';
import { SearchView } from './search-view.mjs';
import { loadHistory, saveHistory, recordQuery, HISTORY_KEY } from './history.mjs';

const paths = {
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  folder: '<path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/>',
  layers: '<rect x="3" y="3" width="9" height="9" rx="2"/><rect x="12" y="12" width="9" height="9" rx="2"/><path d="M16 4h4v4M8 20H4v-4M8 8l8 8"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>',
  upload: '<path d="M5 13v7h14v-7M12 16V3m-5 5 5-5 5 5"/>',
  settings: '<path d="m9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3Z"/><circle cx="12" cy="12" r="3"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  back: '<path d="M20 12H5m6-6-6 6 6 6"/>',
  document: '<path d="M14 3H5v18h14V8Zm0 0v5h5M8 12h8m-8 4h6"/>',
  network: '<rect x="8" y="2" width="8" height="6" rx="1"/><rect x="2" y="16" width="7" height="6" rx="1"/><rect x="15" y="16" width="7" height="6" rx="1"/><path d="M12 8v4H5v4m7-4h7v4"/>',
  spark: '<path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5Z"/>',
};
function icon(name) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.document}</svg>`;
}
document.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); });

const pages = {
  files: ['내 파일', '등록한 파일을 한곳에서 확인하는 공간입니다.'],
  tasks: ['작업 보기', '파일을 작업 단위로 살펴보는 공간입니다.'],
  history: ['최근 검색', '이전 검색 기록을 관리하는 공간입니다.'],
  favorites: ['즐겨찾기', '다시 찾고 싶은 파일을 모아두는 공간입니다.'],
  register: ['파일 등록', '파일과 폴더를 등록하는 공간입니다.'],
  settings: ['설정', '검색과 앱 환경을 설정하는 공간입니다.'],
};
let storage;
try { storage = window.localStorage; } catch { /* Use memory when storage is unavailable. */ }
let recent = loadHistory(storage);
let currentQuery = '';
const searchView = new SearchView();
let searchController;
const workspace = new WorkspaceUI({onChange:()=>{
  searchController?.cancel('mode-change');
  currentQuery='';
  searchView.source=workspace.mode==='demo'?'mock':workspace.mode;
  searchView.setState({status:'cancelled'});
},onSearch:search});
searchView.isFavorite=file=>workspace.isFavorite(file);
const mockService=new MockSearchService();
const routedService={search:(query,options)=>workspace.mode==='demo'?mockService.search(query,options):workspace.mode==='local'?workspace.library.search(query):workspace.api.search(query,options)};
searchController = new SearchController(routedService, state => {
  const actionHadFocus = ['cancel-search', 'retry-search'].includes(document.activeElement?.id);
  searchView.setState(state);
  if (actionHadFocus) document.querySelector('#results-query').focus({ preventScroll: true });
});

document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  document.querySelector('#main').focus();
});

function element(tag, className, text) {
  const el = document.createElement(tag);
  el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function relativeTime(at) {
  const minutes = Math.max(0, Math.floor((Date.now() - at) / 60000));
  if (minutes < 1) return '방금 전';
  if (minutes < 60) return `${minutes}분 전`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}시간 전`;
  if (minutes < 10080) return `${Math.floor(minutes / 1440)}일 전`;
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(at);
}
function renderRecent() {
  const compact = document.querySelector('#recent-searches');
  const full = document.querySelector('#history-list');
  compact.replaceChildren();
  full.replaceChildren();
  document.querySelector('#clear-history').disabled = recent.length === 0;
  if (!recent.length) {
    compact.append(element('p', 'rail-hint', '아직 검색 기록이 없어요. 기억나는 상황으로 첫 검색을 시작해 보세요.'));
    const empty = element('div', 'history-empty');
    empty.innerHTML = `<span class="large-empty-icon">${icon('clock')}</span>`;
    empty.append(element('h2', '', '아직 검색한 내용이 없어요'), element('p', '', '검색어를 입력하면 이곳에서 다시 찾을 수 있습니다.'));
    const link = element('a', 'subtle-link', '검색 시작하기 →');
    link.href = '#home';
    empty.append(link);
    full.append(empty);
  }
  recent.forEach((item, index) => {
    const row = element('div', 'history-row');
    const button = element('button', 'recent-query');
    button.type = 'button';
    button.innerHTML = `<span class="history-icon">${icon('search')}</span>`;
    const text = element('span', 'history-query-text', item.query);
    button.append(text);
    button.title = item.query;
    button.addEventListener('click', () => search(item.query));
    const time = element('time', 'history-time', relativeTime(item.at));
    time.dateTime = new Date(item.at).toISOString();
    button.append(time);
    row.append(button);
    const remove = element('button', 'remove-history', '×');
    remove.type = 'button';
    remove.setAttribute('aria-label', `${item.query} 검색 기록 삭제`);
    remove.addEventListener('click', () => {
      recent = recent.filter(entry => entry.query !== item.query);
      persistHistory();
      renderRecent();
      document.querySelector('#announcer').textContent = '검색 기록을 삭제했습니다.';
      const next = full.querySelectorAll('.recent-query');
      if (next.length) next[Math.min(index, next.length - 1)].focus();
      else document.querySelector('#history-title').focus();
    });
    row.append(remove);
    full.append(row);
    if (index < 4) {
      const shortcut = button.cloneNode(true);
      shortcut.addEventListener('click', () => search(item.query));
      compact.append(shortcut);
    }
  });
}
function persistHistory() {
  const saved = saveHistory(storage, recent);
  document.querySelector('#history-storage-note').textContent = saved
    ? '이 브라우저에만 저장됩니다.' : '현재 방문 중에만 기록됩니다. 브라우저 저장을 사용할 수 없습니다.';
  document.querySelector('.history-privacy').textContent = saved
    ? '최근 검색어 최대 8개가 이 브라우저에 저장됩니다.'
    : '브라우저 저장을 사용할 수 없어 현재 방문 중에만 기록됩니다.';
}
function search(rawQuery) {
  const query = rawQuery.trim();
  if (!query) return;
  currentQuery = query;
  searchView.source=workspace.mode==='demo'?'mock':workspace.mode;
  recent = recordQuery(recent, query);
  persistHistory();
  renderRecent();
  document.querySelector('#results-query').value = query;
  document.querySelector('#results-query').dispatchEvent(new Event('input'));
  document.querySelector('#query-summary').textContent = `입력한 검색어: “${query}”`;
  if (location.hash === '#results') route();
  else location.hash = 'results';
  searchController.search(query, { scenario: document.querySelector('#response-scenario').value });
}
function route() {
  const requested = location.hash.slice(1) || 'home';
  const page = requested === 'results' && !currentQuery ? 'home' : requested;
  const placeholder = Object.hasOwn(pages, page);
  if (page !== 'results') searchController.cancel('navigation');
  const target = ['files','register','favorites','tasks','settings'].includes(page) ? `${page}-page` : page === 'history' ? 'history-page' : placeholder ? 'placeholder-page' : page === 'results' ? 'results-page' : 'home-page';
  document.querySelectorAll('main > .page').forEach(el => { el.hidden = el.id !== target; });
  document.querySelectorAll('[data-page]').forEach(el => {
    const selected = el.dataset.page === (page === 'results' || !placeholder ? 'home' : page);
    el.classList.toggle('active', selected);
    if (selected) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  });
  if (placeholder) {
    document.querySelector('#placeholder-title').textContent = pages[page][0];
    document.querySelector('#placeholder-description').textContent = pages[page][1];
  }
  workspace.navigate(page);
  document.title = `${placeholder ? pages[page][0] : page === 'results' ? '검색 결과' : '홈'} · Context Search`;
  document.querySelector('#announcer').textContent = `${document.title} 화면`;
  window.scrollTo({ top: 0, behavior: 'instant' });
  if (target === 'results-page') document.querySelector('#results-query').focus({ preventScroll: true });
  else if (target === 'home-page') document.querySelector('#home-query').focus({ preventScroll: true });
  else document.querySelector('#main').focus({ preventScroll: true });
}
document.querySelectorAll('.search-form').forEach(form => {
  const input = form.querySelector('input');
  const button = form.querySelector('.search-submit');
  const clear = form.querySelector('.clear-query');
  const update = () => {
    button.disabled = !input.value.trim();
    if (clear) clear.hidden = !input.value;
  };
  if (clear) clear.addEventListener('click', () => {
    input.value = '';
    update();
    input.focus();
  });
  input.addEventListener('input', update);
  form.addEventListener('submit', event => { event.preventDefault(); search(input.value); });
  update();
});
document.querySelectorAll('[data-query]').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelector('#home-query').value = button.dataset.query;
    document.querySelector('#home-query').dispatchEvent(new Event('input'));
    search(button.dataset.query);
  });
});
const demoTasks = [
  { id: 'r-analysis', title: 'R 데이터 분석 과제', color: 'orange', date: '2026. 10', query: '지난달 R 과제할 때 사용했던 데이터', description: '입력 데이터에서 분석 코드, 그래프, 보고서로 이어지는 작업 예시입니다.', files: [['R_과제_설명.pdf', '참고 문서'], ['student_data.csv', '입력 데이터'], ['analysis.R', '분석 코드'], ['result_plot.png', '그래프'], ['분석_보고서.docx', '결과 문서']] },
  { id: 'presentation', title: '딥러닝 발표 준비', color: 'purple', date: '2026. 09', query: '딥러닝 발표 준비했던 PPT 찾아줘', description: '참고 논문과 정리 노트를 모아 발표를 준비한 작업 예시입니다.', files: [['강화학습_논문.pdf', '참고 자료'], ['발표_메모.txt', '작업 노트'], ['딥러닝_발표.pptx', '발표자료']] },
  { id: 'python', title: 'Python 실습', color: 'blue', date: '2026. 09', query: 'Python 실습할 때 쓴 코드랑 결과 파일', description: '원본 데이터를 코드로 처리하고 결과를 저장한 실습 예시입니다.', files: [['Python_실습_안내.pdf', '실습 안내'], ['raw_data.csv', '입력 데이터'], ['process.py', '처리 코드'], ['output.csv', '결과 데이터']] },
];
const dialog = document.querySelector('#task-dialog');
function showTask(task) {
  const container = document.querySelector('#task-dialog-content');
  container.replaceChildren();
  const title = element('h2', '', task.title);
  title.id = 'task-dialog-title';
  container.append(title, element('p', 'task-description', task.description));
  const files = element('ul', 'task-files');
  task.files.forEach(([name, role]) => {
    const row = element('li', '');
    row.innerHTML = `<span class="task-file-icon ${task.color}">${icon('document')}</span>`;
    row.append(element('span', '', name), element('small', '', role));
    files.append(row);
  });
  container.append(files, element('p', 'task-demo-note', '화면 설명을 위한 예시입니다. 실제 파일이 등록되거나 열리지는 않습니다.'));
  const searchButton = element('button', 'task-search-button', '이 작업의 예시 질문으로 검색 →');
  searchButton.addEventListener('click', () => { dialog.close(); search(task.query); });
  container.append(searchButton);
  dialog.showModal();
}
demoTasks.forEach(task => {
  const button = element('button', 'task-shortcut');
  button.type = 'button';
  button.innerHTML = `<span class="task-icon ${task.color}">${icon('folder')}</span>`;
  const text = element('span', 'task-shortcut-text');
  text.append(element('strong', '', task.title), element('small', '', `예시 파일 ${task.files.length}개 · ${task.date}`));
  button.append(text);
  button.addEventListener('click', () => showTask(task));
  document.querySelector('#recent-tasks').append(button);
});
document.querySelector('#view-demo-tasks').addEventListener('click', () => {
  const container = document.querySelector('#task-dialog-content');
  container.replaceChildren();
  const title = element('h2', '', '작업 맥락 미리보기');
  title.id = 'task-dialog-title';
  container.append(title, element('p', 'task-description', '작업을 선택해 관련 파일 구성을 살펴보세요.'));
  demoTasks.forEach(task => {
    const button = element('button', 'task-overview-button', `${task.title} · 예시 파일 ${task.files.length}개 →`);
    button.addEventListener('click', () => { dialog.close(); showTask(task); });
    container.append(button);
  });
  dialog.showModal();
});
document.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => {
  const rect = dialog.getBoundingClientRect();
  if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
});
document.querySelector('#clear-history').addEventListener('click', () => {
  recent = [];
  persistHistory();
  renderRecent();
  document.querySelector('#announcer').textContent = '검색 기록을 모두 삭제했습니다.';
  document.querySelector('#history-title').focus();
});
window.addEventListener('storage', event => {
  if (event.key === HISTORY_KEY || event.key === null) {
    recent = loadHistory(storage);
    renderRecent();
  }
});
document.querySelector('#cancel-search').addEventListener('click', () => searchController.cancel());
document.querySelector('#retry-search').addEventListener('click', () => {
  if(workspace.mode==='demo')document.querySelector('#response-scenario').value = 'normal';
  search(currentQuery);
});
document.querySelector('#run-scenario').addEventListener('click', () => {
  search(document.querySelector('#results-query').value);
});
window.addEventListener('pageshow', () => renderRecent());
window.addEventListener('hashchange', route);
persistHistory();
renderRecent();
route();

window.addEventListener('pagehide',()=>{searchController.cancel('navigation');workspace.registration?.abort();});

if(window.CONTEXT_SEARCH_CONFIG?.mode==='api')workspace.checkIntegration();
