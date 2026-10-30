import { INSTRUMENTS, PROVIDERS, formatFigure, formatPrice, normalizeSnapshot, quoteState, canFloat, statusLabel } from './market-model.mjs';

const art = document.querySelector('.hero .art');
if (art) initMarket(art);

function initMarket(art) {
  const node = (tag, cls, text) => { const n = document.createElement(tag); n.className = cls || ''; if (text !== undefined) n.textContent = text; return n; };
  const layer = node('section', 'market-layer');
  layer.setAttribute('aria-label', '世界の市場データ');
  const top = node('div', 'market-top', 'WORLD IN NUMBERS');
  const note = node('div', 'market-note', '市場データは準備中です');
  const numbers = node('div', 'market-numbers');
  layer.tabIndex = -1;
  const reception = node('div', 'market-reception'); reception.hidden = true; reception.setAttribute('aria-hidden', 'true');
  const receptionRing = node('i', 'market-reception-ring');
  const receptionLabel = node('span', 'market-reception-label', 'SIGNAL RECEIVED');
  reception.append(receptionRing, receptionLabel);
  const settings = node('div', 'market-panel-tools');
  const pause = node('button', 'market-control', '数字の動きを止める'); pause.type = 'button'; pause.setAttribute('aria-pressed', 'false'); settings.append(pause);
  const panel = node('div', 'market-panel'); panel.hidden = true; panel.id = 'market-detail'; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-labelledby', 'market-title');
  const panelHead = node('div', 'market-panel-head');
  const titleGroup = node('div');
  const index = node('div', 'market-panel-index');
  const title = node('h2'); title.id = 'market-title'; titleGroup.append(index, title);
  const close = node('button', 'market-close', '×'); close.type = 'button'; close.setAttribute('aria-label', '市場データの詳細を閉じる');
  panelHead.append(titleGroup, close);
  const description = node('p', 'market-description');
  const value = node('p', 'market-value');
  const unit = node('div', 'market-unit');
  const change = node('div', 'market-change');
  const detail = node('dl');
  const source = node('div', 'market-source');
  const external = node('a', '', '参考情報を見る ↗'); external.target = '_blank'; external.rel = 'noopener noreferrer';
  external.setAttribute('aria-label', '参考価格情報を新しいタブで開く（表示値と異なる場合があります）');
  const credit = node('span', 'market-attribution');
  const providerLink = node('a', '', 'Data: Twelve Data'); providerLink.href = 'https://twelvedata.com/'; providerLink.target = '_blank'; providerLink.rel = 'noopener noreferrer';
  source.append(credit);
  const picker = node('div', 'market-picker'); picker.setAttribute('role', 'group'); picker.setAttribute('aria-label', '指標を選択');
  const pickerButtons = INSTRUMENTS.map(i => {
    const b = node('button', '', i.ticker); b.type = 'button'; b.setAttribute('aria-pressed', 'false'); b.addEventListener('click', () => open(i.id, opener || layer, true)); picker.append(b); return b;
  });
  panel.append(panelHead, description, value, unit, change, detail, source, picker, settings);
  layer.append(top, note, numbers, reception, panel); art.append(layer);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = matchMedia('(max-width: 700px)');
  const narrow = matchMedia('(max-width: 399px)');
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  let pending = new Set(), quotes = [], selected = null, opener = null, offset = 0, paused = false, hovering = false, visible = true, specimen = false, loading = false, lastRotation = Date.now(), timer, fadeTimer, request, acquisitionTimer, revealTimer, suppressAcquire = false;
  const count = () => mobile.matches ? 3 : 4;
  const coords = () => mobile.matches ? [[22, 30], [78, 37], [28, 73]] : [[22, 27], [78, 37], [23, 72], [78, 77]];
  const active = () => quotes.filter(q => canFloat(q));
  const frozen = () => paused || reduced.matches || selected !== null || hovering || layer.contains(document.activeElement) || !visible || document.hidden;
  const quoteFor = id => quotes.find(q => q.id === id);
  function status() {
    if (specimen) { top.textContent = 'DESIGN PREVIEW / 架空の数値'; note.textContent = 'デザイン確認用 · 実際の市場価格ではありません'; return; }
    top.textContent = 'WORLD IN NUMBERS';
    note.textContent = active().length ? '数字に触れて、シグナルを受信。参考値・基準日は詳細へ。' : quotes.length ? '市場データの更新を確認できません · 詳細へ' : '市場データは準備中です';
  }
  function renderNumbers(animate = false) {
    clearTimeout(fadeTimer);
    const rows = active();
    const ids = rows.length ? Array.from({length: Math.min(count(), rows.length)}, (_, i) => rows[(offset + i) % rows.length]) : [];
    // Preserve hit targets, motion phase and a hovered/received signal during refresh.
    if (!animate && numbers.children.length === ids.length && [...numbers.children].every((b, i) => b.dataset.id === ids[i].id)) {
      for (const [i, b] of [...numbers.children].entries()) {
        const q = quoteFor(b.dataset.id), info = INSTRUMENTS.find(i => i.id === q.id);
        b.firstElementChild.textContent = formatFigure(q.price);
        b.style.setProperty('--x', `${coords()[i][0]}%`); b.style.setProperty('--y', `${coords()[i][1]}%`);
        b.setAttribute('aria-label', `${info.name} ${formatPrice(q.id, q.price)} · ${statusLabel(q)}。詳細を表示`);
      }
      syncState(); return;
    }
    if (numbers.contains(document.activeElement)) layer.focus({preventScroll:true});
    numbers.replaceChildren();
    ids.forEach((q, i) => {
      const info = INSTRUMENTS.find(x => x.id === q.id);
      const b = node('button', `market-number${animate ? ' is-entering' : ''}`); b.type = 'button'; b.dataset.id = q.id;
      b.style.setProperty('--x', `${coords()[i][0]}%`); b.style.setProperty('--y', `${coords()[i][1]}%`);
      b.style.setProperty('--tilt', `${[-28, 48, -63, 19][i]}deg`);
      b.style.setProperty('--period', `${[33, 41, 37, 46][i]}s`);
      b.style.setProperty('--phase', `${[-4, -17, -9, -27][i]}s`);
      b.setAttribute('aria-controls', panel.id); b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', String(!panel.hidden && q.id === selected));
      b.setAttribute('aria-label', `${info.name} ${formatPrice(q.id, q.price)} · ${statusLabel(q)}。詳細を表示`);
      b.append(node('span', '', formatFigure(q.price)));
      b.addEventListener('pointerenter', e => {
        if (e.pointerType !== 'mouse' || !finePointer.matches) return;
        hovering = true; cancelFade(); clearTimeout(acquisitionTimer);
        acquisitionTimer = setTimeout(() => receive(q.id, b, false), 180);
      });
      b.addEventListener('pointerleave', () => { hovering = false; clearTimeout(acquisitionTimer); lastRotation = Date.now(); });
      b.addEventListener('focus', () => { if (!suppressAcquire) receive(q.id, b, false); });
      b.addEventListener('click', () => receive(q.id, b)); numbers.append(b);
      if (q.id === selected) lockNumber(b);
    });
    syncState();
  }
  function syncState() {
    pause.hidden = reduced.matches || active().length === 0;
    pause.textContent = paused ? '数字の動きを再開' : '数字の動きを止める';
    pause.setAttribute('aria-label', paused ? '数値の動きを再開' : '数値の動きを静止');
    layer.dataset.paused = String(paused || reduced.matches);
    layer.dataset.reduced = String(reduced.matches);
    status();
  }
  function renderPanel() {
    if (!selected) return;
    const info = INSTRUMENTS.find(i => i.id === selected), q = quoteFor(selected), state = quoteState(q);
    index.textContent = `${String(INSTRUMENTS.indexOf(info) + 1).padStart(2, '0')} / SIGNAL RECEIVED`;
    title.textContent = q?.provider === 'gold-api' && selected === 'gold' ? 'GOLD' : info.name; description.textContent = q?.provider === 'gold-api' && selected === 'gold' ? '金の参考価格 · Gold API / XAU' : q?.provider === 'frankfurter' ? '1米ドルあたりの日本円 · 日次ブレンドレート' : info.description;
    value.textContent = q ? formatFigure(q.price) : '—';
    unit.textContent = (q?.provider === 'gold-api' && selected === 'gold' ? 'USD / OZ · XAU' : info.unit) + (specimen ? ' · DESIGN SAMPLE' : '') + (state === 'stale' ? ' · 最後に確認した参考値' : '');
    change.replaceChildren();
    if (q && q.changePercent !== null) { change.append(node('span', '', `${q.changePercent > 0 ? '+' : ''}${q.changePercent.toFixed(2)}%`), node('small', '', ({'24h':'過去24時間比',previous_close:'前営業日終値比',observed_24h:'約24時間前の観測値比',previous_publication:'前回公表値比'})[q.changeBasis])); }
    else change.append(node('small', '', q?.changeBasis === 'observed_24h' ? '変動率は算出準備中 · 24時間の観測が必要' : '変動率を取得できません'));
    const stamp = iso => new Intl.DateTimeFormat('ja-JP', { timeZone:'Asia/Tokyo', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false }).format(new Date(iso)) + ' JST';
    const rows = [['状態', pending.has(selected) && !q ? '未接続 · 公開表示条件を確認中' : (specimen ? '架空データ · ' : '') + statusLabel(q)], [q?.timing === 'daily_reference' ? '基準日' : '価格の更新', q ? q.timing === 'daily_reference' ? q.asOf + '（日次）' : stamp(q.asOf) : '—'], ['取得確認', q ? stamp(q.fetchedAt) : '—']];
    if (q?.comparisonAt) rows.push(['比較対象', q.timing === 'daily_reference' ? q.comparisonAt + '（日次）' : stamp(q.comparisonAt)]);
    if (q) rows.push(['配信条件', q.timing === 'delayed' ? `${Math.ceil(q.delaySeconds / 60)}分遅延` : q.timing === 'eod' ? '日次終値' : q.timing === 'daily_reference' ? '日次参考値 · 取引レートではありません' : q.timing === 'reference' ? '5分ごとに取得 · 遅延・休場は未確認' : '随時更新 · 参考値']);
    detail.replaceChildren(...rows.map(([term, text]) => { const row = node('div'); row.append(node('dt', '', term), node('dd', '', text)); return row; }));
    external.href = info.url;
    source.prepend(external);
    if (q && !specimen) { const provider = PROVIDERS[q.provider || 'twelve-data']; providerLink.textContent = 'Data: ' + provider.name; providerLink.href = provider.url; if (!credit.contains(providerLink)) credit.replaceChildren(providerLink); }
    else credit.textContent = specimen ? 'ILLUSTRATIVE ONLY' : 'データ接続前';
    pickerButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(INSTRUMENTS[i].id === selected)));
    for (const b of numbers.children) b.setAttribute('aria-expanded', String(!panel.hidden && b.dataset.id === selected));
  }
  function unlockNumbers() {
    for (const b of numbers.children) {
      const glyph = b.firstElementChild;
      if (b.dataset.locked) { glyph.getAnimations().forEach(a => a.cancel()); glyph.style.removeProperty('animation'); glyph.style.removeProperty('transform'); delete b.dataset.locked; }
    }
  }
  function lockNumber(b) {
    if (b.dataset.locked) return;
    const glyph = b.firstElementChild, transform = getComputedStyle(glyph).transform;
    glyph.style.animation = 'none'; glyph.style.transform = 'none'; b.dataset.locked = 'true';
    // Capture the current angle, then settle into a readable signal without a jump.
    glyph.animate([{transform}, {transform:'none'}], {duration:reduced.matches ? 0 : 520, easing:'cubic-bezier(.16,1,.3,1)', fill:'forwards'});
  }
  function open(id, trigger, moveFocus = true) {
    clearTimeout(acquisitionTimer); clearTimeout(revealTimer); cancelFade();
    if (selected !== id) unlockNumbers();
    selected = id; opener = trigger; reception.hidden = true; layer.dataset.receiving = 'false';
    panel.hidden = false; layer.dataset.open = 'true'; renderPanel(); panel.scrollTop = 0;
    const signal = [...numbers.children].find(b => b.dataset.id === id); if (signal) lockNumber(signal);
    if (moveFocus) close.focus({preventScroll:true});
  }
  function receive(id, trigger, moveFocus = true) {
    clearTimeout(acquisitionTimer); cancelFade();
    if (selected === id && !panel.hidden) { if (moveFocus) close.focus({preventScroll:true}); return; }
    if (selected === id && layer.dataset.receiving === 'true') {
      if (moveFocus) { clearTimeout(revealTimer); revealTimer = setTimeout(() => open(id, trigger, true), reduced.matches ? 320 : 680); }
      return;
    }
    clearTimeout(revealTimer); unlockNumbers(); selected = id; opener = trigger; panel.hidden = true;
    layer.dataset.open = 'false'; layer.dataset.receiving = 'true'; renderPanel(); lockNumber(trigger);
    reception.style.left = trigger.style.getPropertyValue('--x'); reception.style.top = trigger.style.getPropertyValue('--y');
    reception.hidden = true; void reception.offsetWidth; reception.hidden = false;
    // Give the visible acknowledgement its own moment before the detail covers it.
    revealTimer = setTimeout(() => open(id, trigger, moveFocus), reduced.matches ? 320 : 680);
  }
  function dismiss(restore = true) {
    clearTimeout(acquisitionTimer); clearTimeout(revealTimer); selected = null; panel.hidden = true; reception.hidden = true;
    layer.dataset.open = 'false'; layer.dataset.receiving = 'false'; unlockNumbers();
    for (const b of numbers.children) b.setAttribute('aria-expanded','false');
    if (restore) { suppressAcquire = true; (opener?.isConnected ? opener : layer).focus({preventScroll:true}); suppressAcquire = false; }
    lastRotation = Date.now();
  }
  function advance() {
    if (selected) return;
    lastRotation = Date.now();
    if (reduced.matches || layer.contains(document.activeElement)) { offset = (offset + 1) % Math.max(active().length, 1); renderNumbers(); return; }
    for (const b of numbers.children) b.classList.add('is-leaving');
    fadeTimer = setTimeout(() => { if (frozen()) return cancelFade(); offset = (offset + 1) % Math.max(active().length, 1); renderNumbers(true); }, 1400);
  }
  function cancelFade() { clearTimeout(fadeTimer); for (const b of numbers.children) b.classList.remove('is-leaving'); lastRotation = Date.now(); }
  close.addEventListener('click', () => dismiss());
  pause.addEventListener('click', () => { paused = !paused; pause.setAttribute('aria-pressed', String(paused)); syncState(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && selected) { e.preventDefault(); dismiss(); }
    else if (['ArrowLeft', 'ArrowRight'].includes(e.key) && e.target.matches('.market-number')) {
      e.preventDefault(); dismiss(false);
      offset = (offset + (e.key === 'ArrowRight' ? 1 : -1) + Math.max(active().length, 1)) % Math.max(active().length, 1);
      renderNumbers(); numbers.firstElementChild?.focus({preventScroll:true});
    }
  });
  document.addEventListener('focusin', e => { if (layer.contains(e.target)) cancelFade(); else if (selected) dismiss(false); });
  art.addEventListener('pointerleave', () => { hovering = false; clearTimeout(acquisitionTimer); lastRotation = Date.now(); });
  document.addEventListener('pointerdown', e => { if (selected && !panel.contains(e.target) && !e.target.closest('.market-number')) dismiss(false); });
  for (const query of [mobile, narrow, reduced]) query.addEventListener('change', () => { renderNumbers(); lastRotation = Date.now(); });
  const rawEndpoint = document.querySelector('meta[name="work-signal-market-endpoint"]')?.content;
  const freeDirect = !rawEndpoint && document.querySelector('meta[name="work-signal-market-mode"]')?.content === 'free';
  let endpoint;
  try { const u = new URL(rawEndpoint || '', location.origin); if (rawEndpoint && (u.protocol === 'https:' || ['localhost','127.0.0.1'].includes(u.hostname) && u.origin === location.origin)) endpoint = u.href; } catch { /* fail closed */ }
  async function refresh() {
    if ((!endpoint && !freeDirect) || loading || !visible || document.hidden) return;
    loading = true; request = new AbortController(); const timeout = setTimeout(() => request.abort(), freeDirect ? 12000 : 8000);
    try {
      let raw;
      if(freeDirect){
        const {getFreeSnapshot}=await import('./free-market-client.mjs');raw=await getFreeSnapshot({signal:request.signal});
      }else{
        const response = await fetch(endpoint, { signal:request.signal, credentials:'omit', cache:'no-store', referrerPolicy:'no-referrer' });
        if (!response.ok) throw new Error('unavailable');
        raw = await response.json();
      }
      if (raw.mode === 'specimen' && !['localhost','127.0.0.1'].includes(location.hostname)) throw new Error('specimen forbidden');
      specimen = raw.mode === 'specimen';
      pending = new Set(Array.isArray(raw.pendingIds) ? raw.pendingIds.filter(id => INSTRUMENTS.some(i => i.id === id)) : []);
      quotes = normalizeSnapshot(raw); renderNumbers(); renderPanel();
    } catch { // Keep only explicitly dated prior observations; age checks remove them from the artwork.
      if (!visible || document.hidden) return;
      quotes = quotes.map(q => ({...q, fetchFailed:true})); renderNumbers(); renderPanel();
      if (!specimen) note.textContent = '市場データを取得できません · 詳細で状態を確認';
    } finally { clearTimeout(timeout); loading = false; }
  }
  let lastFetch = 0;
  function tick() {
    if (!visible || document.hidden) return;
    const now = Date.now();
    if ([...numbers.children].some(b => !canFloat(quoteFor(b.dataset.id)))) { renderNumbers(); renderPanel(); }
    if (!frozen() && now - lastRotation >= 12000 && active().length > count()) advance();
    if (!loading && now - lastFetch >= (freeDirect ? 300000 : 60000)) { lastFetch = now; refresh(); }
  }
  if ('IntersectionObserver' in window) new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (!visible) request?.abort(); else { lastFetch = 0; lastRotation = Date.now(); tick(); } }, {rootMargin:'100px'}).observe(art);
  document.addEventListener('visibilitychange', () => { if (document.hidden) { request?.abort(); if (layer.dataset.receiving === 'true') dismiss(false); } else { lastFetch = 0; lastRotation = Date.now(); tick(); } });
  renderNumbers(); tick(); timer = setInterval(tick, 1000);
  addEventListener('pagehide', () => { clearInterval(timer); clearTimeout(fadeTimer); clearTimeout(acquisitionTimer); clearTimeout(revealTimer); request?.abort(); if (layer.dataset.receiving === 'true') dismiss(false); });
  addEventListener('pageshow', e => { if (e.persisted) { lastFetch = 0; lastRotation = Date.now(); timer = setInterval(tick, 1000); tick(); } });
}
