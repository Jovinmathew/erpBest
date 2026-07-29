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
A supplier's refusal to quote at all — distinct from a Quote with no Versions yet, which means "hasn't replied."
_Avoid_: Reject (reserved for the GM/Director acting on an MR or a proposed Selection)

**Selection**:
The GM's chosen supplier + Version for an RFQ, proposed and then decided on by the Director. Always pins a specific Version, never a supplier alone — a supplier's price can move after proposal, and the Selection must survive that.
_Avoid_: Approval, choice

**Propose**:
The GM's act of putting forward a Selection. Re-proposing after a Decide clears the prior decision.
_Avoid_: Suggest, submit

**Decide**:
The Director's act of ratifying, overriding, or rejecting a proposed Selection. Not symmetric with Propose — Decide is a distinct, higher-authority act, not a second identical vote.
_Avoid_: Approve (too narrow — Decide also covers override and reject)

**Override**:
A Decide where the Director picks a different Version than the one the GM proposed. Both the proposed Selection and the final Selection are always recorded, even when they agree, so "was this overridden?" is always answerable.
_Avoid_: Change, correction

## Process Sheet / Stage Inspection

**Process Sheet**:
A job-shop routing document, authored by a Programmer per client drawing, listing the ordered Operations (machine, spec, tolerance) needed to produce a part, plus the execution record (Operator, target/achieved qty, load/unload time) for that job — definition and actuals live together on one record (see ADR 0003). Modeled as a new custom doctype, not ERPNext's native Work Order/Job Card, which assume BOM-driven planning this domain doesn't have.
_Avoid_: Routing, Traveler (synonyms used in other shops; this organization's own document is titled "Process Sheet")

**Process Sheet Operation**:
A single numbered step in a Process Sheet's routing (e.g. Op. No. 03) — one machine, one spec, one Operator, one row in the Process Sheet's child table.
_Avoid_: Step (the organization's own document header is "Operation" / "Op. No.")

**Stage Inspection**:
The organization's own term for the per-operation dimensional QC check on a Process Sheet Operation — recorded using ERPNext's native Quality Inspection doctype under the hood, connected back to its Process Sheet via `reference_type`/`reference_name` plus a plain `op_no` field.
_Avoid_: Using "Quality Inspection" in domain conversation — that's the underlying ERPNext doctype name, not what the organization calls it; the two terms refer to the same record in this system, so keep the mapping explicit rather than treating them as interchangeable vocabulary
