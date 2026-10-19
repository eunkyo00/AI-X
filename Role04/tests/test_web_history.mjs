import test from 'node:test';
import assert from 'node:assert/strict';
import { HISTORY_KEY, loadHistory, normalizeHistory, recordQuery, saveHistory } from '../web/history.mjs';

function memoryStorage() {
  const data = new Map();
  return {
    getItem: key => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: key => data.delete(key),
  };
}

test('searches persist, deduplicate and retain only the newest eight', () => {
  const storage = memoryStorage();
  let entries = [];
  for (let index = 0; index < 12; index++) entries = recordQuery(entries, `질문 ${index}`, index);
  entries = recordQuery(entries, ' 질문 6 ', 20);
  assert.equal(entries.length, 8);
  assert.deepEqual(entries[0], { query: '질문 6', at: 20 });
  assert.equal(entries.filter(item => item.query === '질문 6').length, 1);
  assert.equal(saveHistory(storage, entries), true);
  assert.deepEqual(loadHistory(storage), entries);
});

test('malformed storage and invalid records do not break the home page', () => {
  const storage = memoryStorage();
  storage.setItem(HISTORY_KEY, '{not json');
  assert.deepEqual(loadHistory(storage), []);
  assert.deepEqual(normalizeHistory([
    null, { query: '  ', at: 1 }, { query: 'x', at: 'date' },
    { query: 'x'.repeat(1001), at: 1 }, { query: 'x', at: 1e30 },
    { query: ' <파일> ', at: 1 }, { query: '<파일>', at: 2 },
  ]), [{ query: '<파일>', at: 1 }]);
});

test('restricted storage still permits in-memory history and clearing touches only our key', () => {
  const blocked = { getItem() { throw Error(); }, setItem() { throw Error(); } };
  assert.deepEqual(loadHistory(blocked), []);
  assert.equal(saveHistory(blocked, [{ query: '질문', at: 1 }]), false);
  const storage = memoryStorage();
  storage.setItem('other-app', 'keep');
  saveHistory(storage, [{ query: '질문', at: 1 }]);
  saveHistory(storage, []);
  assert.deepEqual(loadHistory(storage), []);
  assert.equal(storage.getItem('other-app'), 'keep');
});
