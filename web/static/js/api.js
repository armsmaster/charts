/**
 * Thin wrapper over the REST API. The only module that knows about URLs.
 */

const BASE = '/api';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function unwrap(response) {
  if (response.ok) return response;
  let detail = `HTTP ${response.status}`;
  try {
    const body = await response.json();
    if (body && body.detail) {
      detail = Array.isArray(body.detail)
        ? body.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
        : body.detail;
    }
  } catch {
    /* non-JSON error body - keep the status line */
  }
  throw new ApiError(detail, response.status);
}

async function getJson(path, params) {
  const url = new URL(BASE + path, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  });
  const response = await unwrap(await fetch(url, { headers: { Accept: 'application/json' } }));
  return response.json();
}

async function postJson(path, payload) {
  const response = await unwrap(
    await fetch(BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  );
  return response.json();
}

async function postForm(path, form) {
  const response = await unwrap(await fetch(BASE + path, { method: 'POST', body: form }));
  return response.json();
}

export const api = {
  intervals: () => getJson('/meta/intervals'),
  periods: (source) => getJson('/meta/periods', { source }),
  titlePlaceholders: () => getJson('/meta/title-placeholders'),
  styleSchema: () => getJson('/meta/style-schema'),
  styleDefaults: () => getJson('/meta/style-defaults'),
  capabilities: () => getJson('/meta/capabilities'),

  searchInstruments: (q, limit = 12) => getJson('/instruments/search', { q, limit }),
  resolveInstrument: (secid, board) => getJson(`/instruments/${encodeURIComponent(secid)}`, { board }),
  instrumentBoards: (secid) => getJson(`/instruments/${encodeURIComponent(secid)}/boards`),

  moexSeries: ({ secid, interval, period, board }) =>
    getJson('/series/moex', { secid, interval, period, board }),

  csvSeries: ({ file, period, ticker, name }) => {
    const form = new FormData();
    form.append('file', file);
    form.append('period', period);
    form.append('ticker', ticker || '');
    form.append('name', name || '');
    return postForm('/series/csv', form);
  },

  figure: (series, style) => postJson('/charts/figure', { series, style }),
  title: (series, style) => postJson('/charts/title', { series, style }),

  uploadWatermark: (file) => {
    const form = new FormData();
    form.append('file', file);
    return postForm('/charts/watermark', form);
  },

  async png(series, style) {
    const response = await unwrap(
      await fetch(`${BASE}/charts/png`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ series, style }),
      }),
    );
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = /filename="([^"]+)"/.exec(disposition);
    return { blob: await response.blob(), filename: match ? match[1] : 'chart.png' };
  },
};
