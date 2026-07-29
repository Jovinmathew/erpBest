# ERPNext RFQ sending, Letterhead/Print Format, and Supplier Portal — research

Scope: primary-source research (Frappe/ERPNext GitHub source + official docs.frappe.io pages) into whether native ERPNext already solves "get the RFQ letter in front of each supplier," to inform the BFF's RFQ-sending design per [ADR 0001](../adr/0001-erpnext-native-persistence.md)'s "reuse ERPNext's own native behavior" philosophy.

**Versions and commits cited.** ERPNext's GitHub repo (`frappe/erpnext`) keeps one long-lived branch per major version: `version-13`, `version-14`, `version-15` (plus `develop` for the unreleased next line, currently v16). Branch heads used below (fetched 2026-07-29):

| Repo | Branch | Commit SHA |
|---|---|---|
| `frappe/erpnext` | `version-13` | `37e00a66da7f38107ee31141c43154a4615ff568` |
| `frappe/erpnext` | `version-14` | `bd7e5b3e0589db07e45e49cbe1b250b62ad868d3` |
| `frappe/erpnext` | `version-15` | `c63022684605c912aba5464bb4f0a9c2e15ae255` |
| `frappe/frappe` | `version-15` | `95444a13d13bfaefda943a8597e1de3cf1f2b218` |

All ERPNext permalinks below use these three SHAs; all Frappe-framework permalinks use the `frappe/frappe@95444a1` SHA (framework behavior cited here — `sendmail`, `Letter Head`, `Print Format`, `Email Account` — did not show meaningful differences across v13/v14/v15 in what was checked, see the version-differences section for the one exception found).

---

## Summary — does native ERPNext already solve this?

**Mostly yes, for the core "letter reaches the supplier" mechanics — with real gaps around arbitrary file attachments requiring the Office user to attach files to the RFQ document first, and around whether the pilot wants to depend on ERPNext's own supplier-portal/user-account machinery at all.**

- RFQ has a native, whitelisted **`send_supplier_emails`** action (wired to a "Send Emails to Suppliers" button), and — importantly — **RFQ already auto-sends on submit** (`on_submit` calls `self.send_to_supplier()`), across v13, v14, and v15 alike. The manual button exists for **resending** (e.g. after adding a supplier or fixing an email address), not as the only trigger. See [Q1](#1-native-send-action).
- What gets sent is a real HTML email (Communication) with, optionally, a PDF of the RFQ rendered through the standard Print Format + Letter Head pipeline attached, plus any files already attached to the RFQ document. All of this is table-stakes Frappe framework capability (`frappe.sendmail`/`frappe.core.doctype.communication.email.make`, `frappe.attach_print`, `frappe.utils.print_format.download_pdf`) — **not ERPNext-specific and not something the BFF needs to reinvent.** See [Q2](#2-letterhead--print-format) and [Q3](#3-attaching-arbitrary-files).
- Arbitrary technical drawings/spec sheets **can** ride along on the auto-generated email natively — but only if they are already Frappe `File` attachments on the RFQ document before sending; there's no code path to attach ad-hoc files that aren't already attached to the doc. If the BFF's flow doesn't already put such files onto the RFQ record (e.g. because it's uploaded elsewhere or attached to the Material Request instead), the BFF would need to copy/attach it to the RFQ first — a real, if small, integration task, not a gap in ERPNext itself.
- A full **Supplier Portal** exists natively: an invited supplier gets emailed a portal link (and, if they don't have a Frappe user yet, a "set password" link — ERPNext creates a Website User for them automatically), logs in, and can submit a `Supplier Quotation` themselves from the portal page. This is a materially bigger commitment than "send an email" — it means ERPNext is creating and managing User/Contact/Portal User records for suppliers as a side effect of clicking Send. See [Q4](#4-supplier-portal).
- **The one non-trivial prerequisite is Email Account/SMTP setup.** A fresh ERPNext install has **no** default outgoing Email Account and the setup wizard does not create one — sending throws `frappe.OutgoingEmailError` ("Please setup default outgoing Email Account from Tools > Email Account") until an admin configures one (or `common_site_config.json` mail settings are present). This is real, one-time setup cost, not a code gap — see [Q5](#5-prerequisites--setup-cost).

**Net for the BFF:** the "send the letter" problem is close to fully solved by ERPNext's native RFQ send flow + Print Format/Letter Head + Email Account, requiring configuration (Email Account, a Letter Head, optionally an Email Template) rather than new code. The two design decisions genuinely left to the BFF are (a) whether to lean on ERPNext's supplier-portal/self-service-quote-submission machinery (which implicitly provisions Website Users for suppliers) versus treating the email as one-way and having Office staff record replies manually — ADR 0001 already leans towards the latter by rejecting native Supplier Quotation for storing quote Versions — and (b) making sure any supplier-facing attachment (drawing/spec) is actually attached to the RFQ document before the BFF triggers the native send, since ERPNext won't reach into other records for attachments.

---

## 1. Native send action

**Yes.** `RequestforQuotation.send_to_supplier()` iterates the RFQ's `suppliers` child table and, for each row with an email and `send_email` checked, builds and sends an email:

```python
def send_to_supplier(self):
	"""Sends RFQ mail to involved suppliers."""
	for rfq_supplier in self.suppliers:
		if rfq_supplier.email_id is not None and rfq_supplier.send_email:
			self.validate_email_id(rfq_supplier)
			# make new user if required
			update_password_link, contact = self.update_supplier_contact(rfq_supplier, self.get_link())
			self.update_supplier_part_no(rfq_supplier.supplier)
			self.supplier_rfq_mail(rfq_supplier, update_password_link, self.get_link())
			rfq_supplier.email_sent = 1
			...
```
[`request_for_quotation.py#L189-L203`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L189-L203) (v15)

Two entry points call it:

1. **Automatically on submit** — `on_submit` resets each supplier row to "Pending" and calls `send_to_supplier()` unconditionally: [`request_for_quotation.py#L158-L163`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L158-L163). This is **not new in v15** — the same `on_submit → send_to_supplier()` wiring exists in v14 ([`request_for_quotation.py#L76-L81`](https://github.com/frappe/erpnext/blob/bd7e5b3e0589db07e45e49cbe1b250b62ad868d3/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L76-L81)) and v13 ([`request_for_quotation.py#L76-L81`](https://github.com/frappe/erpnext/blob/37e00a66da7f38107ee31141c43154a4615ff568/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L76-L81)).
2. **The whitelisted "Send Emails to Suppliers" button**, for resending:
   ```python
   @frappe.whitelist()
   def send_supplier_emails(rfq_name):
   	check_portal_enabled("Request for Quotation")
   	rfq = frappe.get_doc("Request for Quotation", rfq_name)
   	if rfq.docstatus == 1:
   		rfq.send_to_supplier()
   ```
   [`request_for_quotation.py#L409-L414`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L409-L414), wired to a form button in the client script:
   ```js
   frm.add_custom_button(__("Send Emails to Suppliers"), function () {
       frappe.call({
           method: "erpnext.buying.doctype.request_for_quotation.request_for_quotation.send_supplier_emails",
           freeze: true,
           args: { rfq_name: frm.doc.name },
           callback: function (r) { frm.reload_doc(); },
       });
   }, __("Tools"));
   ```
   [`request_for_quotation.js#L47-L62`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.js#L47-L62)

**What it actually sends: both a portal link and (optionally) a PDF — configurable per RFQ, not hardcoded.**

`supplier_rfq_mail()` builds the message, then conditionally attaches:

```python
attachments = []
if self.send_attached_files:
	attachments = self.get_attachments()

if self.send_document_print:
	supplier_language = frappe.db.get_value("Supplier", data.supplier, "language")
	system_language = frappe.db.get_single_value("System Settings", "language")
	attachments.append(
		frappe.attach_print(
			self.doctype, self.name, doc=self,
			print_format=self.meta.default_print_format or "Standard",
			lang=supplier_language or system_language,
			letterhead=self.letter_head,
		)
	)

self.send_email(data, sender, rendered_subject, rendered_message, attachments)
```
[`request_for_quotation.py#L342-L366`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L342-L366)

`send_attached_files` and `send_document_print` are plain `Check` fields on the RFQ doctype (defaults: `send_attached_files=1`, `send_document_print=0`) — confirmed in the doctype JSON. The email body itself always carries a **portal link** button (`{{ portal_link }}`, rendered as an `<a>` to the supplier portal RFQ page) and, for suppliers without an existing Frappe user, a **"Set Password" link** (`{{ update_password_link }}`) — built in `supplier_rfq_mail()`: [`request_for_quotation.py#L299-L360`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L299-L360). So the email is portal-link-first by construction; the PDF is opt-in per RFQ.

**Template / Notification doctype used:** RFQ does **not** use Frappe's generic `Notification` doctype (that's for rule-based alerts on document events, unrelated here). Instead:
- v15: the RFQ document's own `message_for_supplier` (Text Editor) / `mfs_html` (Code, if `use_html` is checked) field is the message body, rendered via `frappe.render_template`; `Email Template` is optional and, if set, only supplies a fallback subject (`frappe.get_value("Email Template", self.email_template, "subject")`) — [`request_for_quotation.py#L326-L335`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L326-L335).
- v14 instead **requires** an `Email Template` record and renders its `response_`/`subject` fields directly: `email_template = frappe.get_doc("Email Template", self.email_template)` — [`request_for_quotation.py#L209-L211`](https://github.com/frappe/erpnext/blob/bd7e5b3e0589db07e45e49cbe1b250b62ad868d3/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L209-L211) (see [version differences](#version-differences-v13--v14--v15) — this is a real behavior change between v14 and v15, not just doc drift).
- v13 uses a fixed framework-shipped Jinja file, `templates/emails/request_for_quotation.html`, combined with the RFQ's own `message_for_supplier` field: [`request_for_quotation.py#L192-L204`](https://github.com/frappe/erpnext/blob/37e00a66da7f38107ee31141c43154a4615ff568/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L192-L204).

Delivery itself goes through `frappe.core.doctype.communication.email.make(..., send_email=True, doctype=self.doctype, name=self.name)` ([`request_for_quotation.py#L368-L378`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L368-L378)), which creates a `Communication` record (visible in the RFQ's activity/emails timeline) and queues the actual send — see [Q3](#3-attaching-arbitrary-files) for what `make()` does with attachments.

There is also an "Office staff preview before sending" affordance: `get_supplier_email_preview()` renders the same message/subject without sending, surfaced by a "Preview Email" dialog in the client script that also attaches a note: *"This is a preview of the email to be sent. A PDF of the document will automatically be attached with the email."* — [`request_for_quotation.js#L264-L324`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.js#L264-L324).

A separate, ad-hoc "Download PDF" button (Tools menu) lets a user pick a supplier + print format + language + letterhead and open a PDF directly (not emailed) via a whitelisted `get_pdf` endpoint — [`request_for_quotation.js#L64-L149`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.js#L64-L149), [`request_for_quotation.py#L553-L573`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L554-L573).

Corroborated by the official manual: *"Upon submission, an email to each supplier that has Send Email enabled"* is sent automatically, and the email template variables documented include `{{ update_password_link }}` ("A link where your supplier can set a new password to log into your portal") and `{{ portal_link }}` ("A link to this RFQ in your supplier portal") — [Request for Quotation — docs.frappe.io](https://docs.frappe.io/erpnext/request-for-quotation).

---

## 2. Letterhead + Print Format system

**Generic to any doctype — this is core Frappe framework machinery, not an ERPNext-specific or RFQ-specific feature**, despite the fact that the user-facing manual page for it happens to be hosted under a `/erpnext/` docs URL (`docs.frappe.io/erpnext/letter-head`). The `Letter Head` and `Print Format` doctypes both live in the `frappe/frappe` repo itself, under `frappe/printing/doctype/`, not in `frappe/erpnext`:
- [`frappe/printing/doctype/letter_head/letter_head.py`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/printing/doctype/letter_head/letter_head.py)
- [`frappe/printing/doctype/print_format/print_format.json`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/printing/doctype/print_format/print_format.json)

**Configuring a Letter Head:** create a `Letter Head` record, choose `source` = Image or HTML. If Image, attach a logo and the framework auto-generates header HTML into the `content` field via `set_image_as_html()`; there's a parallel `footer_source`/`footer_image`/`footer` pair for the footer. Exactly one Letter Head can be `is_default=1` at a time — `validate_disabled_and_default()` enforces "cannot be both disabled and default," and `on_update()`/`set_as_default()` unsets any other default and pushes `frappe.db.set_default("default_letter_head_content", ...)`. Full logic: [`letter_head.py#L1-L112`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/printing/doctype/letter_head/letter_head.py).

**Attaching a Letter Head to a document/print**: there is **no field on `Print Format` linking it to a specific Letter Head** — confirmed by walking the full field list of `print_format.json` (`doc_type`, `module`, `standard`, `print_format_type`, `html`, style/margin/font settings, `pdf_generator`, etc. — no letterhead field at all: [`print_format.json`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/printing/doctype/print_format/print_format.json)). Instead, letterhead selection happens **per print/PDF render call**, resolved by `get_letter_head()`:

```python
def get_letter_head(doc: "Document", no_letterhead: bool, letterhead: str | None = None):
	if no_letterhead:
		return {}
	letterhead_name = letterhead or doc.get("letter_head")
	if letterhead_name:
		return frappe.db.get_value("Letter Head", letterhead_name, [...], as_dict=True)
	else:
		return frappe.db.get_value("Letter Head", {"is_default": 1}, [...], as_dict=True) or {}
```
[`frappe/www/printview.py#L400-L421`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/www/printview.py#L400-L421)

So the precedence is: **explicit `letterhead` param → the document's own `letter_head` field (if the doctype has one) → the system default Letter Head → none.** A doctype only gets *per-document* letterhead override if it happens to carry its own `letter_head` Link field (RFQ does — see the `letter_head` field in its JSON, used explicitly in the `send_document_print` branch above); doctypes without that field simply fall back to the global default. `Print Settings.with_letterhead` is the master on/off toggle ("Enabling this property will automatically tick the Letter Head option when printing a document" — [Print Settings — docs.frappe.io](https://docs.frappe.io/erpnext/print-settings)), and `Print Settings.send_print_as_pdf` controls whether emailed/downloaded prints are PDF vs HTML.

**Generating a PDF with letterhead, in code**, three overlapping entry points, all framework-level:
- `frappe.utils.print_format.download_pdf(doctype, name, print_format=None, doc=None, no_letterhead=0, letterhead=None, ...)` — used by RFQ's own `get_pdf` whitelisted method: [`request_for_quotation.py#L553-L573`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L554-L573).
- `frappe.attach_print(doctype, name, print_format=None, doc=None, lang=None, print_letterhead=True, letterhead=None) -> {"fname":..., "fcontent": <pdf bytes>}` — used to build the emailed PDF attachment (see [Q1](#1-native-send-action)); if `print_letterhead` is true and no explicit `letterhead` is passed it falls back to `get_cached_value("Letter Head", {"is_default": 1}, "name")`: [`frappe/__init__.py#L2149-L2213`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/__init__.py#L2149-L2213).
- The web print view (`/printview`) itself, whose `get_letter_head()` is quoted above: [`frappe/www/printview.py`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/www/printview.py).

Official docs confirm the genericity and Jinja-level embedding: *"A Standard print format is generated for all DocTypes based on the form layout and mandatory fields in it"* ([Printing — docs.frappe.io/framework](https://docs.frappe.io/framework/user/en/printing)); custom print formats can embed `{{ letter_head }}` / `{{ footer }}` directly, and *"Footer will be visible only when the document's print is seen in the PDF... will not be visible in the HTML based print preview"* ([Letter Head — docs.frappe.io/erpnext](https://docs.frappe.io/erpnext/letter-head)).

**Bottom line for the BFF:** no custom code needed to get an RFQ PDF on organization letterhead — set one `Letter Head` record as default (or link it explicitly on the RFQ via its native `letter_head` field), and every PDF/print/emailed-attachment path already threads it through.

---

## 3. Attaching arbitrary files to the outgoing email

**Native capability, no custom code required — but attachments must already be attached to the reference document (or generated by print) before the send call; there's no "attach any file from anywhere" mechanism.**

The path RFQ uses: `get_attachments()` returns `[d.name for d in get_attachments(self.doctype, self.name)]` — [`request_for_quotation.py#L382-L383`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L382-L383), where the imported `get_attachments` is Frappe's own:
```python
def get_attachments(dt, dn):
	return frappe.get_all("File", fields=["name", "file_name", "file_url", "is_private"],
		filters={"attached_to_name": str(dn), "attached_to_doctype": dt})
```
[`frappe/desk/form/load.py#L191-L196`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/desk/form/load.py#L191-L196) — i.e. every Frappe `File` record already attached to that RFQ document (via the standard attach-file UI, drag-drop, or API upload). This is the mechanism that would carry a technical drawing or spec sheet: **attach it to the RFQ document as a File first** (native `Attach`-style capability every doctype has), and if `send_attached_files` is checked, it rides along automatically.

Those file names (plus, optionally, the `{"fname":..., "fcontent":...}` dict `attach_print()` returns for the generated PDF) are passed straight into `frappe.core.doctype.communication.email.make(..., attachments=attachments, send_email=True, ...)`:
```python
@frappe.whitelist()
def make(doctype=None, name=None, content=None, subject=None, ..., attachments=None, ...) -> dict[str, str]:
	"""...
	:param attachments: List of File names or dicts with keys "fname" and "fcontent"
	"""
```
[`frappe/core/doctype/communication/email.py#L27-L73`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/core/doctype/communication/email.py#L28-L73), which internally calls `add_attachments()`:
```python
def add_attachments(name, attachments):
	for a in attachments:
		if isinstance(a, str):
			attach = frappe.db.get_value("File", {"name": a}, ["file_url", "is_private"], as_dict=1)
			file_args = {"file_url": attach.file_url, "is_private": attach.is_private}
		elif isinstance(a, dict) and "fcontent" in a and "fname" in a:
			file_args = {"file_name": a["fname"], "content": a["fcontent"], "is_private": 1}
		...
		file_args.update({"attached_to_doctype": "Communication", "attached_to_name": name, ...})
		_file = frappe.new_doc("File"); _file.update(file_args); _file.save(ignore_permissions=True)
```
[`frappe/core/doctype/communication/email.py#L240-L274`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/core/doctype/communication/email.py#L240-L274) — each string is resolved as an existing `File` and re-attached to the outgoing `Communication`; each dict is written as a brand-new private `File` (this is how the freshly-rendered PDF gets attached).

The lower-level `frappe.sendmail(recipients=None, sender="", subject=..., message=..., attachments=None, ...)` accepts the same `attachments` shape at the framework level (any code path, not just the Communication composer) — [`frappe/__init__.py#L688-L761`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/__init__.py#L688-L761), and is the general-purpose primitive the Notification doctype, workflow-alert emails, and any custom server script would use for the same purpose.

**Practical implication for the BFF:** if a drawing/spec sheet the BFF wants supplied lives on the Material Request (or elsewhere) rather than the RFQ itself, the BFF would need to copy it onto the RFQ as a `File` (a one-line `frappe.new_doc("File")` / REST equivalent) before triggering `send_supplier_emails` — small integration glue, not a gap in ERPNext's own capability.

---

## 4. Supplier Portal

**Yes — ERPNext has a native, functioning supplier portal for RFQ response, and the "Send Emails" action is the actual mechanism that provisions supplier access to it.**

`send_to_supplier()` calls `self.get_link()` to compute the portal URL:
```python
def get_link(self):
	# RFQ link for supplier portal
	route = frappe.db.get_value("Portal Menu Item", {"reference_doctype": "Request for Quotation"}, ["route"])
	if not route:
		frappe.throw(_("Please add Request for Quotation to the sidebar in Portal Settings."))
	return get_url(f"{route}/{self.name}")
```
[`request_for_quotation.py#L205-L213`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L205-L213). ERPNext ships this Portal Menu Item **out of the box**: `erpnext/hooks.py` registers RFQ as a `standard_portal_menu_items` entry with route `/rfq` and `role: "Supplier"`:
```python
standard_portal_menu_items = [
	...
	{"title": "Request for Quotations", "route": "/rfq", "reference_doctype": "Request for Quotation", "role": "Supplier"},
]
```
[`erpnext/hooks.py#L211-L218`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/hooks.py#L211-L218) — and the corresponding website route/page controller exists at [`erpnext/templates/pages/rfq.py`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/templates/pages/rfq.py), which locks the page to the requesting supplier's own record via `unauthorized_user()`/`check_supplier_has_docname_access()` ([`rfq.py#L32-L46`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/templates/pages/rfq.py#L32-L46)). The `check_portal_enabled()` guard in the send flow only fails if an admin has explicitly disabled that Portal Menu Item ([`request_for_quotation.py#L417-L423`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L417-L423)) — the default state, as shipped, is enabled.

**Portal user accounts are provisioned automatically, as a side effect of sending, not a manual pre-requisite:**
```python
def update_supplier_contact(self, rfq_supplier, link):
	"""Create a new user for the supplier if not set in contact"""
	if frappe.db.exists("User", rfq_supplier.email_id):
		user = frappe.get_doc("User", rfq_supplier.email_id)
	else:
		user, update_password_link = self.create_user(rfq_supplier, link)
	contact = self.link_supplier_contact(rfq_supplier, user)
	return update_password_link, contact
```
[`request_for_quotation.py#L222-L233`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L222-L233), and `create_user()` makes a `user_type: "Website User"` account with `send_welcome_email: 0`, generating a password-reset link instead: [`request_for_quotation.py#L275-L297`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L275-L297). The user is then linked into `Supplier.portal_users` (`update_user_in_supplier()`, [`request_for_quotation.py#L258-L273`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L258-L273)) and a `Contact` is created/linked to the `Supplier` if one didn't already exist (`link_supplier_contact()`, [`request_for_quotation.py#L235-L256`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L235-L256)). So: **the email always contains a portal link; whether it also needs a "set password" link depends purely on whether that supplier email already has a Frappe User** — no separate manual account-provisioning step exists or is required.

**Once on the portal**, the supplier's browser-side JS calls a whitelisted endpoint to submit their quote directly, without email:
```js
frappe.call({
	method: "erpnext.buying.doctype.request_for_quotation.request_for_quotation.create_supplier_quotation",
	...
});
```
[`erpnext/templates/includes/rfq.js#L77-L80`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/templates/includes/rfq.js#L77-L80), which server-side creates a native **Supplier Quotation** document, gated to users linked as a `Portal User` on that supplier:
```python
@frappe.whitelist()
def create_supplier_quotation(doc):
	...
	if frappe.session.user not in frappe.get_all("Portal User", {"parent": doc.get("supplier")}, pluck="user"):
		frappe.throw(_("Not Permitted"), frappe.PermissionError)
	sq_doc = frappe.get_doc({"doctype": "Supplier Quotation", ...})
	...
```
[`request_for_quotation.py#L480-L511`](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L482-L511). The official manual corroborates end-to-end: *"If no account exists, the system creates one and sends credentials... If an account exists, the system sends a login link... suppliers access a portal form to submit quotation details with amounts and payment terms"* and *"The supplier can submit you a quotation himself via ERPNext"* — [Request for Quotation](https://docs.frappe.io/erpnext/request-for-quotation), [Supplier Quotation](https://docs.frappe.io/erpnext/supplier-quotation).

**Relevance to this project's own ADRs:** [ADR 0001](../adr/0001-erpnext-native-persistence.md) already deliberately rejected native `Supplier Quotation` as the storage shape for negotiated quote Versions (item-line-heavy, doesn't fit the flat price/currency/terms-per-Version domain model) — this research doesn't change that call, but it does mean the BFF should decide explicitly whether to also **disable/ignore** the self-service portal submission path (leaving the RFQ email as one-way, with Office staff transcribing supplier replies into the BFF's own custom fields as ADR 0001 already does), or embrace it and read `Supplier Quotation` as a secondary/informal channel. Nothing in the native send flow forces either choice — the portal-submission code path only fires if a supplier actually logs in and submits, which requires no extra configuration to *reach* (it's live on submit) but the BFF's domain model doesn't currently read from it.

---

## 5. Prerequisites / setup cost

**Real, one-time setup cost — not something that works purely out of the box.** A fresh ERPNext install has no outgoing Email Account, and the setup wizard does not create one:

- `frappe/desk/page/setup_wizard/install_fixtures.py` (which seeds various defaults during setup) contains no Email Account creation logic at all — only creates `Email Unsubscribe` fixture rows for `admin@example.com`/`guest@example.com` — [`install_fixtures.py`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/desk/page/setup_wizard/install_fixtures.py). `frappe/desk/page/setup_wizard/setup_wizard.py` has no Email Account references either.
- When ERPNext (or any Frappe code) tries to resolve an outgoing account and none is configured, `EmailAccount.find_outgoing(..., _raise_error=True)` throws:
  ```python
  @classmethod
  def find_default_outgoing(cls):
  	"""Find default outgoing account."""
  	doc = cls.find_one_by_filters(enable_outgoing=1, default_outgoing=1)
  	doc = doc or cls.find_from_config()
  	return doc or (are_emails_muted() and cls.create_dummy())
  ```
  and the caller:
  ```python
  if _raise_error:
  	frappe.throw(_("Please setup default outgoing Email Account from Tools > Email Account"), frappe.OutgoingEmailError)
  ```
  [`frappe/email/doctype/email_account/email_account.py#L382-L417`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/email/doctype/email_account/email_account.py#L382-L417).

**What has to be configured before RFQ sending works, in practice:**
1. **An `Email Account`** with `enable_outgoing=1` and `default_outgoing=1` (SMTP host/port/credentials, or OAuth), created manually via the desk UI ("Tools > Email Account" per the thrown error message) — **or**, as a fallback recognized by `find_from_config()` ([`email_account.py#L371-L376`](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/email/doctype/email_account/email_account.py#L371-L376)), mail server settings placed directly in `common_site_config.json`/site config — either way, an admin action, not zero-config.
2. **At least one default `Letter Head`** if the org wants its logo/address on the PDF attachment (optional — RFQ will still send without one, just with no letterhead on the PDF).
3. Optionally an `Email Template` (mandatory in v14's code path, optional in v15's — see below) if the org wants a reusable subject/body template rather than editing the RFQ's own `message_for_supplier` field per RFQ.
4. The RFQ Portal Menu Item must remain enabled (it is enabled by default per ERPNext's `standard_portal_menu_items` hook — see [Q4](#4-supplier-portal)) if the org wants the portal-link / self-service-quote path to function; this needs no setup unless previously disabled.

None of this is unique to RFQ — it's the same Email Account prerequisite every outgoing Frappe email (password resets, notifications, other document "send" actions) depends on, so if the BFF's ERPNext instance already sends any mail today (e.g. user-invite emails), this prerequisite is already satisfied.

---

## Version differences (v13 / v14 / v15)

Framework-level behavior (`frappe.sendmail`, `Communication.make`, `Letter Head`, `Print Format`, `Print Settings`, `Email Account.find_outgoing`) showed no meaningful differences across the versions checked. RFQ-specific behavior in `erpnext` did change across versions in three ways:

1. **Auto-send-on-submit and the manual resend button are unchanged since at least v13** — `on_submit` has called `send_to_supplier()` and a "Send Emails to Suppliers" / "Download PDF" button pair has existed in the client script in all three versions checked ([v13](https://github.com/frappe/erpnext/blob/37e00a66da7f38107ee31141c43154a4615ff568/erpnext/buying/doctype/request_for_quotation/request_for_quotation.js#L47-L93), [v14](https://github.com/frappe/erpnext/blob/bd7e5b3e0589db07e45e49cbe1b250b62ad868d3/erpnext/buying/doctype/request_for_quotation/request_for_quotation.js#L47-L61), [v15](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.js#L47-L62)). Not a difference — noted to rule it out.

2. **Attachment control was added in v14, absent in v13.** v13's `get_attachments()` unconditionally appends a freshly-`attach_print()`'d PDF to whatever files are already attached — no way to opt out per RFQ:
   ```python
   def get_attachments(self):
   	attachments = [d.name for d in get_attachments(self.doctype, self.name)]
   	attachments.append(frappe.attach_print(self.doctype, self.name, doc=self))
   	return attachments
   ```
   [`request_for_quotation.py#L227-L230`](https://github.com/frappe/erpnext/blob/37e00a66da7f38107ee31141c43154a4615ff568/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L227-L230) (v13). v14 introduces the `send_attached_files`/`send_document_print` `Check` fields and branches on them (confirmed present in the v14 doctype JSON with the same field names/defaults as v15). If the BFF ever needs to support a pilot instance still running v13, "don't attach the PDF" isn't an option without a code patch.

3. **The email body/template source changed twice.** v13 renders a fixed framework HTML template file plus the RFQ's own `message_for_supplier` field; v14 requires an `Email Template` record and renders its `response_`/`subject` fields directly, with no fallback if `email_template` is unset (`frappe.get_doc("Email Template", self.email_template)` on [`request_for_quotation.py#L209`](https://github.com/frappe/erpnext/blob/bd7e5b3e0589db07e45e49cbe1b250b62ad868d3/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L209) — despite the RFQ doctype JSON still carrying a mandatory-by-schema `message_for_supplier` field that this v14 code path never reads, a discrepancy worth flagging rather than fully explaining); v15 reverts to using the RFQ's own inline `message_for_supplier`/`mfs_html` fields as primary source, with `Email Template` now optional and used only as a subject fallback. **If the target ERPNext instance is v14, the BFF/Office user must ensure an `Email Template` is set on every RFQ or sending will error**, unlike v13 or v15.

4. **`get_pdf`'s signature/UX gained supplier-facing print controls between v13 and v14, unchanged v14→v15.** v13: `get_pdf(doctype, name, supplier)` — Download PDF prompt only asks for a Supplier ([`request_for_quotation.js#L60-L93`](https://github.com/frappe/erpnext/blob/37e00a66da7f38107ee31141c43154a4615ff568/erpnext/buying/doctype/request_for_quotation/request_for_quotation.js#L60-L93)). v14/v15: `get_pdf(name, supplier, print_format=None, language=None, letterhead=None)` and the Download PDF prompt additionally offers Print Format / Language / Letter Head pickers ([v14](https://github.com/frappe/erpnext/blob/bd7e5b3e0589db07e45e49cbe1b250b62ad868d3/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L418-L437), [v15](https://github.com/frappe/erpnext/blob/c63022684605c912aba5464bb4f0a9c2e15ae255/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py#L554-L573)).

Everything else checked for this research (native send action's existence, portal-link + set-password-link email content, Supplier Quotation portal submission flow, Letter Head/Print Format genericity, Email Account prerequisite/error message) was consistent across v13, v14, and v15 in what was directly read from source.
