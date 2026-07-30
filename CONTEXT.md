# Procurement & Stock Pilot

A FastAPI BFF that sits in front of a self-hosted ERPNext instance and exposes a clean procurement API for a manufacturing business's Material Request → RFQ/Quote → Purchase Order → Receipt → Stock pilot. This glossary defines the vocabulary of the public API surface — deliberately free of ERPNext/Frappe internals, which live in `docs/adr/` instead.

## Roles

**Requester**:
A Production Supervisor, Store Person, or Floor Manager who raises a Material Request.
_Avoid_: User, creator

**GM**:
Rahul — validates every raised Material Request and proposes a supplier selection on an RFQ.
_Avoid_: Approver, manager

**Director**:
John — decides an RFQ's proposed selection: ratify, override, or reject.
_Avoid_: Approver, final approver

**Office**:
Staff who send RFQs to suppliers and record incoming quotes.
_Avoid_: Staff, admin

**Actor**:
The identity performing a state-changing call, always derived server-side from the caller's token — never accepted as client input.
_Avoid_: User (User is an ERPNext/Frappe concept; Actor is deliberately independent of it — see ADR 0002)

**Programmer**:
The person who authors a Process Sheet — reads the client drawing and decides the operation sequence, machines, and tolerances. Roles/permissions for this and the two roles below are deliberately left loose (see ADR 0003) — to be discovered as the domain gets built out further.
_Avoid_: Planner, CAM Programmer (synonyms used in other shops; this organization's own staff and documents say "Programmer")

**Operator**:
The person who executes one Process Sheet Operation — logs machine load/unload time and target vs. achieved qty for that operation.
_Avoid_: Machinist (a synonym used elsewhere; the organization's own process sheet header is "Operator Name")

**Inspector**:
The person who records a Stage Inspection — actual dimensions against tolerance, tied to a specific Process Sheet Operation.
_Avoid_: QC as a role name — the organization's own process sheet uses "QC" for a workstation/station label (alongside CNC TURNING, WIRECUT, etc.), not a person; using it for the role would clash with that

## Material Request

**Material Request (MR)**:
A request for materials, raised by a Requester, that must pass Validation before procurement can proceed.
_Avoid_: Purchase request, requisition

**Validation**:
The GM's approval gate on a Material Request. A validated MR may proceed to RFQ; a rejected one returns to the Requester to revise.
_Avoid_: Approval (reserved for the RFQ Decide step, to keep the two gates distinct)

**Revise**:
The Requester's act of resubmitting a rejected MR. The only exit from a rejected MR — it re-enters at Validation, never skips ahead.
_Avoid_: Resubmit, update

**Rejection**:
A recorded refusal at a gate (MR Validation, RFQ Decide), always carrying a reason and always append-only — never overwritten, only added to.
_Avoid_: Decline (reserved for a supplier's refusal to quote)

**raised_for**:
Free-text field on an MR naming the job or reference it was raised for (e.g. a client PO number). Deliberately unstructured — not a link to any other record.
_Avoid_: Work order, job reference (these imply a structured record that doesn't exist for this business)

## RFQ / Quote

**RFQ**:
A request for pricing sent to multiple suppliers for one Material Request, holding one Quote per supplier.
_Avoid_: Request for quotation spelled out — RFQ is canonical

**Quote**:
A supplier's response to an RFQ — a running, append-only history of Versions, never a single overwritable price.
_Avoid_: Bid, offer

**Version**:
One price submission within a Quote. Suppliers revise price during negotiation; each revision is a new Version, and the latest always wins — older Versions are historical record only, never re-selectable.
_Avoid_: Revision (reserved for an MR being revised after rejection, to keep the two distinct)

**Decline**:
A supplier's refusal to quote at all — distinct from a Quote with no Versions yet, which means "hasn't replied." Not a permanent lock: a supplier can still submit a Version after declining (e.g. reconsidering later), same as everything else in this domain being historical record rather than a gate — the decline stays visible, it just stops being the current state.
_Avoid_: Reject (reserved for the GM/Director acting on an MR or a proposed Selection)

**Quote status**:
A Quote's current state — `PENDING` (hasn't replied), `DECLINED`, or `QUOTED` — explicit per-supplier, not inferred from field presence.
_Avoid_: Inferring "hasn't replied" from the absence of other fields; it's its own named state

**Selection**:
The GM's chosen supplier + Version for an RFQ, proposed and then decided on by the Director. Always pins a specific Version, never a supplier alone — a supplier's price can move after proposal, and the Selection must survive that.
_Avoid_: Approval, choice

**Propose**:
The GM's act of putting forward a Selection. Re-proposing after a Decide clears the prior decision.
_Avoid_: Suggest, submit

**Decide**:
The Director's act of ratifying, overriding, or rejecting a proposed Selection. Not symmetric with Propose — Decide is a distinct, higher-authority act, not a second identical vote. Only a Reject re-opens the RFQ for a new Propose (clearing the prior proposed Selection, RFQ returns to `SENT`) — Ratify and Override both produce a `final` Selection that's treated as settled, not reproposable.
_Avoid_: Approve (too narrow — Decide also covers override and reject)

**Override**:
A Decide where the Director picks a different Version than the one the GM proposed. Both the proposed Selection and the final Selection are always recorded, even when they agree, so "was this overridden?" is always answerable.
_Avoid_: Change, correction

**Supplier Portal self-service**:
ERPNext's native capability for a supplier to submit a Supplier Quotation directly once an RFQ email reaches them — activated automatically by sending an RFQ natively, but deliberately ignored by this system (see ADR 0004). A supplier's price is only ever recorded through Office keying it in as a Version, regardless of how the supplier communicated it back (email, phone, or the portal).
_Avoid_: Treating a native Supplier Quotation as equivalent to a Version — it isn't consumed at all

## Purchase Order / Receipt / Stock

**Purchase Order (PO)**:
A commitment to buy, created manually by Office from a `DECIDED` RFQ — never auto-created off a Decide. Supplier, items, and price are derived from the RFQ's final Selection at creation time, not retyped.
_Avoid_: Auto-generating a PO the moment an RFQ is decided — that would skip a deliberate human act every other stage in this domain requires

**Receipt**:
The record of goods physically arriving against a PO, using ERPNext's native Purchase Receipt doctype as-is. A PO may be received in multiple partial Receipts (native `per_received` tracking) — this pilot doesn't assume single-shipment delivery.
_Avoid_: Assuming one Receipt closes a PO — partial/batched receipt is the expected case, not an edge case

**Stock**:
Read-only visibility into ERPNext's native Stock Ledger/Bin, updated automatically by ERPNext when a Receipt is submitted — no BFF logic involved. This pilot has no issue-to-production or other stock-consuming action in scope.
_Avoid_: Building any stock-mutating endpoint — everything here is native ERPNext behavior, observed only

## Sales Order (conceptual — not yet linked)

**Sales Order**:
ERPNext's native Selling-module doctype representing a client's own issued PO to us (`customer`, `po_no`, `po_date`, items, delivery date) — confirmed as the correct real-world "first step" upstream of both Material Request and Process Sheet: a client sends in their PO, and whoever receives it creates a Sales Order from it. Deliberately **not yet linked** to either Material Request (`raised_for` stays free-text) or Process Sheet (`client`/`drawing_no` stay free-text, no `sales_order` field) — known to be the right anchor conceptually, but staying lean until an actual need to query across the link is observed.
_Avoid_: Building a bespoke "Client Request" doctype for this — considered and dropped once Sales Order was confirmed to already cover it natively

## Process Sheet / Stage Inspection

**Process Sheet**:
A job-shop routing document, authored by a Programmer per client drawing, listing the ordered Operations (machine, spec, tolerance) needed to produce a part, plus the execution record (Operator, target/achieved qty, load/unload time) for that job — definition and actuals live together on one record (see ADR 0003). Modeled as a new custom doctype, not ERPNext's native Work Order/Job Card, which assume BOM-driven planning this domain doesn't have.
_Avoid_: Routing, Traveler (synonyms used in other shops; this organization's own document is titled "Process Sheet")

**Process Sheet Operation**:
A single numbered step in a Process Sheet's routing (e.g. Op. No. 03) — records who ran it, on what machine, and the qty/timing, but deliberately carries no technical description of what the step entails; that lives only in the Process Sheet's attached document, so nobody re-types the drawing's own spec into the system. Rows exist only for operations someone has actually started — created incrementally as work happens, not pre-populated as a full plan when the Process Sheet is created. A rework attempt appends a new row under the same Op. No. rather than overwriting the failed one; `rework`/`rejection` are independently recorded facts, never inferred from a Stage Inspection's outcome.
_Avoid_: Step (the organization's own document header is "Operation" / "Op. No."); treating this row as "the spec for the operation" — it never was

**Stage Inspection**:
The organization's own term for the per-operation dimensional QC check on a Process Sheet Operation — recorded using ERPNext's native Quality Inspection doctype under the hood, connected back to its Process Sheet via `reference_type`/`reference_name` plus a plain `op_no` field. Its overall pass/fail status is explicitly set by the Inspector once they've completed the inspection, not auto-derived from the individual reading rows.
_Avoid_: Using "Quality Inspection" in domain conversation — that's the underlying ERPNext doctype name, not what the organization calls it; the two terms refer to the same record in this system, so keep the mapping explicit rather than treating them as interchangeable vocabulary
