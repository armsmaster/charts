/**
 * Ticker input with search-as-you-type and validation against ISS.
 *
 * A ticker is only accepted once /api/instruments/{secid} resolves it, so an
 * instrument that does not exist on MOEX can never reach the load request.
 */

import { api } from './api.js';

const DEBOUNCE_MS = 250;

export class InstrumentPicker {
  /**
   * @param {{input: HTMLInputElement, list: HTMLElement, status: HTMLElement,
   *          boardSelect: HTMLSelectElement, onResolved: Function}} options
   */
  constructor({ input, list, status, boardSelect, onResolved }) {
    this.input = input;
    this.list = list;
    this.status = status;
    this.boardSelect = boardSelect;
    this.onResolved = onResolved || (() => {});
    this.instrument = null;
    this._timer = null;
    this._token = 0;
    this._bind();
  }

  _bind() {
    this.input.addEventListener('input', () => {
      this.instrument = null;
      this.setStatus('', '');
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this.search(), DEBOUNCE_MS);
    });
    this.input.addEventListener('blur', () => {
      // Let a click on a suggestion land before the list closes.
      setTimeout(() => this.hideList(), 150);
      if (this.input.value.trim()) this.validate();
    });
    this.input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        const active = this.list.querySelector('li.is-active');
        if (active && !this.list.hidden) this.choose(active.dataset.secid);
        else this.validate();
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        this.move(event.key === 'ArrowDown' ? 1 : -1);
      } else if (event.key === 'Escape') {
        this.hideList();
      }
    });
    this.boardSelect.addEventListener('change', () => {
      if (this.input.value.trim()) this.validate();
    });
  }

  async search() {
    const query = this.input.value.trim();
    if (query.length < 2) return this.hideList();
    const token = ++this._token;
    try {
      const hits = await api.searchInstruments(query);
      if (token !== this._token) return;
      this.showList(hits);
    } catch {
      this.hideList();
    }
  }

  showList(hits) {
    this.list.textContent = '';
    if (!hits.length) return this.hideList();
    hits.forEach((hit, index) => {
      const item = document.createElement('li');
      item.dataset.secid = hit.secid;
      if (index === 0) item.classList.add('is-active');
      const code = document.createElement('b');
      code.textContent = hit.secid;
      const name = document.createElement('span');
      name.textContent = ` — ${hit.shortname || hit.name}`;
      item.append(code, name);
      item.addEventListener('mousedown', (event) => {
        event.preventDefault();
        this.choose(hit.secid);
      });
      this.list.appendChild(item);
    });
    this.list.hidden = false;
  }

  hideList() {
    this.list.hidden = true;
  }

  move(step) {
    const items = [...this.list.querySelectorAll('li')];
    if (!items.length) return;
    const current = items.findIndex((i) => i.classList.contains('is-active'));
    const next = Math.max(0, Math.min(items.length - 1, (current < 0 ? 0 : current) + step));
    items.forEach((item) => item.classList.remove('is-active'));
    items[next].classList.add('is-active');
    items[next].scrollIntoView({ block: 'nearest' });
  }

  choose(secid) {
    this.input.value = secid;
    this.hideList();
    this.validate();
  }

  /** Resolve the typed ticker; returns the instrument or null. */
  async validate() {
    const secid = this.input.value.trim().toUpperCase();
    if (!secid) {
      this.instrument = null;
      this.setStatus('', '');
      return null;
    }
    this.setStatus('Проверяем…', '');
    const token = ++this._token;
    try {
      const instrument = await api.resolveInstrument(secid, this.boardSelect.value || undefined);
      if (token !== this._token) return this.instrument;
      this.instrument = instrument;
      this.input.value = instrument.secid;
      this.setStatus(
        `${instrument.shortname} · ${instrument.board}${instrument.is_traded ? '' : ' · не торгуется'}`,
        'is-ok',
      );
      await this.loadBoards(instrument);
      this.onResolved(instrument);
      return instrument;
    } catch (error) {
      if (token !== this._token) return this.instrument;
      this.instrument = null;
      this.setStatus(
        error.status === 404 ? `Инструмент «${secid}» не найден на MOEX.` : error.message,
        'is-error',
      );
      return null;
    }
  }

  async loadBoards(instrument) {
    if (this.boardSelect.dataset.secid === instrument.secid) return;
    try {
      const boards = await api.instrumentBoards(instrument.secid);
      const current = this.boardSelect.value;
      this.boardSelect.textContent = '';
      const auto = document.createElement('option');
      auto.value = '';
      auto.textContent = 'определить автоматически';
      this.boardSelect.appendChild(auto);
      boards
        .filter((board) => board.is_traded)
        .forEach((board) => {
          const option = document.createElement('option');
          option.value = board.board;
          option.textContent = `${board.board} — ${board.title}`;
          this.boardSelect.appendChild(option);
        });
      this.boardSelect.value = current;
      this.boardSelect.dataset.secid = instrument.secid;
    } catch {
      /* board list is a convenience; auto-detection still works */
    }
  }

  setStatus(text, className) {
    this.status.textContent = text;
    this.status.className = `field-status ${className}`.trim();
  }

  setValue(secid) {
    this.input.value = secid || '';
    this.instrument = null;
    this.setStatus('', '');
  }
}
