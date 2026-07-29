---
status: accepted
---

# ERPNext native doctypes + custom fields as sole persistence, no local database

The BFF has no database of its own — ERPNext is the sole system of record for Material Request and RFQ/Quote state, including data with no native ERPNext equivalent (the validation gate, proposed/final Selection, append-only rejections). We reuse ERPNext's native Material Request and Request for Quotation doctypes, extending them via Frappe's Customize Form with custom fields and one new reusable child doctype ("BFF Rejection"). Quote versioning is stored as extra custom fields directly on RFQ's native Suppliers child table (one row appended per Version) rather than via ERPNext's native Supplier Quotation doctype — Supplier Quotation is item-line-heavy and doesn't fit the pilot's flat price/currency/terms-per-Version model, and Frappe doesn't support a child table nested inside another child table, so the contract's `quotes[].versions[]` shape has to be flattened into one child table grouped by supplier at read time.

**Considered and rejected:**
- **A local Postgres database for BFF-owned state.** This pilot doesn't need two systems of record, and a second store would fight ERPNext's own submit/docstatus lifecycle for the MR/PO/stock data it already owns.
- **Native Supplier Quotation for quote Versions.** Forces item-level rows for what the domain model treats as a flat per-quote price, and each revision would need its own submitted SQ document — heavier than the in-progress negotiation the domain model describes.

**Consequences:** the BFF has no independent backup/migration story — ERPNext's own backup covers everything. All custom fields are provisioned manually via Customize Form, not in code or version control — see `docs/erpnext-custom-fields.md` for the checklist.
