/**
 * Renders the design settings panel from the schema the API publishes.
 *
 * The form has no hard-coded knowledge of any individual setting: adding a
 * field to ChartStyle on the server makes it appear here automatically.
 */

import { api } from './api.js';

const WIDE_WIDGETS = new Set(['text', 'textarea', 'image']);

function el(tag, className, attrs = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  Object.entries(attrs).forEach(([key, value]) => {
    if (value !== undefined && value !== null) node.setAttribute(key, value);
  });
  return node;
}

function isWide(field) {
  return WIDE_WIDGETS.has(field.widget) || (field.help || '').length > 60;
}

export class StyleForm {
  /**
   * @param {HTMLElement} root
   * @param {(style: object) => void} onChange called (debounced) on every edit
   */
  constructor(root, onChange) {
    this.root = root;
    this.onChange = onChange;
    this.schema = [];
    this.defaults = {};
    this.values = {};
    this.inputs = new Map(); // "section.key" -> HTMLElement
    this._timer = null;
  }

  async init() {
    [this.schema, this.defaults] = await Promise.all([api.styleSchema(), api.styleDefaults()]);
    this.values = structuredClone(this.defaults);
    this.render();
  }

  render() {
    this.root.textContent = '';
    this.inputs.clear();
    this.schema.forEach((section, index) => {
      const details = el('details', 'style-section');
      if (index === 0) details.open = true;
      const summary = el('summary');
      summary.textContent = section.title;
      details.appendChild(summary);

      const body = el('div', 'style-body');
      // Hidden fields stay in the model and in presets, but a purpose-built
      // editor owns them (see TitleEditor) - rendering them twice would give
      // the user two places to change the same thing.
      section.fields
        .filter((field) => !field.hidden)
        .forEach((field) => body.appendChild(this.renderField(section.key, field)));
      if (!body.childElementCount) return;
      details.appendChild(body);
      this.root.appendChild(details);
    });
  }

  renderField(sectionKey, field) {
    const path = `${sectionKey}.${field.key}`;
    const value = this.get(path);
    const wrapper = el('label', `field${isWide(field) ? ' is-wide' : ''}`);

    if (field.widget === 'checkbox') {
      wrapper.className = 'field check-field';
      const input = el('input', null, { type: 'checkbox' });
      input.checked = Boolean(value);
      this.bind(path, input, () => input.checked);
      const label = el('span', 'field-label');
      label.textContent = field.label;
      wrapper.append(input, label);
      return wrapper;
    }

    const label = el('span', 'field-label');
    label.textContent = field.label;
    wrapper.appendChild(label);

    if (field.widget === 'image') {
      wrapper.appendChild(this.renderImageField(path, field, value));
    } else if (field.widget === 'select') {
      const select = el('select');
      (field.options || []).forEach((option) => {
        const node = el('option', null, { value: option.value });
        node.textContent = option.label;
        select.appendChild(node);
      });
      select.value = value ?? '';
      this.bind(path, select, () => select.value);
      wrapper.appendChild(select);
    } else if (field.widget === 'color') {
      wrapper.appendChild(this.renderColorField(path, value));
    } else if (field.widget === 'number') {
      const input = el('input', null, {
        type: 'number',
        min: field.min,
        max: field.max,
        step: field.step ?? 1,
      });
      input.value = value ?? '';
      this.bind(path, input, () => (input.value === '' ? null : Number(input.value)));
      wrapper.appendChild(input);
    } else {
      const input = el('input', null, { type: 'text' });
      input.value = value ?? '';
      this.bind(path, input, () => input.value);
      wrapper.appendChild(input);
    }

    if (field.help) {
      const hint = el('small', 'field-hint');
      hint.textContent = field.help;
      wrapper.appendChild(hint);
    }
    return wrapper;
  }

  /**
   * Swatch plus a text box, so a colour can be picked *or* pasted.
   *
   * The text box holds the authoritative value: it accepts `#rrggbb`, a bare
   * `rrggbb`, the short `#rgb` form, and any other CSS colour Plotly
   * understands (`rgba(...)`, `tomato`). The swatch is a best-effort preview -
   * `<input type=color>` can only represent 6-digit hex - so it never
   * overwrites a value it cannot express.
   */
  renderColorField(path, value) {
    const box = el('div', 'color-field');
    const swatch = el('input', null, { type: 'color' });
    const text = el('input', 'color-hex', {
      type: 'text',
      spellcheck: 'false',
      autocomplete: 'off',
      placeholder: '#rrggbb',
    });

    const paint = (next) => {
      const raw = next ?? '';
      text.value = raw;
      const hex = toHex(raw);
      swatch.value = hex || '#000000';
      box.classList.toggle('is-invalid', Boolean(raw) && !isColour(raw));
    };
    paint(value);

    swatch.addEventListener('input', () => {
      text.value = swatch.value;
      box.classList.remove('is-invalid');
      this.set(path, swatch.value);
      this.emit();
    });

    const commitText = () => {
      const typed = text.value.trim();
      const valid = isColour(typed);
      box.classList.toggle('is-invalid', Boolean(typed) && !valid);
      if (!valid) return; // keep the last good value while the user is typing
      const canonical = typed.startsWith('#') || !/^[0-9a-f]{3,8}$/i.test(typed) ? typed : `#${typed}`;
      text.value = canonical;
      const hex = toHex(canonical);
      if (hex) swatch.value = hex;
      this.set(path, canonical);
      this.emit();
    };
    text.addEventListener('input', commitText);
    text.addEventListener('change', commitText);
    // A paste lands before the input event reads .value, so defer one tick.
    text.addEventListener('paste', () => setTimeout(commitText, 0));

    box.append(swatch, text);
    this.inputs.set(path, { repaint: paint });
    return box;
  }

  renderImageField(path, field, value) {
    const box = el('div', 'image-field');
    const preview = el('div', 'image-preview');
    const file = el('input', null, { type: 'file', accept: 'image/*' });
    const clear = el('button', 'btn btn-ghost btn-sm', { type: 'button' });
    clear.textContent = 'Вернуть логотип по умолчанию';

    const paint = (source) => {
      preview.textContent = '';
      if (source) {
        const img = el('img', null, { src: source, alt: '' });
        preview.appendChild(img);
      } else {
        const hint = el('span');
        hint.textContent = 'логотип по умолчанию';
        preview.appendChild(hint);
      }
    };
    paint(value);

    file.addEventListener('change', async () => {
      const chosen = file.files && file.files[0];
      if (!chosen) return;
      try {
        const { data_uri: dataUri } = await api.uploadWatermark(chosen);
        this.set(path, dataUri);
        paint(dataUri);
        this.emit();
      } catch (error) {
        this.root.dispatchEvent(
          new CustomEvent('style-error', { bubbles: true, detail: error.message }),
        );
      } finally {
        file.value = '';
      }
    });

    clear.addEventListener('click', () => {
      this.set(path, '');
      paint('');
      this.emit();
    });

    box.append(preview, file, clear);
    this.inputs.set(path, { repaint: paint });
    return box;
  }

  bind(path, input, read) {
    this.inputs.set(path, input);
    const handler = () => {
      this.set(path, read());
      this.emit();
    };
    input.addEventListener('change', handler);
    if (input.type === 'text' || input.type === 'number') input.addEventListener('input', handler);
  }

  emit() {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this.onChange(this.getStyle()), 250);
  }

  get(path) {
    const [section, key] = path.split('.');
    return this.values?.[section]?.[key];
  }

  set(path, value) {
    const [section, key] = path.split('.');
    this.values[section] = this.values[section] || {};
    this.values[section][key] = value;
  }

  getStyle() {
    return structuredClone(this.values);
  }

  /** Read one setting, e.g. ``'title.template'``. */
  getValue(path) {
    return this.get(path);
  }

  /** Write one setting from outside the panel and trigger a re-render. */
  setValue(path, value) {
    this.set(path, value);
    this.emit();
  }

  /** The shipped default for one setting - used by "reset this field". */
  defaultValue(path) {
    const [section, key] = path.split('.');
    return this.defaults?.[section]?.[key];
  }

  /** Replace all values (loading a preset) and refresh every control. */
  setStyle(style) {
    this.values = mergeDeep(structuredClone(this.defaults), style || {});
    this.syncInputs();
  }

  reset() {
    this.setStyle(structuredClone(this.defaults));
  }

  syncInputs() {
    this.inputs.forEach((input, path) => {
      const value = this.get(path);
      if (input && typeof input.repaint === 'function') {
        input.repaint(value);
      } else if (input.type === 'checkbox') {
        input.checked = Boolean(value);
      } else {
        input.value = value ?? '';
      }
    });
  }
}

/** The 6-digit hex a `<input type=color>` can show, or '' if there isn't one. */
function toHex(value) {
  if (typeof value !== 'string') return '';
  const raw = value.trim().replace(/^#/, '');
  if (/^[0-9a-f]{6}$/i.test(raw)) return `#${raw}`;
  if (/^[0-9a-f]{8}$/i.test(raw)) return `#${raw.slice(0, 6)}`; // #rrggbbaa
  if (/^[0-9a-f]{3}$/i.test(raw)) {
    return '#' + raw.split('').map((c) => c + c).join('');
  }
  return '';
}

/** Anything the browser (and therefore Plotly) recognises as a colour. */
function isColour(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return false;
  if (toHex(raw)) return true;
  const probe = new Option().style;
  probe.color = '';
  probe.color = raw;
  return probe.color !== '';
}

function mergeDeep(target, source) {
  Object.entries(source || {}).forEach(([key, value]) => {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      target[key] = mergeDeep(target[key] || {}, value);
    } else if (value !== undefined) {
      target[key] = value;
    }
  });
  return target;
}
