# eGOS Module — Implementation Spec for SmartOptics (Cloud PMS)

**Status:** Draft for review
**Audience:** Engineering, product
**Scope:** How to build an NHS England eGOS (electronic General Ophthalmic Services) claims module inside SmartOptics, a 100% cloud-based PMS.

> This spec is derived from the Optinet FLEX / Nova help articles supplied (the legacy desktop + part-cloud implementation). It re-expresses that behaviour as a cloud-native design and calls out where SmartOptics can do better than the legacy product. It is a **functional + architectural** spec — it does **not** yet include the PCSE wire-level message schemas, which we still need (see §13, Open Questions).

---

## 1. Purpose & scope

The eGOS module lets an optical practice create, sign, submit, track, reconcile and report on NHS GOS claims electronically to **PCSE (Primary Care Support England)**, without paper. It must cover the claim types FLEX already supports:

| Form  | Purpose                                                            | Notes |
|-------|-------------------------------------------------------------------|-------|
| GOS1  | NHS-funded sight test claim                                       | The high-volume everyday claim |
| GOS3  | Optical voucher towards spectacles (incl. **takeaway** vouchers)  | Has a "takeaway" / voucher-only (`GOS3_VO`) variant |
| GOS4  | Repair / replacement of spectacles                               | Paid value can differ from claimed → reconciliation matters |
| GOS5  | Complex / supplementary                                           | Lower volume |
| GOS6  | Domiciliary (home / care-home) sight test                        | Requires an **accepted PVN** first |
| PVN   | Pre-Visit Notification (precursor to GOS6)                        | Specifies venue + date/time of a domiciliary visit |

Out of scope for v1 (candidates for later): Wales/Scotland/NI GOS variants, non-GOS private claims.

---

## 2. Background — how eGOS works (domain primer)

- **PCSE** is the NHS body that receives GOS claims for England and pays contractors. eGOS went fully live Feb 2021.
- A practice is identified to PCSE by an **8-digit practice/site licence number** and an **NHS organisation (contractor) code**.
- To talk to PCSE, the **software vendor** (us) must hold a **Pre-Shared Key (PSK)** issued per practice. Onboarding a practice means requesting that PSK from PCSE on the practice's behalf (legacy: via a JotForm). Credentials stored per branch: org code, username, password, PSK.
- Claims are exchanged as **XML messages** over a PCSE endpoint. Submissions are validated server-side by PCSE and move through a status lifecycle (below). Responses are asynchronous.
- Most GOS forms require **two signatures**: the **patient** (declaration of eligibility) and the **performer/optometrist**.
- Money is reconciled later: PCSE issues a **statement** (downloadable CSV) showing what was actually paid; the practice imports it monthly to mark claims Paid and to catch under/overpayments.
- **Time limit:** as of 01/01/2024, claims must be submitted within **3 months**.

---

## 3. Domain model (entities)

All entities are tenant-scoped (see §10). Suggested core tables/aggregates:

### 3.1 `egos_practice_config` (per branch)
- `branch_id` (FK)
- `practice_licence_no` (8-digit)
- `org_code` (NHS contractor/ODS code)
- `pcse_username`, `pcse_password` (secret refs, not raw)
- `psk_secret_ref` (reference into secrets store — never the raw PSK)
- `auto_populate_voucher_values` (bool)
- `default_signature_method` enum: `signature_pad | mobile | screen | external`
- `active` (bool)

### 3.2 `egos_claim`
- `id`, `branch_id`, `patient_id`, `appointment_id?`, `performer_id`
- `form_type` enum: `GOS1 | GOS3 | GOS3_VO | GOS4 | GOS5 | GOS6`
- `status` (see §4 state machine)
- `claim_ref` (our internal ref) + `pcse_claim_ref` (assigned/echoed by PCSE)
- `pvn_id?` (FK, required for GOS6)
- `venue_id?` (FK, for domiciliary)
- `form_payload` (JSONB — the structured answers to the GOS form; see §3.7)
- `claimed_amount` (for voucher/repair forms)
- `paid_amount?`, `paid_date?`, `payment_statement_id?`
- `eligibility` (HC2/HC3/benefit codes etc. captured on the form)
- `submitted_at?`, `accepted_at?`, `rejected_reason?`
- `created_at`, `updated_at`, `created_by`
- Audit trail (append-only `egos_claim_event`).

### 3.3 `egos_signature`
- `id`, `claim_id`, `role` enum: `patient | performer`
- `image_ref` (object-store key for the signature image / vector)
- `captured_at`, `capture_method`, `device_info`
- `signatory_name`, `declaration_version`

### 3.4 `egos_pvn`
- `id`, `branch_id`, `venue_id`, `internal_ref`, `pvn_ref?` (PCSE), `status`
- `date_of_visit`, `estimated_time_of_visit`
- `contractor_details` (snapshot from branch setup)
- `patients[]` (a PVN can list many patients at a venue)
- Links to resulting `egos_claim` (GOS6) rows.

### 3.5 `egos_venue`
- `id`, `branch_id`, `name`, `address`, `postcode`
- `premises_type` enum: `D-DayCentre | H-Home | N-NursingHome | R-ResidentialHome | S-ShelteredHome`
- `contact_name`

### 3.6 `egos_payment_statement` + `egos_payment_line`
- Header from imported PCSE CSV; lines matched to claims for reconciliation.

### 3.7 GOS form payloads
Each `form_type` has a versioned JSON schema describing its fields (eligibility, clinical declarations, voucher band, prescription, performer declaration, etc.). Store as JSONB validated against the schema version recorded on the row, so form revisions by NHS/PCSE don't break old records.

---

## 4. Claim lifecycle (state machine)

Statuses observed in the legacy product, normalised:

```
                          ┌─────────────────────────────────────────┐
                          ▼                                         │
  DRAFT / DATA_ENTRY_IN_PROGRESS ──> READY_TO_CLAIM ──> SUBMITTED ──┤
                          │                                │        │
                          │                                ▼        │
                          │                          AWAITING_REVIEW│
                          │                                │        │
                          │                ┌───────────────┼────────┘
                          │                ▼               ▼
                          │            ACCEPTED         REJECTED ──> (fix) ──> READY_TO_CLAIM
                          │                │            FAILED_VALIDATION
                          │                ▼            ERROR
                          │              PAID
                          ▼
                       CANCELLED / CLOSED
```

- **Unfinished** = anything not in `{ACCEPTED, PAID}` → appears in worklists for staff to action.
- **Finished** = `ACCEPTED` (clinically/administratively done) or `PAID` (money reconciled).
- `REJECTED | FAILED_VALIDATION | ERROR` are recoverable: surface the PCSE reason, let staff correct and resubmit.
- Every transition writes an immutable `egos_claim_event` (who/when/from→to/payload) for audit.

---

## 5. Functional requirements

### 5.1 Onboarding & configuration
- Per-branch eGOS setup screen capturing licence no, org code, PCSE credentials, signature method, voucher auto-populate.
- PSK provisioning workflow: in-app request that we (vendor) action with PCSE; PSK stored only in the secrets manager, referenced by handle.
- Self-service "test connection" against PCSE to confirm credentials before go-live.

### 5.2 Create & complete a claim
- Start a claim from: **patient record**, **appointment**, or the **eGOS worklist**. Pre-populate patient demographics, performer, eligibility from the patient/appointment context.
- Form-type-specific guided form (validation client + server side against the form schema).
- **Voucher auto-population** (GOS3): pull the voucher band/value from the dispensed order / till where configured.
- Save as draft at any point; "Ready to Claim" gate runs full validation.
- **Rejections handling:** dedicated view of rejected/failed claims with the PCSE reason inline and a one-click "correct & resubmit" that reopens the form.

### 5.3 Domiciliary: PVN → GOS6
- Create a PVN from the patient record (pre-populates patient + assigned venue) or from reporting (blank PVN, contractor details from branch).
- A PVN must be **≥24h before** the visit and carry **date + time**.
- Submit PVN → must reach **ACCEPTED** before a GOS6 can be claimed against it.
- GOS6 creation auto-finds the patient's accepted PVN and populates PVN reference + "address where sight test took place".
- **Changes to date/time → create a NEW PVN** (recommended) rather than editing; editing a submitted PVN uses a different message format and is discouraged.
- Cancel a PVN only if previously accepted (otherwise delete).
- **Venues:** CRUD venues with premises type; assign many patients to one venue; assigning a venue can temporarily override the patient's address (restored on removal).

### 5.4 Signature capture (cloud-native)
Patient + performer signatures, captured on a touch device. Replace the legacy "signature webpage + refresh list" polling model with a real-time cloud flow:
- From the open claim, staff hit **Request signature** → SmartOptics pushes a signing session to the practice's paired device(s) in real time (WebSocket/push), no manual "refresh list".
- Device shows patient declarations (reasons for NHS test / eligibility) for the patient to read and accept, then captures the signature; performer signs likewise.
- Signature returns to the claim instantly and is stored as `egos_signature`.
- Support the same device classes the legacy system did — Android tablet, iPad/Safari, dedicated e-signature pad — but as **first-class paired devices**, authenticated by account/branch rather than re-typing licence-no + postcode each session.
- Configurable default method per branch; per-claim override.
- Works for domiciliary/off-site (device just needs internet — see §11 offline note).

### 5.5 Submission to PCSE
- Build the form-type XML from `form_payload`, sign/secure with PSK, POST to PCSE endpoint.
- Asynchronous: submission returns a pending state; a worker polls/receives PCSE responses and advances claim status.
- Idempotent submit (dedupe on internal ref) so retries can't double-claim.
- Full request/response logged (PII-aware) for support.

### 5.6 Management screen / worklists
- A live **eGOS dashboard** (the cloud successor to the FLEX "eGOS widget"/management screen): claims by status, by form type, by date, by branch.
- Built-in saved worklists mirroring the legacy "popular searches":
  - Unfinished claims (need action)
  - Rejected / failed validation
  - Today's claims (end-of-day "did everything submit?")
  - GOS3 takeaway vouchers outstanding / to retrieve
- Filter by date range, form type, status, branch; export.

### 5.7 Till / voucher reconciliation
Cross-check the till against eGOS, both directions (legacy "popular searches"):
- **Voucher in till but no eGOS claim started** (missing claim).
- **eGOS claim but no matching till voucher** (missing till entry).
- Surface as actionable lists tied to patient + invoice + claim.

### 5.8 Payment reconciliation
- Import the **PCSE statement CSV** (expanded format) monthly.
- Match statement lines to claims; set `PAID`, `paid_amount`, `paid_date`.
- **Under/overpaid detection** (esp. GOS3/4): flag where `paid_amount != claimed_amount`.
- Keep the imported statement available (e.g. for the accountant).

### 5.9 Reporting
- Claims by status / date / form type, printable + exportable.
- Reconciliation reports (till↔eGOS, claimed↔paid).
- **3-month time-limit ageing report**: claims approaching the deadline, plus a "write-off" workflow for uncollected GOS3 takeaways.
- GOS3 takeaway retrieval list.

---

## 6. Integration architecture (PCSE)

```
 SmartOptics (cloud)                                   PCSE / NHS
 ┌───────────────────────────┐                         ┌──────────────┐
 │ eGOS API (claims, PVN)     │                         │              │
 │   │                        │   XML over HTTPS        │  eOphthalmic │
 │   ├─ form builder ─────────┼──── submit ───────────► │  Payments    │
 │   │                        │   (PSK-secured)         │  endpoint    │
 │   ├─ submission worker ◄───┼──── async response ──── │              │
 │   │   (queue + retries)    │                         └──────────────┘
 │   └─ signature service     │
 │        (real-time push)    │        ┌──────────────────────────┐
 └───────────────────────────┘         │ Secrets manager (PSK,     │
                                        │ PCSE creds per branch)    │
                                        └──────────────────────────┘
```

Key points:
- **Async, queue-backed submission worker** (the SmartOptics equivalent of a background job): build XML → submit → handle PCSE acknowledgements/rejections → advance status. Retries with backoff; dead-letter for manual review.
- **PSK & credentials** live in a secrets manager, referenced per branch — never in the DB rows or source.
- **Form schemas versioned** so NHS/PCSE form changes are a config/schema update, not a code rewrite.
- **Separate message formats** for new PVN vs PVN edit vs cancel — model as distinct message builders.

---

## 7. Cloud-native fit within SmartOptics

The legacy product is desktop FLEX with bolt-on cloud workarounds. SmartOptics is 100% cloud, so several legacy frictions disappear:

| Legacy (FLEX/Nova) constraint | SmartOptics (cloud) approach |
|---|---|
| Signatures need "FLEX open" + dial-in for domiciliary | Signing session is a cloud push to any paired device; no host app must be running |
| Signature webpage: re-enter licence-no + postcode, manually "refresh list" | Paired, authenticated devices; real-time session push, no polling |
| Per-practice signature URL (Nova `/signatures`) | One app, tenant-scoped sessions; no per-practice URLs to bookmark |
| Monthly CSV import is the only payment path | Keep CSV import **and** add API-based statement retrieval if/when PCSE exposes one |
| Reports run on the local DB | Multi-branch reporting across the estate from one place |
| Claim status only as fresh as last "refresh" | Webhook/worker keeps status live |

The module slots in as a standard SmartOptics feature module (API service + worker + UI), reusing existing patient, appointment, till/invoice, branch and auth services rather than duplicating them.

---

## 8. Security, compliance & audit

- **NHS Data Security & Protection Toolkit** alignment; data residency in UK (the voice stack already targets UK South / Frankfurt — keep eGOS data UK-resident).
- PSK and PCSE credentials in a secrets manager; encrypted at rest; least-privilege access; rotation supported.
- Signatures are legal artefacts: store immutably with capture metadata (who/when/device/declaration version); never editable after capture.
- Append-only audit trail on every claim/PVN transition and every PCSE message.
- PII minimisation in logs; configurable retention; patient data handling per existing SmartOptics DPA.
- Role-based access (the legacy "add eGOS to Staff Type" becomes a proper permission).

---

## 9. Phased delivery plan

1. **Phase 1 — GOS1 happy path.** Config/onboarding, claim create/complete, signature capture, submit, status tracking, basic worklist. Highest volume, proves the PCSE integration end-to-end.
2. **Phase 2 — GOS3 + till reconciliation.** Voucher auto-population, takeaway handling, till↔eGOS cross-checks.
3. **Phase 3 — Payments.** PCSE statement import, paid/under/overpaid reconciliation, ageing/time-limit reporting.
4. **Phase 4 — Domiciliary.** Venues, PVN lifecycle, GOS6, off-site signing.
5. **Phase 5 — GOS4/5 + reporting polish.** Remaining form types, full reporting suite, write-off workflow.

Each phase is shippable and reuses the Phase-1 submission/worklist plumbing.

---

## 10. Multi-tenancy & data scoping

- Everything keyed by `branch_id` (and an owning `practice`/`organisation` above branch).
- A user may have access to multiple branches; eGOS worklists, dashboards and reports respect that scope and support cross-branch views for groups.
- PCSE identity (licence no, org code, PSK) is **per branch**, so submissions always carry the correct contractor identity.

---

## 11. Edge cases & operational notes

- **Off-site / poor signal (domiciliary):** signing device may be offline at point of care. Provide a PWA signing client that can capture the signature locally and sync the claim when back online; surface clearly that the claim is "captured, pending submission".
- **3-month deadline:** proactive surfacing + write-off workflow (uncollected GOS3 takeaways).
- **PVN date/time change:** force "create new PVN" path; block silent edits.
- **Idempotency:** dedupe submissions on internal ref to prevent double-claims on retry.
- **PCSE downtime:** queue and retry; never lose a claim because the endpoint was briefly unavailable.
- **Form-version drift:** validate against the schema version stored on the claim, not "latest".

---

## 12. Potential improvements (cloud + SmartOptics differentiators)

These go beyond parity with FLEX/Nova:

1. **Voice-driven claim entry.** SmartOptics already has the streaming Azure Speech stack with an optical/GOS phrase list (`server.py`). Let the optometrist dictate the sight-test findings and have the GOS form fields populate by voice — a genuine differentiator no legacy GOS product has. The phrase list already includes `GOS`, `GOS one`, `GOS three`, `GOS six`, `voucher`, `domiciliary`, `HC2`, `HC3`.
2. **Real-time signing, no polling.** Replace "open the webpage and press Refresh List" with a pushed signing session to paired devices — faster, fewer support calls.
3. **Auto-reconciliation.** Continuously match till vouchers ↔ eGOS claims and flag mismatches the moment they happen, instead of monthly popular-search sweeps.
4. **API-based payment reconciliation.** If PCSE offers (or later offers) a statement API, replace the manual monthly CSV import with automatic nightly sync; keep CSV as fallback.
5. **Deadline guardrails.** Automatic ageing alerts and nudges ("GOS3 takeaway for patient X expires in 14 days — chase or write off"), turning a manual monthly chore into a managed queue.
6. **Pre-submission validation against PCSE rules.** Validate the full ruleset client+server **before** submit so "Failed Validation" rejections become rare — catch them at data entry, not after a round-trip.
7. **Estate-wide dashboards.** For multi-branch groups, one live view of claim health, rejection rates, and outstanding money across all branches.
8. **Smart eligibility capture.** Guided eligibility (HC2/HC3/benefit) with inline checks to reduce eligibility-based rejections.
9. **Anomaly detection on payments.** Flag systematic under/overpayments (e.g. a form type consistently paid below claim) for the practice to query with PCSE.
10. **Full digital audit & e-sign provenance.** Immutable, queryable history per claim — useful for NHS post-payment verification/audit, which the legacy product handles only via printouts.

---

## 13. Open questions / what's still needed

The supplied documents are **end-user help articles**, not technical interface specs. To build the PCSE integration we still need:

1. **PCSE/eGOS message schemas** — the XML formats for each form type (GOS1/3/4/5/6), PVN (new/edit/cancel), and the acknowledgement/response messages.
2. **PCSE endpoint details** — URLs (test + prod), transport, and exactly how the **PSK** secures/authenticates a message (signing? envelope encryption?).
3. **Status vocabulary** — the authoritative PCSE status codes and rejection-reason codes to map onto our state machine.
4. **PCSE statement CSV spec** — exact "expanded" column layout for the payment importer.
5. **Onboarding/PSK request process** — current PCSE process for issuing a PSK to a software vendor on a practice's behalf.
6. **Eligibility/declaration rule set** — the validation rules behind each GOS form to power pre-submission validation.
7. **Certification** — any PCSE/NHS conformance testing required before a vendor can go live.

Once we have the PCSE technical pack (items 1–4 especially), this functional spec can be turned into a concrete API + schema + worker design.
