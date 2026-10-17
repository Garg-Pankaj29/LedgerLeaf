// LedgerLeaf Client Application Logic with Real FastAPI Backend Integration
import { api } from './api.js?v=3';

// ---------- Theme Management ----------
(function () {
  const b = document.getElementById('theme');
  if (!b) return;
  const m = ['auto', 'light', 'dark'];
  let i = 0;
  b.onclick = () => {
    i = (i + 1) % 3;
    const r = document.documentElement;
    if (m[i] === 'auto') r.removeAttribute('data-theme');
    else r.setAttribute('data-theme', m[i]);
    b.textContent = 'Theme: ' + m[i];
  };
})();

// ---------- Synthetic Samples & Demonstration Data ----------
const SAMPLES = [
  {
    name: 'Cafe receipt',
    demo: true,
    text: `Juniper & Oak Coffee\nReceipt #R-20418\nDate: 2026-10-03\n2 x Oat latte\n1 x Almond croissant\nSubtotal: $9.00\nTax (8%): $0.72\nTotal: $9.72`,
  },
  {
    name: 'Design invoice (bad math)',
    demo: true,
    text: `Northfield Type Foundry\nInvoice No: INV-3307\nDate: 2026-09-21\nLicence: font software, 3 seats\nSubtotal: €1,200.00\nVAT (19%): €228.00\nTotal: €1,438.00`,
  },
  {
    name: 'Taxi slip (missing date)',
    demo: true,
    text: `Metro Cab Services\nReceipt No: MC-88120\nAirport ride\nTotal: ₹640.00`,
  },
  {
    name: 'Paste your own',
    demo: false,
    text: '',
  },
];

const CATS = ['Software', 'Meals', 'Travel', 'Office', 'Services', 'Other'];
const RULES = [
  ['Software', /software|licen[cs]e|subscription|hosting|domain/i],
  ['Meals', /coffee|latte|cafe|restaurant|lunch|dinner/i],
  ['Travel', /cab|taxi|ride|flight|hotel|train/i],
  ['Office', /paper|printer|desk|stationery/i],
  ['Services', /consult|design|freelance|service/i],
];
const SYM = { '$': 'USD', '€': 'EUR', '£': 'GBP', '₹': 'INR' };
const AMT = '([\\d,]+(?:\\.\\d{1,2})?)';

// Fallback rule parser for demo samples
function extractRuleBased(t) {
  const f = {};
  const set = (k, v, s, e, state) =>
    (f[k] = { v, s, e, state: state || (v == null || v === '' ? 'missing' : 'found') });

  const first = t.split('\n').find((l) => l.trim());
  if (first) {
    const s = t.indexOf(first);
    set('vendor', first.trim(), s, s + first.length);
  } else {
    set('vendor', '', 0, 0);
  }

  const m = (re) => {
    const r = new RegExp(re, 'imd').exec(t);
    return r ? { v: r[1], s: r.indices[1][0], e: r.indices[1][1] } : null;
  };

  const put = (k, re, fn) => {
    const r = m(re);
    r ? set(k, fn ? fn(r.v) : r.v, r.s, r.e) : set(k, '', 0, 0);
  };

  put('number', '(?:invoice|receipt)\\s*(?:no\\.?|number|#)?\\s*[:#]?\\s*([A-Z0-9][A-Z0-9-]{2,})');
  put('date', '(?<!due )\\bdate[:\\s]+(\\d{4}-\\d{2}-\\d{2})');
  put('subtotal', 'sub-?total[^\\n:]*:\\s*[^\\d\\n]*?' + AMT, (n) => n.replace(/,/g, ''));
  put('tax', '(?:tax|vat|gst)[^\\n:]*:\\s*[^\\d\\n]*?' + AMT, (n) => n.replace(/,/g, ''));
  put('total', '^\\s*(?:grand\\s+)?total[^\\n:]*:\\s*[^\\d\\n]*?' + AMT, (n) => n.replace(/,/g, ''));

  const cs = /[$€£₹]/d.exec(t);
  if (cs) {
    set('currency', SYM[cs[0]], cs.index, cs.index + 1);
  } else {
    const cc = /\b(USD|EUR|GBP|INR)\b/d.exec(t);
    cc ? set('currency', cc[1], cc.indices[1][0], cc.indices[1][1]) : set('currency', '', 0, 0);
  }

  const r = RULES.find((r) => r[1].test(t));
  set('category', r ? r[0] : '', 0, 0, r ? 'guess' : 'missing');
  return f;
}

const LABELS = {
  vendor: 'Vendor',
  number: 'Number',
  date: 'Date',
  currency: 'Currency',
  subtotal: 'Subtotal',
  tax: 'Tax',
  total: 'Total',
  category: 'Category',
};
const ORDER = Object.keys(LABELS);

// Application State
let uploadedDocuments = [];
let selectedType = 'sample'; // 'uploaded' | 'sample'
let selectedDocId = null;
let selectedSampleIdx = 0;
let currentDocument = null;
let currentExtraction = null;
let fields = {};
let activeField = null;
let demoTexts = SAMPLES.map((s) => s.text);
let debounceTimer = null;

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const num = (v) => (v === '' || v == null ? null : Number(String(v).replace(/,/g, '')));

// ---------- AI Status Polling ----------
async function refreshAIStatus() {
  const el = $('ai-status');
  if (!el) return;
  try {
    const data = await api.getAIStatus();
    if (data.status === 'connected') {
      el.className = 'chip ok';
      const modelName = data.model || 'Connected';
      el.textContent = `● AI: ${modelName}`;
      el.title = `LM Studio connected (${modelName}) at ${data.endpoint || '127.0.0.1:1234'}`;
    } else {
      el.className = 'chip warn';
      el.textContent = `○ AI: offline`;
      el.title = data.message || 'LM Studio server is not reachable at 127.0.0.1:1234';
    }
  } catch (e) {
    el.className = 'chip miss';
    el.textContent = `○ AI: unavailable`;
    el.title = `Cannot connect to backend (${api.getBaseUrl()}): ${e.message}`;
    console.warn('[LedgerLeaf] Backend AI check failed:', e);
  }
}

// ---------- Document Management & Tabs ----------
async function loadDocuments() {
  try {
    uploadedDocuments = await api.getDocuments();
  } catch (e) {
    console.warn('Could not load uploaded documents from backend:', e);
    uploadedDocuments = [];
  }
  renderTabs();
}

function renderTabs() {
  const tabsEl = $('tabs');
  if (!tabsEl) return;

  let html = '<div class="tabs-container">';

  // 1. Uploaded Documents Section
  html += '<div class="tabs-group">';
  html += '<span class="tabs-label">Your files:</span>';
  html += `<button class="btn" id="btn-upload-trigger" style="padding:4px 12px;font-size:0.85rem">＋ Upload</button>`;

  if (uploadedDocuments.length === 0) {
    html += '<span style="font-size:0.85rem;color:var(--mute)">No uploads yet</span>';
  } else {
    uploadedDocuments.forEach((doc) => {
      const isSelected = selectedType === 'uploaded' && selectedDocId === doc.id;
      const statusClass = doc.processing_status === 'approved' ? 'approved' : doc.processing_status === 'failed' ? 'missing' : 'guess';
      html += `<button class="ghost ${isSelected ? 'active' : ''}" data-type="uploaded" data-id="${doc.id}">
        ${esc(doc.original_filename)} <span class="chip ${statusClass}" style="font-size:0.7rem;padding:0 5px">${doc.processing_status}</span>
      </button>`;
    });
  }
  html += '</div>';

  // 2. Demo Synthetic Samples Section
  html += '<div class="tabs-group" style="margin-top:6px">';
  html += '<span class="tabs-label">Samples:</span>';
  SAMPLES.forEach((s, idx) => {
    const isSelected = selectedType === 'sample' && selectedSampleIdx === idx;
    html += `<button class="ghost ${isSelected ? 'active' : ''}" data-type="sample" data-idx="${idx}">
      ${esc(s.name)}${s.demo ? ' <span class="chip" style="font-size:0.7rem;padding:0 5px">demo</span>' : ''}
    </button>`;
  });
  html += '</div>';

  html += '</div>';
  tabsEl.innerHTML = html;

  // Bind clicks
  const trigger = $('btn-upload-trigger');
  if (trigger) {
    trigger.onclick = () => $('file-input').click();
  }

  tabsEl.querySelectorAll('button[data-type="uploaded"]').forEach((btn) => {
    btn.onclick = () => {
      selectedType = 'uploaded';
      selectedDocId = btn.dataset.id;
      activeField = null;
      loadActiveDocument();
    };
  });

  tabsEl.querySelectorAll('button[data-type="sample"]').forEach((btn) => {
    btn.onclick = () => {
      selectedType = 'sample';
      selectedSampleIdx = +btn.dataset.idx;
      activeField = null;
      loadActiveDocument();
    };
  });
}

// ---------- Load & Render Selected Document ----------
async function loadActiveDocument() {
  renderTabs();
  const msgEl = $('msg');
  if (msgEl) msgEl.textContent = '';

  if (selectedType === 'uploaded') {
    await loadUploadedDoc(selectedDocId);
  } else {
    loadSampleDoc(selectedSampleIdx);
  }
}

async function loadUploadedDoc(id) {
  try {
    currentDocument = await api.getDocument(id);
    try {
      currentExtraction = await api.getDocumentExtraction(id);
    } catch {
      currentExtraction = null;
    }

    renderDocView();
    renderFieldsView();
  } catch (e) {
    $('docview').innerHTML = `<div class="empty">Error loading document: ${esc(e.message)}</div>`;
  }
}

function loadSampleDoc(idx) {
  currentDocument = null;
  currentExtraction = null;
  fields = extractRuleBased(demoTexts[idx]);
  renderDocView();
  renderFieldsView();
}

// ---------- Render Document Viewer ----------
function renderDocView() {
  const el = $('docview');
  if (!el) return;

  if (selectedType === 'uploaded') {
    const doc = currentDocument;
    if (!doc) return;

    let headerHtml = `<div class="doc-header">
      <div class="doc-title">${esc(doc.original_filename)} <span class="chip ${doc.processing_status}">${doc.processing_status}</span></div>
      <div class="doc-actions">
        ${doc.processing_status !== 'processing' ? `<button class="ghost" id="btn-process" style="padding:4px 10px;font-size:0.8rem">⚡ Run AI</button>` : ''}
        <button class="ghost" id="btn-delete-doc" style="padding:4px 10px;font-size:0.8rem;color:var(--bad)">Delete</button>
      </div>
    </div>`;

    if (doc.processing_status === 'processing') {
      el.innerHTML = headerHtml + `<div class="empty" style="border-style:solid"><span class="chip processing">Processing with local AI model...</span></div>`;
      return;
    }

    if (!doc.extracted_text) {
      el.innerHTML = headerHtml + `<div class="empty">
        <p>No text extracted yet.</p>
        <button class="btn" id="btn-process-empty">Start AI Extraction</button>
      </div>`;
      const btn = $('btn-process-empty');
      if (btn) btn.onclick = () => triggerProcess(doc.id);
      bindDocHeaderActions(doc.id);
      return;
    }

    // Render text with source marks
    const text = doc.extracted_text;
    const spans = [];

    if (currentExtraction && currentExtraction.field_provenances) {
      currentExtraction.field_provenances.forEach((p) => {
        if (p.start_offset != null && p.end_offset != null && p.end_offset > p.start_offset) {
          spans.push({ k: p.field_name, s: p.start_offset, e: p.end_offset });
        }
      });
      spans.sort((a, b) => a.s - b.s);
    }

    let out = '', p = 0;
    for (const span of spans) {
      if (span.s < p) continue;
      out += esc(text.slice(p, span.s)) +
        `<mark data-k="${span.k}" tabindex="0" role="button" aria-label="Source of ${span.k}" class="${activeField === span.k ? 'on' : ''}">${esc(text.slice(span.s, span.e))}</mark>`;
      p = span.e;
    }
    out += esc(text.slice(p));

    el.innerHTML = headerHtml + `<pre class="doc">${out}</pre>`;
    bindDocHeaderActions(doc.id);

    el.querySelectorAll('mark').forEach((m) => {
      const go = () => {
        activeField = m.dataset.k;
        renderDocView();
        const input = document.querySelector(`[data-f="${activeField}"]`);
        if (input) input.focus();
      };
      m.onclick = go;
      m.onkeydown = (e) => { if (e.key === 'Enter') go(); };
    });

  } else {
    // Sample / Paste your own
    if (!SAMPLES[selectedSampleIdx].demo) {
      el.innerHTML = `<textarea class="doc" id="paste" aria-label="Paste receipt or invoice text" placeholder="Paste text from a receipt.">${esc(demoTexts[selectedSampleIdx])}</textarea>`;
      const pasteEl = $('paste');
      if (pasteEl) {
        pasteEl.oninput = (e) => {
          demoTexts[selectedSampleIdx] = e.target.value;
          fields = extractRuleBased(demoTexts[selectedSampleIdx]);
          renderFieldsView();
        };
      }
      return;
    }

    const t = demoTexts[selectedSampleIdx];
    const sp = ORDER.filter((k) => fields[k].state !== 'missing' && fields[k].e > fields[k].s && fields[k].state !== 'guess' && k !== 'category')
      .map((k) => [k, fields[k].s, fields[k].e])
      .sort((a, b) => a[1] - b[1]);

    let out = '', p = 0;
    for (const [k, s, e] of sp) {
      if (s < p) continue;
      out += esc(t.slice(p, s)) + `<mark data-k="${k}" tabindex="0" role="button" class="${activeField === k ? 'on' : ''}">${esc(t.slice(s, e))}</mark>`;
      p = e;
    }
    out += esc(t.slice(p));
    el.innerHTML = `<pre class="doc">${out}</pre>`;

    el.querySelectorAll('mark').forEach((m) => {
      const go = () => {
        activeField = m.dataset.k;
        renderDocView();
        const input = document.querySelector(`[data-f="${activeField}"]`);
        if (input) input.focus();
      };
      m.onclick = go;
      m.onkeydown = (e) => { if (e.key === 'Enter') go(); };
    });
  }
}

function bindDocHeaderActions(docId) {
  const btnProcess = $('btn-process');
  if (btnProcess) btnProcess.onclick = () => triggerProcess(docId);

  const btnDelete = $('btn-delete-doc');
  if (btnDelete) {
    btnDelete.onclick = async () => {
      if (!confirm('Are you sure you want to delete this document?')) return;
      try {
        await api.deleteDocument(docId);
        selectedType = 'sample';
        selectedSampleIdx = 0;
        await loadDocuments();
        await loadActiveDocument();
      } catch (e) {
        alert(e.message);
      }
    };
  }
}

async function triggerProcess(docId) {
  const msgEl = $('msg');
  if (msgEl) msgEl.textContent = 'Processing with local AI...';
  try {
    await api.processDocument(docId);
    await loadDocuments();
    await loadActiveDocument();
  } catch (e) {
    alert(`Processing failed: ${e.message}`);
    await loadDocuments();
    await loadActiveDocument();
  }
}

// ---------- Render Fields & Guard ----------
function renderFieldsView() {
  const fieldsEl = $('fields');
  if (!fieldsEl) return;

  if (selectedType === 'uploaded') {
    const ext = currentExtraction || {};
    const provs = (ext.field_provenances || []).reduce((acc, p) => { acc[p.field_name] = p; return acc; }, {});

    fieldsEl.innerHTML = ORDER.map((k) => {
      const p = provs[k] || provs[k === 'number' ? 'invoice_number' : k];
      let val = '';
      if (k === 'vendor') val = ext.vendor ?? '';
      else if (k === 'number') val = ext.invoice_number ?? '';
      else if (k === 'date') val = ext.date ?? '';
      else if (k === 'currency') val = ext.currency ?? 'USD';
      else if (k === 'subtotal') val = ext.subtotal_decimal != null ? ext.subtotal_decimal.toFixed(2) : (ext.subtotal != null ? (ext.subtotal / 100).toFixed(2) : '');
      else if (k === 'tax') val = ext.tax_decimal != null ? ext.tax_decimal.toFixed(2) : (ext.tax != null ? (ext.tax / 100).toFixed(2) : '');
      else if (k === 'total') val = ext.total_decimal != null ? ext.total_decimal.toFixed(2) : (ext.total != null ? (ext.total / 100).toFixed(2) : '');
      else if (k === 'category') val = ext.category ?? '';

      const chipState = (p && p.is_user_edited) ? 'edited' : (val ? 'found' : 'missing');
      const chipLabel = (p && p.is_user_edited) ? 'you confirmed' : (val ? 'found in text' : 'not found');

      const inp = k === 'category'
        ? `<select data-f="${k}" id="f-${k}" aria-label="Category"><option value="">Choose…</option>${CATS.map((c) => `<option ${val === c ? 'selected' : ''}>${c}</option>`).join('')}</select>`
        : `<input data-f="${k}" id="f-${k}" value="${esc(val)}" ${['subtotal', 'tax', 'total'].includes(k) ? 'inputmode="decimal"' : ''} aria-label="${LABELS[k]}">`;

      return `<div class="row ${!val ? 'miss' : ''} ${activeField === k ? 'pin' : ''}">
        <label for="f-${k}">${LABELS[k]}</label>${inp}<span class="chip ${chipState}">${chipLabel}</span>
      </div>`;
    }).join('');

    // Bind inputs to debounced PATCH update
    document.querySelectorAll('[data-f]').forEach((input) => {
      input.onfocus = () => pinField(input.dataset.f);
      input.oninput = input.onchange = () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => handleFieldChangeUploaded(), 400);
      };
    });

    // Run backend validation
    validateUploaded();

  } else {
    // Demo Sample editing
    fieldsEl.innerHTML = ORDER.map((k) => {
      const f = fields[k];
      const inp = k === 'category'
        ? `<select data-f="${k}" id="f-${k}" aria-label="Category"><option value="">Choose…</option>${CATS.map((c) => `<option ${f.v === c ? 'selected' : ''}>${c}</option>`).join('')}</select>`
        : `<input data-f="${k}" id="f-${k}" value="${esc(String(f.v ?? ''))}" ${['subtotal', 'tax', 'total'].includes(k) ? 'inputmode="decimal"' : ''} aria-label="${LABELS[k]}">`;

      const chipState = f.state === 'found' ? 'found' : f.state === 'edited' ? 'edited' : f.state === 'guess' ? 'guess' : 'missing';
      const chipLabel = f.state === 'found' ? 'found in text' : f.state === 'edited' ? 'you confirmed' : f.state === 'guess' ? 'rule guess: check' : 'not found';

      return `<div class="row ${f.state === 'missing' ? 'miss' : ''} ${activeField === k ? 'pin' : ''}">
        <label for="f-${k}">${LABELS[k]}</label>${inp}<span class="chip ${chipState}">${chipLabel}</span>
      </div>`;
    }).join('');

    document.querySelectorAll('[data-f]').forEach((input) => {
      input.onfocus = () => pinField(input.dataset.f);
      input.oninput = input.onchange = () => {
        const f = fields[input.dataset.f];
        f.v = input.value.trim();
        f.state = f.v ? 'edited' : 'missing';
        guardDemo();
        input.closest('.row').classList.toggle('miss', !f.v);
        input.closest('.row').querySelector('.chip').className = `chip ${f.state}`;
      };
    });

    guardDemo();
  }
}

function pinField(k) {
  activeField = k;
  document.querySelectorAll('.row').forEach((r) => {
    const input = r.querySelector('[data-f]');
    if (input) r.classList.toggle('pin', input.dataset.f === k);
  });
  renderDocView();
  const mark = document.querySelector('mark.on');
  if (mark) mark.scrollIntoView({ block: 'nearest' });
}

// ---------- Real Document Validation & Editing ----------
async function handleFieldChangeUploaded() {
  if (!currentDocument || selectedType !== 'uploaded') return;

  const getV = (k) => {
    const el = document.querySelector(`[data-f="${k}"]`);
    return el ? el.value.trim() : null;
  };

  const payload = {
    vendor: getV('vendor') || null,
    invoice_number: getV('number') || null,
    date: getV('date') || null,
    currency: getV('currency') || 'USD',
    subtotal: num(getV('subtotal')),
    tax: num(getV('tax')),
    total: num(getV('total')),
    category: getV('category') || null,
  };

  try {
    currentExtraction = await api.updateDocumentExtraction(currentDocument.id, payload);
    await validateUploaded();
  } catch (e) {
    console.error('Update extraction error:', e);
  }
}

async function validateUploaded() {
  if (!currentDocument || selectedType !== 'uploaded') return;
  const g = $('guard');
  const approveBtn = $('approve');

  try {
    const val = await api.validateDocument(currentDocument.id);
    g.className = 'guard ' + (val.issues.length ? 'bad' : val.warnings.length ? 'warn' : 'ok');
    g.innerHTML = val.issues.length
      ? '<b>Not ready to approve</b><ul>' + val.issues.map((i) => `<li>${esc(i)}</li>`).join('') + '</ul>' +
        (val.warnings.length ? '<ul>' + val.warnings.map((i) => `<li>${esc(i)}</li>`).join('') + '</ul>' : '')
      : val.warnings.length
      ? '<b>Checks pass, with notes</b><ul>' + val.warnings.map((i) => `<li>${esc(i)}</li>`).join('') + '</ul>'
      : '<b>All checks pass</b>Amounts add up and required fields are filled.';

    if (approveBtn) approveBtn.disabled = !val.can_approve;
  } catch (e) {
    g.className = 'guard bad';
    g.innerHTML = `<b>Validation Error</b>${esc(e.message)}`;
    if (approveBtn) approveBtn.disabled = true;
  }
}

function guardDemo() {
  const g = $('guard');
  if (!g) return;
  const F = (k) => fields[k].v;
  const issues = [];
  const warns = [];

  ['vendor', 'date', 'currency', 'total', 'category'].forEach((k) => {
    if (!F(k)) issues.push(LABELS[k] + ' is missing. Enter it from the document.');
  });

  const d = F('date');
  if (d && (!/^\d{4}-\d{2}-\d{2}$/.test(d) || isNaN(Date.parse(d)))) {
    issues.push('Date must be a real date like 2026-10-03.');
  }

  ['subtotal', 'tax', 'total'].forEach((k) => {
    const v = F(k);
    if (v && !(num(v) >= 0)) issues.push(LABELS[k] + ' must be a number.');
  });

  const s = num(F('subtotal')), t = num(F('tax')), T = num(F('total'));
  if (s != null && t != null && T != null && s >= 0 && t >= 0 && T >= 0) {
    const sum = Math.round((s + t) * 100) / 100;
    if (Math.abs(sum - T) > 0.009) {
      issues.push(`Math guard: subtotal ${s.toFixed(2)} + tax ${t.toFixed(2)} = ${sum.toFixed(2)}, but total reads ${T.toFixed(2)} (off by ${Math.abs(sum - T).toFixed(2)}). Check the document.`);
    }
  } else if (T != null && (s == null || t == null)) {
    warns.push('Subtotal or tax is missing, so the total cannot be cross-checked.');
  }

  if (fields.category.state === 'guess') warns.push('Category is a keyword guess. Confirm or change it.');

  g.className = 'guard ' + (issues.length ? 'bad' : warns.length ? 'warn' : 'ok');
  g.innerHTML = issues.length
    ? '<b>Not ready to approve</b><ul>' + issues.map((i) => `<li>${esc(i)}</li>`).join('') + '</ul>' +
      (warns.length ? '<ul>' + warns.map((i) => `<li>${esc(i)}</li>`).join('') + '</ul>' : '')
    : warns.length
    ? '<b>Checks pass, with notes</b><ul>' + warns.map((i) => `<li>${esc(i)}</li>`).join('') + '</ul>'
    : '<b>All checks pass</b>Amounts add up and required fields are filled.';

  const approveBtn = $('approve');
  if (approveBtn) approveBtn.disabled = issues.length > 0;
}

// ---------- Approval & Ledger Handlers ----------
const approveBtn = $('approve');
if (approveBtn) {
  approveBtn.onclick = async () => {
    const msgEl = $('msg');

    if (selectedType === 'uploaded') {
      if (!currentDocument) return;
      try {
        const res = await api.approveDocument(currentDocument.id);
        msgEl.textContent = res.message || 'Approved and committed to the ledger.';
        await loadDocuments();
        await loadActiveDocument();
        await loadLedger();
      } catch (e) {
        alert(e.message);
      }
    } else {
      // Demo approval into ledger
      const F = (k) => fields[k].v;
      if (!F('vendor') || !F('date') || !F('total') || !F('category')) {
        alert('Please fill vendor, date, category, and total before approving.');
        return;
      }
      try {
        const payload = {
          vendor: F('vendor'),
          document_number: F('number') || null,
          date: F('date'),
          currency: F('currency') || 'USD',
          subtotal: num(F('subtotal')),
          tax: num(F('tax')),
          total: num(F('total')),
          category: F('category'),
          edits_count: Object.values(fields).filter((f) => f.state === 'edited').length,
        };
        const res = await api.addDemoSampleToLedger(payload);
        msgEl.textContent = `Demo record "${res.vendor}" approved into ledger.`;
        await loadLedger();
      } catch (e) {
        alert(e.message);
      }
    }
  };
}

// ---------- Persistent Ledger & Multi-Currency Analytics ----------
async function loadLedger() {
  const T = $('totals'), tb = $('table');
  if (!T || !tb) return;

  try {
    const [entries, summary] = await Promise.all([
      api.getLedger(),
      api.getLedgerSummary(),
    ]);

    if (!entries.length) {
      T.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <p>No approved records yet. Approve a reviewed document above or load demo samples to preview multi-currency analytics.</p>
        <button class="ghost" id="btn-seed-empty" style="margin-top:10px;font-size:0.85rem">＋ Load demo samples (USD, EUR, INR)</button>
      </div>`;
      tb.innerHTML = '';
      const seedEmpty = $('btn-seed-empty');
      if (seedEmpty) {
        seedEmpty.onclick = async () => {
          seedEmpty.disabled = true;
          seedEmpty.textContent = 'Loading samples...';
          try {
            await api.seedDemoSamples();
            await loadLedger();
          } catch (e) {
            alert(e.message);
          }
        };
      }
      return;
    }

    // Render multi-currency summary cards (never merged!)
    T.innerHTML = Object.entries(summary.currencies).map(([curr, b]) => {
      const catEntries = Object.entries(b.categories);
      const mx = catEntries.length ? Math.max(...catEntries.map(([, v]) => v)) : 1;
      return `<div class="card">
        <div>${esc(curr)} · ${b.count} approved</div>
        <div class="big">${b.total.toFixed(2)}</div>
        ${catEntries.sort((x, y) => y[1] - x[1]).map(([k, v]) => `
          <div class="bar"><span>${esc(k)}</span><i style="width:${Math.max(4, (v / mx) * 100)}%"></i><span style="text-align:right">${v.toFixed(2)}</span></div>
        `).join('')}
      </div>`;
    }).join('');

    // Render table
    tb.innerHTML = '<table><thead><tr><th>ID</th><th>Vendor</th><th>Date</th><th>Category</th><th class="n">Total</th><th>Trust</th><th></th></tr></thead><tbody>' +
      entries.map((r) => `
        <tr>
          <td>${esc(r.id.slice(0, 8))}</td>
          <td>${esc(r.vendor)}${r.is_demo ? ' <span class="chip">demo</span>' : ''}</td>
          <td>${esc(r.date)}</td>
          <td>${esc(r.category)}</td>
          <td class="n">${esc(r.currency)} ${(r.total / 100).toFixed(2)}</td>
          <td>${r.edits_count > 0 ? `${r.edits_count} fields corrected by you` : 'reviewed as extracted'}</td>
          <td><button class="ghost" data-del="${r.id}" aria-label="Remove entry">Remove</button></td>
        </tr>
      `).join('') +
      '</tbody></table>';

    tb.querySelectorAll('[data-del]').forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm('Remove this entry from the approved ledger?')) return;
        try {
          await api.deleteLedgerEntry(btn.dataset.del);
          await loadLedger();
          await loadDocuments();
        } catch (e) {
          alert(e.message);
        }
      };
    });

  } catch (e) {
    console.error('Failed to load ledger:', e);
  }
}

// CSV Export Handlers
const mkcsvBtn = $('mkcsv');
if (mkcsvBtn) {
  mkcsvBtn.onclick = async () => {
    try {
      const res = await fetch(api.getLedgerExportUrl());
      const text = await res.text();
      $('csv').value = text || 'Nothing to export yet. Approve a record first.';
    } catch {
      $('csv').value = 'Error fetching CSV from backend.';
    }
  };
}

const copycsvBtn = $('copycsv');
if (copycsvBtn) {
  copycsvBtn.onclick = async () => {
    if (!$('csv').value) $('mkcsv').click();
    try {
      await navigator.clipboard.writeText($('csv').value);
      copycsvBtn.textContent = 'Copied';
    } catch {
      $('csv').select();
      copycsvBtn.textContent = 'Press Ctrl+C to copy';
    }
    setTimeout(() => (copycsvBtn.textContent = 'Copy CSV'), 1800);
  };
}

const seedSamplesBtn = $('btn-seed-samples');
if (seedSamplesBtn) {
  seedSamplesBtn.onclick = async () => {
    seedSamplesBtn.disabled = true;
    seedSamplesBtn.textContent = 'Loading...';
    try {
      await api.seedDemoSamples();
      await loadLedger();
    } catch (e) {
      alert(e.message);
    } finally {
      seedSamplesBtn.disabled = false;
      seedSamplesBtn.textContent = '＋ Load demo samples';
    }
  };
}

// Upload file input handler
const fileInput = $('file-input');
if (fileInput) {
  fileInput.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const msgEl = $('msg');
    if (msgEl) msgEl.textContent = `Uploading ${file.name}...`;

    try {
      const uploaded = await api.uploadDocument(file);
      await loadDocuments();
      selectedType = 'uploaded';
      selectedDocId = uploaded.id;
      await loadActiveDocument();

      // Automatically trigger AI extraction
      triggerProcess(uploaded.id);
    } catch (err) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      fileInput.value = '';
    }
  };
}

// AI status click-to-refresh handler
const aiStatusEl = $('ai-status');
if (aiStatusEl) {
  aiStatusEl.addEventListener('click', async () => {
    aiStatusEl.textContent = '● Probing AI...';
    await refreshAIStatus();
  });
}

// Initial Bootstrapping
(async function init() {
  await refreshAIStatus();
  setInterval(refreshAIStatus, 15000); // Check local AI connection periodically
  await loadDocuments();
  await loadActiveDocument();
  await loadLedger();
})();

