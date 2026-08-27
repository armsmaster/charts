/**
 * Presets: design settings + period + timeframe, saved as a single JSON file.
 *
 * Self-contained on purpose - an uploaded watermark travels inside the file as
 * a data URI, so a preset can be emailed to a colleague and just work.
 */

export const PRESET_KIND = 'moex-charts-preset';
export const PRESET_VERSION = 1;

export function buildPreset({ selection, style }) {
  return {
    kind: PRESET_KIND,
    version: PRESET_VERSION,
    saved_at: new Date().toISOString(),
    selection,
    style,
  };
}

export function presetFilename(selection) {
  const parts = [
    selection.source === 'csv' ? 'csv' : selection.secid || 'moex',
    selection.period,
    new Date().toISOString().slice(0, 10),
  ].filter(Boolean);
  return `preset_${parts.join('_')}.json`.replace(/[^\w.-]+/g, '-');
}

export function download(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadJson(filename, data) {
  download(filename, new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
}

export async function readPreset(file) {
  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    throw new Error('Файл не является корректным JSON.');
  }
  if (!parsed || parsed.kind !== PRESET_KIND) {
    throw new Error('Это не файл пресета графиков MOEX.');
  }
  if (Number(parsed.version) > PRESET_VERSION) {
    throw new Error('Пресет сохранён более новой версией приложения.');
  }
  return { selection: parsed.selection || {}, style: parsed.style || {} };
}
