---
status: accepted
---

# RFQ sent via ERPNext's native supplier-email action; native Supplier Portal self-service deliberately ignored

Sending an RFQ to suppliers is not something the BFF builds — it triggers ERPNext's own native capability. Checked directly against the live instance (v16.29.0) and confirmed via `docs/research/erpnext-rfq-send-and-letterhead.md`: the native Request for Quotation doctype already has fields (`email_template`, `subject`, `message_for_supplier`, `mfs_html`, `use_html`, `send_attached_files`, `send_document_print`, `letter_head`) backing a built-in supplier-email action — composing a Letterhead-styled PDF and emailing suppliers directly, no custom mailer or template system required. Two Letter Head records already exist in the instance (`Company Letterhead`, `Company Letterhead - Grey`).

The BFF's `POST /rfqs` therefore: creates the native RFQ doc, copies any Frappe File attachments from the originating Material Request onto the RFQ itself (native send only carries attachments already on the RFQ doc, not the MR — a gap the BFF has to bridge), then submits the RFQ, which fires the native email. `letter_head`, `subject`, `message_for_supplier`, `use_html`, and `message_for_supplier_html` are required inputs on this call, not defaulted — Office is expected to make a deliberate call on wording per RFQ rather than always getting the same boilerplate.

Sending natively also activates ERPNext's Supplier Portal — any supplier who receives the email can self-submit a native **Supplier Quotation** directly, entirely independent of anything the BFF does. This is deliberately **ignored**. ADR 0001 already rejected native Supplier Quotation as the store for quote Versions (too item-line-heavy for the flat price/currency/terms model); building a sync to translate portal-submitted Supplier Quotations into the BFF's custom Version fields would reintroduce that exact mismatch, just moved into sync code instead of avoided. If a supplier does submit one via the portal, it sits inert in ERPNext — Office still keys the actual price into the custom Version fields the same way regardless of how the supplier communicated it back (email reply, phone, or portal).

**Considered and rejected:**
- **BFF composes and sends its own supplier email**, independent of ERPNext's native capability. Rejected once the native fields were confirmed live — would duplicate letterhead rendering, template logic, and attachment handling ERPNext already does for free.
- **Consuming native Supplier Quotation submissions from the Supplier Portal** (a sync/webhook translating them into custom Version entries). Rejected: reopens the exact item-line-vs-flat-price mismatch ADR 0001 already walked away from, just relocated into new sync code instead of eliminated.
- **A resend/reminder action** (re-triggering ERPNext's manual "Send Supplier Emails" for a supplier who hasn't replied). Out of scope for now — not needed until the basic send path is proven out.

**Consequences:**
- An Email Account must be configured in ERPNext before send works at all (confirmed live: 0 configured currently) — one-time manual setup, consistent with ADR 0001's "provision manually" pattern, not something the BFF can paper over.
- Supplier master data must exist before any RFQ can be sent (confirmed live: 0 Supplier records currently) — also manual setup, not a BFF concern.
- If supplier self-service via the Portal later becomes a real priority, this ADR's "ignore it" stance should be revisited explicitly — it is a deliberate simplification, not an oversight.
