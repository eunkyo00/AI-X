import { BrowserLibrary, ApiWorkspace, validateFile, normalizeFile, formatSize, extension, validateBaseUrl } from './workspace-service.mjs';
import { files as demoFiles } from './search-data.mjs';

const node = (tag, cls='', text) => {const el=document.createElement(tag);el.className=cls;if(text!==undefined)el.textContent=text;return el;};
const read = (key,fallback) => {try {return JSON.parse(localStorage.getItem(key)) ?? fallback;}catch{return fallback;}};
const write = (key,value) => {try {localStorage.setItem(key,JSON.stringify(value));return true;}catch{return false;}};
const abortableWait = (ms,signal) => new Promise((resolve,reject)=>{
  const cancel=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',cancel);resolve();},ms);
  if(signal.aborted)cancel();else signal.addEventListener('abort',cancel,{once:true});
});
export class WorkspaceUI {
  constructor({onChange,onSearch}={}) {
    this.onChange=onChange;this.onSearch=onSearch;
    const runtime=window.CONTEXT_SEARCH_CONFIG || {};
    const config=runtime.mode ? {...runtime,base:new URL(runtime.base,location.href).href} : read('context-search.settings.v1',{});
    this.bundledBase=runtime.mode ? config.base : null;
    this.mode=['demo','local','api'].includes(config.mode)?config.mode:'demo';
    try {this.base=validateBaseUrl(config.base || 'http://127.0.0.1:8000/api');}catch{this.base='http://127.0.0.1:8000/api';}
    this.previewVersion=0;this.library=new BrowserLibrary();this.queue=[];this.catalog=[];this.refreshId=0;
    this.api=new ApiWorkspace(this.base);this.health=null;
    this.favorites=read('context-search.favorites.v1',[]);
    if(!Array.isArray(this.favorites))this.favorites=[];
    this.favorites=this.favorites.slice(0,100).flatMap(raw=>{try{return [normalizeFile(raw,0,['local','api','demo'].includes(raw.source)?raw.source:'demo')];}catch{return [];}});
    this.observations=read('context-search.usability.v1',[]);
    if(!Array.isArray(this.observations))this.observations=[];
    this.observations=this.observations.filter(item=>item && typeof item.participant==='string' && typeof item.task==='string').slice(0,200);
    this.homeCopies=[...document.querySelectorAll('.feature-card h3,.feature-card p,.suggestions button,.example-card strong,.example-card .tags,.rail-tip p')].map(el=>({el,html:el.innerHTML,query:el.closest('[data-query]')?.dataset.query}));
    this.bind();this.renderMode();this.renderObservations();
    this.watchTimer=setInterval(()=>this.pollWorkspace(),5000);
    this.pollWorkspace();
  }
  message(text) {const box=document.querySelector('#workspace-message');box.querySelector('p').textContent=text;box.hidden=false;}
  bind() {
    document.querySelector('#workspace-message button').onclick=()=>document.querySelector('#workspace-message').hidden=true;
    document.querySelector('#workspace-mode').value=this.mode;document.querySelector('#api-base').value=this.base;
    document.querySelector('#workspace-settings').onsubmit=event=>{
      event.preventDefault();
      if(this.registration){this.message('등록이 끝나거나 대기를 중단한 뒤 모드를 변경하세요.');return;}
      try {
        const base=validateBaseUrl(document.querySelector('#api-base').value);
        this.mode=document.querySelector('#workspace-mode').value;this.base=base;this.api=new ApiWorkspace(base);this.health=null;
        const saved=write('context-search.settings.v1',{mode:this.mode,base});
        this.onChange?.();this.renderMode();this.catalog=[];this.refreshId++;
        document.querySelector('#integration-report').textContent='주소가 저장되었습니다. 연결 확인은 아직 하지 않았습니다.';
        this.message(saved?'데이터 모드를 변경했습니다. 실제 API 연결은 연결 확인 버튼으로 점검하세요.':'현재 방문에만 설정을 적용했습니다. 브라우저 저장이 제한되어 있습니다.');
      }catch(error){this.message(error.message);}
    };
    document.querySelector('#check-integration').onclick=()=>this.checkIntegration();
    document.querySelector('#choose-files').onclick=()=>document.querySelector('#file-picker').click();
    document.querySelector('#choose-folder').onclick=()=>document.querySelector('#folder-picker').click();
    for(const id of ['file-picker','folder-picker'])document.querySelector(`#${id}`).onchange=event=>{this.enqueue(event.target.files);event.target.value='';};
    const zone=document.querySelector('#upload-zone');
    zone.ondragover=event=>{event.preventDefault();zone.classList.add('drag-over');};
    zone.ondragleave=()=>zone.classList.remove('drag-over');
    zone.ondrop=event=>{event.preventDefault();zone.classList.remove('drag-over');this.enqueue(event.dataTransfer.files);};
    document.querySelector('#start-registration').onclick=()=>this.register();
    document.querySelector('#stop-registration').onclick=()=>{this.registration?.abort();};
    document.querySelector('#clear-queue').onclick=()=>{if(!this.registration){this.queue=[];this.renderQueue();}};
    document.querySelector('#retry-registration').onclick=()=>{for(const item of this.queue)if(['failed','cancelled'].includes(item.state))item.state='waiting';this.register();};
    document.querySelector('#search-library').onclick=()=>{
      if(this.registration){this.message('등록이 끝난 뒤 검색 모드를 바꿀 수 있습니다.');return;}
      if(this.mode!=='api'){this.mode='local';write('context-search.settings.v1',{mode:this.mode,base:this.base});document.querySelector('#workspace-mode').value=this.mode;this.onChange?.();this.renderMode();}
      location.hash='home';
    };
    document.querySelector('#refresh-files').onclick=()=>this.refresh();
    document.querySelector('#refresh-index').onclick=()=>this.refreshIndex();
    document.querySelector('#watch-folder-form').onsubmit=async event=>{
      event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;
      try{await this.api.saveFolder({path:document.querySelector('#watch-folder-path').value.trim()});document.querySelector('#watch-folder-path').value='';await this.renderFolders();}
      catch(error){this.message(error.message);}finally{button.disabled=false;}
    };
    document.querySelector('#library-filter').oninput=()=>this.renderFiles();
    window.addEventListener('workspace-open-file',event=>this.preview(event.detail));
    window.addEventListener('workspace-favorite',event=>this.toggleFavorite(event.detail));
    window.addEventListener('workspace-reveal',event=>this.reveal(event.detail));
    document.querySelector('#close-preview').onclick=()=>document.querySelector('#file-preview-dialog').close();
    document.querySelector('#file-preview-dialog').addEventListener('close',()=>{this.previewVersion=(this.previewVersion||0)+1;if(this.objectUrl)URL.revokeObjectURL(this.objectUrl);this.objectUrl=null;document.querySelector('#file-preview-content').replaceChildren();});
    document.querySelector('#usability-form').onsubmit=event=>{
      event.preventDefault();const data=new FormData(event.target);
      if(!String(data.get('participant')).trim()){this.message('참가자 코드를 입력하세요.');return;}
      this.observations.unshift({kind:data.get('kind'),participant:String(data.get('participant')).trim(),task:data.get('task'),outcome:data.get('outcome'),seconds:Number(data.get('seconds')),notes:String(data.get('notes')).trim(),at:new Date().toISOString()});
      this.observations=this.observations.slice(0,200);
      const saved=write('context-search.usability.v1',this.observations);this.renderObservations();this.message(saved?'관찰 결과를 저장했습니다.':'브라우저 저장이 제한되어 있습니다. 지금 JSON으로 내보내세요.');event.target.reset();
    };
    document.querySelector('#export-usability').onclick=()=>{
      const blob=new Blob([JSON.stringify(this.observations,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=node('a');link.href=url;link.download='context-search-usability.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
  }
  renderMode() {
    const bundled=this.mode==='api' && this.base===this.bundledBase;
    for(const {el,html,query} of this.homeCopies){el.innerHTML=html;if(query)el.closest('[data-query]').dataset.query=query;}
    if(bundled){
      const features=[['내용으로 검색','기억나는 주제와 내용으로 파일 찾기'],['파일 정보 확인','역할·크기·수정 날짜 살펴보기'],['시간 조건 검색','지난달·최근 7일 등 날짜 조건으로 찾기'],['관련 파일 확인','명시적 참조와 유사한 파일의 근거 확인']];
      document.querySelectorAll('.feature-card').forEach((card,i)=>{card.querySelector('h3').textContent=features[i][0];card.querySelector('p').textContent=features[i][1];});
      const queries=['SARIMA 예측 코드','교차 검증 방법을 설명한 강의자료','2026년 4월 수정한 강의자료','갑오개혁의 전개와 성과'];
      document.querySelectorAll('.suggestions button').forEach((button,i)=>{button.textContent=queries[i];button.dataset.query=queries[i];});
      document.querySelectorAll('.example-card').forEach((button,i)=>{button.querySelector('strong').textContent=queries[i];button.querySelector('.tags').textContent=i===0?'시계열 · R 코드':'강의·읽기 자료 · PDF';button.dataset.query=queries[i];});
      document.querySelector('.rail-tip p').textContent='“2026년 4월 수정한 강의자료”처럼 내용과 날짜를 함께 적어보세요. 수정일은 실제 사용 시각과 다를 수 있습니다.';
    }

    document.querySelector('#home-title').textContent=this.mode==='local'?'보관한 파일을 찾아보세요':'어떤 파일을 찾으시나요?';
    document.querySelector('.hero > p').textContent=this.mode==='local'?'파일명 또는 폴더 경로의 단어로 검색합니다. AI 의미 검색은 팀원 API 연결 후 사용할 수 있습니다.':'파일 이름은 잊어도 괜찮아요. 기억나는 상황으로 다시 찾아보세요.';
    document.querySelector('.search-helper').firstChild.textContent=this.mode==='local'?'파일명 · 상대 경로로 검색합니다 ':'시기 · 작업 · 파일의 역할을 떠올려 보세요 ';
    if(this.mode==='api' && this.base===this.bundledBase){
      document.querySelector('.search-helper').firstChild.textContent='파일 내용 · 생성일 · 수정일 조건으로 검색합니다 ';
    }
    document.querySelector('#home-query').placeholder=this.mode==='local'?'예) 분석 코드, 학생 데이터':this.mode==='api' && this.base===this.bundledBase?'예) SARIMA 예측 코드':'예) 지난달 R 과제할 때 사용했던 데이터 찾아줘';
    for(const selector of ['.suggestions','.features','.examples'])document.querySelector(selector).hidden=this.mode==='local';
    const names={demo:'예시 시나리오',local:'브라우저 보관 · 이름·경로 검색',api:'팀원 API · 연결 상태는 설정에서 확인'};
    document.querySelector('#workspace-mode-label').textContent=names[this.mode];
    document.querySelector('#registration-destination').textContent=this.mode==='api' && this.base===this.bundledBase?'이 컴퓨터에 파일을 복사한 뒤 본문·DB·검색 인덱스·관계를 갱신합니다. 완료까지 기다려 주세요. 이미지 검색 등록은 지원하지 않습니다.':this.mode==='api'?`선택한 파일을 팀원 서버 ${this.base} 로 전달합니다.`:'선택한 파일을 이 브라우저에 보관합니다. 원본 파일은 변경하지 않습니다.';
    document.querySelector('.demo-search-banner p').textContent=this.mode==='demo'?'화면 확인용 샘플 데이터입니다. 실제 파일 검색과 열기는 연결되지 않았습니다.':this.mode==='local'?'브라우저에 보관한 실제 파일의 이름·경로를 검색합니다. AI 의미 검색은 수행하지 않습니다.':bundled?'파일 내용으로 찾은 상위 5개 후보입니다. 낮은 유사도 결과도 포함될 수 있습니다.':`팀원 API를 사용합니다: ${this.base}`;
    document.querySelector('.demo-search-banner .demo-badge').textContent=this.mode==='demo'?'예시 검색':this.mode==='local'?'로컬 검색':'API 검색';
    document.querySelector('.demo-response-controls').hidden=this.mode!=='demo';
    document.querySelector('.index-status p').textContent=this.mode==='demo'?'예시 모드 · 실제 인덱싱 없음':this.mode==='local'?'브라우저 보관 · AI 인덱스 미연결':'서버 준비 상태 미확인';
    document.querySelector('.index-status progress').value=0;
    document.querySelector('#library-description').textContent=this.mode==='demo'?'예시 파일 목록입니다. 실제 파일은 파일 등록에서 보관하세요.':this.mode==='local'?'이 브라우저에 보관한 실제 파일입니다. 브라우저 데이터를 지우면 보관본도 삭제됩니다.':'팀원 API가 반환한 파일 목록입니다.';
    document.querySelector('#refresh-index').hidden=!bundled;
    document.querySelector('#watch-folders').hidden=!bundled;
    document.querySelector('#registration-note').textContent=bundled?'PDF · CSV · TSV · XLSX · PPTX · DOCX · TXT · Python · R · MD · JSON · IPYNB · HTML · CSS · JS · SQL를 등록할 수 있습니다. 이미지·OCR 전용 문서는 지원하지 않습니다.':'브라우저 보관은 AI 검색 인덱싱을 수행하지 않습니다.';
    this.renderQueue();
  }
  async navigate(page) {
    if(['files','favorites'].includes(page))await this.refresh();
    if(page==='settings')this.renderObservations();
    if(page==='register')this.renderMode();
    if(page==='files' && this.mode==='api' && this.base===this.bundledBase){this.resumeRefresh();this.renderFolders();}
  }
  async refresh() {
    const version=++this.refreshId;const mode=this.mode;
    document.querySelector('#library-list').textContent='파일 목록을 불러오는 중입니다…';
    try {
      const catalog=mode==='demo'?demoFiles.map(file=>({...file,source:'demo'})):mode==='local'?await this.library.list():await this.api.list();
      if(version!==this.refreshId || mode!==this.mode)return;
      this.catalog=catalog;this.renderFiles();this.renderFavorites();
      if(mode==='local')document.querySelector('.index-status p').textContent=`로컬 보관 ${catalog.length}개 · AI 인덱스 미연결`;
    }catch(error){if(version===this.refreshId){this.catalog=[];document.querySelector('#library-list').textContent='목록을 불러오지 못했습니다. 연결 설정이나 브라우저 저장 권한을 확인하고 새로고침하세요.';this.renderFavorites();this.message(error.message);}}
  }
  fileRow(file) {
    const row=node('article','library-row');const info=node('div','library-row-info');info.append(node('strong','',file.name),node('p','',file.path),node('small','',`${file.project || '프로젝트 미제공'} · ${file.role || '알 수 없음'} · ${file.modified || '날짜 알 수 없음'} · ${file.size || '크기 알 수 없음'} · ${file.source==='demo'?'예시':file.source==='local'?'로컬 보관':file.indexStatus==='ready'?'서버 검색 준비 완료':file.indexStatus==='no_text'?'검색할 본문 없음':'서버 분석 상태 미확인'}`));
    const actions=node('div','workspace-actions');
    for(const [name,action]of [['열기',()=>this.preview(file)],['저장 위치',()=>this.reveal(file)],[this.isFavorite(file)?'즐겨찾기 해제':'즐겨찾기',()=>this.toggleFavorite(file)]]){const button=node('button','outline-button',name);button.onclick=action;actions.append(button);}
    row.append(info,actions);return row;
  }
  renderFiles() {
    const list=document.querySelector('#library-list');list.replaceChildren();
    const query=document.querySelector('#library-filter').value.toLowerCase();const filtered=this.catalog.filter(file=>`${file.name} ${file.path}`.toLowerCase().includes(query));
    if(!filtered.length)list.append(node('p','workspace-empty','표시할 파일이 없습니다. 파일을 등록하거나 검색 조건을 바꿔보세요.'));
    filtered.forEach(file=>list.append(this.fileRow(file)));
  }
  isFavorite(file){return this.favorites.some(item=>item.id===file.id && item.source===(file.source||'demo') && (item.apiBase||'')===(file.apiBase||''));}
  toggleFavorite(file) {
    const normalized={...file,source:file.source||'demo'};
    if(this.isFavorite(normalized))this.favorites=this.favorites.filter(item=>!(item.id===file.id && item.source===normalized.source && (item.apiBase||'')===(normalized.apiBase||'')));
    else if(this.favorites.length>=100){this.message('즐겨찾기는 100개까지 저장할 수 있습니다.');return;}
    else this.favorites.push(normalized);
    const saved=write('context-search.favorites.v1',this.favorites);this.renderFavorites();if(this.catalog.length)this.renderFiles();window.dispatchEvent(new Event('workspace-favorites-changed'));
    this.message(saved?'즐겨찾기를 변경했습니다.':'현재 방문에만 즐겨찾기를 변경했습니다. 브라우저 저장이 제한되어 있습니다.');
  }
  renderFavorites(){const list=document.querySelector('#favorites-list');list.replaceChildren();const visible=this.favorites.filter(file=>file.source===this.mode && (file.source!=='api' || file.apiBase===this.base));if(!visible.length)list.append(node('p','workspace-empty','현재 모드에 저장한 즐겨찾기가 없습니다. 파일 상세 또는 내 파일에서 추가하세요.'));visible.forEach(file=>list.append(this.fileRow(file)));}
  enqueue(files) {
    if(this.registration){this.message('등록이 끝나거나 대기를 중단한 뒤 파일을 추가하세요.');return;}
    const added=Array.from(files);if(this.queue.length+added.length>500){this.message('한 번에 최대 500개까지 선택할 수 있습니다.');return;}
    if([...this.queue.map(item=>item.file),...added].reduce((sum,file)=>sum+file.size,0)>100*1024*1024){this.message('선택한 파일의 합계는 100MB까지 지원합니다.');return;}
    for(const file of added){const duplicate=this.queue.some(item=>item.file.name===file.name && item.file.size===file.size && item.file.lastModified===file.lastModified && item.file.webkitRelativePath===file.webkitRelativePath);const error=validateFile(file);this.queue.push({file,state:duplicate?'skipped':error?'invalid':'waiting',message:duplicate?'같은 경로·크기·수정 시각의 항목입니다.':error||'등록 대기'});}
    this.renderQueue();
  }
  renderQueue() {
    const busy=Boolean(this.registration);const list=document.querySelector('#registration-list');list.replaceChildren();const labels={waiting:'대기',processing:'전송·보관 중',stored:'로컬 보관 완료',ready:'검색 준비 완료',registered:'서버 등록',failed:'실패',invalid:'지원 불가',skipped:'건너뜀',cancelled:'대기 중단',unknown:'상태 미확인'};
    this.queue.forEach(item=>{const row=node('div',`registration-row state-${item.state}`);const info=node('div');info.append(node('strong','',item.file.webkitRelativePath||item.file.name),node('p','',`${formatSize(item.file.size)} · ${item.message}`));row.append(info,node('span','',labels[item.state]||item.state));list.append(row);});
    const counts={};for(const item of this.queue)counts[item.state]=(counts[item.state]||0)+1;
    const finished=this.queue.filter(item=>!['waiting','processing'].includes(item.state)).length;
    document.querySelector('#registration-summary').textContent=this.queue.length?`전체 ${this.queue.length}개 · 로컬 보관 ${counts.stored||0} · 서버 등록 ${counts.registered||0} · 검색 준비 ${counts.ready||0} · 실패 ${(counts.failed||0)+(counts.invalid||0)} · 건너뜀 ${counts.skipped||0} · 중단 ${counts.cancelled||0} · 미확인 ${counts.unknown||0}`:'등록할 파일을 선택하세요.';
    const progress=document.querySelector('#registration-progress');progress.max=Math.max(1,this.queue.length);progress.value=finished;
    document.querySelector('#start-registration').disabled=busy||!this.queue.some(item=>item.state==='waiting');document.querySelector('#stop-registration').hidden=!busy;document.querySelector('#retry-registration').hidden=busy||!this.queue.some(item=>['failed','cancelled'].includes(item.state));
    for(const id of ['choose-files','choose-folder','clear-queue'])document.querySelector(`#${id}`).disabled=busy;
  }
  async register() {
    if(this.registration)return;
    if(this.indexMonitor){this.message('진행 중인 데이터 갱신이 끝난 뒤 등록하세요.');return;}
    this.registration=new AbortController();const signal=this.registration.signal;const apiMode=this.mode==='api';const api=this.api;
    this.renderQueue();
    try {
      for(const item of this.queue){if(item.state!=='waiting')continue;if(signal.aborted){item.state='cancelled';item.message='아직 시작하지 않은 항목입니다.';continue;}
        item.state='processing';item.message=apiMode?'서버로 파일을 전송합니다.':'브라우저 저장소에 보관합니다.';this.renderQueue();
        try {
          if(apiMode){const result=await api.add(item.file,{signal});if(result.duplicate){item.state='skipped';item.message='서버가 이미 등록된 파일이라고 응답했습니다.';this.renderQueue();continue;}item.state=result.file.indexStatus==='ready'?'ready':'registered';item.message=result.jobId?'서버 분석 상태를 확인합니다.':'서버가 검색 준비 완료를 알리지 않은 경우 분석 완료로 표시하지 않습니다.';this.renderQueue();
            if(result.jobId){
              let completed=false;
              for(let attempts=0;attempts<1800;attempts++){
                if(signal.aborted)throw new DOMException('Aborted','AbortError');
                const job=await api.job(result.jobId,{signal});
                if(job.status==='ready'){item.state='ready';item.message='서버가 인덱스 준비 완료를 반환했습니다.';completed=true;break;}
                if(job.status==='failed')throw Error(job.error||job.phase||'서버 분석에 실패했습니다.');
                item.message=`서버 처리 중: ${typeof job.phase==='string'?job.phase:'단계 미제공'}`;this.renderQueue();await abortableWait(1000,signal);
              }
              if(!completed){item.state='registered';item.message='서버 작업이 계속 진행 중입니다. 내 파일에서 진행 상태를 확인하세요.';this.registration.abort();}
            }
          }else{await this.library.add(item.file);item.state='stored';item.message='브라우저 보관 완료 · AI 내용 분석·인덱싱은 수행하지 않았습니다.';}
        }catch(error){if(error.message==='DUPLICATE'){item.state='skipped';item.message='같은 경로·크기·수정 시각의 파일이 이미 보관되어 있습니다.';}else if(signal.aborted){item.state=apiMode?'unknown':'cancelled';item.message=apiMode?'서버 처리 완료 여부는 확인되지 않았습니다. 내 파일을 새로고침하세요.':'대기가 중단되었습니다.';}else{item.state='failed';item.message=error.message||'실패했습니다. 다시 시도하세요.';}}
        this.renderQueue();
      }
    }finally{this.registration=null;if(!apiMode && this.mode==='demo' && this.queue.some(item=>item.state==='stored')){this.mode='local';write('context-search.settings.v1',{mode:this.mode,base:this.base});document.querySelector('#workspace-mode').value=this.mode;this.onChange?.();this.renderMode();this.message('파일을 보관했습니다. 브라우저 보관 파일 모드로 전환했습니다.');}this.renderQueue();await this.refresh();document.querySelector('#registration-note').textContent=apiMode?'대기 중단은 서버 작업 취소가 아닙니다. 서버 상태를 내 파일에서 다시 확인하세요.':'완료한 파일은 브라우저에 보관되어 있습니다. AI 분석·인덱싱은 미연결 상태입니다.';}
  }
  async checkIntegration(){
    const button=document.querySelector('#check-integration');button.disabled=true;
    const report=document.querySelector('#integration-report');report.textContent='서버 상태와 파일 목록 확인 중…';
    this.health=null;const api=this.api;
    try{
      const health=await api.health();const files=await api.list();if(api!==this.api)return;
      this.health=health;
      report.textContent=`연결됨 · 파일 ${files.length}개 · 검색 인덱스 ${health.index_ready?'준비 완료':'갱신 중 또는 준비 미확인'}`;
      if(this.mode==='api')document.querySelector('.index-status p').textContent=health.index_ready?'서버 검색 인덱스 준비 완료':'데이터 갱신 중 또는 준비 미확인';
      if(health.active_job && this.base===this.bundledBase && !this.indexMonitor && !this.registration)this.monitorIndex(health.active_job);
    }catch(error){if(api===this.api)report.textContent=`미연결: ${error.message}`;}finally{button.disabled=false;}
  }
  async pollWorkspace(){
    if(this.mode!=='api' || this.base!==this.bundledBase || this.polling)return;
    this.polling=true;const api=this.api;
    try{
      const health=await api.health();if(api!==this.api)return;
      const watch=health.watch;
      if(watch)document.querySelector('#watch-status').textContent=watch.error || (watch.folders||[]).filter(folder=>folder.error).map(folder=>`${folder.path}: ${folder.error}`).join(' · ') || (watch.watching?'폴더 자동 감시 중':'자동 감시 중지');
      const job=health.active_job || health.last_job;
      if(job && job!==this.lastObservedJob && !this.indexMonitor && !this.registration)this.monitorIndex(job);
    }catch{}finally{this.polling=false;}
  }
  async renderFolders(){
    const api=this.api;
    try{
      const state=await api.folders();if(api!==this.api)return;
      const list=document.querySelector('#watch-folder-list');list.replaceChildren();
      for(const folder of state.folders || []){
        const row=node('div','workspace-actions');row.append(node('span','',folder.path+(folder.error?' · '+folder.error:'')));
        const button=node('button','outline-button','연결 해제');button.onclick=async()=>{button.disabled=true;try{await api.saveFolder({id:folder.id},true);await this.renderFolders();}catch(error){this.message(error.message);button.disabled=false;}};
        row.append(button);list.append(row);
      }
      document.querySelector('#watch-status').textContent=state.error || (state.folders||[]).filter(folder=>folder.error).map(folder=>`${folder.path}: ${folder.error}`).join(' · ') || (state.watching?'폴더 자동 감시 중':'자동 감시 중지');
    }catch(error){this.message(error.message);}
  }
  async resumeRefresh(){
    if(this.indexMonitor || this.registration)return;
    try{const health=await this.api.health();if(health.active_job)this.monitorIndex(health.active_job);}catch{}
  }
  async refreshIndex(){
    if(this.indexMonitor || this.registration){this.message('현재 등록·갱신 작업이 끝날 때까지 기다려 주세요.');return;}
    const button=document.querySelector('#refresh-index');button.disabled=true;
    try{const result=await this.api.refreshIndex();await this.monitorIndex(result.job_id);}
    catch(error){this.message(error.message);}finally{button.disabled=false;}
  }
  async monitorIndex(id){
    if(this.indexMonitor)return;
    this.indexMonitor=id;this.lastObservedJob=id;const api=this.api;const status=document.querySelector('#index-update-status');
    const button=document.querySelector('#refresh-index');button.disabled=true;
    try{
      for(let attempt=0;attempt<1800;attempt++){
        const job=await api.job(id);if(api!==this.api)return;
        status.textContent=job.phase||'갱신 중…';
        document.querySelector('.index-status p').textContent=status.textContent;
        if(job.status==='failed')throw Error(job.error||job.phase||'데이터 갱신 실패');
        if(job.status==='ready'){await this.refresh();this.message(['데이터·검색·관련 파일 갱신이 완료되었습니다.',...(job.warnings||[])].join(' '));await this.checkIntegration();return;}
        await new Promise(resolve=>setTimeout(resolve,1000));
      }
      status.textContent='서버 작업이 계속 진행 중입니다. 잠시 후 내 파일을 다시 여세요.';
    }catch(error){status.textContent=error.message;this.message(error.message);}
    finally{this.indexMonitor=null;button.disabled=false;}
  }
  async preview(file) {
    const dialog=document.querySelector('#file-preview-dialog');if(dialog.open)dialog.close();
    document.querySelector('#preview-title').textContent=file.name;const area=document.querySelector('#file-preview-content');area.replaceChildren(node('p','','파일을 불러오는 중입니다…'));dialog.showModal();const version=++this.previewVersion;
    try {
      const source=file.source||'demo';if(source==='demo')throw Error('예시 파일에는 실제 원본이 없습니다. 파일 등록에서 직접 보관한 파일을 열어보세요.');
      if(source==='api' && (this.mode!=='api' || (file.apiBase && file.apiBase!==this.base)))throw Error('API 모드로 전환한 뒤 다시 시도하세요.');
      const blob=source==='local'?await this.library.blob(file.id):await this.api.blob(file.id);
      if(version!==this.previewVersion || !dialog.open)return;
      area.replaceChildren();const ext=extension(file.name);
      if(['txt','csv','tsv','py','r','md','json','ipynb','html','css','js','sql'].includes(ext)){
        const pre=node('pre','code-preview',await blob.slice(0,300000).text());if(version!==this.previewVersion)return;area.append(node('p','preview-note','읽기 전용 텍스트 보기입니다. 코드를 실행하지 않습니다.'),pre);if(blob.size>300000)area.append(node('p','preview-note','큰 파일은 앞부분만 표시합니다.'));
      }else if(['png','jpg','jpeg','webp'].includes(ext)){this.objectUrl=URL.createObjectURL(blob);const image=node('img','image-preview');image.src=this.objectUrl;image.alt=file.name;image.onerror=()=>{if(version===this.previewVersion && dialog.open)area.replaceChildren(node('p','','이미지를 표시하지 못했습니다. 파일 형식과 내용을 확인하세요.'));};area.append(image);
      }else if(ext==='pdf'){
        if(source==='api' && this.base===this.bundledBase){
          const controls=node('div','workspace-actions');const previous=node('button','outline-button','이전 페이지');const next=node('button','outline-button','다음 페이지');const label=node('span','preview-note');const pages=node('div','pdf-pages');
          previous.type=next.type='button';area.append(node('p','preview-note','원본 PDF의 페이지를 표시합니다. 원본은 아래에서 다운로드할 수 있습니다.'),controls,pages);controls.append(previous,label,next);
          let page=1;
          const showPage=async(target)=>{
            previous.disabled=next.disabled=true;label.textContent='페이지를 불러오는 중입니다…';
            try{const result=await this.api.previewPdf(file.id,target);if(version!==this.previewVersion || !dialog.open)return;
              page=result.page;const image=node('img','pdf-page-image');image.alt=`${file.name} · ${page}페이지`;image.src='data:image/png;base64,'+result.image_base64;pages.replaceChildren(image);label.textContent=`${page} / ${result.page_count}페이지`;previous.disabled=page<=1;next.disabled=page>=result.page_count;
            }catch(error){if(version===this.previewVersion && dialog.open){pages.replaceChildren(node('p','preview-error',error.message));label.textContent='페이지 표시 실패';}}
          };
          previous.onclick=()=>showPage(page-1);next.onclick=()=>showPage(page+1);showPage(1);
        }else{
          this.objectUrl=URL.createObjectURL(new Blob([blob],{type:'application/pdf'}));const frame=node('iframe','pdf-preview');frame.title=file.name;frame.setAttribute('sandbox','');frame.src=this.objectUrl;area.append(node('p','preview-note','브라우저 PDF 미리보기입니다. 표시되지 않으면 아래 보관본 다운로드를 이용하세요.'),frame);
        }
      }else area.append(node('p','preview-note','이 형식은 브라우저 내부 미리보기를 지원하지 않습니다. 보관본을 다운로드해 연결 앱에서 확인하세요.'));
      const url=URL.createObjectURL(blob);const download=node('a','outline-button','보관본 다운로드');download.href=url;download.download=file.name;area.append(download);dialog.addEventListener('close',()=>URL.revokeObjectURL(url),{once:true});
    }catch(error){if(version===this.previewVersion && dialog.open)area.replaceChildren(node('p','preview-error',`${error.message} 파일 등록 상태와 연결을 확인하세요.`));}
  }
  async reveal(file){
    if(file.source==='api' && this.mode==='api' && (!file.apiBase || file.apiBase===this.base) && this.health?.capabilities?.reveal===true){try{await this.api.reveal(file.id);this.message('서버에 저장 폴더 열기를 요청했습니다.');}catch(error){this.message(error.message);}return;}
    this.message(`저장 위치: ${file.path || '경로 미제공'} · 브라우저는 PC 폴더를 직접 열 수 없습니다. 로컬 API의 reveal 기능이 연결되면 폴더 열기를 사용할 수 있습니다.`);
  }
  renderObservations(){document.querySelector('#usability-count').textContent=`실제 사용자 관찰 ${this.observations.filter(item=>item.kind==='study').length}건 · 개발 점검 ${this.observations.filter(item=>item.kind==='qa').length}건 · 사용자 평가 완료 여부는 시연 점검 문서에 별도로 기록하세요.`;document.querySelector('#export-usability').disabled=!this.observations.length;}
}
