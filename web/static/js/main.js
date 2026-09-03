/**
 * Application wiring: connects the controls, the API and the Plotly canvas.
 */

import { api, ApiError } from './api.js';
import { InstrumentPicker } from './instrument-picker.js';
import { buildPreset, download, downloadJson, presetFilename, readPreset } from './presets.js';
import { StyleForm } from './style-form.js';
import { TitleEditor } from './title-editor.js';

const $ = (id) => document.getElementById(id);

const dom = {
  tabs: document.querySelectorAll('.tab'),
  panes: document.querySelectorAll('[data-source-pane]'),
  secid: $('secid'),
  secidResults: $('secid-results'),
  secidStatus: $('secid-status'),
  board: $('board'),
  interval: $('interval'),
  period: $('period'),
  csvFile: $('csv-file'),
  csvStatus: $('csv-status'),
  csvTicker: $('csv-ticker'),
  csvName: $('csv-name'),
  load: $('load'),
  loadStatus: $('load-status'),
  titleCard: $('title-card'),
  styleForm: $('style-form'),
  render: $('render'),
  download: $('download'),
  stageInfo: $('stage-info'),
  chart: $('chart'),
  placeholder: $('placeholder'),
  toast: $('toast'),
  presetSave: $('preset-save'),
  presetLoad: $('preset-load'),
  styleReset: $('style-reset'),
};

const state = {
  source: 'moex',
  series: null,
  capabilities: { server_png: false },
  rendered: false,
  loadToken: 0,
};

const styleForm = new StyleForm(dom.styleForm, () => scheduleRender());
const titleEditor = new TitleEditor({
  root: dom.titleCard,
  styleForm,
  getSeries: () => state.series,
  onChange: () => scheduleRender(),
});
const picker = new InstrumentPicker({
  input: dom.secid,
  list: dom.secidResults,
  status: dom.secidStatus,
  boardSelect: dom.board,
  onResolved: () => refreshLoadButton(),
});

let renderTimer = null;

// ---------------------------------------------------------------- utilities

function toast(message, kind = '') {
  dom.toast.textContent = message;
  dom.toast.className = `toast ${kind}`.trim();
  dom.toast.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    dom.toast.hidden = true;
  }, 6000);
}

function setLoadStatus(text, kind = '') {
  dom.loadStatus.textContent = text;
  dom.loadStatus.className = `load-status ${kind}`.trim();
}

function describeError(error) {
  return error instanceof ApiError || error instanceof Error ? error.message : String(error);
}

async function withBusy(button, task) {
  const previous = button.textContent;
  button.disabled = true;
  document.body.classList.add('is-busy');
  try {
    return await task();
  } finally {
    button.textContent = previous;
    button.disabled = false;
    document.body.classList.remove('is-busy');
  }
}

function fillSelect(select, items, { value, label }) {
  const previous = select.value;
  select.textContent = '';
  items.forEach((item) => {
    const option = document.createElement('option');
    option.value = item[value];
    option.textContent = item[label];
    select.appendChild(option);
  });
  if (previous && items.some((item) => String(item[value]) === previous)) select.value = previous;
}

// ------------------------------------------------------------------ startup

async function boot() {
  try {
    const [intervals, capabilities] = await Promise.all([
      api.intervals(),
      api.capabilities(),
      styleForm.init(),
    ]);
    await titleEditor.init();
    state.capabilities = capabilities;
    fillSelect(dom.interval, intervals, { value: 'code', label: 'title' });
    dom.interval.value = intervals.some((i) => i.code === 60) ? '60' : String(intervals[0].code);
    await loadPeriods();
    dom.csvStatus.textContent = `Обязательные колонки: ${capabilities.required_csv_columns.join(', ')}`;
  } catch (error) {
    toast(`Не удалось загрузить справочники: ${describeError(error)}`, 'is-error');
  }
  refreshLoadButton();
}

async function loadPeriods() {
  const periods = await api.periods(state.source);
  const previous = dom.period.value;
  fillSelect(dom.period, periods, { value: 'code', label: 'title' });
  const fallback = state.source === 'csv' ? 'full' : '3m';
  dom.period.value = periods.some((p) => p.code === previous) ? previous : fallback;
}

// ------------------------------------------------------------------- source

function selectSource(source) {
  state.source = source;
  dom.tabs.forEach((tab) => tab.classList.toggle('is-active', tab.dataset.source === source));
  dom.panes.forEach((pane) => {
    pane.hidden = pane.dataset.sourcePane !== source;
  });
  loadPeriods().catch((error) => toast(describeError(error), 'is-error'));
  refreshLoadButton();
}

function refreshLoadButton() {
  dom.load.disabled = !canLoad();
}

// --------------------------------------------------------------------- data

async function loadSeries() {
  // Changing the timeframe and the period in quick succession fires two loads;
  // without a token the slower (stale) answer can overwrite the fresh one.
  const token = ++state.loadToken;
  await withBusy(dom.load, async () => {
    dom.load.textContent = 'Загружаем…';
    setLoadStatus('Загружаем…');
    try {
      const response =
        state.source === 'moex'
          ? await loadFromMoex()
          : await api.csvSeries({
              file: dom.csvFile.files[0],
              period: dom.period.value,
              ticker: dom.csvTicker.value,
              name: dom.csvName.value,
            });
      if (token !== state.loadToken) return;

      state.series = response.series;
      const { count, from, till } = response.stats;
      setLoadStatus(
        `Загружено ${count} свечей: ${from.slice(0, 16).replace('T', ' ')} — ${till
          .slice(0, 16)
          .replace('T', ' ')}`,
        'is-ok',
      );
      if (response.warnings.length) setLoadStatus(response.warnings.join(' '), 'is-warn');
      updateStageInfo(response);
      dom.render.disabled = false;
      dom.download.disabled = false;
      await renderChart();
    } catch (error) {
      if (token !== state.loadToken) return;
      state.series = null;
      dom.render.disabled = true;
      dom.download.disabled = true;
      setLoadStatus(describeError(error), 'is-error');
    } finally {
      if (token === state.loadToken) refreshLoadButton();
    }
  });
}

/** True when the current source has everything it needs to fetch data. */
function canLoad() {
  return state.source === 'moex'
    ? Boolean(picker.instrument)
    : Boolean(dom.csvFile.files && dom.csvFile.files[0]);
}

/**
 * Re-fetch after a selection change. Deliberately independent of whether the
 * previous attempt succeeded: picking a smaller period is exactly how a user
 * recovers from "this range is too large".
 */
function reloadIfPossible() {
  if (canLoad()) loadSeries();
}

async function loadFromMoex() {
  const instrument = picker.instrument || (await picker.validate());
  if (!instrument) throw new Error('Выберите существующий инструмент MOEX.');
  return api.moexSeries({
    secid: instrument.secid,
    interval: Number(dom.interval.value),
    period: dom.period.value,
    board: dom.board.value || undefined,
  });
}

function updateStageInfo(response) {
  const series = response.series;
  const bits = [
    series.ticker || 'CSV',
    series.interval_title,
    series.period_title,
    `${series.candles.length} свечей`,
  ].filter(Boolean);
  dom.stageInfo.innerHTML = '';
  const strong = document.createElement('b');
  strong.textContent = bits.shift();
  dom.stageInfo.append(strong, document.createTextNode(` · ${bits.join(' · ')}`));
}

// ------------------------------------------------------------------ drawing

function scheduleRender() {
  if (!state.series || !state.rendered) return;
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => renderChart(), 120);
}

async function renderChart() {
  if (!state.series) return;
  try {
    const figure = await api.figure(state.series, styleForm.getStyle());
    dom.placeholder.hidden = true;
    // newPlot rather than react: Plotly omits empty collections (images,
    // annotations) from the spec, and a full replace is what reliably clears a
    // watermark or note the user has just switched off.
    await Plotly.newPlot(dom.chart, figure.data, figure.layout, {
      // Russian month/day names on the datetime axis; dictionary registered by
      // /api/vendor/plotly-locale-ru.js, loaded before this module.
      locale: 'ru',
      displaylogo: false,
      responsive: false,
      scrollZoom: true,
      modeBarButtonsToRemove: ['toImage', 'select2d', 'lasso2d'],
    });
    state.rendered = true;
    titleEditor.refreshPreview();
  } catch (error) {
    toast(`Не удалось построить график: ${describeError(error)}`, 'is-error');
  }
}

async function downloadPng() {
  await withBusy(dom.download, async () => {
    dom.download.textContent = 'Готовим PNG…';
    const style = styleForm.getStyle();
    try {
      if (state.capabilities.server_png) {
        const { blob, filename } = await api.png(state.series, style);
        download(filename, blob);
      } else {
        await downloadPngInBrowser(style);
      }
      toast('PNG сохранён.', 'is-ok');
    } catch (error) {
      // Server-side export can be unavailable in a trimmed container; the
      // browser can always rasterise the very same figure itself.
      try {
        await downloadPngInBrowser(style);
        toast('PNG сохранён (рендер в браузере).', 'is-ok');
      } catch {
        toast(`Не удалось сохранить PNG: ${describeError(error)}`, 'is-error');
      }
    }
  });
}

async function downloadPngInBrowser(style) {
  if (!state.rendered) await renderChart();
  await Plotly.downloadImage(dom.chart, {
    format: 'png',
    width: style.canvas.width,
    height: style.canvas.height,
    scale: style.canvas.scale,
    filename: `${state.series.ticker || 'chart'}_${state.series.period_code || ''}`.replace(/_$/, ''),
  });
}

// ------------------------------------------------------------------ presets

function currentSelection() {
  return {
    source: state.source,
    secid: picker.instrument ? picker.instrument.secid : dom.secid.value.trim().toUpperCase(),
    board: dom.board.value || '',
    interval: Number(dom.interval.value) || null,
    period: dom.period.value,
    csv_ticker: dom.csvTicker.value,
    csv_name: dom.csvName.value,
  };
}

async function applyPreset(file) {
  try {
    const { selection, style } = await readPreset(file);
    styleForm.setStyle(style);
    titleEditor.sync();
    if (selection.source) selectSource(selection.source);
    await loadPeriods();
    if (selection.period) dom.period.value = selection.period;
    if (selection.interval) dom.interval.value = String(selection.interval);
    if (selection.board !== undefined) dom.board.value = selection.board || '';
    if (selection.csv_ticker) dom.csvTicker.value = selection.csv_ticker;
    if (selection.csv_name) dom.csvName.value = selection.csv_name;
    if (selection.secid && selection.source !== 'csv') {
      picker.setValue(selection.secid);
      await picker.validate();
    }
    refreshLoadButton();
    if (state.series) await renderChart();
    toast('Пресет загружен.', 'is-ok');
  } catch (error) {
    toast(describeError(error), 'is-error');
  } finally {
    dom.presetLoad.value = '';
  }
}

// -------------------------------------------------------------------- events

dom.tabs.forEach((tab) => tab.addEventListener('click', () => selectSource(tab.dataset.source)));
dom.csvFile.addEventListener('change', refreshLoadButton);
dom.load.addEventListener('click', loadSeries);
dom.render.addEventListener('click', renderChart);
dom.download.addEventListener('click', downloadPng);
dom.period.addEventListener('change', reloadIfPossible);
dom.interval.addEventListener('change', () => {
  if (state.source === 'moex') reloadIfPossible();
});

dom.presetSave.addEventListener('click', () => {
  const selection = currentSelection();
  downloadJson(presetFilename(selection), buildPreset({ selection, style: styleForm.getStyle() }));
});
dom.presetLoad.addEventListener('change', () => {
  const file = dom.presetLoad.files && dom.presetLoad.files[0];
  if (file) applyPreset(file);
});
dom.styleReset.addEventListener('click', () => {
  styleForm.reset();
  titleEditor.sync();
  scheduleRender();
});
dom.styleForm.addEventListener('style-error', (event) => toast(event.detail, 'is-error'));

boot();
