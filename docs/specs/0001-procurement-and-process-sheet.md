---
status: ready-for-agent
---

# Procurement pipeline + Process Sheet/Stage Inspection

The implementation spec for both BFF domains, synthesized from the settled design in `CONTEXT.md`, `docs/adr/0001`–`0004`, `docs/api-shapes.md`, and `docs/erpnext-custom-fields.md`. This document is the intent; the work is tracked as cards on the Trello board (see `docs/agents/issue-tracker.md`), each card linking back to the sections here rather than restating them.

## Problem Statement

The business runs two paper-and-memory workflows today, both prone to lost history and no auditable trail:

1. **Procurement**: a Requester (Production Supervisor, Store Person, or Floor Manager) needs materials, the GM must validate the request before anything happens, Office runs a multi-supplier RFQ and manually tracks who quoted what and when quotes changed during negotiation, the GM proposes a supplier, the Director makes the final call (possibly overriding the GM), and only then does Office cut a Purchase Order. None of this — validation gates, quote history across revisions, who proposed vs. who decided — has anywhere to live today except memory and paper.
2. **Production/QC**: a Programmer reads a client drawing and lays out a routing (machine, tolerance, operation sequence) on a Process Sheet; Operators execute each numbered operation and log load/unload times and quantities; Inspectors run a Stage Inspection at specific operations, recording actual dimensions against tolerance. Reworks happen and need to be distinguishable from first-pass attempts. None of this is captured anywhere queryable — it lives on paper process sheets and in people's heads.

ERPNext is already self-hosted for this business and natively covers parts of this (Purchase Order, Purchase Receipt, Stock Ledger, Quality Inspection) but has no notion of the approval gates, quote negotiation history, or job-shop routing/execution record this business actually needs.

## Solution

Build out the FastAPI BFF (`main.py`) that already sits in front of the self-hosted ERPNext instance into a full domain API covering both pipelines end to end:

- **Procurement**: Material Request → RFQ/Quote → Purchase Order → Receipt → Stock, with explicit Validation and Decide gates, append-only rejection history, and per-supplier quote version history.
- **Process Sheet / Stage Inspection**: job-shop routing + execution record-keeping (not scheduling), with per-operation Stage Inspections reusing ERPNext's native Quality Inspection doctype.

ERPNext remains the sole system of record for both domains (no local database) — the BFF's job is to layer the gates, history, and vocabulary this business actually uses on top of ERPNext's native doctypes plus a small number of custom fields and two new custom doctypes.

This spec covers implementing every endpoint already worked out in the design-stage docs (`CONTEXT.md`, `docs/adr/0001`–`0004`, `docs/api-shapes.md`, `docs/erpnext-custom-fields.md`) — no new design decisions, this is the `/implement` pass over settled design.

## User Stories

**Material Request**

1. As a Requester, I want to raise a Material Request with items, qty, uom, a required-by date, and a free-text `raised_for` reference, so that procurement has what it needs to act on my request.
2. As a Requester, I want my Material Request to start in a `PENDING_VALIDATION` state, so that it's clear nothing proceeds until the GM validates it.
3. As a GM, I want to validate a pending Material Request, so that it can proceed to RFQ.
4. As a GM, I want to reject a Material Request with a required reason, so that the Requester knows what to fix.
5. As a GM, I want a rejection to capture a snapshot of the MR's live fields (items, required_by, raised_for) at the moment of rejection, so that later revisions can be compared against what was actually rejected.
6. As a GM, I want to reject the same Material Request more than once across its lifetime without losing earlier rejection history, so that the full back-and-forth is auditable.
7. As any Requester (not just the original one), I want to revise a rejected Material Request with updated items/required_by, so that the request can be corrected and resubmitted by whoever's available.
8. As a Requester, I want a revise attempt on a non-`REJECTED` Material Request to fail with a clear error, so that I don't accidentally bypass the validation gate.
9. As a GM, I want a revised Material Request to return to `PENDING_VALIDATION`, so that it goes through the same gate again.

**RFQ / Quote**

10. As Office, I want to send an RFQ for a validated Material Request to multiple suppliers in one call, so that I don't have to contact each supplier separately.
11. As Office, I want RFQ send to use ERPNext's own native supplier-email action (letterhead, subject, message), so that suppliers receive a properly formatted email without the BFF building its own mailer.
12. As Office, I want any file attachments on the originating Material Request to carry over onto the RFQ before it's sent, so that suppliers receive the same reference material.
13. As Office, I want `letter_head`, `subject`, and `message_for_supplier` to be required on every send (no default boilerplate), so that I make a deliberate wording call each time.
14. As Office, I want a clear, distinguishable error (not a silent failure) if ERPNext has no Email Account configured when I try to send, so that I know to fix ERPNext setup rather than assume the RFQ went out.
15. As Office, I want each supplier on a sent RFQ to start in `PENDING` quote status, so that I can see at a glance who hasn't replied yet.
16. As Office, I want to record that a supplier declined to quote, with a reason, so that the decline is visible without discarding the supplier from the RFQ.
17. As Office, I want a supplier who previously declined to still be able to submit a quote later, so that reconsidering isn't blocked by an earlier decline.
18. As Office, I want to record a supplier's price/currency/terms/valid-until as a new quote Version rather than overwriting the previous one, so that the full negotiation history (price coming down over rounds) is preserved.
19. As Office, I want the latest Version to always be treated as the current price for a supplier, so that stale historical prices never get accidentally selected.
20. As a GM, I want to propose a supplier + specific quote Version as my recommended Selection, with a rationale, so that the Director has a clear recommendation to act on.
21. As a Director, I want to ratify a proposed Selection, so that the RFQ moves to a final, settled `DECIDED` state.
22. As a Director, I want to override a proposed Selection with a different supplier/Version and a remark explaining why, so that I can act on information the GM didn't have.
23. As a Director, I want both the originally proposed Selection and the final decided Selection preserved when I override, so that "was this overridden?" is always answerable later.
24. As a Director, I want to reject a proposed Selection with a reason, reopening the RFQ back to `SENT` so the GM can propose again, so that a bad recommendation doesn't dead-end the RFQ.
25. As a Director, I want RATIFY and OVERRIDE to be terminal (no further re-proposing), so that a decided RFQ can't be silently reopened.
26. As Office, I want an RFQ's rejection history to stay append-only across multiple reject/re-propose cycles, so that the full decision trail survives.

**Purchase Order / Receipt / Stock**

27. As Office, I want to manually create a Purchase Order from a `DECIDED` RFQ, with supplier/items/price pulled from the RFQ's final Selection (not retyped), so that the PO always matches what was actually decided.
28. As Office, I want PO creation to be blocked if the RFQ isn't yet `DECIDED`, so that a PO can never precede a real decision.
29. As a Store Person, I want to record a Purchase Receipt against a PO with received/accepted/rejected quantities, so that goods arrival is tracked.
30. As a Store Person, I want to record multiple partial receipts against a single PO, so that split/batched deliveries are handled without forcing a single-shipment assumption.
31. As anyone with stock visibility needs, I want to read current Stock Ledger/Bin state via the BFF, so that I don't need direct ERPNext UI access just to check stock.

**Process Sheet**

32. As a Programmer, I want to create a Process Sheet with header fields (client, drawing number, part name, material, qty, date, programmer, attachment) and no pre-populated operations, so that I can hand off a job for execution without re-typing the full routing plan into structured fields.
33. As a Programmer, I want to attach the original routing document (scanned/PDF) to the Process Sheet, so that the technical spec for each operation lives in one authoritative place instead of being retyped.
34. As an Operator, I want to log that I started (loaded) a specific numbered operation, with machine and target quantity, so that there's a record of who's working what.
35. As an Operator, I want to update that operation with achieved quantity and unload date once I finish it, so that the execution record is complete.
36. As an Operator running an outsourced operation, I want to use the same load/unload shape (operator = coordinator, dates = sent-to/received-from vendor), so that outsourced steps don't need special-cased fields.
37. As an Operator or Programmer, I want a rework attempt on a given operation number to create a new row rather than overwrite the failed attempt, so that both attempts' history survives.
38. As an Operator, I want `rework` and `rejection` to be flags I set explicitly on a row, so that they reflect a deliberate record rather than being inferred from inspection outcomes.
39. As a Programmer, I want to create a second, fully independent Process Sheet for a repeat order against the same drawing, so that each job run has its own clean execution record.

**Stage Inspection**

40. As an Inspector, I want to record a Stage Inspection against a specific Process Sheet + operation number, with multiple reading rows (specification, tolerance, up to 10 sample readings, per-reading status), so that dimensional QC data is captured the way the paper form already captures it.
41. As an Inspector, I want to explicitly set the overall pass/fail status myself rather than have it auto-derived from individual readings, so that my judgment call is the recorded fact, not an aggregation.
42. As an Inspector recording a failed inspection, I want the record to stand on its own (the resulting rework is a separate, manually recorded fact on a new Operation row), so that inspection outcome and rework action aren't conflated.
43. As anyone reviewing a completed job, I want a passed Stage Inspection on the final operation (Op 12 / dispatch) to be sufficient evidence the job is done, without needing a separate Process-Sheet-level completion field.

**Cross-cutting**

44. As any caller, I want every state-changing endpoint to derive the acting identity from my auth token server-side (never from a client-supplied field), so that actor attribution can't be spoofed by whatever the client happens to send.
45. As a developer integrating against this BFF, I want response shapes that match `docs/api-shapes.md` exactly (field names, status codes, state values), so that the design-stage contract is what actually ships.

## Implementation Decisions

**Architecture & persistence** (ADR 0001, ADR 0002)
- No local database. ERPNext is the sole system of record for both domains, including BFF-only state (gates, proposed/final Selection, append-only rejections) — that state is stored via Frappe's Customize Form as custom fields on native doctypes, plus one new reusable child doctype (`BFF Rejection`, used as a Table field on both Material Request and Request for Quotation).
- Quote Versions are stored as extra custom fields directly on RFQ's native Suppliers child table (one row appended per Version), not via native Supplier Quotation — Frappe doesn't support a child table nested inside another child table, so the `quotes[].versions[]` response shape is assembled at read time by grouping child-table rows by supplier.
- Actor identity comes from a static token → `{user_id, roles}` table held in BFF settings, not Frappe User. All actor fields (`raised_by`, `validated_by`, rejection `by`, `proposed_by`/`final_by`, `programmer`, `operator`, `inspected_by`, etc.) are plain strings resolved server-side from the caller's token, never accepted as client input.
- All custom fields/doctypes listed in `docs/erpnext-custom-fields.md` must be provisioned manually in ERPNext via Customize Form before the corresponding endpoints can be built against them — this is a prerequisite checklist, not something the BFF provisions in code.

**Material Request module**
- Endpoints: raise, validate, reject (with reason + live-field snapshot), revise.
- `bff_status`: `PENDING_VALIDATION` → `VALIDATED` (via validate) or `REJECTED` (via reject, with reason + snapshot) → `PENDING_VALIDATION` again (via revise, only legal when status is `REJECTED`; any Requester may revise, not only the original raiser).
- Rejections are an append-only list; each entry carries `reason`, `by`, `at`, and a JSON `snapshot` of the MR's live-editable fields (`items`, `required_by`, `raised_for`) at rejection time.
- Items and `required_by` use Material Request's native fields as-is.

**RFQ / Quote module** (ADR 0004)
- Endpoints: send, decline (per supplier), submit quote version (per supplier), propose selection, decide.
- Send creates the native RFQ doc, copies Frappe File attachments from the originating Material Request onto the RFQ (native send only carries attachments already on the RFQ itself), then submits it — submitting fires ERPNext's native supplier-email action. `letter_head`, `subject`, `message_for_supplier` are required inputs with no defaults; `use_html`/`message_for_supplier_html` map to native `use_html`/`mfs_html`.
- If ERPNext raises `OutgoingEmailError` on submit (no Email Account configured), surface it as `424 Failed Dependency` rather than swallowing it.
- Per-supplier `quote_status`: `PENDING` (initial, on send) → `DECLINED` (on decline, with reason + timestamp) → `QUOTED` (on any version submit, including flipping back from `DECLINED` — decline doesn't lock a supplier out).
- Each quote version submit appends a new `version_index` row rather than overwriting; the latest version index for a supplier is the current price. Versions store only the flat price/currency/terms/valid_until summary — no attachment of the supplier's original quote document (explicitly deferred, matching the Process Sheet attachment gap).
- `bff_status`: `SENT` → `SELECTION_PROPOSED` (via propose, capturing `proposed_supplier`/`proposed_version_index`/`proposed_by`/`proposed_rationale`) → `DECIDED` (via decide with `RATIFY` or `OVERRIDE`, capturing `final_supplier`/`final_version_index`/`final_by`/`final_remark`) or back to `SENT` (via decide with `REJECT`, clearing proposed fields, appending to the same append-only rejections list used by MR).
- `OVERRIDE` always records both the proposed and final Selection even when they happen to agree, so override history is always reconstructable. `RATIFY`/`OVERRIDE` are terminal — no re-proposing after either; only `REJECT` reopens the RFQ.
- Known wrinkle to sanity-check once built: ERPNext's native RFQ Supplier "quote status" indicator assumes one row per supplier — appending multiple version rows per supplier may make that native indicator misbehave. Safe to ignore if so; the custom `quote_status`/`received_at`/`declined_at` fields are the real source of truth.

**Purchase Order / Receipt / Stock module**
- Purchase Order creation is manual only (never auto-created off a Decide), blocked unless the referenced RFQ's `bff_status` is `DECIDED`. Supplier, items, and price are read from the RFQ's final Selection at creation time, not retyped by the caller.
- Native PO `status` is used as-is with no `bff_status` mirror (no BFF-specific gate on top of it).
- Purchase Receipt uses ERPNext's native doctype and native `per_received` tracking as-is, supporting multiple partial receipts against one PO. `accepted_qty`/`rejected_qty` routing to default/Rejected Warehouse is native ERPNext behavior, not BFF logic.
- Stock endpoint(s) are read-only pass-throughs to ERPNext's native Stock Ledger/Bin — no stock-mutating endpoint of any kind is in scope.

**Process Sheet module** (ADR 0003)
- Two new doctypes to provision: `Process Sheet` (parent) and `Process Sheet Operation` (child table on Process Sheet). Neither reuses native Work Order/Job Card (those require BOM-driven planning this record-keeping-only scope doesn't have).
- Process Sheet creation takes header fields only (`client`, `drawing_no`, `part_name`, `material`, `qty` as free-text/Data to allow compound values like "1+1", `date`, `programmer`, `attachment`) — `operations` starts empty, never pre-populated from the routing document.
- `attachment` is uploaded via Frappe's native `upload_file` endpoint first (returning a file URL), then referenced on the Process Sheet — the Process Sheet create/update endpoints themselves stay plain JSON, no multipart handling.
- Process Sheet Operation rows are created incrementally as work happens (load: `op_no`, `machine`, `operator`, `target_qty`, `date_loaded`; then a follow-up update for `achieved_qty`/`date_unloaded`). No field describes what an operation technically entails — that lives only in the Process Sheet's attachment.
- Outsourced operations reuse the identical Operation shape (`operator` = coordinator, `date_loaded`/`date_unloaded` = sent-to/received-from vendor) — no separate vendor/dispatch fields.
- A rework attempt is a new row with the same `op_no` as the failed attempt, never an overwrite. `rework`/`rejection` are independent boolean fields set manually by whoever records the row — never derived from a Stage Inspection outcome.
- Final Inspection & Dispatch (Op 12) is just another Operation row + Stage Inspection with no special-cased Process-Sheet-level completion field — a passed Op 12 Stage Inspection is the completion signal.
- A repeat order against the same drawing is a brand new, independent Process Sheet with no structural link to the earlier one — no template/instance entity exists yet (explicitly deferred debt per ADR 0003).
- No `sales_order` link field — Process Sheet's `client`/`drawing_no` stay free-text (see Out of Scope).

**Stage Inspection module** (ADR 0003)
- Reuses ERPNext's native Quality Inspection doctype as-is, plus one custom field: `op_no` (Int), identifying which Process Sheet Operation the inspection covers. The parent link uses Quality Inspection's native `reference_type`/`reference_name` dynamic link (`reference_type = "Process Sheet"`).
- Reading rows keep native `reading_1`..`reading_10` fields available (matching the paper form's 1–10 sample columns) even though most jobs only fill `reading_1`.
- Top-level `status` (Accepted/Rejected) is explicitly set by the Inspector on submit — never auto-derived from individual reading statuses.
- **Verify before building**: whether this ERPNext version's Quality Inspection `reference_type` accepts a custom doctype value ("Process Sheet") at all is an unverified assumption per ADR 0003 — confirm against the live instance before wiring this endpoint; if it doesn't work, this is the one point in ADR 0003 that needs revisiting.

**Roles/permissions**
- Programmer, Operator, Inspector roles have no defined permission boundaries in this phase (deliberate, per ADR 0003) — any valid actor token can perform any action in the Process Sheet/Stage Inspection domain for now.

## Testing Decisions

- **Seam**: tests exercise the FastAPI app through its HTTP surface (e.g. `TestClient`/`httpx.ASGITransport`), asserting on status codes and response JSON exactly as documented in `docs/api-shapes.md` — never on internal function calls or ERPNext request bodies. `main.py`'s existing `get_erp_client` FastAPI dependency (currently injecting a real `httpx.AsyncClient` against ERPNext) is the natural override point: tests override it with a fake/in-memory Frappe REST client that understands enough of the `/api/resource/...` surface (list/get/insert/update, plus `submit` for docstatus transitions) to back all endpoints in this spec, so the bulk of the suite runs with no live ERPNext instance required.
- A small, separate contract-test pass (not part of the main suite, run manually/CI-gated separately) exercises the same endpoints against the real local `frappe_docker` instance to catch drift between the fake and ERPNext's actual behavior — particularly for the two verify-before-building wrinkles called out above (RFQ Supplier native quote-status indicator, Quality Inspection `reference_type` accepting a custom doctype).
- Good tests here assert externally observable behavior only: given a sequence of calls, does the response shape/status/state match what `docs/api-shapes.md` specifies — not which internal helper or Frappe endpoint was called to get there.
- Priority coverage, since these are exactly where a wrong implementation would silently corrupt history or skip a gate:
  - MR: reject → revise → re-validate cycle, including that a second rejection appends rather than overwrites, and that revise on a non-`REJECTED` MR errors.
  - RFQ: full send → decline → quote → propose → decide (RATIFY, OVERRIDE, REJECT) matrix, confirming REJECT reopens to `SENT` while RATIFY/OVERRIDE are terminal, and that OVERRIDE preserves both proposed and final Selections.
  - RFQ send failure path: missing Email Account surfaces as `424`, not swallowed.
  - PO creation blocked unless RFQ is `DECIDED`; PO fields match the RFQ's final Selection.
  - Process Sheet: rework appends a new row under the same `op_no` rather than mutating the original; `rework`/`rejection` never auto-set.
  - Stage Inspection: `status` reflects what's explicitly submitted, not derived from reading rows.
- No prior art exists in this repo yet — there is no `tests/` directory and no endpoints beyond the two read-only reference ones (`/items`, `/bin`) in `main.py`. This spec is the first real test suite for the project; establish the fake-client fixture as the shared foundation the rest of the suite builds on.

## Out of Scope

- Linking Material Request (`raised_for`) or Process Sheet (`client`/`drawing_no`) to a Sales Order or any other structured record — both stay free-text. Sales Order is confirmed as the correct conceptual upstream anchor but is deliberately not wired in yet.
- Any mechanism for a job/client PO to enter the system automatically (e.g. Frappe's native email-to-doctype `append_to` intake) — research exists (`docs/research/erpnext-email-to-document-intake.md`) but no decision has been made to act on it.
- RFQ resend/reminder action for suppliers who haven't replied.
- Consuming or syncing native Supplier Quotation submissions from ERPNext's Supplier Portal — the portal activates automatically on send but is deliberately ignored; a supplier's price is only ever recorded through Office keying in a Version.
- Attaching a supplier's original quote document to a quote Version (only the flat price/currency/terms/valid_until summary is stored).
- Any stock-mutating endpoint — Stock access is read-only.
- Process Sheet template/instance split (a reusable per-drawing template vs. per-run actuals) — deferred per ADR 0003 until real repeat-order data shows the variation pattern.
- Defined permission boundaries for Programmer/Operator/Inspector roles, or for Requester/GM/Director/Office beyond what the state machine itself enforces (e.g. nothing currently stops a Requester token from calling `/validate`) — left loose per ADR 0003, to be discovered later.
- A real auth/identity system (token issuance, multi-tenant identity, login UI) — the static token table is an accepted pilot-scope simplification per ADR 0002.
- Any frontend/UI — this is an API-only pilot, driven via Postman/curl.

## Further Notes

- Manual prerequisite before implementation can proceed: every checklist item in `docs/erpnext-custom-fields.md` must be provisioned by hand in ERPNext (Customize Form) — the two new doctypes (`Process Sheet`, `Process Sheet Operation`), the new reusable child doctype (`BFF Rejection`), and all custom fields on Material Request, Request for Quotation (+ its Suppliers child table), Purchase Order, Purchase Receipt, and Quality Inspection. None of this is provisioned in code.
- Two explicitly unverified assumptions carried over from the ADRs should be confirmed early during implementation, since either failing changes the design: (1) whether Quality Inspection's `reference_type` accepts the custom "Process Sheet" doctype on this ERPNext version (v16.29.0 at design time); (2) whether ERPNext's native RFQ Supplier quote-status indicator tolerates multiple version rows appended per supplier without misbehaving (low risk — the BFF's own `quote_status`/`received_at`/`declined_at` fields are the real source of truth regardless).
- An Email Account and at least one Supplier record must exist in the live ERPNext instance before the RFQ send path can be exercised end to end (confirmed at design time: zero of either configured).
