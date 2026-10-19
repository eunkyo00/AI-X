/** Browser-local query history; storage failures never prevent a search. */
export const HISTORY_KEY = 'context-search.history.v1';
export const HISTORY_LIMIT = 8;

export function normalizeHistory(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  return value.filter(item => {
    if (!item || typeof item.query !== 'string' || typeof item.at !== 'number') return false;
    const query = item.query.trim();
    if (!query || query.length > 1000 || !Number.isFinite(item.at) || item.at < 0 || item.at > 8.64e15) return false;
    if (seen.has(query)) return false;
    seen.add(query);
    return true;
  }).slice(0, HISTORY_LIMIT).map(item => ({ query: item.query.trim(), at: item.at }));
}

export function loadHistory(storage) {
  try { return normalizeHistory(JSON.parse(storage.getItem(HISTORY_KEY) || '[]')); }
  catch { return []; }
}

export function saveHistory(storage, entries) {
  try {
    if (entries.length) storage.setItem(HISTORY_KEY, JSON.stringify(normalizeHistory(entries)));
    else storage.removeItem(HISTORY_KEY);
    return true;
  } catch { return false; }
}

export function recordQuery(entries, rawQuery, at = Date.now()) {
  const query = rawQuery.trim();
  return normalizeHistory([{ query, at }, ...entries.filter(item => item.query !== query)]);
}
