'use strict';

const STORAGE = {
  squad: 'fantalab-squad-v2',
  favorites: 'fantalab-favorites-v1',
  view: 'fantalab-view-v1'
};
const ROLE_LIMITS = { P: 3, D: 8, C: 8, A: 6 };
const PAGE_SIZE = 60;

let DB = { players: [], summary: {} };
const state = {
  players: [],
  filtered: [],
  byKey: new Map(),
  role: '',
  visible: PAGE_SIZE,
  view: localStorage.getItem(STORAGE.view) || 'grid',
  favorites: new Set(readJson(STORAGE.favorites, [])),
  compare: new Set(),
  squad: restoreSquad()
};

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const formatInteger = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 0 });
const formatDecimal = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 2 });

function readJson(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value ?? fallback;
  } catch {
    localStorage.removeItem(key);
    return fallback;
  }
}

function restoreSquad() {
  const saved = readJson(STORAGE.squad, null);
  if (!saved || saved.version !== 2) return { budget: 500, players: [] };
  return {
    budget: clampNumber(saved.budget, 25, 5000, 500),
    players: Array.isArray(saved.players) ? saved.players : []
  };
}

function saveSquad() {
  localStorage.setItem(STORAGE.squad, JSON.stringify({
    version: 2,
    budget: state.squad.budget,
    players: state.squad.players,
    updatedAt: new Date().toISOString()
  }));
}

function saveFavorites() {
  localStorage.setItem(STORAGE.favorites, JSON.stringify([...state.favorites]));
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function clampNumber(value, min, max, fallback) {
  const parsed = numberOrNull(value);
  if (parsed === null) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function displayNumber(value, decimals = true) {
  const parsed = numberOrNull(value);
  if (parsed === null) return '—';
  return decimals && !Number.isInteger(parsed) ? formatDecimal.format(parsed) : formatInteger.format(parsed);
}

function displayPercent(value) {
  const parsed = numberOrNull(value);
  return parsed === null ? '—' : `${formatDecimal.format(parsed)}%`;
}

function recordKey(player) {
  return [player.player_id, player.season || '', player.club || ''].join('|');
}

function normalizeText(value) {
  return String(value || '').trim().toLocaleLowerCase('it');
}

function roleOf(player) {
  const explicit = String(player.fantasy_role || '').trim().toUpperCase();
  if (['P', 'D', 'C', 'A'].includes(explicit)) return explicit;
  const position = normalizeText(player.position);
  if (!position) return '—';
  if (/goal|portier|\bgk\b/.test(position)) return 'P';
  if (/defen|back|terzin|stopper|centre-back|center-back|\bdf\b/.test(position)) return 'D';
  if (/midfield|mediano|mezzala|trequart|centrocamp|\bmf\b/.test(position)) return 'C';
  if (/forward|attack|offen|striker|winger|punta|attacc|\bfw\b/.test(position)) return 'A';
  const first = position.charAt(0).toUpperCase();
  return ['P', 'D', 'C', 'A'].includes(first) ? first : '—';
}

function suggestedPrice(player) {
  const value = numberOrNull(player.budget_500_value) ?? numberOrNull(player.auction_value);
  return Math.max(1, Math.round(value ?? 1));
}

function playerCompleteness(player) {
  const fields = ['appearances', 'minutes', 'goals', 'assists'];
  const complete = fields.filter(field => numberOrNull(player[field]) !== null).length;
  return Math.round((complete / fields.length) * 100);
}

function availability(player) {
  const status = normalizeText(player.lineup_status);
  const risk = numberOrNull(player.injury_risk);
  const chance = numberOrNull(player.starter_probability);
  if (/out|injur|indispon|squalif|assente/.test(status) || (risk !== null && risk >= 75)) {
    return { label: 'A rischio', className: 'bad' };
  }
  if ((risk !== null && risk >= 45) || (chance !== null && chance < 45)) {
    return { label: 'Da valutare', className: 'warn' };
  }
  if (chance !== null && chance >= 70) return { label: 'Probabile titolare', className: 'good' };
  return { label: status ? player.lineup_status : 'Disponibilità n/d', className: '' };
}

function roleMetrics(player) {
  const role = roleOf(player);
  if (role === 'P') return [
    ['Pres.', player.appearances],
    ['Minuti', player.minutes],
    ['Titolarità', percentValue(player.starter_probability)]
  ];
  if (role === 'D') return [
    ['Pres.', player.appearances],
    ['Titolarità', percentValue(player.starter_probability)],
    ['Affidab.', player.reliability_index]
  ];
  if (role === 'C') return [
    ['Assist', player.assists],
    ['xA', player.xa],
    ['Forma', player.form_index]
  ];
  if (role === 'A') return [
    ['Gol', player.goals],
    ['xG', player.xg],
    ['Titolarità', percentValue(player.starter_probability)]
  ];
  return [['Pres.', player.appearances], ['Gol', player.goals], ['Assist', player.assists]];
}

function percentValue(value) {
  const parsed = numberOrNull(value);
  return parsed === null ? null : `${formatDecimal.format(parsed)}%`;
}

function scoreForSort(player, key) {
  const selectors = {
    recommendation_desc: player.recommendation_score ?? player.form_index ?? player.reliability_index,
    auction_desc: player.budget_500_value ?? player.auction_value,
    starter_desc: player.starter_probability,
    form_desc: player.form_index,
    minutes_desc: player.minutes,
    goals_desc: player.goals,
    assists_desc: player.assists,
    xg_desc: player.xg
  };
  return numberOrNull(selectors[key]);
}

function filterValue(id) {
  return numberOrNull($(id).value);
}

function currentFilters() {
  return {
    query: normalizeText($('#search').value),
    season: $('#season').value,
    club: $('#club').value,
    role: state.role,
    priceMin: filterValue('#priceMin'),
    priceMax: filterValue('#priceMax'),
    appearancesMin: filterValue('#appearancesMin'),
    minutesMin: filterValue('#minutesMin'),
    goalsMin: filterValue('#goalsMin'),
    assistsMin: filterValue('#assistsMin'),
    xgMin: filterValue('#xgMin'),
    xaMin: filterValue('#xaMin'),
    starterMin: filterValue('#starterMin'),
    formMin: filterValue('#formMin'),
    reliabilityMin: filterValue('#reliabilityMin'),
    injuryMax: filterValue('#injuryMax'),
    excludeInjured: $('#excludeInjured').checked,
    onlyComplete: $('#onlyComplete').checked,
    onlyFavorites: $('#onlyFavorites').checked
  };
}

function meetsMinimum(value, minimum) {
  if (minimum === null) return true;
  const parsed = numberOrNull(value);
  return parsed !== null && parsed >= minimum;
}

function meetsMaximum(value, maximum) {
  if (maximum === null) return true;
  const parsed = numberOrNull(value);
  return parsed !== null && parsed <= maximum;
}

async function load() {
  try {
    const response = await fetch('data/database.json', { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    DB = await response.json();
    state.players = Array.isArray(DB.players) ? DB.players : [];
    state.byKey = new Map(state.players.map(player => [recordKey(player), player]));
    reconcileStoredSquad();
    init();
  } catch (error) {
    console.error(error);
    $('#status').textContent = 'Archivio non disponibile. Esegui il workflow di pubblicazione e riprova.';
    $('#players').innerHTML = '<div class="empty-state"><h3>Database non caricato</h3><p>Il file dati non è disponibile in questo momento.</p></div>';
  }
}

function reconcileStoredSquad() {
  state.squad.players = state.squad.players.filter(entry => {
    const current = state.players.find(player => player.player_id === entry.playerId && (!entry.season || player.season === entry.season));
    if (!current) return false;
    entry.key = recordKey(current);
    entry.name = current.name;
    entry.club = current.club;
    entry.role = roleOf(current);
    entry.season = current.season;
    return true;
  });
  saveSquad();
}

function init() {
  populateSelects();
  renderSummary();
  bindEvents();
  applyView(state.view);
  $('#totalBudget').value = state.squad.budget;
  renderSquad();
  renderFavoritesCount();
  render();
}

function populateSelects() {
  const seasons = [...new Set(state.players.map(player => player.season).filter(Boolean))].sort().reverse();
  const clubs = [...new Set(state.players.map(player => player.club).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'it'));
  for (const season of seasons) $('#season').add(new Option(season, season));
  for (const club of clubs) $('#club').add(new Option(club, club));
  if (seasons.length) $('#season').value = seasons[0];

  const prices = state.players.map(suggestedPrice).filter(Number.isFinite);
  if (prices.length) {
    $('#priceMax').value = Math.max(150, Math.ceil(Math.max(...prices) / 10) * 10);
  }
  updatePriceOutput();
}

function renderSummary() {
  const items = [
    [DB.summary.players || new Set(state.players.map(p => p.player_id)).size, 'giocatori'],
    [DB.summary.clubs || new Set(state.players.map(p => p.club)).size, 'club'],
    [DB.summary.matches || 0, 'partite'],
    [DB.summary.kaggle_records || DB.summary.stats_records || 0, 'statistiche reali']
  ];
  $('#summary').innerHTML = items.map(([value, label]) =>
    `<div class="summary-chip"><strong>${formatInteger.format(value)}</strong><span>${escapeHtml(label)}</span></div>`
  ).join('');
}

function bindEvents() {
  const liveControls = [
    '#search', '#season', '#club', '#sort', '#priceMin', '#priceMax', '#appearancesMin', '#minutesMin',
    '#goalsMin', '#assistsMin', '#xgMin', '#xaMin', '#starterMin', '#formMin', '#reliabilityMin',
    '#injuryMax', '#excludeInjured', '#onlyComplete', '#onlyFavorites'
  ];
  liveControls.forEach(selector => $(selector).addEventListener('input', () => {
    state.visible = PAGE_SIZE;
    updatePriceOutput();
    render();
  }));

  $('#roleQuickFilters').addEventListener('click', event => {
    const button = event.target.closest('[data-role]');
    if (!button) return;
    state.role = button.dataset.role;
    $$('#roleQuickFilters [data-role]').forEach(item => {
      const active = item === button;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-pressed', String(active));
    });
    state.visible = PAGE_SIZE;
    render();
  });

  $('#players').addEventListener('click', handlePlayerGridClick);
  $('#squadList').addEventListener('input', handleSquadInput);
  $('#squadList').addEventListener('click', handleSquadClick);
  $('#activeFilters').addEventListener('click', handleActiveFilterClick);

  $('#loadMore').addEventListener('click', () => {
    state.visible += PAGE_SIZE;
    renderPlayers();
  });
  $('#resetFilters').addEventListener('click', resetFilters);
  $('#applyFilters').addEventListener('click', closePanels);
  $('#clearSearch').addEventListener('click', () => {
    $('#search').value = '';
    $('#search').focus();
    render();
  });
  $('#favoritesButton').addEventListener('click', () => {
    $('#onlyFavorites').checked = !$('#onlyFavorites').checked;
    render();
  });
  $('#gridView').addEventListener('click', () => applyView('grid'));
  $('#listView').addEventListener('click', () => applyView('list'));
  $('#totalBudget').addEventListener('input', event => {
    state.squad.budget = clampNumber(event.target.value, 25, 5000, 500);
    saveSquad();
    renderSquad();
  });
  $('#clearSquad').addEventListener('click', clearSquad);
  $('#exportSquad').addEventListener('click', exportSquad);

  $('#openFilters').addEventListener('click', () => openPanel('filters'));
  $('#closeFilters').addEventListener('click', closePanels);
  $('#openSquadHeader').addEventListener('click', () => openPanel('squad'));
  $('#mobileSquadBar').addEventListener('click', () => openPanel('squad'));
  $('#closeSquad').addEventListener('click', closePanels);
  $('#scrim').addEventListener('click', closePanels);

  $('#close').addEventListener('click', () => $('#detail').close());
  $('#detail').addEventListener('click', event => {
    if (event.target === $('#detail')) $('#detail').close();
    const add = event.target.closest('[data-detail-add]');
    if (add) addToSquad(add.dataset.detailAdd);
  });
  $('#closeCompare').addEventListener('click', () => $('#compareDialog').close());
  $('#openCompare').addEventListener('click', openCompareDialog);
  $('#clearCompare').addEventListener('click', clearCompare);

  window.addEventListener('keydown', event => {
    if (event.key === 'Escape') closePanels();
  });
}

function updatePriceOutput() {
  const min = numberOrNull($('#priceMin').value) ?? 0;
  const max = numberOrNull($('#priceMax').value) ?? 0;
  $('#priceOutput').textContent = `${displayNumber(min, false)}–${displayNumber(max, false)} crediti`;
}

function render() {
  const filters = currentFilters();
  state.filtered = state.players.filter(player => {
    const searchable = `${normalizeText(player.name)} ${normalizeText(player.club)}`;
    if (filters.query && !searchable.includes(filters.query)) return false;
    if (filters.season && player.season !== filters.season) return false;
    if (filters.club && player.club !== filters.club) return false;
    if (filters.role && roleOf(player) !== filters.role) return false;
    const price = suggestedPrice(player);
    if (!meetsMinimum(price, filters.priceMin) || !meetsMaximum(price, filters.priceMax)) return false;
    if (!meetsMinimum(player.appearances, filters.appearancesMin)) return false;
    if (!meetsMinimum(player.minutes, filters.minutesMin)) return false;
    if (!meetsMinimum(player.goals, filters.goalsMin)) return false;
    if (!meetsMinimum(player.assists, filters.assistsMin)) return false;
    if (!meetsMinimum(player.xg, filters.xgMin)) return false;
    if (!meetsMinimum(player.xa, filters.xaMin)) return false;
    if (!meetsMinimum(player.starter_probability, filters.starterMin)) return false;
    if (!meetsMinimum(player.form_index, filters.formMin)) return false;
    if (!meetsMinimum(player.reliability_index, filters.reliabilityMin)) return false;
    if (!meetsMaximum(player.injury_risk, filters.injuryMax)) return false;
    if (filters.excludeInjured && availability(player).className === 'bad') return false;
    if (filters.onlyComplete && playerCompleteness(player) < 100) return false;
    if (filters.onlyFavorites && !state.favorites.has(player.player_id)) return false;
    return true;
  });

  const sort = $('#sort').value;
  state.filtered.sort((a, b) => {
    if (sort === 'name') return String(a.name || '').localeCompare(String(b.name || ''), 'it');
    const left = scoreForSort(a, sort);
    const right = scoreForSort(b, sort);
    if (left === null && right === null) return String(a.name || '').localeCompare(String(b.name || ''), 'it');
    if (left === null) return 1;
    if (right === null) return -1;
    return right - left || String(a.name || '').localeCompare(String(b.name || ''), 'it');
  });

  $('#status').textContent = `${formatInteger.format(state.filtered.length)} risultati · ${formatInteger.format(state.players.length)} record totali`;
  renderActiveFilters(filters);
  renderPlayers();
  updateFilterCount(filters);
  renderFavoritesCount();
}

function renderPlayers() {
  const rows = state.filtered.slice(0, state.visible);
  if (!rows.length) {
    $('#players').innerHTML = '<div class="empty-state"><h3>Nessun giocatore trovato</h3><p>Riduci i filtri oppure prova un altro nome.</p><button class="secondary-button" type="button" data-reset-empty>Azzera filtri</button></div>';
    const reset = $('#players [data-reset-empty]');
    if (reset) reset.addEventListener('click', resetFilters);
    $('#loadMore').hidden = true;
    return;
  }

  $('#players').innerHTML = rows.map(playerCard).join('');
  $('#loadMore').hidden = rows.length >= state.filtered.length;
  $('#loadMore').textContent = `Carica altri (${formatInteger.format(state.filtered.length - rows.length)})`;
}

function playerCard(player) {
  const key = recordKey(player);
  const role = roleOf(player);
  const price = suggestedPrice(player);
  const metrics = roleMetrics(player);
  const available = availability(player);
  const favorite = state.favorites.has(player.player_id);
  const compared = state.compare.has(key);
  const inSquad = state.squad.players.some(entry => entry.playerId === player.player_id);
  const quality = numberOrNull(player.data_quality) ?? playerCompleteness(player);
  return `
    <article class="player-card role-${role.toLowerCase()}" data-key="${escapeHtml(key)}">
      <div class="card-main">
        <div class="card-top">
          <div class="player-identity">
            <span class="role-badge" title="Ruolo ${role}">${role}</span>
            <div>
              <h3 class="player-name">${escapeHtml(player.name || 'Senza nome')}</h3>
              <p class="player-meta">${escapeHtml(player.club || 'Club n/d')} · ${escapeHtml(player.season || 'Stagione n/d')}</p>
            </div>
          </div>
          <div class="card-actions">
            <button class="card-action ${favorite ? 'is-active' : ''}" type="button" data-action="favorite" aria-label="${favorite ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}" aria-pressed="${favorite}">★</button>
            <button class="card-action ${compared ? 'is-active' : ''}" type="button" data-action="compare" aria-label="${compared ? 'Rimuovi dal confronto' : 'Aggiungi al confronto'}" aria-pressed="${compared}">⇄</button>
          </div>
        </div>

        <div class="card-score-row">
          <div class="value-block">
            <span>Valore consigliato</span>
            <strong>${displayNumber(price, false)}</strong> <small>crediti</small>
          </div>
          <span class="availability-badge ${available.className}">${escapeHtml(available.label)}</span>
        </div>

        <div class="card-metrics">
          ${metrics.map(([label, value]) => `<div class="mini-metric"><strong>${typeof value === 'string' ? escapeHtml(value) : displayNumber(value)}</strong><span>${escapeHtml(label)}</span></div>`).join('')}
        </div>

        <div class="data-line">
          <span><span class="coverage-dot"></span>${escapeHtml(player.data_source || 'Fonte aggregata')}</span>
          <span>${displayNumber(quality, false)}% dati</span>
        </div>
      </div>
      <div class="card-footer">
        <button class="details-button" type="button" data-action="details">Dettagli</button>
        <button class="add-button" type="button" data-action="add" ${inSquad ? 'disabled' : ''}>${inSquad ? 'In rosa' : '+ Aggiungi'}</button>
      </div>
    </article>`;
}

function handlePlayerGridClick(event) {
  const card = event.target.closest('.player-card');
  if (!card) return;
  const player = state.byKey.get(card.dataset.key);
  if (!player) return;
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (!action) return;
  if (action === 'details') showPlayer(player);
  if (action === 'favorite') toggleFavorite(player.player_id);
  if (action === 'compare') toggleCompare(recordKey(player));
  if (action === 'add') addToSquad(recordKey(player));
}

function toggleFavorite(playerId) {
  if (state.favorites.has(playerId)) state.favorites.delete(playerId);
  else state.favorites.add(playerId);
  saveFavorites();
  render();
  showToast(state.favorites.has(playerId) ? 'Giocatore aggiunto ai preferiti' : 'Giocatore rimosso dai preferiti');
}

function renderFavoritesCount() {
  $('#favoriteCount').textContent = state.favorites.size;
  const active = $('#onlyFavorites').checked;
  $('#favoritesButton').classList.toggle('is-active', active);
  $('#favoritesButton').setAttribute('aria-pressed', String(active));
}

function toggleCompare(key) {
  if (state.compare.has(key)) state.compare.delete(key);
  else {
    if (state.compare.size >= 2) {
      showToast('Puoi confrontare al massimo due giocatori.');
      return;
    }
    state.compare.add(key);
  }
  renderCompareBar();
  renderPlayers();
}

function clearCompare() {
  state.compare.clear();
  renderCompareBar();
  renderPlayers();
}

function renderCompareBar() {
  const count = state.compare.size;
  $('#compareBar').hidden = count === 0;
  $('#compareCount').textContent = count;
  $('#openCompare').disabled = count !== 2;
}

function openCompareDialog() {
  const players = [...state.compare].map(key => state.byKey.get(key)).filter(Boolean);
  if (players.length !== 2) return;
  const [a, b] = players;
  const rows = [
    ['Valore asta', suggestedPrice(a), suggestedPrice(b), 'high'],
    ['Presenze', a.appearances, b.appearances, 'high'],
    ['Minuti', a.minutes, b.minutes, 'high'],
    ['Gol', a.goals, b.goals, 'high'],
    ['Assist', a.assists, b.assists, 'high'],
    ['xG', a.xg, b.xg, 'high'],
    ['xA', a.xa, b.xa, 'high'],
    ['Prob. titolare', a.starter_probability, b.starter_probability, 'high', true],
    ['Forma', a.form_index, b.form_index, 'high'],
    ['Affidabilità', a.reliability_index, b.reliability_index, 'high'],
    ['Rischio infortunio', a.injury_risk, b.injury_risk, 'low']
  ];
  $('#compareContent').innerHTML = `
    <div class="compare-header"><p class="eyebrow">CONFRONTO DIRETTO</p><h2>${escapeHtml(a.name)} vs ${escapeHtml(b.name)}</h2></div>
    <div class="compare-table-wrap"><table class="compare-table"><thead><tr><th>Metrica</th><th>${escapeHtml(a.name)}<br><small>${escapeHtml(a.club || '')}</small></th><th>${escapeHtml(b.name)}<br><small>${escapeHtml(b.club || '')}</small></th></tr></thead><tbody>
    ${rows.map(([label, av, bv, direction, isPercent]) => compareRow(label, av, bv, direction, isPercent)).join('')}
    </tbody></table></div>`;
  $('#compareDialog').showModal();
}

function compareRow(label, a, b, direction, isPercent = false) {
  const an = numberOrNull(a);
  const bn = numberOrNull(b);
  let aw = false;
  let bw = false;
  if (an !== null && bn !== null && an !== bn) {
    aw = direction === 'low' ? an < bn : an > bn;
    bw = !aw;
  }
  const format = value => isPercent ? displayPercent(value) : displayNumber(value);
  return `<tr><td>${escapeHtml(label)}</td><td class="${aw ? 'compare-winner' : ''}">${format(a)}</td><td class="${bw ? 'compare-winner' : ''}">${format(b)}</td></tr>`;
}

function addToSquad(key) {
  const player = state.byKey.get(key);
  if (!player) return;
  const role = roleOf(player);
  if (!ROLE_LIMITS[role]) {
    showToast('Ruolo non riconosciuto: impossibile aggiungere il giocatore.');
    return;
  }
  if (state.squad.players.some(entry => entry.playerId === player.player_id)) {
    showToast('Il giocatore è già presente nella rosa.');
    return;
  }
  const roleCount = state.squad.players.filter(entry => entry.role === role).length;
  if (roleCount >= ROLE_LIMITS[role]) {
    showToast(`Hai già completato gli slot ${role}.`);
    return;
  }
  const price = suggestedPrice(player);
  if (price > remainingBudget()) {
    showToast('Budget insufficiente per aggiungere questo giocatore.');
    return;
  }
  state.squad.players.push({
    key,
    playerId: player.player_id,
    name: player.name,
    club: player.club,
    role,
    season: player.season,
    price
  });
  saveSquad();
  renderSquad();
  renderPlayers();
  showToast(`${player.name} aggiunto alla rosa a ${price} crediti.`);
}

function spentBudget() {
  return state.squad.players.reduce((total, entry) => total + (numberOrNull(entry.price) ?? 0), 0);
}

function remainingBudget() {
  return state.squad.budget - spentBudget();
}

function renderSquad() {
  const counts = Object.fromEntries(Object.keys(ROLE_LIMITS).map(role => [role, state.squad.players.filter(entry => entry.role === role).length]));
  const total = state.squad.players.length;
  const remaining = remainingBudget();
  $('#remainingBudget').textContent = displayNumber(remaining, false);
  $('#mobileBudget').textContent = displayNumber(remaining, false);
  $('#headerSquadCount').textContent = `${total}/25`;
  $('#mobileSquadCount').textContent = `${total}/25`;
  for (const role of Object.keys(ROLE_LIMITS)) $(`#count${role}`).textContent = `${counts[role]}/${ROLE_LIMITS[role]}`;

  const message = $('#squadMessage');
  message.className = 'squad-message';
  if (remaining < 0) {
    message.textContent = `Budget superato di ${Math.abs(remaining)} crediti.`;
    message.classList.add('warning');
  } else if (total === 25 && Object.keys(ROLE_LIMITS).every(role => counts[role] === ROLE_LIMITS[role])) {
    message.textContent = `Rosa completa e valida · ${remaining} crediti residui.`;
    message.classList.add('success');
  } else {
    const missing = Object.keys(ROLE_LIMITS).map(role => `${role} ${Math.max(0, ROLE_LIMITS[role] - counts[role])}`).join(' · ');
    message.textContent = `Mancano: ${missing} · ${remaining} crediti residui.`;
  }

  const sorted = [...state.squad.players].sort((a, b) => 'PDCA'.indexOf(a.role) - 'PDCA'.indexOf(b.role) || a.name.localeCompare(b.name, 'it'));
  $('#squadList').innerHTML = sorted.length ? sorted.map(entry => `
    <div class="squad-item role-${entry.role.toLowerCase()}" data-player-id="${escapeHtml(entry.playerId)}">
      <span class="squad-role">${entry.role}</span>
      <div class="squad-name"><strong>${escapeHtml(entry.name)}</strong><span>${escapeHtml(entry.club || '')}</span></div>
      <input class="squad-price" type="number" min="1" max="${state.squad.budget}" value="${displayNumber(entry.price, false)}" inputmode="numeric" aria-label="Prezzo di ${escapeHtml(entry.name)}">
      <button class="remove-player" type="button" aria-label="Rimuovi ${escapeHtml(entry.name)}">×</button>
    </div>`).join('') : '<div class="squad-empty">La rosa è vuota. Usa “+ Aggiungi” sulle card.</div>';
}

function handleSquadInput(event) {
  if (!event.target.classList.contains('squad-price')) return;
  const item = event.target.closest('[data-player-id]');
  const entry = state.squad.players.find(player => player.playerId === item.dataset.playerId);
  if (!entry) return;
  entry.price = clampNumber(event.target.value, 1, state.squad.budget, 1);
  saveSquad();
  renderSquad();
}

function handleSquadClick(event) {
  const button = event.target.closest('.remove-player');
  if (!button) return;
  const item = button.closest('[data-player-id]');
  const entry = state.squad.players.find(player => player.playerId === item.dataset.playerId);
  state.squad.players = state.squad.players.filter(player => player.playerId !== item.dataset.playerId);
  saveSquad();
  renderSquad();
  renderPlayers();
  showToast(`${entry?.name || 'Giocatore'} rimosso dalla rosa.`);
}

function clearSquad() {
  if (!state.squad.players.length) return;
  if (!window.confirm('Vuoi svuotare completamente la rosa?')) return;
  state.squad.players = [];
  saveSquad();
  renderSquad();
  renderPlayers();
  showToast('Rosa svuotata.');
}

function exportSquad() {
  const payload = {
    app: 'FantaLab',
    exportedAt: new Date().toISOString(),
    budget: state.squad.budget,
    spent: spentBudget(),
    remaining: remainingBudget(),
    players: state.squad.players
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `fantalab-rosa-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  showToast('Rosa esportata in formato JSON.');
}

function renderActiveFilters(filters) {
  const chips = [];
  const add = (label, field) => chips.push(`<span class="filter-chip">${escapeHtml(label)}<button type="button" data-clear-filter="${field}" aria-label="Rimuovi filtro ${escapeHtml(label)}">×</button></span>`);
  if (filters.query) add(`Ricerca: ${$('#search').value.trim()}`, 'search');
  if (filters.season) add(filters.season, 'season');
  if (filters.club) add(filters.club, 'club');
  if (filters.role) add(`Ruolo ${filters.role}`, 'role');
  if (filters.appearancesMin !== null) add(`Presenze ≥ ${filters.appearancesMin}`, 'appearancesMin');
  if (filters.minutesMin !== null) add(`Minuti ≥ ${filters.minutesMin}`, 'minutesMin');
  if (filters.goalsMin !== null) add(`Gol ≥ ${filters.goalsMin}`, 'goalsMin');
  if (filters.assistsMin !== null) add(`Assist ≥ ${filters.assistsMin}`, 'assistsMin');
  if (filters.xgMin !== null) add(`xG ≥ ${filters.xgMin}`, 'xgMin');
  if (filters.xaMin !== null) add(`xA ≥ ${filters.xaMin}`, 'xaMin');
  if (filters.starterMin !== null) add(`Titolare ≥ ${filters.starterMin}%`, 'starterMin');
  if (filters.formMin !== null) add(`Forma ≥ ${filters.formMin}`, 'formMin');
  if (filters.reliabilityMin !== null) add(`Affidabilità ≥ ${filters.reliabilityMin}`, 'reliabilityMin');
  if (filters.injuryMax !== null) add(`Rischio ≤ ${filters.injuryMax}`, 'injuryMax');
  if (filters.excludeInjured) add('No indisponibili', 'excludeInjured');
  if (filters.onlyComplete) add('Dati completi', 'onlyComplete');
  if (filters.onlyFavorites) add('Preferiti', 'onlyFavorites');
  $('#activeFilters').innerHTML = chips.join('');
}

function handleActiveFilterClick(event) {
  const button = event.target.closest('[data-clear-filter]');
  if (!button) return;
  const field = button.dataset.clearFilter;
  if (field === 'role') {
    state.role = '';
    $$('#roleQuickFilters [data-role]').forEach(item => {
      const active = item.dataset.role === '';
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-pressed', String(active));
    });
  } else {
    const element = $(`#${field}`);
    if (element) {
      if (element.type === 'checkbox') element.checked = false;
      else element.value = '';
    }
  }
  render();
}

function updateFilterCount(filters) {
  const ignored = new Set(['priceMin', 'priceMax']);
  let count = 0;
  Object.entries(filters).forEach(([key, value]) => {
    if (ignored.has(key)) return;
    if (typeof value === 'boolean' ? value : value !== '' && value !== null) count += 1;
  });
  $('#mobileFilterCount').textContent = count;
}

function resetFilters() {
  $('#search').value = '';
  $('#club').value = '';
  const seasons = [...$('#season').options].map(option => option.value).filter(Boolean);
  $('#season').value = seasons[0] || '';
  ['appearancesMin', 'minutesMin', 'goalsMin', 'assistsMin', 'xgMin', 'xaMin', 'starterMin', 'formMin', 'reliabilityMin', 'injuryMax'].forEach(id => $(`#${id}`).value = '');
  $('#priceMin').value = 0;
  const prices = state.players.map(suggestedPrice).filter(Number.isFinite);
  $('#priceMax').value = prices.length ? Math.max(150, Math.ceil(Math.max(...prices) / 10) * 10) : 150;
  ['excludeInjured', 'onlyComplete', 'onlyFavorites'].forEach(id => $(`#${id}`).checked = false);
  state.role = '';
  $$('#roleQuickFilters [data-role]').forEach(item => {
    const active = item.dataset.role === '';
    item.classList.toggle('is-active', active);
    item.setAttribute('aria-pressed', String(active));
  });
  state.visible = PAGE_SIZE;
  updatePriceOutput();
  render();
}

function applyView(view) {
  state.view = view === 'list' ? 'list' : 'grid';
  localStorage.setItem(STORAGE.view, state.view);
  $('#players').classList.toggle('list-view', state.view === 'list');
  $('#gridView').classList.toggle('is-active', state.view === 'grid');
  $('#listView').classList.toggle('is-active', state.view === 'list');
  $('#gridView').setAttribute('aria-pressed', String(state.view === 'grid'));
  $('#listView').setAttribute('aria-pressed', String(state.view === 'list'));
}

function openPanel(panel) {
  const filters = panel === 'filters';
  $('#filterPanel').classList.toggle('is-open', filters);
  $('#squadPanel').classList.toggle('is-open', !filters);
  $('#scrim').hidden = false;
  document.body.style.overflow = 'hidden';
}

function closePanels() {
  $('#filterPanel').classList.remove('is-open');
  $('#squadPanel').classList.remove('is-open');
  $('#scrim').hidden = true;
  document.body.style.overflow = '';
}

function metric(label, value, percent = false) {
  return `<div class="detail-metric"><strong>${percent ? displayPercent(value) : displayNumber(value)}</strong><span>${escapeHtml(label)}</span></div>`;
}

function showPlayer(player) {
  const key = recordKey(player);
  const role = roleOf(player);
  const price = suggestedPrice(player);
  const available = availability(player);
  const history = state.players.filter(item => item.player_id === player.player_id).sort((a, b) => String(b.season || '').localeCompare(String(a.season || '')));
  const inSquad = state.squad.players.some(entry => entry.playerId === player.player_id);
  $('#detailContent').innerHTML = `
    <section class="detail-hero role-${role.toLowerCase()}" style="--role-color:var(--role-${role.toLowerCase()},#64748b)">
      <div class="detail-title-row"><span class="role-badge">${role}</span><div><p class="eyebrow">${escapeHtml(player.club || 'CLUB N/D')} · ${escapeHtml(player.season || '')}</p><h2>${escapeHtml(player.name || 'Senza nome')}</h2><p class="detail-subtitle">${escapeHtml(player.nationality || 'Nazionalità n/d')} · ${escapeHtml(player.position || 'Posizione n/d')}</p></div></div>
      <div class="detail-price">
        <div class="summary-chip"><strong>${price}</strong><span>crediti consigliati</span></div>
        <div class="summary-chip"><strong>${displayPercent(player.starter_probability)}</strong><span>prob. titolare</span></div>
        <div class="summary-chip"><strong>${escapeHtml(available.label)}</strong><span>disponibilità</span></div>
        <button class="primary-button" type="button" data-detail-add="${escapeHtml(key)}" ${inSquad ? 'disabled' : ''}>${inSquad ? 'Già in rosa' : '+ Aggiungi alla rosa'}</button>
      </div>
    </section>
    <div class="detail-body">
      <section class="detail-section"><h3>Rendimento</h3><div class="detail-grid">
        ${metric('Presenze', player.appearances)}${metric('Titolare', player.starts)}${metric('Minuti', player.minutes)}${metric('Gol', player.goals)}${metric('Assist', player.assists)}${metric('Voto medio', player.average_rating)}${metric('Fantamedia', player.fantasy_average)}${metric('Punti fantasy', player.fantasy_points)}
      </div></section>
      <section class="detail-section"><h3>Statistiche avanzate</h3><div class="detail-grid">
        ${metric('xG', player.xg)}${metric('xA', player.xa)}${metric('xG/90', player.xg_per90)}${metric('xA/90', player.xa_per90)}${metric('Tiri', player.shots)}${metric('Tiri in porta', player.shots_on_target)}${metric('Passaggi chiave', player.key_passes)}${metric('Precisione passaggi', player.pass_accuracy, true)}${metric('Contrasti', player.tackles)}${metric('Intercetti', player.interceptions)}
      </div></section>
      <section class="detail-section"><h3>Indicatori Fantacalcio</h3><div class="detail-grid">
        ${metric('Forma', player.form_index)}${metric('Affidabilità', player.reliability_index)}${metric('Continuità', player.continuity_index)}${metric('Bonus index', player.bonus_index)}${metric('Rischio malus', player.malus_risk)}${metric('Prob. presenza', player.appearance_probability, true)}${metric('Minuti previsti', player.expected_minutes)}${metric('Prob. gol', player.goal_probability, true)}${metric('Prob. assist', player.assist_probability, true)}${metric('Rischio infortunio', player.injury_risk)}${metric('Indice esplosione', player.explosion_index)}${metric('Rischio flop', player.ai_flop_index ?? player.flop_probability)}
      </div></section>
      ${player.recommendation ? `<section class="detail-section"><h3>Consiglio del modello</h3><div class="detail-note"><strong>${escapeHtml(player.recommendation)}</strong>${player.recommendation_explanation ? `<br>${escapeHtml(player.recommendation_explanation)}` : ''}</div></section>` : ''}
      <section class="detail-section"><h3>Qualità e fonte</h3><div class="detail-note">Fonte: <strong>${escapeHtml(player.data_source || 'aggregazione interna')}</strong> · Completezza scheda: <strong>${displayNumber(numberOrNull(player.data_quality) ?? playerCompleteness(player), false)}%</strong>. Il simbolo “—” indica un dato non disponibile, non un valore pari a zero.</div></section>
      <section class="detail-section"><h3>Storico</h3><div class="history-wrap"><table class="history"><thead><tr><th>Stagione</th><th>Club</th><th>Pres.</th><th>Minuti</th><th>Gol</th><th>Assist</th><th>xG</th><th>Valore</th></tr></thead><tbody>
        ${history.map(item => `<tr><td>${escapeHtml(item.season || '—')}</td><td>${escapeHtml(item.club || '—')}</td><td>${displayNumber(item.appearances)}</td><td>${displayNumber(item.minutes)}</td><td>${displayNumber(item.goals)}</td><td>${displayNumber(item.assists)}</td><td>${displayNumber(item.xg)}</td><td>${suggestedPrice(item)}</td></tr>`).join('')}
      </tbody></table></div></section>
    </div>`;
  $('#detail').showModal();
}

let toastTimer;
function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 3000);
}

load();
