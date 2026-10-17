// LedgerLeaf API Client Module
// Connects the frontend interface to the FastAPI backend

const CANDIDATE_BASES = window.location.port === '8000'
  ? ['', 'http://127.0.0.1:8000', 'http://localhost:8000']
  : ['http://127.0.0.1:8000', 'http://localhost:8000', ''];

let ACTIVE_BASE = CANDIDATE_BASES[0];

async function apiFetch(endpoint, options = {}) {
  const basesToTry = [ACTIVE_BASE, ...CANDIDATE_BASES.filter((b) => b !== ACTIVE_BASE)];
  let lastError = null;

  for (const base of basesToTry) {
    const url = `${base}${endpoint}`;
    try {
      const res = await fetch(url, options);
      if (res.ok || (res.status >= 200 && res.status < 500)) {
        ACTIVE_BASE = base;
        return res;
      }
      lastError = new Error(`HTTP ${res.status} from ${url}`);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error(`Failed to reach ${endpoint}`);
}

export const api = {
  getBaseUrl() {
    return ACTIVE_BASE || window.location.origin;
  },

  // AI Status
  async getAIStatus() {
    const res = await apiFetch(`/api/v1/ai/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to get AI status`);
    return await res.json();
  },

  async testAIConnection() {
    const res = await apiFetch(`/api/v1/ai/test-connection`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Connection test failed`);
    return await res.json();
  },

  // Document Ingestion & Management
  async getDocuments() {
    const res = await apiFetch(`/api/v1/documents`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch documents`);
    return await res.json();
  },

  async uploadDocument(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiFetch(`/api/v1/documents`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed with HTTP ${res.status}`);
    }
    return await res.json();
  },

  async getDocument(id) {
    const res = await apiFetch(`/api/v1/documents/${id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch document ${id}`);
    return await res.json();
  },

  async deleteDocument(id) {
    const res = await apiFetch(`/api/v1/documents/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to delete document ${id}`);
    return await res.json();
  },

  async processDocument(id) {
    const res = await apiFetch(`/api/v1/documents/${id}/process`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Processing failed with HTTP ${res.status}`);
    }
    return await res.json();
  },

  // Human Review & Field Editing
  async getDocumentExtraction(id) {
    const res = await apiFetch(`/api/v1/documents/${id}/extraction`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch extraction`);
    return await res.json();
  },

  async updateDocumentExtraction(id, payload) {
    const res = await apiFetch(`/api/v1/documents/${id}/extraction`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update extraction: HTTP ${res.status}`);
    }
    return await res.json();
  },

  async validateDocument(id) {
    const res = await apiFetch(`/api/v1/documents/${id}/validate`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Validation failed: HTTP ${res.status}`);
    }
    return await res.json();
  },

  async approveDocument(id) {
    const res = await apiFetch(`/api/v1/documents/${id}/approve`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        (err.detail && err.detail.message) || err.detail || `Approval failed with HTTP ${res.status}`
      );
    }
    return await res.json();
  },

  async rejectDocument(id) {
    const res = await apiFetch(`/api/v1/documents/${id}/reject`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Rejection failed`);
    return await res.json();
  },

  // Persistent Ledger
  async getLedger() {
    const res = await apiFetch(`/api/v1/ledger`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch ledger`);
    return await res.json();
  },

  async getLedgerSummary() {
    const res = await apiFetch(`/api/v1/ledger/summary`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch ledger summary`);
    return await res.json();
  },

  getLedgerExportUrl() {
    return `${API_BASE || 'http://127.0.0.1:8000'}/api/v1/ledger/export.csv`;
  },

  async deleteLedgerEntry(id) {
    const res = await apiFetch(`/api/v1/ledger/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to delete ledger entry`);
    return await res.json();
  },

  async addDemoSampleToLedger(payload) {
    const res = await apiFetch(`/api/v1/ledger/demo-sample`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to add demo record: HTTP ${res.status}`);
    }
    return await res.json();
  },

  async seedDemoSamples() {
    const res = await apiFetch(`/api/v1/ledger/seed-demo-samples`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to seed demo samples`);
    return await res.json();
  },
};
