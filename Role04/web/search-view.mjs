import { filterResults } from './search-data.mjs';

const el = (tag, className = '', text) => {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
function displayDate(value) {
  return value ? value.replace('T',' ').replace(/:00$/, '') : '알 수 없음';
}
function fileIcon(file) {
  return el('span', `file-type-icon type-${file.type}`, file.name.split('.').pop().toUpperCase());
}
function badge(certainty) {
  return el('span', `certainty ${certainty}`, certainty === 'confirmed' ? '확인된 참조' : certainty === 'inferred' ? '추정' : '분류 미제공');
}

export class SearchView {
  constructor() {
    this.catalog = [];this.relations=[];this.taskNames={};this.source="mock";
    this.results = [];
    this.visible = [];
    this.selected = null;
    this.activeTab = 'overview';
    this.type = 'all';
    this.status = 'idle';
    this.cards = document.querySelector('#result-cards');
    this.detail = document.querySelector('#detail-content');
    this.tabs = [...document.querySelectorAll('[role="tab"]')];
    document.querySelectorAll('[data-filter]').forEach(button => {
      button.addEventListener('click', () => { this.type = button.dataset.filter; this.render(); });
    });
    document.querySelector('#date-filter').addEventListener('change', () => this.render());
    document.querySelector('#sort-results').addEventListener('change', () => this.render());
    document.querySelector('#reset-filters').addEventListener('click', () => {
      this.resetFilters();
      this.render();
      document.querySelector('[data-filter="all"]').focus();
    });
    this.tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => this.setTab(tab.dataset.tab));
      tab.addEventListener('keydown', event => {
        const next = { ArrowRight: (index + 1) % 4, ArrowLeft: (index + 3) % 4, Home: 0, End: 3 }[event.key];
        if (next !== undefined) {
          event.preventDefault();
          this.setTab(this.tabs[next].dataset.tab);
          this.tabs[next].focus();
        }
      });
    });
    document.querySelector('#open-selected-file').addEventListener('click',()=>{if(this.selected)window.dispatchEvent(new CustomEvent('workspace-open-file',{detail:this.selected}));});
    document.querySelector('#favorite-selected-file').addEventListener('click',()=>{if(this.selected)window.dispatchEvent(new CustomEvent('workspace-favorite',{detail:this.selected}));});
    document.querySelector('#reveal-selected-file').addEventListener('click',()=>{if(this.selected)window.dispatchEvent(new CustomEvent('workspace-reveal',{detail:this.selected}));});
    window.addEventListener('workspace-favorites-changed',()=>this.renderFavorite());
    this.renderDetail();
  }
  renderFavorite(){
    const button=document.querySelector('#favorite-selected-file');
    const favorite=Boolean(this.selected && this.isFavorite?.(this.selected));
    button.setAttribute('aria-pressed',String(favorite));button.textContent=favorite?'즐겨찾기 해제':'즐겨찾기';
  }
  resetFilters() {
    this.type = 'all';
    document.querySelector('#date-filter').value = 'all';
    document.querySelector('#sort-results').value = 'relevance';
  }
  show(results, response={}) {
    this.catalog=response.catalog||results;this.relations=response.relations||[];this.taskNames=response.taskNames||{};this.source=response.source||"mock";
    this.status = 'success';
    this.results = results;
    const dateFilter=document.querySelector('#date-filter');
    const periods=new Set();
    for(const item of this.catalog){const match=/^(\d{4})-(0[1-9]|1[0-2])/.exec(item.modified||'');if(match){periods.add(match[1]);periods.add(`${match[1]}-${match[2]}`);}}
    dateFilter.replaceChildren();
    const all=el('option','','전체 기간');all.value='all';dateFilter.append(all);
    [...periods].sort().reverse().forEach(period=>{const option=el('option','',period.length===4?`${period}년`:`${period.slice(0,4)}년 ${Number(period.slice(5))}월`);option.value=period;dateFilter.append(option);});
    document.querySelector('#sort-results option[value="relevance"]').textContent=this.source==='local'?'목록순':'추천순';
    this.selected = null;
    this.activeTab = 'overview';
    this.resetFilters();
    this.render();
  }
  setState(state) {
    this.status = state.status;
    if (state.status === 'success') {
      this.show(state.files,state);
      if (state.scenario === 'empty') {
        document.querySelector('#empty-description').textContent = '결과 0건 응답을 재현한 예시입니다. 예시 응답 설정을 정상 응답으로 바꾼 뒤 다시 검색할 수 있습니다.';
      }
    } else {
      this.results = [];
      this.visible = [];
      this.selected = null;
      this.activeTab = 'overview';
      this.resetFilters();
      this.cards.replaceChildren();
      this.renderDetail();
    }
    const busy = state.status === 'loading';
    const feedback = document.querySelector('#search-feedback');
    const showFeedback = ['loading', 'error', 'cancelled'].includes(state.status);
    feedback.hidden = !showFeedback;
    feedback.dataset.state = state.status;
    this.cards.hidden = state.status !== 'success';
    this.cards.setAttribute('aria-busy', String(busy));
    document.querySelectorAll('[data-filter], #date-filter, #sort-results').forEach(control => {
      control.disabled = state.status !== 'success';
    });
    document.querySelector('#cancel-search').hidden = !busy;
    document.querySelector('#cancel-search').textContent=this.source==='api'?'응답 대기 중단':'검색 중단';
    document.querySelector('#retry-search').textContent=this.source==='mock'?'정상 응답으로 다시 시도':'다시 시도';
    document.querySelector('#retry-search').hidden = !['error', 'cancelled'].includes(state.status);
    if (showFeedback) {
      document.querySelector('#results-empty').hidden = true;
      const title = busy ? '기억의 단서로 파일을 찾고 있어요' : state.status === 'cancelled' ? '검색을 중단했어요' : state.code === 'TIMEOUT' ? '응답을 기다리는 시간이 길어졌어요' : '검색 결과를 가져오지 못했어요';
      const description = busy ? '검색이 끝나면 결과와 근거를 함께 보여드릴게요. 검색어를 바꿔 새로 검색할 수도 있습니다.' : state.status === 'cancelled' ? this.source==='mock'?'진행하던 예시 요청을 중단했습니다. 다시 검색하거나 다른 검색어를 입력해 보세요.':'화면에서 응답 대기를 중단했습니다. 서버 작업은 계속될 수 있습니다. 다시 검색하거나 연결 상태를 확인하세요.' : state.code === 'TIMEOUT' ? '10초 안에 응답이 도착하지 않아 요청을 중단했습니다. 다시 시도해 주세요.' : this.source==='mock'?'오류 응답을 재현한 예시입니다. 정상 응답으로 다시 시도해 결과 복구를 확인하세요.':'연결 주소와 서버 실행 상태를 확인한 뒤 다시 시도하세요. 서버 응답 형식이 맞지 않는 경우에도 발생할 수 있습니다.';
      document.querySelector('#search-feedback-title').textContent = title;
      document.querySelector('#search-feedback-description').textContent = description;
      document.querySelector('#result-count').textContent = busy ? '검색 중' : state.status === 'cancelled' ? '중단됨' : '응답 실패';
      document.querySelector('#announcer').textContent = title;
    } else if (state.status === 'success') {
      document.querySelector('#announcer').textContent = `${this.source==='mock'?'예시 ':''}검색 결과 ${state.files.length}개를 표시했습니다.`;
    }
  }
  render() {
    this.visible = filterResults(this.results, {
      type: this.type, period: document.querySelector('#date-filter').value,
      sort: document.querySelector('#sort-results').value,
    });
    if (!this.visible.some(file => file.id === this.selected?.id)) this.selected = this.visible[0] || null;
    document.querySelectorAll('[data-filter]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.filter === this.type));
    });
    document.querySelector('#result-count').textContent = `${this.source==='mock'?'예시 ':''}${this.visible.length}개 / 전체 ${this.results.length}개`;
    this.cards.replaceChildren();
    this.visible.forEach(file => {
      const button = el('button', 'result-card');
      button.type = 'button';
      button.dataset.fileId = file.id;
      button.setAttribute('aria-pressed', String(this.selected?.id === file.id));
      button.setAttribute('aria-label', `${file.name} 상세 보기`);
      button.append(fileIcon(file));
      const body = el('span', 'result-card-body');
      const heading = el('span', 'result-card-heading');
      heading.append(el('strong', '', file.name), el('span', 'result-rank', `${this.source==='local'?'순서':'추천'} ${file.rank}`));
      const meta = el('span', 'result-meta');
      [file.name.split('.').pop().toUpperCase(), this.taskNames[file.task] || file.taskName || '작업 정보 없음', file.role || '알 수 없음', displayDate(file.modified)].forEach(value => meta.append(el('span', '', value)));
      if(Number.isFinite(file.score))meta.append(el('span','','유사도 '+file.score.toFixed(3)));
      body.append(heading, el('span', 'result-path', file.path), meta, el('span', 'result-summary', file.summary));
      button.append(body);
      button.addEventListener('click', () => this.select(file));
      this.cards.append(button);
    });
    const empty = document.querySelector('#results-empty');
    empty.hidden = this.visible.length > 0;
    document.querySelector('#empty-title').textContent = this.results.length ? '선택한 조건에 맞는 파일이 없어요' : this.source==='mock'?'일치하는 예시 파일이 없어요':'일치하는 파일이 없어요';
    document.querySelector('#empty-description').textContent = this.results.length
      ? '파일 형식이나 수정 날짜 조건을 바꿔보세요.'
      : this.source==='mock'?'R 과제, Python 실습, 딥러닝 발표, 강화학습 논문 등의 예시 질문으로 검색해 보세요.':this.source==='local'?'등록한 파일명이나 경로의 단어로 검색해 보세요. 로컬 모드는 AI 의미 검색을 수행하지 않습니다.':'질의를 바꾸거나 등록·인덱스 준비 상태를 확인하세요.';
    document.querySelector('#reset-filters').hidden = !this.results.length;
    this.renderDetail();
  }
  select(file, fromRelated = false) {
    this.selected = file;
    this.cards.querySelectorAll('.result-card').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.fileId === file.id)));
    this.activeTab = 'overview';
    this.renderDetail();
    document.querySelector('#announcer').textContent = `${file.name} 상세 정보를 표시했습니다.`;
    if (fromRelated || matchMedia('(max-width: 800px)').matches) {
      const panel = document.querySelector('.detail-panel');
      panel.focus({ preventScroll: true });
      panel.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
    }
  }
  setTab(key) {
    this.activeTab = key;
    this.renderDetail();
  }
  renderDetail() {
    const file = this.selected;
    this.tabs.forEach(tab => {
      const selected = tab.dataset.tab === this.activeTab;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    this.detail.setAttribute('aria-labelledby', `tab-${this.activeTab}`);
    this.detail.replaceChildren();
    for(const id of ['open-selected-file','favorite-selected-file','reveal-selected-file'])document.querySelector(`#${id}`).disabled=!file;
    const openButton=document.querySelector('#open-selected-file');
    openButton.disabled=!file || file.contentAvailable===false;
    openButton.title=file?.contentAvailable===false?'현재 서버에는 원본 파일 열기가 연결되지 않았습니다.':'';
    this.renderFavorite();
    document.querySelector('#detail-title').textContent = file?.name || '파일 상세';
    document.querySelector('#detail-path').textContent = file?.path || '결과에서 파일을 선택해 주세요';
    document.querySelector('#detail-icon').replaceChildren(...(file ? [fileIcon(file)] : []));
    document.querySelector('#detail-selection-note').hidden = !file || this.visible.some(item => item.id === file.id);
    if (!file) {
      this.detail.append(el('p', 'detail-empty-message', this.status === 'loading' ? '검색이 완료되면 파일 정보를 확인할 수 있습니다.' : this.status === 'error' ? '응답을 받지 못해 표시할 파일 정보가 없습니다.' : this.status === 'cancelled' ? '검색을 다시 실행하면 파일 정보를 확인할 수 있습니다.' : '표시할 파일이 없습니다. 검색어나 필터를 바꿔보세요.'));
      return;
    }
    if(file.contentAvailable===false)this.detail.append(el('p','capability-note','원본 파일 열기는 아직 연결되지 않았습니다. 검색에 사용한 본문 발췌를 아래에서 확인할 수 있습니다.'));
    if (this.activeTab === 'overview') {
      const table = el('dl', 'file-properties');
      [['파일 형식', file.name.split('.').pop().toUpperCase()], ['크기', file.size], ['역할', file.role || '알 수 없음'], ['수정 날짜', displayDate(file.modified)], ['위치', file.path]].forEach(([name, value]) => {
        table.append(el('dt', '', name), el('dd', '', value));
      });
      this.detail.append(table);
      this.renderEvidence(file, true);
      this.renderRelated(file, true);
    } else if (this.activeTab === 'evidence') this.renderEvidence(file);
    else if (this.activeTab === 'related') this.renderRelated(file);
    else this.renderContext(file);
    this.detail.append(el('p', 'detail-footnote', this.source==='mock'?'화면용 예시 데이터입니다. 예시 파일에는 실제 원본이 없습니다.':this.source==='local'?'브라우저에 보관한 파일입니다. AI 분석·검색 인덱싱과 작업 관계는 아직 제공되지 않았습니다.':'팀원 API가 반환한 정보입니다. 누락된 근거는 임의로 채우지 않습니다.'));
  }
  renderEvidence(file, compact = false) {
    const heading = el('div', 'detail-section-heading');
    heading.append(el('h3', '', '검색 근거'));
    this.detail.append(heading);
    const list = el('ul', 'evidence-list');
    (compact ? file.evidence.slice(0, 2) : file.evidence).forEach(evidence => {
      const row = el('li', '');
      row.append(el('p', '', evidence.text), badge(evidence.certainty));
      list.append(row);
    });
    this.detail.append(list);
    if(file.excerpt){
      this.detail.append(el('h4','','검색에 대응된 본문 발췌'),el('p','result-excerpt',file.excerpt),el('p','evidence-legend','본문 중 검색어와 가장 유사한 구간입니다. 추천 이유를 생성한 설명은 아닙니다.'));
    }
    if(!file.evidence.length && !file.excerpt)this.detail.append(el('p','related-empty','제공된 검색 근거가 없습니다.'));
    if (compact && (file.excerpt || file.evidence.length)) this.detail.append(this.tabLink('검색 근거 자세히 보기 →', 'evidence'));
    else this.detail.append(el('p', 'evidence-legend', this.source==='mock'?'확인된 참조는 예시 파일 내용에 나타난 참조를, 추정은 단서에 따른 해석을 뜻합니다. 수정 날짜는 실제 사용 시각과 다를 수 있습니다.':'유사도는 검색어와 본문의 가까운 정도이며 정답 확률이 아닙니다. 수정 날짜는 실제 사용 시각과 다를 수 있습니다.'));
  }
  tabLink(text, key) {
    const button = el('button', 'detail-text-button', text);
    button.type = 'button';
    button.addEventListener('click', () => {
      this.setTab(key);
      document.querySelector(`#tab-${key}`).focus();
    });
    return button;
  }
  renderRelated(file, compact = false) {
    const related = this.relations.filter(link=>link.from===file.id||link.to===file.id).map(link=>({file:this.catalog.find(item=>item.id===(link.from===file.id?link.to:link.from)),relation:link})).filter(item=>item.file);
    const heading = el('div', 'detail-section-heading');
    heading.append(el('h3', '', `관련 파일 (${related.length})`));
    this.detail.append(heading);
    if (!related.length) this.detail.append(el('p', 'related-empty', file.relationsAvailable===false?'현재 검색 엔진은 파일 간 관계를 제공하지 않습니다. 검색 순위가 비슷한 파일을 관련 파일로 간주하지 않습니다.':'제공된 직접 연결 관계가 없습니다.'));
    const list = el('div', compact ? 'related-grid' : 'related-list');
    related.forEach(({file: target, relation}) => {
      const button = el('button', 'related-file');
      button.type = 'button';
      button.setAttribute('aria-label', `${target.name} 관련 파일 상세 보기`);
      button.append(fileIcon(target), el('strong', '', target.name));
      if (!compact) button.append(el('span', 'related-description', relation.label));
      button.append(badge(relation.certainty));
      button.addEventListener('click', () => this.select(target, true));
      list.append(button);
    });
    this.detail.append(list);
    if (compact && related.length) this.detail.append(this.tabLink('관계와 근거 확인 →', 'related'));
  }
  renderContext(file) {
    if(!file.task){this.detail.append(el('p','context-intro','제공된 작업 정보가 없습니다. 파일명이나 시각만으로 같은 작업이라고 단정하지 않습니다.'));return;}
    this.detail.append(el('h3', '', this.taskNames[file.task] || file.taskName || '작업 정보 없음'), el('p', 'context-intro', this.source==='mock'?'예시 파일의 내용·참조를 바탕으로 구성한 작업 맥락입니다. 같은 작업이라는 판단에는 추정이 포함됩니다.':'서비스가 제공한 작업 ID와 관계를 표시합니다. 확인된 사실과 추정을 구분해 확인하세요.'));
    const group = el('div', 'context-files');
    this.catalog.filter(item => item.task === file.task).forEach(item => {
      const button = el('button', 'context-file', `${item.role} · ${item.name}`);
      button.type = 'button';
      button.setAttribute('aria-current', String(item.id === file.id));
      button.addEventListener('click', () => this.select(item, true));
      group.append(button);
    });
    this.detail.append(group, el('h3', 'context-relations-title', '파일 간 연결'));
    const list = el('ul', 'context-relations');
    this.relations.filter(link => this.catalog.find(item => item.id === link.from)?.task === file.task).forEach(link => {
      const row = el('li', link.certainty);
      row.append(el('strong', '', `${this.catalog.find(item => item.id === link.from).name} → ${this.catalog.find(item => item.id === link.to).name}`), el('span', '', link.label), badge(link.certainty));
      list.append(row);
    });
    this.detail.append(list);
  }
}
