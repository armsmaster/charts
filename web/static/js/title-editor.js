/**
 * The chart title card.
 *
 * The title is the one setting analysts touch on every chart, so it gets its
 * own editor at the top of the panel instead of a row buried in the design
 * accordion: one field that edits either the template or a literal text,
 * one-click placeholder chips, bold/italic buttons instead of typed tags, and
 * a live preview rendered the way Plotly will draw it.
 *
 * The values still live in ChartStyle (`title.visible/mode/template/text`) and
 * are saved in presets like everything else - those fields are simply flagged
 * `hidden` so the generic panel does not offer them a second time.
 */

import { api } from './api.js';

/** Inline tags Plotly renders in titles - anything else is shown as text. */
const ALLOWED_TAGS = new Set(['B', 'STRONG', 'I', 'EM', 'SUB', 'SUP', 'BR', 'SPAN']);

export class TitleEditor {
  /**
   * @param {{root: HTMLElement, styleForm: import('./style-form.js').StyleForm,
   *          getSeries: () => object|null, onChange: () => void}} options
   */
  constructor({ root, styleForm, getSeries, onChange }) {
    this.root = root;
    this.styleForm = styleForm;
    this.getSeries = getSeries;
    this.onChange = onChange || (() => {});
    this.placeholders = [];

    this.visible = root.querySelector('#title-visible');
    this.modeButtons = [...root.querySelectorAll('[data-title-mode]')];
    this.input = root.querySelector('#title-input');
    this.chips = root.querySelector('#title-chips');
    this.preview = root.querySelector('#title-preview');
    this.hint = root.querySelector('#title-hint');
    this.fromTemplate = root.querySelector('#title-from-template');
    this.reset = root.querySelector('#title-reset');

    this._previewToken = 0;
    this._bind();
  }

  async init() {
    try {
      this.placeholders = await api.titlePlaceholders();
    } catch {
      this.placeholders = [];
    }
    this.renderChips();
    this.sync();
  }

  get mode() {
    return this.styleForm.getValue('title.mode') === 'manual' ? 'manual' : 'auto';
  }

  get valuePath() {
    return this.mode === 'manual' ? 'title.text' : 'title.template';
  }

  // ------------------------------------------------------------------ wiring

  _bind() {
    this.visible.addEventListener('change', () => {
      this.styleForm.setValue('title.visible', this.visible.checked);
      this.root.classList.toggle('is-off', !this.visible.checked);
    });

    this.modeButtons.forEach((button) =>
      button.addEventListener('click', () => this.setMode(button.dataset.titleMode)),
    );

    const commit = () => {
      this.styleForm.setValue(this.valuePath, this.input.value);
      this.refreshPreview();
    };
    this.input.addEventListener('input', commit);
    this.input.addEventListener('change', commit);

    this.root.querySelectorAll('[data-wrap]').forEach((button) =>
      button.addEventListener('click', () => this.wrapSelection(button.dataset.wrap)),
    );
    this.root.querySelectorAll('[data-insert]').forEach((button) =>
      button.addEventListener('click', () => this.insert(button.dataset.insert)),
    );
    this.root.querySelector('#title-strip').addEventListener('click', () => {
      this.input.value = this.input.value.replace(/<\/?[a-z][^>]*>/gi, '');
      commit();
    });

    this.fromTemplate.addEventListener('click', () => {
      this.input.value = this.preview.dataset.plain || this.input.value;
      commit();
      this.input.focus();
    });

    this.reset.addEventListener('click', () => {
      this.input.value = this.styleForm.defaultValue(this.valuePath) ?? '';
      commit();
    });
  }

  setMode(mode) {
    const next = mode === 'manual' ? 'manual' : 'auto';
    // Switching to "my own text" for the first time hands the user the
    // suggested title to edit rather than an empty box.
    if (next === 'manual' && !this.styleForm.getValue('title.text')) {
      this.styleForm.setValue('title.text', this.preview.dataset.plain || this.input.value);
    }
    this.styleForm.setValue('title.mode', next);
    this.sync();
  }

  /** Reflect the current style values into the controls (also after a preset). */
  sync() {
    const mode = this.mode;
    this.visible.checked = this.styleForm.getValue('title.visible') !== false;
    this.root.classList.toggle('is-off', !this.visible.checked);
    this.modeButtons.forEach((button) =>
      button.classList.toggle('is-active', button.dataset.titleMode === mode),
    );
    this.input.value = this.styleForm.getValue(this.valuePath) ?? '';
    this.input.placeholder =
      mode === 'manual' ? 'Заголовок графика' : '<b>{ticker}</b> | {candles}';
    this.chips.hidden = mode !== 'auto';
    this.hint.textContent =
      mode === 'auto'
        ? 'Подставится автоматически. Пустые части и лишние «|» убираются.'
        : 'Текст используется как есть, без подстановок.';
    this.fromTemplate.hidden = mode !== 'manual';
    this.reset.textContent = mode === 'manual' ? 'Очистить' : 'Вернуть шаблон';
    this.refreshPreview();
  }

  // ------------------------------------------------------------------ chips

  renderChips() {
    this.chips.textContent = '';
    this.placeholders.forEach((placeholder) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip';
      chip.textContent = placeholder.label;
      chip.title = `Вставить ${placeholder.token}`;
      chip.dataset.token = placeholder.token;
      chip.addEventListener('click', () => this.insertToken(placeholder.token));
      this.chips.appendChild(chip);
    });
  }

  /** Show what each chip currently resolves to, once data is loaded. */
  annotateChips(context) {
    this.chips.querySelectorAll('.chip').forEach((chip) => {
      const key = chip.dataset.token.slice(1, -1);
      const value = context ? context[key] : '';
      chip.title = value ? `${chip.dataset.token} → ${value}` : `Вставить ${chip.dataset.token}`;
    });
  }

  // ------------------------------------------------------- text manipulation

  /**
   * Insert a placeholder chip.
   *
   * Appending at the end of a non-empty template means "add another part to
   * the title", so the separator comes along - `|` is what the renderer uses
   * to drop parts that resolve to nothing. Inserting mid-text is taken
   * literally.
   */
  insertToken(token) {
    const caret = this.input.selectionStart ?? this.input.value.length;
    const atEnd = caret >= this.input.value.length;
    const tail = this.input.value.trimEnd().slice(-1);
    const needsSeparator = atEnd && this.input.value.trim() && !'|·,-–—(/ '.includes(tail);
    this.insert(needsSeparator ? ` | ${token}` : token);
  }

  insert(snippet) {
    const start = this.input.selectionStart ?? this.input.value.length;
    const end = this.input.selectionEnd ?? start;
    const before = this.input.value.slice(0, start);
    const after = this.input.value.slice(end);
    this.input.value = before + snippet + after;
    const caret = start + snippet.length;
    this.input.focus();
    this.input.setSelectionRange(caret, caret);
    this.input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  /** Wrap the selection (or the whole field, if nothing is selected) in a tag. */
  wrapSelection(tag) {
    const hasSelection = this.input.selectionEnd > this.input.selectionStart;
    const start = hasSelection ? this.input.selectionStart : 0;
    const end = hasSelection ? this.input.selectionEnd : this.input.value.length;
    const inner = this.input.value.slice(start, end);
    const wrapped = `<${tag}>${inner}</${tag}>`;
    this.input.value = this.input.value.slice(0, start) + wrapped + this.input.value.slice(end);
    this.input.focus();
    this.input.setSelectionRange(start + tag.length + 2, start + tag.length + 2 + inner.length);
    this.input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  // ----------------------------------------------------------------- preview

  async refreshPreview() {
    const series = this.getSeries();
    const raw = this.input.value;

    if (this.mode === 'manual' || !series) {
      this.paintPreview(raw, raw);
      if (!series) this.annotateChips(null);
      return;
    }
    // The server owns template rendering, so the preview cannot drift from the
    // title that actually ends up on the chart.
    const token = ++this._previewToken;
    try {
      const { title, context } = await api.title(series, this.styleForm.getStyle());
      if (token !== this._previewToken) return;
      this.paintPreview(title, title);
      this.annotateChips(context);
    } catch {
      this.paintPreview(raw, raw);
    }
  }

  paintPreview(html, plain) {
    this.preview.dataset.plain = plain || '';
    this.preview.textContent = '';
    if (!html) {
      this.preview.append(Object.assign(document.createElement('span'), {
        className: 'preview-empty',
        textContent: 'без заголовка',
      }));
      return;
    }
    this.preview.append(...renderInlineMarkup(html));
  }
}

/**
 * Render Plotly's inline markup for the preview.
 *
 * Parsed with the browser's own parser, then rebuilt keeping only the tags
 * Plotly supports - so a stray `<img onerror=...>` in the field is displayed
 * as text rather than executed.
 */
function renderInlineMarkup(html) {
  const template = document.createElement('template');
  template.innerHTML = html;
  return [...template.content.childNodes].flatMap(cloneAllowed);
}

function cloneAllowed(node) {
  if (node.nodeType === Node.TEXT_NODE) return [document.createTextNode(node.nodeValue)];
  if (node.nodeType !== Node.ELEMENT_NODE) return [];
  if (!ALLOWED_TAGS.has(node.tagName)) {
    // Not a tag Plotly would honour: show the source verbatim.
    return [document.createTextNode(node.outerHTML)];
  }
  const clone = document.createElement(node.tagName.toLowerCase());
  [...node.childNodes].flatMap(cloneAllowed).forEach((child) => clone.appendChild(child));
  return [clone];
}
