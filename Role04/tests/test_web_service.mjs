import test from 'node:test';
import assert from 'node:assert/strict';
import { MockSearchService, SearchController } from '../web/search-service.mjs';

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
const response = id => ({ files: [{id}], source: 'test' });

test('mock adapter returns normal and empty responses, and rejects simulated errors', async () => {
  const service = new MockSearchService();
  const [normal, empty] = await Promise.all([
    service.search('R 과제'), service.search('R 과제', {scenario: 'empty'}),
  ]);
  assert.equal(normal.files[0].id, 'r-data');
  assert.deepEqual(empty.files, []);
  await assert.rejects(service.search('R 과제', {scenario: 'error'}), {code: 'MOCK_UNAVAILABLE'});
  const abort = new AbortController();
  const slow = service.search('R 과제', {scenario: 'slow', signal: abort.signal});
  abort.abort();
  await assert.rejects(slow, {name: 'AbortError'});
});

test('late completion of an adapter that ignores abort cannot overwrite the newest query', async () => {
  const old = deferred(), latest = deferred();
  const states = [];
  const controller = new SearchController({search: query => query === 'old' ? old.promise : latest.promise}, state => states.push(state));
  const first = controller.search('old');
  const second = controller.search('new');
  latest.resolve(response('new'));
  await second;
  old.resolve(response('old'));
  await first;
  assert.deepEqual(states.map(state => [state.status, state.query]), [
    ['loading', 'old'], ['loading', 'new'], ['success', 'new'],
  ]);
});

test('late failure from superseded request does not replace a successful result', async () => {
  const old = deferred();
  const states = [];
  const controller = new SearchController({search: query => query === 'old' ? old.promise : Promise.resolve(response('new'))}, state => states.push(state));
  const first = controller.search('old');
  await controller.search('new');
  old.reject(Error('late error'));
  await first;
  assert.equal(states.at(-1).status, 'success');
  assert.equal(states.at(-1).query, 'new');
});

test('cancel and navigation clear pending work, without publishing its eventual result', async () => {
  for (const reason of ['user', 'navigation']) {
    const pending = deferred(), states = [];
    let signal;
    const controller = new SearchController({search(query, options) { signal = options.signal; return pending.promise; }}, state => states.push(state));
    const work = controller.search('R 과제');
    controller.cancel(reason);
    assert.equal(signal.aborted, true);
    pending.resolve(response('old'));
    await work;
    assert.equal(states.at(-1).status, 'cancelled');
    assert.equal(states.at(-1).reason, reason);
    assert.equal(controller.pending, null);
  }
});

test('timeout stops a hung adapter and retry can recover with a fresh request', async () => {
  const states = [];
  let hangs = true;
  const service = {search: () => hangs ? new Promise(() => {}) : Promise.resolve(response('recovered'))};
  const controller = new SearchController(service, state => states.push(state), {timeoutMs: 10});
  await controller.search('R 과제');
  assert.equal(states.at(-1).code, 'TIMEOUT');
  assert.equal(controller.pending, null);
  hangs = false;
  await controller.search('R 과제');
  assert.equal(states.at(-1).status, 'success');
  assert.equal(states.at(-1).files[0].id, 'recovered');
});

test('error and invalid responses publish recoverable failure; whitespace starts no request', async () => {
  const states = [];
  const controller = new SearchController({search: async () => ({files: null})}, state => states.push(state));
  await controller.search('  ');
  assert.equal(states.length, 0);
  await controller.search('R 과제');
  assert.equal(states.at(-1).code, 'SEARCH_FAILED');
});
