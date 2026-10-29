/** Service contracts and browser-local storage. No semantic search is fabricated. */
export const SUPPORTED = new Set(['pdf','csv','pptx','txt','py','r','png','jpg','jpeg','webp','docx','md','json','ipynb']);
export const MAX_FILE_SIZE = 25 * 1024 * 1024;
export function extension(name) { return String(name).split('.').pop().toLowerCase(); }
export function fileType(name) {
  const ext = extension(name);
  return ['csv','json'].includes(ext) ? 'data' : ['py','r','ipynb'].includes(ext) ? 'code' : ['png','jpg','jpeg','webp'].includes(ext) ? 'image' : ext === 'pptx' ? 'presentation' : 'document';
}
export function validateFile(file) {
  if (!SUPPORTED.has(extension(file.name))) return '지원하지 않는 파일 형식입니다.';
  if (file.size > MAX_FILE_SIZE) return '파일당 25MB까지 보관할 수 있습니다.';
  return null;
}
export function validateBaseUrl(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw Error('인증정보·쿼리·해시 없는 HTTP(S) API 주소를 입력하세요.');
  return url.href.replace(/\/$/, '');
}
const text = (value, fallback = '') => typeof value === 'string' ? value : fallback;
export function normalizeFile(raw, index = 0, source = 'api') {
  if (!raw || typeof raw !== 'object') throw Error('파일 응답이 올바르지 않습니다.');
  const id = text(raw.file_id || raw.id);
  const name = text(raw.name);
  if (!id || !name) throw Error('파일 ID 또는 파일명이 없습니다.');
  return {
    id, name, source, apiBase:text(raw.apiBase), type: ['document','data','code','image','presentation'].includes(raw.type) ? raw.type : fileType(name),
    path: text(raw.path, name), role: text(raw.role, '알 수 없음'), modified: text(raw.modified || raw.modified_at),
    size: typeof raw.size === 'number' ? formatSize(raw.size) : text(raw.size, '알 수 없음'),
    task: text(raw.task_id || raw.task) || null, taskName: text(raw.task_name),
    rank: Number.isFinite(raw.rank) && raw.rank > 0 ? raw.rank : index + 1,
    contentAvailable: typeof (raw.content_available ?? raw.contentAvailable)==='boolean' ? (raw.content_available ?? raw.contentAvailable) : null,
    relationsAvailable: typeof (raw.relations_available ?? raw.relationsAvailable)==='boolean' ? (raw.relations_available ?? raw.relationsAvailable) : null,
    score: Number.isFinite(raw.score) ? raw.score : null, excerpt: text(raw.excerpt),
    summary: text(raw.summary, '제공된 요약이 없습니다.'),
    evidence: Array.isArray(raw.evidence) ? raw.evidence.filter(item => item && typeof item.text === 'string').map(item => ({text: item.text, certainty: ['confirmed','inferred'].includes(item.certainty) ? item.certainty : 'unknown'})) : [],
    indexStatus: text(raw.index_status, 'unknown'),
  };
}
export function normalizeResponse(raw, source = 'api') {
  if (!raw || !Array.isArray(raw.files)) throw Error('files 배열이 필요합니다.');
  const resultFiles = raw.files.map((file, index) => normalizeFile({...file,rank:index+1}, index, source));
  if(raw.catalog !== undefined && !Array.isArray(raw.catalog))throw Error('catalog는 배열이어야 합니다.');
  const catalog = [...resultFiles];
  const ids = new Set(catalog.map(file => file.id));
  if (ids.size !== resultFiles.length) throw Error('중복된 파일 ID가 반환되었습니다.');
  for (const item of raw.catalog || []) {
    const file = normalizeFile(item, catalog.length, source);
    if (!ids.has(file.id)) { catalog.push(file); ids.add(file.id); }
  }
  const relations = (Array.isArray(raw.relations) ? raw.relations : []).filter(link => link && ids.has(link.source_file_id || link.from) && ids.has(link.target_file_id || link.to)).map(link => ({
    from: link.source_file_id || link.from, to: link.target_file_id || link.to,
    label: text(link.label || link.relation_type, '관계 정보 없음'), certainty: ['confirmed','inferred'].includes(link.certainty) ? link.certainty : 'unknown',
  }));
  const taskNames = {};
  for (const file of catalog) if (file.task && file.taskName) taskNames[file.task] = file.taskName;
  return {files: resultFiles, catalog, relations, taskNames, source};
}
export function formatSize(bytes) { return bytes >= 1024 * 1024 ? `${(bytes/1024/1024).toFixed(1)} MB` : `${(bytes/1024).toFixed(1)} KB`; }

export class BrowserLibrary {
  constructor(indexedDB = globalThis.indexedDB, name = 'context-search-library-v1') { this.indexedDB = indexedDB; this.name = name; }
  async db() {
    if (this.connection) return this.connection;
    if (!this.indexedDB) throw Error('이 브라우저에서 로컬 파일 보관을 사용할 수 없습니다.');
    this.connection = await new Promise((resolve,reject) => {
      const request = this.indexedDB.open(this.name,1);
      request.onupgradeneeded = () => {
        const store = request.result.createObjectStore('files',{keyPath:'id'});
        store.createIndex('fingerprint','fingerprint',{unique:true});
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(Error('브라우저 저장소를 열지 못했습니다.'));
      request.onblocked = () => reject(Error('다른 탭을 닫고 다시 시도하세요.'));
    });
    this.connection.onversionchange = () => { this.connection.close(); this.connection = null; };
    return this.connection;
  }
  async transaction(mode, action) {
    const db = await this.db();
    return new Promise((resolve,reject) => {
      const transaction = db.transaction('files',mode);
      const request = action(transaction.objectStore('files'));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onabort = () => reject(Error(request.error?.name === 'ConstraintError' ? 'DUPLICATE' : '파일 저장에 실패했습니다. 저장 공간과 브라우저 권한을 확인하세요.'));
      transaction.onerror = () => {};
    });
  }
  async list() {
    const records = await this.transaction('readonly',store=>store.getAll());
    return records.map(({blob,fingerprint,...file})=>file);
  }
  async add(file) {
    const reason = validateFile(file);
    if (reason) throw Error(reason);
    const path = file.webkitRelativePath || file.name;
    const fingerprint = `${path}\u0000${file.size}\u0000${file.lastModified}`;
    const metadata = normalizeFile({file_id:crypto.randomUUID(),name:file.name,path,size:file.size,modified:new Date(file.lastModified).toISOString().slice(0,10),index_status:'stored',summary:'브라우저에 보관한 파일입니다. 이름·경로로 찾을 수 있으며 AI 내용 검색은 아직 연결되지 않았습니다.'},0,'local');
    await this.transaction('readwrite',store=>store.add({...metadata,fingerprint,blob:file}));
    return metadata;
  }
  async blob(id) {
    const record = await this.transaction('readonly',store=>store.get(id));
    if (!record) throw Error('보관한 파일을 찾을 수 없습니다. 파일을 다시 등록하세요.');
    return record.blob;
  }
  async search(query) {
    const catalog = await this.list();
    const words = query.toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const files = catalog.filter(file => words.every(word=>`${file.name} ${file.path}`.toLocaleLowerCase().includes(word))).map((file,index)=>({...file,rank:index+1}));
    return {files,catalog,relations:[],taskNames:{},source:'local'};
  }
}

export class ApiWorkspace {
  constructor(base, fetcher = globalThis.fetch?.bind(globalThis)) { this.base = validateBaseUrl(base); this.fetcher = fetcher; }
  async request(path, {signal, timeoutMs=10000, blob=false, ...options}={}) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal?.aborted) controller.abort();
    else signal?.addEventListener('abort',abort,{once:true});
    const timer = setTimeout(abort,timeoutMs);
    try {
      const response = await this.fetcher(`${this.base}${path}`, {...options,signal:controller.signal,credentials:'omit',redirect:'error'});
      if (!response.ok) {
        let message;
        try {const body=await response.json();if(typeof body.error==='string')message=body.error;}catch{}
        throw Error(message || (response.status === 404 ? '파일 또는 API 경로를 찾지 못했습니다.' : `서버 요청 실패 (${response.status})`));
      }
      return blob ? await response.blob() : await response.json();
    } catch(error) {
      if (controller.signal.aborted) {
        if (signal?.aborted) throw error;
        throw Error('서버 응답 시간이 초과되었습니다. 연결 주소와 서버 상태를 확인하세요.');
      }
      if(error instanceof TypeError)throw Error('API 서버에 연결하지 못했습니다. 서버 실행과 CORS 설정을 확인하세요.');
      if(error instanceof SyntaxError)throw Error('서버 JSON 응답 형식이 올바르지 않습니다.');
      throw error;
    } finally {clearTimeout(timer); signal?.removeEventListener('abort',abort);}
  }
  async health() {
    const raw = await this.request('/health');
    if (!raw || raw.status !== 'ok' || raw.contract_version !== 'gui-v1') throw Error('서버 상태 또는 gui-v1 계약 버전을 확인하세요.');
    return raw;
  }
  async search(query,{signal}={}) {
    const raw = await this.request('/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,request_id:crypto.randomUUID()}),signal});
    const response = normalizeResponse(raw);
    for(const file of response.catalog)file.apiBase=this.base;
    return response;
  }
  async list() { return normalizeResponse(await this.request('/files')).files.map(file=>({...file,apiBase:this.base})); }
  async add(file,{signal}={}) {
    const reason = validateFile(file); if (reason) throw Error(reason);
    const form = new FormData(); form.append('file',file); form.append('relative_path',file.webkitRelativePath || file.name);
    const response = await this.request('/files',{method:'POST',body:form,signal,timeoutMs:60000});
    return {file:{...normalizeFile(response.file),apiBase:this.base}, jobId:typeof response.job_id === 'string' ? response.job_id : null, duplicate:response.duplicate===true};
  }
  async job(id,{signal}={}) { return this.request(`/jobs/${encodeURIComponent(id)}`,{signal}); }
  async previewPdf(id,page=1) { return this.request(`/files/${encodeURIComponent(id)}/preview?page=${page}`); }
  async blob(id) { return this.request(`/files/${encodeURIComponent(id)}/content`,{blob:true}); }
  async reveal(id) { return this.request(`/files/${encodeURIComponent(id)}/reveal`,{method:'POST'}); }
}
