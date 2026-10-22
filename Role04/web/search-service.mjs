import { files, relations, taskNames, mockSearch } from './search-data.mjs';

export const scenarios = {
  normal: { delay: 350 },
  empty: { delay: 350 },
  error: { delay: 350 },
  slow: { delay: 4000 },
};
function abortError() {
  const error = new Error('Search aborted');
  error.name = 'AbortError';
  return error;
}
function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(abortError()); return; }
    const onAbort = () => { clearTimeout(timer); reject(abortError()); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', onAbort); resolve(); }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/** Replace this class with an API adapter; keep search(query, options) unchanged. */
export class MockSearchService {
  async search(query, { scenario = 'normal', signal } = {}) {
    await wait((scenarios[scenario] || scenarios.normal).delay, signal);
    if (scenario === 'error') {
      const error = new Error('예시 검색 서비스에서 응답 오류가 발생했습니다.');
      error.code = 'MOCK_UNAVAILABLE';
      throw error;
    }
    return { files: (scenario === 'empty' ? [] : mockSearch(query)).map(file=>({...file,source:'demo'})), catalog:files.map(file=>({...file,source:'demo'})),relations,taskNames,source:'mock' };
  }
}

/** Own request lifetime separately from the DOM, including non-cooperative adapters. */
export class SearchController {
  constructor(service, onState, { timeoutMs = 10000 } = {}) {
    this.service = service;
    this.onState = onState;
    this.timeoutMs = timeoutMs;
    this.version = 0;
    this.pending = null;
  }
  cancel(reason = 'user') {
    const previous = this.pending;
    if (!previous) return;
    this.version++;
    this.pending = null;
    previous.controller.abort();
    this.onState({ status: 'cancelled', query: previous.query, reason });
  }
  async search(rawQuery, { scenario = 'normal' } = {}) {
    const query = rawQuery.trim();
    if (!query) return;
    // Invalidate first: the previous adapter may finish while ignoring abort.
    const version = ++this.version;
    this.pending?.controller.abort();
    const controller = new AbortController();
    this.pending = { controller, query };
    let timedOut = false;
    let onAbort;
    const aborted = new Promise((resolve, reject) => {
      onAbort = () => reject(abortError());
      controller.signal.addEventListener('abort', onAbort, { once: true });
    });
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    this.onState({ status: 'loading', query, scenario });
    try {
      const response = await Promise.race([
        this.service.search(query, { scenario, signal: controller.signal }), aborted,
      ]);
      if (version !== this.version) return;
      if (!response || !Array.isArray(response.files)) throw Error('Invalid search response');
      this.pending = null;
      this.onState({ ...response, status: 'success', query, scenario });
    } catch (error) {
      if (version !== this.version) return;
      this.pending = null;
      this.onState({ status: 'error', query, code: timedOut ? 'TIMEOUT' : 'SEARCH_FAILED' });
    } finally {
      clearTimeout(timeout);
      controller.signal.removeEventListener('abort', onAbort);
    }
  }
}
