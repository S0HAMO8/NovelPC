/**
 * novelPC — Builder JS
 * Handles: tab switching, component insertion, RAM quantity, price tracking,
 * SVG slot highlighting (incl. motherboard/cabinet/fans), compatibility checks,
 * autosave, save/confirm/reset, sorting, and the AI build advisor.
 */

const build = {};          // { type: { id, name, price, wattage, ramSlots? } }
let ramQuantity = 1;
let fanQuantity = 0;
let currentBuildId = null; // used for autosave / updating the same Build row
let autosaveTimer = null;

const REQUIRED = ['cpu', 'gpu', 'motherboard', 'ram', 'psu', 'cabinet'];
const STORAGE   = ['ssd', 'hdd'];
const COOLING   = ['air_cooler', 'liquid_cooler'];

const SLOT_MAP = {
  cpu: 'slot-cpu', gpu: 'slot-gpu', ram: 'slot-ram',
  ssd: 'slot-ssd', hdd: 'slot-hdd',
  psu: 'slot-psu', air_cooler: 'slot-cooling', liquid_cooler: 'slot-cooling',
};
const LABEL_MAP = {
  cpu: 'lbl-cpu', gpu: 'lbl-gpu', ram: null,
  ssd: 'lbl-ssd', hdd: 'lbl-hdd',
  psu: 'lbl-psu', air_cooler: 'lbl-cooling', liquid_cooler: 'lbl-cooling',
  motherboard: 'lbl-mb', cabinet: 'lbl-cabinet',
};

// ─── Tab Switching ───────────────────────────────────────────────────────────
function switchTab(type) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
  const tabContent = document.getElementById('tab-' + type);
  if (tabContent) tabContent.classList.remove('hidden');
  document.querySelectorAll('.tab-btn').forEach(b => {
    if (b.getAttribute('onclick') && b.getAttribute('onclick').includes(`'${type}'`)) {
      b.classList.add('active');
    }
  });
}

// ─── Insert Component (CPU, GPU, Motherboard, Cabinet, SSD, HDD, PSU, Cooling) ──
function insertComponent(id, type, name, price, wattage, ramSlots) {
  if (build[type]) {
    const oldCard = document.getElementById('card-' + build[type].id);
    if (oldCard) oldCard.classList.remove('selected-card');
  }
  build[type] = { id, name, price, wattage, ramSlots: ramSlots || 0 };

  const card = document.getElementById('card-' + id);
  if (card) card.classList.add('selected-card');

  updateSVGSlot(type, name);
  updatePrice();
  runCompatibility();
  scheduleAutosave();
}

// ─── Insert RAM (needs quantity; item 2: only highlight the slots actually used) ──
function insertRam(id, name, price, wattage) {
  const qtySelect = document.getElementById('ramqty-' + id);
  const qty = qtySelect ? parseInt(qtySelect.value, 10) : 1;
  ramQuantity = qty;

  if (build['ram']) {
    const oldCard = document.getElementById('card-' + build['ram'].id);
    if (oldCard) oldCard.classList.remove('selected-card');
  }
  build['ram'] = { id, name: `${name} (x${qty})`, price: price * qty, wattage: wattage * qty, baseName: name };

  const card = document.getElementById('card-' + id);
  if (card) card.classList.add('selected-card');

  // Redraw RAM slots: total slots from motherboard, but only `qty` shown as filled
  const totalSlots = (build['motherboard'] && build['motherboard'].ramSlots) || 4;
  drawRamSlots(totalSlots, qty, name);

  updatePrice();
  runCompatibility();
  scheduleAutosave();
}

// ─── Insert Fan (needs quantity; item 3: only highlight the fan slots used) ──
function insertFan(id, name, price, wattage) {
  const qtySelect = document.getElementById('fanqty-' + id);
  const qty = qtySelect ? parseInt(qtySelect.value, 10) : 1;
  fanQuantity = qty;

  if (build['fan']) {
    const oldCard = document.getElementById('card-' + build['fan'].id);
    if (oldCard) oldCard.classList.remove('selected-card');
  }
  build['fan'] = { id, name: `${name} (x${qty})`, price: price * qty, wattage: wattage * qty, baseName: name };

  const card = document.getElementById('card-' + id);
  if (card) card.classList.add('selected-card');

  drawFanSlots(qty, name);
  updatePrice();
  runCompatibility();
  scheduleAutosave();
}

// ─── SVG Slot Visual (fixes item 1: motherboard + cabinet now visually update) ──
function updateSVGSlot(type, name) {
  const short = name.length > 22 ? name.substring(0, 20) + '…' : name;

  if (type === 'motherboard') {
    const mbRect = document.getElementById('mb-rect');
    const mbLabel = document.getElementById('mb-label');
    if (mbRect) mbRect.classList.add('slot-filled-mb');
    if (mbLabel) mbLabel.setAttribute('fill', '#39ff14');
    const lbl = document.getElementById('lbl-mb');
    if (lbl) { lbl.textContent = short; lbl.setAttribute('visibility', 'visible'); }
    // item 11: redraw RAM slot count based on motherboard's ram_slots (max 4, never 8)
    // item 2: preserve the currently selected RAM fill count when motherboard changes
    const totalSlots = (build['motherboard'] && build['motherboard'].ramSlots) || 4;
    const filled = build['ram'] ? ramQuantity : 0;
    drawRamSlots(totalSlots, filled);
    return;
  }

  if (type === 'cabinet') {
    const outline = document.getElementById('cabinet-outline');
    const top = document.getElementById('cabinet-top');
    if (outline) outline.classList.add('slot-filled-cabinet');
    if (top) top.setAttribute('fill', '#39ff1422');
    const lbl = document.getElementById('lbl-cabinet');
    if (lbl) { lbl.textContent = short; lbl.setAttribute('visibility', 'visible'); }
    return;
  }

  const slotId = SLOT_MAP[type];
  const labelId = LABEL_MAP[type];
  if (!slotId) return;
  const slot = document.getElementById(slotId);
  const label = labelId ? document.getElementById(labelId) : null;

  if (slot) {
    slot.classList.remove('slot-filled', 'slot-filled-gpu', 'slot-filled-psu', 'slot-filled-cooling');
    if (type === 'gpu') slot.classList.add('slot-filled-gpu');
    else if (type === 'psu') slot.classList.add('slot-filled-psu');
    else if (type === 'air_cooler' || type === 'liquid_cooler') slot.classList.add('slot-filled-cooling');
    else slot.classList.add('slot-filled');
  }
  if (label) {
    label.textContent = short;
    label.setAttribute('visibility', 'visible');
  }
}

// item 2 & 11: dynamically draw RAM slot rectangles on the motherboard.
// totalSlots = how many physical slots the motherboard has (2 or 4).
// filledCount = how many of those slots are actually being used by the selected RAM (item 2).
function drawRamSlots(totalSlots, filledCount, ramName) {
  const g = document.getElementById('slot-ram');
  if (!g) return;
  g.innerHTML = '';
  const startX = 115, slotWidth = 10, gap = 4, y = 75, height = 60;
  const count = totalSlots >= 4 ? 4 : 2;   // item 11: cap at 4, never 8
  const filled = Math.min(filledCount || 0, count);

  for (let i = 0; i < count; i++) {
    const x = startX + i * (slotWidth + gap);
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x); rect.setAttribute('y', y);
    rect.setAttribute('width', slotWidth); rect.setAttribute('height', height);
    rect.setAttribute('rx', 2);
    if (i < filled) {
      // this slot is actually populated by the chosen RAM quantity
      rect.setAttribute('fill', '#0a1a0a');
      rect.setAttribute('stroke', '#39ff14');
      rect.setAttribute('stroke-width', '2');
    } else {
      // empty/unused slot
      rect.setAttribute('fill', '#111c2e');
      rect.setAttribute('stroke', '#1e3a5f');
      rect.setAttribute('stroke-width', '1');
    }
    g.appendChild(rect);
  }
  const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  text.setAttribute('x', startX + (count * (slotWidth + gap)) / 2 - gap / 2);
  text.setAttribute('y', y + height + 13);
  text.setAttribute('text-anchor', 'middle'); text.setAttribute('fill', filled > 0 ? '#39ff14' : '#3a6fa0');
  text.setAttribute('font-size', '7'); text.setAttribute('font-family', 'Rajdhani,sans-serif');
  text.textContent = filled > 0 ? `RAM: ${filled}/${count} slots used` : `RAM (${count} slots)`;
  g.appendChild(text);
}

// item 3: dynamically draw fan circles in the fan zone, only highlighting the quantity selected
// item: fan box mirrors the motherboard box (same height), holds up to 8 fans in a 2x4 grid
function drawFanSlots(filledCount, fanName) {
  const g = document.getElementById('slot-fan');
  if (!g) return;
  g.innerHTML = '';
  const count = Math.min(filledCount || 0, 8);

  const boxX = 215, boxY = 50, boxW = 90, boxH = 230;
  const cols = 2, rows = 4;
  const r = 16;
  const cellW = boxW / cols, cellH = (boxH - 24) / rows; // leave room at top for "FANS" label

  const positions = [];
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      positions.push({
        cx: boxX + cellW * col + cellW / 2,
        cy: boxY + 24 + cellH * row + cellH / 2,
      });
    }
  }

  for (let i = 0; i < 8; i++) {
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', positions[i].cx);
    circle.setAttribute('cy', positions[i].cy);
    circle.setAttribute('r', r);
    if (i < count) {
      circle.setAttribute('fill', '#0a1a2a');
      circle.setAttribute('stroke', '#00e5ff');
      circle.setAttribute('stroke-width', '2');
    } else {
      circle.setAttribute('fill', '#111c2e');
      circle.setAttribute('stroke', '#1e3a5f');
      circle.setAttribute('stroke-width', '1');
    }
    g.appendChild(circle);

    // small blade hint inside filled fans for a more "fan-like" look
    if (i < count) {
      const blade = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      blade.setAttribute('cx', positions[i].cx);
      blade.setAttribute('cy', positions[i].cy);
      blade.setAttribute('r', 5);
      blade.setAttribute('fill', 'none');
      blade.setAttribute('stroke', '#00e5ff');
      blade.setAttribute('stroke-width', '1');
      blade.setAttribute('opacity', '0.6');
      g.appendChild(blade);
    }
  }

  const fanBoxLabel = document.getElementById('fan-box-rect');
  if (fanBoxLabel) {
    if (count > 0) fanBoxLabel.classList.add('slot-filled-mb');
    else fanBoxLabel.classList.remove('slot-filled-mb');
  }
  const lbl = document.getElementById('lbl-fanbox');
  if (lbl) {
    lbl.textContent = count > 0 ? `${count}/8 fans` : '';
    lbl.setAttribute('visibility', count > 0 ? 'visible' : 'hidden');
  }
}

// ─── Price Tracker ───────────────────────────────────────────────────────────
function updatePrice() {
  const breakdown = document.getElementById('price-breakdown');
  const totalEl = document.getElementById('price-total');
  let html = '', total = 0;
  for (const comp of Object.values(build)) {
    total += comp.price;
    html += `<div class="price-line"><span class="pname">${comp.name}</span><span>₹${comp.price.toLocaleString('en-IN')}</span></div>`;
  }
  breakdown.innerHTML = html || '<div class="price-empty">No components selected yet.</div>';
  totalEl.textContent = '₹' + total.toLocaleString('en-IN');
}

// ─── Compatibility Check ─────────────────────────────────────────────────────
async function runCompatibility() {
  const components = {};
  for (const [type, comp] of Object.entries(build)) components[type] = comp.id;
  try {
    const res = await fetch('/api/compatibility', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ components, ram_quantity: ramQuantity }),
    });
    const data = await res.json();
    renderCompatibility(data.checks);
  } catch (e) { console.error('Compatibility check failed:', e); }
}

function renderCompatibility(checks) {
  const box = document.getElementById('compat-results');
  if (!checks || checks.length === 0) {
    box.innerHTML = '<p class="compat-pending">Add components to see compatibility results.</p>';
    return;
  }
  box.innerHTML = checks.map(c => `
    <div class="compat-item compat-${c.status}">
      <span class="compat-icon">${c.status === 'ok' ? '✅' : '❌'}</span>
      <div><div class="compat-label">${c.component}</div><div class="compat-msg">${c.message}</div></div>
    </div>`).join('');
}

// ─── Autosave (item 22) ──────────────────────────────────────────────────────
function scheduleAutosave() {
  document.getElementById('autosave-note').textContent = 'Saving…';
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(doAutosave, 800);
}

async function doAutosave() {
  if (Object.keys(build).length === 0) return;
  const components = {}; let total = 0;
  for (const [type, comp] of Object.entries(build)) { components[type] = comp.id; total += comp.price; }
  try {
    const res = await fetch('/api/save_build', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ components, total_price: total, ram_quantity: ramQuantity, build_id: currentBuildId }),
    });
    const data = await res.json();
    if (data.success) {
      currentBuildId = data.build_id;
      const note = document.getElementById('autosave-note');
      note.textContent = '✓ Autosaved';
      setTimeout(() => { if (note.textContent === '✓ Autosaved') note.textContent = ''; }, 2000);
    }
  } catch (e) { console.error('Autosave failed:', e); }
}

// ─── Save Build (manual) ─────────────────────────────────────────────────────
async function saveBuild() {
  if (Object.keys(build).length === 0) {
    showAlert('Please select at least one component before saving.', 'warning');
    return;
  }
  const components = {}; let total = 0;
  for (const [type, comp] of Object.entries(build)) { components[type] = comp.id; total += comp.price; }
  try {
    const res = await fetch('/api/save_build', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ components, total_price: total, ram_quantity: ramQuantity, build_id: currentBuildId }),
    });
    const data = await res.json();
    if (data.success) {
      currentBuildId = data.build_id;
      showAlert('Build saved successfully! View it under "My Builds".', 'success');
    }
  } catch (e) { showAlert('Failed to save build. Please try again.', 'danger'); }
}

// ─── Reset Build (item 26) ───────────────────────────────────────────────────
function resetBuild() {
  if (!confirm('Reset your current build? This will clear all selected components.')) return;
  for (const key of Object.keys(build)) delete build[key];
  ramQuantity = 1;
  fanQuantity = 0;
  currentBuildId = null;
  document.querySelectorAll('.selected-card').forEach(c => c.classList.remove('selected-card'));
  updatePrice();
  renderCompatibility([]);
  document.getElementById('autosave-note').textContent = '';
  // Reset SVG
  document.querySelectorAll('.slot-filled, .slot-filled-gpu, .slot-filled-psu, .slot-filled-cooling, .slot-filled-mb, .slot-filled-cabinet')
    .forEach(el => el.classList.remove('slot-filled', 'slot-filled-gpu', 'slot-filled-psu', 'slot-filled-cooling', 'slot-filled-mb', 'slot-filled-cabinet'));
  document.querySelectorAll('.slot-label').forEach(el => el.setAttribute('visibility', 'hidden'));
  drawRamSlots(4, 0);
  drawFanSlots(0);
  showAlert('Build reset.', 'info');
}

// ─── Confirm Build → goes to Accessories step (item 33) ─────────────────────
async function confirmBuild() {
  const missing = [];
  for (const r of REQUIRED) if (!build[r]) missing.push(r.toUpperCase());
  const hasStorage = STORAGE.some(s => build[s]);
  if (!hasStorage) missing.push('STORAGE (SSD or HDD)');
  const hasCooling = COOLING.some(c => build[c]);
  if (!hasCooling) missing.push('COOLING (Air or Liquid)');

  if (missing.length > 0) {
    showAlert('Please complete your build before proceeding. Missing: ' + missing.join(', '), 'danger');
    return;
  }

  await runCompatibility();

  const components = {}; let total = 0;
  for (const [type, comp] of Object.entries(build)) { components[type] = comp.id; total += comp.price; }

  try {
    const res = await fetch('/api/save_build', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ components, total_price: total, ram_quantity: ramQuantity, build_id: currentBuildId }),
    });
    const data = await res.json();
    if (data.success) {
      currentBuildId = data.build_id;
      window.location.href = `/builder/accessories?build_id=${data.build_id}&core_total=${total}`;
    }
  } catch (e) { showAlert('Failed to proceed. Please try again.', 'danger'); }
}

// ─── Sorting (items 14 & 29) ─────────────────────────────────────────────────
function sortComponentCards(type, criteria) {
  const list = document.getElementById('list-' + type);
  if (!list) return;
  const cards = Array.from(list.children);
  cards.sort((a, b) => {
    if (criteria === 'price-asc') return parseFloat(a.dataset.price) - parseFloat(b.dataset.price);
    if (criteria === 'price-desc') return parseFloat(b.dataset.price) - parseFloat(a.dataset.price);
    if (criteria === 'brand') return a.dataset.brand.localeCompare(b.dataset.brand);
    if (criteria === 'performance') return parseFloat(b.dataset.performance) - parseFloat(a.dataset.performance);
    return parseFloat(a.dataset.order) - parseFloat(b.dataset.order);
  });
  cards.forEach(c => list.appendChild(c));
}

// ─── AI Build Advisor (item 6, rule-based) ───────────────────────────────────
let advisorResult = null;

async function runAdvisor() {
  const useCase = document.getElementById('advisor-usecase').value;
  const budget = parseFloat(document.getElementById('advisor-budget').value);
  if (!budget || budget <= 0) {
    showAlert('Please enter a valid budget.', 'warning');
    return;
  }
  const resultsBox = document.getElementById('advisor-results');
  resultsBox.classList.remove('hidden');
  resultsBox.innerHTML = '<p class="compat-pending">Thinking through the best build for your budget…</p>';

  try {
    const res = await fetch('/api/recommend_build', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ use_case: useCase, budget }),
    });
    const data = await res.json();
    if (data.error) {
      resultsBox.innerHTML = `<p class="compat-pending advisor-error">⚠️ ${data.message || data.error}</p>`;
      advisorResult = null;
      return;
    }
    advisorResult = data;
    renderAdvisorResult(data);
  } catch (e) {
    resultsBox.innerHTML = '<p class="compat-pending">Something went wrong. Please try again.</p>';
  }
}

function renderAdvisorResult(data) {
  const resultsBox = document.getElementById('advisor-results');
  let html = '';
  for (const [type, comp] of Object.entries(data.picks)) {
    let qtyLabel = '';
    let lineTotal = comp.price;
    if (type === 'ram' && data.ram_quantity) { qtyLabel = ` (x${data.ram_quantity})`; lineTotal = comp.price * data.ram_quantity; }
    if (type === 'fan' && data.fan_quantity) { qtyLabel = ` (x${data.fan_quantity})`; lineTotal = comp.price * data.fan_quantity; }
    html += `<div class="advisor-pick"><span>${type.toUpperCase()}: ${comp.name}${qtyLabel}</span><span>₹${lineTotal.toLocaleString('en-IN')}</span></div>`;
  }
  if (data.notes && data.notes.length) {
    html += data.notes.map(n => `<div class="advisor-note">💡 ${n}</div>`).join('');
  }
  html += `<div class="advisor-total">Total: ₹${data.total.toLocaleString('en-IN')}</div>`;
  html += `<button class="btn btn-primary advisor-apply-btn" onclick="applyAdvisorBuild()">✅ Apply This Build</button>`;
  resultsBox.innerHTML = html;
}

function applyAdvisorBuild() {
  if (!advisorResult) return;
  for (const key of Object.keys(build)) delete build[key];
  document.querySelectorAll('.selected-card').forEach(c => c.classList.remove('selected-card'));
  ramQuantity = advisorResult.ram_quantity || 2;
  fanQuantity = advisorResult.fan_quantity || 0;

  for (const [type, comp] of Object.entries(advisorResult.picks)) {
    const card = document.getElementById('card-' + comp.id);
    if (type === 'ram') {
      build['ram'] = { id: comp.id, name: `${comp.name} (x${ramQuantity})`, price: comp.price * ramQuantity, wattage: (comp.wattage || 0) * ramQuantity };
      if (card) card.classList.add('selected-card');
      continue; // RAM slots drawn after motherboard is placed below
    }
    if (type === 'fan') {
      build['fan'] = { id: comp.id, name: `${comp.name} (x${fanQuantity})`, price: comp.price * fanQuantity, wattage: (comp.wattage || 0) * fanQuantity };
      if (card) card.classList.add('selected-card');
      continue; // fan slots drawn explicitly below
    }
    build[type] = { id: comp.id, name: comp.name, price: comp.price, wattage: comp.wattage || 0, ramSlots: comp.ram_slots || 0 };
    if (card) card.classList.add('selected-card');
    updateSVGSlot(type, comp.name);
  }

  // Now that motherboard (if any) has set the slot count, draw RAM fill + fan fill explicitly
  const totalSlots = (build['motherboard'] && build['motherboard'].ramSlots) || 4;
  drawRamSlots(totalSlots, build['ram'] ? ramQuantity : 0);
  drawFanSlots(build['fan'] ? fanQuantity : 0);

  updatePrice();
  runCompatibility();
  scheduleAutosave();
  showAlert('Advisor build applied! Review and adjust as needed.', 'success');
}

// ─── Alert Helper ────────────────────────────────────────────────────────────
function showAlert(message, type) {
  const existing = document.querySelector('.js-alert');
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.className = `flash flash-${type} js-alert`;
  div.style.cssText = 'position:fixed;top:70px;left:50%;transform:translateX(-50%);z-index:999;min-width:320px;max-width:90vw;text-align:center;';
  div.textContent = message;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 4000);
}

// ─── Init: draw default 4 RAM slots on load ──────────────────────────────────
document.addEventListener('DOMContentLoaded', () => drawRamSlots(4));
