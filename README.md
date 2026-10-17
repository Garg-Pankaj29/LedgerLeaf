# LedgerLeaf — Your finances. Your files. Your AI.

**LedgerLeaf** is a local-first, privacy-respecting financial document processing application that turns receipts, invoices, and paperwork into structured accounting records on your own machine. Every number points directly back to the line it came from in the original document, and nothing enters your approved ledger until you explicitly review and verify it.

---

## 1. Core Principles & Philosophy

1. **Local-First & Private by Default:** All text extraction, OCR, database storage, and AI inference run locally on `127.0.0.1`. Uploaded files are stored in `data/uploads/` outside the web directory. Documents never leave your computer unless you explicitly export CSV data or configure an external integration.
2. **Deterministic Arithmetic Guards:** Local models can misread numbers or make arithmetic mistakes. The AI model proposes structured values; deterministic validation rules cross-check math (`subtotal + tax == total`), dates, and required fields; and a human approves before anything enters the ledger. The system never silently alters numbers to make math balance.
3. **Source Provenance & Line Highlighting:** Every extracted field links back to its character offset and verbatim snippet in the source document so you can click any field to verify it against the source text.
4. **Integer Minor Units:** All monetary amounts are stored internally as integer minor units (e.g. cents, paise) with ISO 4217 currency codes (`USD`, `EUR`, `GBP`, `INR`) to eliminate floating-point precision loss.
5. **Strict Multi-Currency Isolation:** Ledger totals and category summaries never merge different currencies into a meaningless combined total. Each currency stays on its own dedicated ledger balance.
6. **No Fake Output or Invented Values:** When fields are missing from source paperwork, they remain unpopulated (`null`) rather than being fabricated. If local AI is offline or encounters an error, the backend reports honest error states with actionable details rather than returning mock success.
7. **Not an Accounting Firm Replacement:** LedgerLeaf is an intelligent document review and ingestion assistant. It does not replace a certified public accountant, tax adviser, or full double-entry accounting suite.

---

## 2. Architecture & Project Tree

```text
LedgerLeaf/
├── LedgerLeaf.html                # Original standalone leaf-themed prototype
├── README.md                      # Comprehensive architecture, setup, and troubleshooting guide
├── requirements.txt               # Pinned Python dependencies
├── pytest.ini                     # Pytest configuration with pythonpath
├── alembic.ini                    # Alembic migration configuration
├── .env                           # Local environment configuration (git-ignored)
├── .env.example                   # Environment configuration template
├── .gitignore                     # Git ignore rules for .env, DB, uploads, .venv
├── alembic/                       # Alembic database migration management
│   ├── env.py                     # Migration runner with SQLite batch alter support
│   ├── script.py.mako             # Revision template
│   └── versions/                  # Versioned schema migrations
├── data/                          # Private runtime data directory (git-ignored)
│   ├── ledgerleaf.db              # SQLite database (auto-migrated)
│   └── uploads/                   # Stored original receipt and invoice files
├── frontend/                      # Modular leaf-inspired client application
│   ├── index.html                 # UI entry point with accessibility tags & responsive layout
│   ├── assets/                    # Icons and static brand assets
│   ├── css/
│   │   └── style.css              # Curated leaf design tokens, dark/light themes, typography
│   └── js/
│       ├── api.js                 # FastAPI client module (no direct browser-to-AI calls)
│       ├── app.js                 # Review bench, field pinning, guard, ledger, and CSV export
│       └── veins.js               # Canvas leaf-vein procedural branch animation
└── backend/                       # Python FastAPI backend
    ├── requirements.txt           # Backend package dependencies
    ├── app/
    │   ├── main.py                # FastAPI entry point, CORS, lifespan, and static mounting
    │   ├── config.py              # Pydantic BaseSettings, host, port, directory management
    │   ├── database.py            # SQLite engine, session maker, and schema init
    │   ├── api/
    │   │   └── v1/
    │   │       ├── router.py      # Aggregated v1 API router
    │   │       ├── health.py      # GET /api/v1/health
    │   │       ├── ai.py          # GET /api/v1/ai/status, test-connection, models
    │   │       ├── documents.py   # Ingestion, review, PATCH editing, validation, approval, deletion
    │   │       └── ledger.py      # Approved ledger, multi-currency summary, RFC 4180 CSV export
    │   ├── models/                # SQLAlchemy ORM models
    │   │   ├── document.py        # Document entity (statuses, extracted_text, hash)
    │   │   ├── extraction.py      # ExtractionResult entity (minor units, method, issues)
    │   │   ├── ledger.py          # LedgerEntry entity (immutable approved accounting records)
    │   │   └── provenance.py      # FieldProvenance entity (snippets, offsets, user edits)
    │   ├── schemas/               # Pydantic v2 validation schemas
    │   │   ├── common.py          # Health and AI status schemas
    │   │   ├── document.py        # Document upload and response schemas
    │   │   ├── extraction.py      # Extraction and PATCH schemas
    │   │   ├── ledger.py          # Ledger entry, summary, and demo seed schemas
    │   │   ├── money.py           # Minor units conversion utilities (cents/paise)
    │   │   └── provenance.py      # Provenance and user-edit tracking schemas
    │   └── services/              # Application services
    │       ├── storage_service.py # Path traversal defense, magic signatures, SHA-256
    │       ├── text_extraction_service.py # PDF text layer, Tesseract OCR, plain text parser
    │       ├── local_ai.py        # Local LM Studio OpenAI-compatible client
    │       └── validation_service.py # Deterministic math guards, dates, duplicates, categories
    └── tests/                     # Automated Pytest test suite
        ├── conftest.py            # In-memory test fixtures and FastAPI TestClient
        ├── test_startup.py        # Directory creation & database initialization
        ├── test_health.py         # Health, OpenAPI schema, and Swagger UI
        ├── test_models.py         # Monetary minor units, UUIDs, and missing fields
        ├── test_documents_api.py  # File validation, duplicate detection, listing & deletion
        ├── test_local_ai_and_processing.py # AI extraction, prompts, mocks, and timeout handling
        ├── test_phase3_workflow.py # Full review bench, field editing, validation, and approval
        └── test_phase4_reliability.py # Idempotency, path traversal defense, CSV escaping, cascades
```

---

## 3. Supported File Types & Privacy Boundaries

### Supported Ingestion Types
- **PDF Documents (`.pdf`):** Fast extraction from digital text layers via `pypdf`, falling back to OCR for scanned PDFs.
- **Images (`.png`, `.jpg`, `.jpeg`, `.webp`):** Optical Character Recognition (OCR) via local `pytesseract` and Pillow.
- **Plain Text (`.txt`):** Direct UTF-8 ingestion.

### Privacy Boundaries
- **Server Binding:** The FastAPI application binds strictly to `127.0.0.1` by default to avoid exposing internal endpoints on local area networks.
- **Path Traversal Defense:** `StorageService` strictly verifies that resolved file paths reside within `data/uploads/` and generates random UUID filenames.
- **Data Retention:** Documents and SQLite records remain on local disk. No third-party analytics, telemetry, or external cloud LLM APIs are contacted.
- **Local AI Connection:** Requests to LM Studio travel entirely over local loopback (`http://127.0.0.1:1234/v1`).

---

## 4. Environment Setup & Installation

### Prerequisites
- **Python:** 3.10 or higher (tested with Python 3.12.3)
- **Tesseract OCR (System dependency for images and scanned PDFs):**
  > **Note:** Python's `pytesseract` library is already listed in `requirements.txt`, but it requires the native Tesseract OCR engine installed on your operating system to process images (`.png`, `.jpg`, `.webp`) and scanned PDFs:
  - **Ubuntu / Debian:** `sudo apt-get update && sudo apt-get install -y tesseract-ocr`
  - **macOS (Homebrew):** `brew install tesseract`
  - **Windows:** Download the installer from [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and ensure it is added to your system `PATH`.
  *(Text-based PDFs and `.txt` files do not require Tesseract and work out of the box).*

### 1. Clone & Set Up Virtual Environment
```bash
# Navigate to the project root
cd LedgerLeaf

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate       # Linux / macOS
# or: .venv\Scripts\activate   # Windows
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
```bash
cp .env.example .env
```

Review or adjust `.env` if desired:
```env
APP_NAME=LedgerLeaf
APP_ENV=development
DEBUG=True
HOST=127.0.0.1
PORT=8000

DATA_DIR=data
DATABASE_URL=sqlite:///./data/ledgerleaf.db
UPLOAD_DIR=data/uploads
MAX_UPLOAD_MB=15

CORS_ORIGINS=["http://localhost:8000","http://127.0.0.1:8000","http://localhost:3000","http://127.0.0.1:3000"]

AI_PROVIDER=lm_studio
AI_BASE_URL=http://127.0.0.1:1234/v1
AI_MODEL=meta-llama-3.1-8b-instruct
AI_TIMEOUT_SECONDS=120
AI_MAX_RETRIES=1
```

### 4. Database Migrations
Database tables auto-initialize on startup. To inspect or run versioned Alembic migrations:
```bash
alembic upgrade head
```

---

## 5. Local AI Setup with LM Studio

To enable zero-cloud, fully offline structured extraction:

1. **Install LM Studio:** Download and install from [https://lmstudio.ai](https://lmstudio.ai).
2. **Download an Instruction Model:** In the search tab inside LM Studio, download a modern open-weight instruction model:
   - **Recommended:** `meta-llama-3.1-8b-instruct` or `mistral-7b-instruct-v0.3` (GGUF format, `Q4_K_M` or `Q5_K_M`).
3. **Start the Local Inference Server:**
   - Go to the **Local Server** tab (icon `<->` on the left sidebar).
   - Select your downloaded model from the top dropdown to load it into memory.
   - Ensure the server port is set to `1234` and CORS is enabled.
   - Click **Start Server**.
   - Verify logs state: `HTTP server listening on http://127.0.0.1:1234`.
4. **Offline Mode:** If LM Studio is not running, LedgerLeaf operates cleanly in offline mode: you can still upload documents, view extracted text, manually input and edit fields, run deterministic validation checks, approve records, and export CSVs.

---

## 6. How to Run Frontend & Backend Locally

### Option A: Run Backend + Static Frontend via FastAPI (Single Server)
```bash
# Start FastAPI backend
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser to:
- **Application UI:** [http://127.0.0.1:8000/app](http://127.0.0.1:8000/app)
- **Interactive Swagger Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### Option B: Run Separate Dev Servers
```bash
# Terminal 1: Backend
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Frontend static server
python3 -m http.server 3000 --directory frontend
```
Open your browser to:
- **Frontend App:** [http://127.0.0.1:3000](http://127.0.0.1:3000)

---

## 7. API Endpoints Reference

### AI Health & Status
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Service health, SQLite connectivity, and version |
| `GET` | `/api/v1/ai/status` | Current LM Studio connectivity status and active model |
| `POST` | `/api/v1/ai/test-connection` | Probe local AI latency and list available models |
| `GET` | `/api/v1/ai/models` | List all models loaded or cached in LM Studio |

### Document Management & Extraction
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/documents` | Upload document (MIME, size, magic signature checks, SHA-256) |
| `GET` | `/api/v1/documents` | List uploaded documents with status and metadata |
| `GET` | `/api/v1/documents/{id}` | Retrieve document details and processing history |
| `DELETE` | `/api/v1/documents/{id}` | Safely delete document, extractions, and stored disk file |
| `POST` | `/api/v1/documents/{id}/process` | Trigger local AI extraction and deterministic validation |
| `GET` | `/api/v1/documents/{id}/extraction` | Get latest extracted fields and source provenance |
| `PATCH` | `/api/v1/documents/{id}/extraction` | Edit extracted fields (records user edits in provenance) |
| `POST` | `/api/v1/documents/{id}/validate` | Run deterministic math guards and return diagnostic issues |
| `POST` | `/api/v1/documents/{id}/approve` | Commit approved record to the persistent ledger (blocks on issues) |
| `POST` | `/api/v1/documents/{id}/reject` | Mark document review status as rejected |

### Approved Ledger & Multi-Currency Analytics
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/ledger` | Retrieve all approved ledger entries with trust indicators |
| `GET` | `/api/v1/ledger/summary` | Multi-currency summary (strict currency isolation) |
| `GET` | `/api/v1/ledger/export.csv` | RFC 4180 compliant CSV export of approved entries |
| `POST` | `/api/v1/ledger/demo-sample` | Explicitly insert a demo sample entry (`is_demo=True`) |
| `POST` | `/api/v1/ledger/seed-demo-samples` | Seed sample multi-currency demo records (USD, EUR, INR) |
| `DELETE` | `/api/v1/ledger/{id}` | Remove entry from ledger and restore document to `needs_review` |

---

## 8. Testing Instructions

Run the automated Pytest test suite:
```bash
pytest backend/tests -v
```

### Coverage Highlights (37 Automated Tests)
- **Security & Storage:** File magic byte validation, size limit enforcement, path traversal defense (`../../etc/passwd` rejection).
- **Integrity & Cascades:** Document deletion safely unlinks disk files and cascades extraction and provenance records.
- **Approval Idempotency:** Repeated approval calls return `already_approved` without duplicating ledger entries.
- **Mathematical Guard:** Deterministic cross-checking of `subtotal + tax == total`, flagging discrepancies without altering numbers.
- **Local AI Failure Handling:** Graceful 503 handling on LM Studio connection failure or timeout without inventing fake output.
- **CSV & Trust Metrics:** Proper RFC 4180 escaping (commas, quotes, newlines) and source/trust attribution (`demo` vs `user`).

---

## 9. Known Limitations & Troubleshooting

### Known Limitations
1. **OCR on Noisy Images:** Skewed, crumpled, low-contrast, or handwritten receipts may produce incomplete OCR text. Users can manually type or adjust fields in the review bench.
2. **Inference Latency on CPU:** Running 8B models entirely on CPU without GPU acceleration can take 15–45 seconds per document. Use quantized models (e.g. `Q4_K_M`) and allocate GPU layers in LM Studio when possible.
3. **Multi-Page Tabular Invoices:** Complex multi-page invoices with multi-line item tables are currently extracted as high-level summary fields and line items; highly nested table layouts may require manual verification.

### Troubleshooting
- **AI status shows `○ AI: offline`:** Verify LM Studio is open, a model is loaded, and the local server is started on port 1234.
- **Upload fails with `Unsupported file type`:** Verify the file has an allowed extension (`.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.txt`) and matches its actual content signature (not renamed binary).
- **Port conflicts:** If port 8000 or 3000 is occupied, set `PORT=8001` in `.env` and start with `--port 8001`.
- **Resetting the database:** To reset test data, remove `data/ledgerleaf.db` and restart the backend server; tables will auto-initialize cleanly.
