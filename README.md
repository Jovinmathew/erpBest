# Procurement & Stock Pilot

A FastAPI BFF in front of a self-hosted ERPNext instance, covering a manufacturing business's **Material Request → RFQ/Quote → Purchase Order → Receipt → Stock** pipeline, plus a second **Process Sheet / Stage Inspection** domain for shop-floor production and QC record-keeping.

**Status: design-stage.** `main.py` currently only has read-only `/items` and `/bin` endpoints, kept for manual API testing against the live ERPNext instance — no domain endpoints (Material Request, RFQ, Process Sheet, etc.) are implemented yet. Everything else below is settled design, ready for `/implement`.

## Where things live

- **`CONTEXT.md`** — the domain glossary: roles, terms, what to call things and what to avoid calling them.
- **`docs/adr/`** — architecture decisions, numbered in order:
  - `0001` — ERPNext native doctypes + custom fields as sole persistence, no local DB
  - `0002` — actor identity via a static token table, not Frappe User
  - `0003` — Process Sheet as a new custom doctype; native Quality Inspection reused for Stage Inspection
  - `0004` — RFQ send triggers ERPNext's native supplier-email action; native Supplier Portal self-service deliberately ignored
- **`docs/api-shapes.md`** — concrete request/response JSON for every endpoint, worked out via an API-roleplay walkthrough covering both domains end to end.
- **`docs/erpnext-custom-fields.md`** — the manual Customize Form checklist: exactly which custom fields/doctypes need provisioning in ERPNext before `/implement` can build against any of this.
- **`docs/research/`** — background research notes (ERPNext native capabilities, cited against primary sources) that informed specific design calls above.
- **`docs/agents/`** — how agent skills (issue tracker, triage, domain docs) should operate in this repo.

## Local ERPNext

A `frappe_docker` ERPNext instance runs locally (`http://localhost:8080` by default, see `settings.py`/`.env`). `.env` holds live API credentials — never commit it (see `.gitignore`).
