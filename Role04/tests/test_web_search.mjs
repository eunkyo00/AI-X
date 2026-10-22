import test from 'node:test';
import assert from 'node:assert/strict';
import { files, relations, mockSearch, filterResults, getRelated } from '../web/search-data.mjs';

test('representative queries select distinct fixture tasks and role ordering', () => {
  const r = mockSearch('지난달 R 과제할 때 사용했던 데이터');
  assert.equal(r[0].id, 'r-data');
  assert.ok(r.every(file => file.task === 'r'));
  assert.equal(mockSearch('Python 실습 코드와 결과 파일')[0].id, 'py-code');
  assert.equal(mockSearch('딥러닝 발표 PPT 찾아줘')[0].id, 'p-slides');
  assert.equal(mockSearch('작년에 읽었던 강화학습 논문')[0].id, 'p-paper');
  assert.deepEqual(mockSearch('관련 없는 축구 일정'), []);
  assert.deepEqual(mockSearch('   '), []);
});

test('type and period filters combine, empty sets are supported, sorting keeps original ranks', () => {
  const source = mockSearch('R 과제 데이터');
  const copy = source.map(file => file.id);
  assert.deepEqual(filterResults(source, {type: 'code', period: '2026-10'}).map(file => file.id), ['r-code']);
  assert.deepEqual(filterResults(source, {type: 'presentation'}), []);
  assert.deepEqual(filterResults(source, {period: '2025'}), []);
  assert.equal(filterResults(source, {sort: 'date'})[0].id, 'r-report');
  const dateSorted = filterResults(source, {sort: 'date'});
  assert.equal(filterResults(dateSorted)[0].id, 'r-data');
  assert.deepEqual(source.map(file => file.id), copy);
  assert.deepEqual(filterResults([{id:'earlier',modified:'2026-10-19T10:00:00+09:00',rank:1},{id:'later',modified:'2026-10-19T03:00:00Z',rank:2},{id:'unknown',modified:'',rank:3}],{sort:'date'}).map(file=>file.id),['later','earlier','unknown']);
});

test('all relationships resolve, preserve evidence certainty, and only include direct neighbors', () => {
  const ids = new Set(files.map(file => file.id));
  assert.equal(ids.size, files.length);
  for (const link of relations) {
    assert.ok(ids.has(link.from) && ids.has(link.to));
    assert.ok(['confirmed', 'inferred'].includes(link.certainty));
  }
  const related = getRelated('r-data');
  assert.deepEqual(related.map(item => item.file.id), ['r-code', 'r-guide']);
  assert.ok(!related.some(item => item.file.id === 'r-plot'));
  assert.deepEqual(getRelated('missing'), []);
  assert.equal(getRelated('r-code').find(item => item.file.id === 'r-plot').relation.certainty, 'confirmed');
});
