---
title: "eGOS (NHS England) Module — Specification"
subtitle: "SmartOptics · Rev 1 · 29 June 2026 · Confidential — Internal Only"
---

# Document Details

| Field | Value |
|---|---|
| Document | SmartOptics eGOS (NHS England) Module Specification |
| Revision | Rev 1 — initial draft. Specifies the NHS England electronic GOS claims module: GOS 1 / 3 / 4 / 5 / 6, Pre-Visit Notifications and domiciliary, e-signature capture, submission to NHS / PCSE, payment and till reconciliation, worklists and reporting. Folds in a competitive-gap review of Optix / Optix 2 and the incumbent FLEX / Nova product. |
| Status | Draft for review. |
| Module sequence | Depends on the Patient module, the Till / Dispensing module and the Business Intelligence module; consumes the NHS Gateway integration; relates to the Diary / Calendar module (domiciliary visits, end-of-day claim check) and the Communications module (signing-session push, patient chase). Exact sequence position to be set in the Top-Level Spec module development plan. |
| Author | Claude (initial draft) |
| Predecessors | Top-Level Spec; Patient Module Spec; Diary / Calendar Module Spec; Till / Dispensing Module Spec; Practice DB Schema Index. |
| Successors | Business Intelligence module (eGOS dashboards, reconciliation, forecasting); Payments module (if NHS voucher receipts are folded into the payments ledger); Patient App module. |

# Document Revision History

| Date | Author | Revision | Comments |
|---|---|---|---|
| 29 Jun 2026 | Claude | Rev 1 | Initial draft. Establishes the eGOS module in the SmartOptics house style: cross-module critical issues (§0), objective (§1), scope (§2), conceptual model (§3), module integration map (§4), configuration and roles (§5), claim lifecycle (§6), submission-readiness / auto-submit model (§7), core workflows for GOS 1 / 3 / 4 / 6 and domiciliary (§8), signature capture and rejection prevention (§9), worklists and reporting (§10), data model (§11), integration with other modules and the NHS Gateway (§12), security and audit (§13), competitive analysis and differentiation (§14), feature comparison matrix (§15), phased delivery (§16), open questions (§17), referenced documents (§18). Derived from the Optinet FLEX / Nova help material and an Optix / Optix 2 help-documentation review. |

# 0. Critical issues — read before sign-off

This section is placed first deliberately. It records the cross-module dependencies that govern whether the eGOS module can be built and signed off on its own, and the sequencing risks the team must resolve.

## 0.1 CRITICAL — NHS Gateway (PCSE) interface is an external dependency

The module cannot submit a single claim without the NHS / PCSE interface. Per the agreed working assumption, the submission, status-response, signing-content and payment-statement interfaces are **provisioned once the practice is signed up for eGOS**. All NHS specifics are isolated behind a single internal **NHS Gateway** service (§12.2) so the rest of the module is built and tested against a mock Gateway now and wired to the live endpoints on sign-up without touching workflow code.

Required actions before build sign-off: confirm the eGOS sign-up and Pre-Shared Key (PSK) provisioning route with PCSE; confirm the Gateway contract (message set, status vocabulary, statement format) so the mock matches production; agree a fallback if a practice's PSK is not issued before go-live.

## 0.2 IMPORTANT — Eligibility fields depend on the Patient module's NHS-entitlement record

Claim eligibility pre-fills from the patient record's NHS-entitlement section (why this patient — and, where relevant, another person — is entitled). Those fields must exist and be captured in the canonical patient entity. The eGOS module reads them; it does not own them. Dependency on the Patient module.

## 0.3 IMPORTANT — GOS3 / GOS4 voucher value depends on the Till / Dispensing module

The GOS3 / GOS4 voucher type and value are calculated live inside the spectacle dispense. This depends on the Till / Dispensing module exposing the dispense contents and an **EGOS payment type**, and on the agreed contract by which the dispense feeds voucher type and value to the claim (§12.3).

## 0.4 IMPORTANT — Real-time signing depends on the platform real-time channel and a device registry

The signing-session push to a paired tablet (§9) depends on the platform's real-time channel and a paired-device registry authenticated by account / branch. If the real-time channel is not available at MVP, signing falls back to a device-pull model behind a feature flag.

## 0.5 IMPORTANT — Payment reconciliation lives in the Business Intelligence module

Importing the PCSE statement and auto-reconciling payments (§8.6, §10) is delivered in the Business Intelligence module. The eGOS module raises the claim and exposes claimed / paid state; BI owns the statement import and the reconciliation reports.

# 1. Objective and goal statement

This document specifies the **eGOS (NHS England) module** — the surface through which a practice creates, signs, submits, tracks, reconciles and reports on NHS General Ophthalmic Services claims to Primary Care Support England (PCSE), with no paper and no separate NHS portal.

The product goal is that NHS claiming becomes a by-product of normal front-of-house work rather than a separate administrative chore: a claim assembles itself as the patient is seen, dispensed and rung through the till, and **submits itself** the moment it is complete. Three design principles shape every decision here:

- **Claiming should be invisible.** Staff do their normal job — examine, dispense, take payment, capture a signature — and the claim completes and submits without a separate "do the NHS claim" step.
- **Catch errors before the NHS does.** Eligibility and validation are checked at the point of entry so rejections become rare, not corrected after a round-trip.
- **Money must be visible.** What has been claimed, accepted, paid, under-paid and is ageing toward the deadline is shown as a live cashflow view, not reconstructed monthly by hand.

# 2. Scope

## 2.1 In scope

- GOS 1 (NHS sight test) claim creation, signing, submission and tracking.
- GOS 3 (optical voucher) raised within the spectacle dispense, with live voucher-type / value calculation, the takeaway / voucher-only variant, and the two-stage (order + collection) patient signature.
- GOS 4 (repair / replacement) including the NHS approval code for adults.
- GOS 5 (complex / supplementary).
- GOS 6 (domiciliary sight test) and the Pre-Visit Notification (PVN) lifecycle it depends on.
- Venues (care homes / day centres / patient homes) and care-home batch visits.
- The submission-readiness checklist and auto-submission model (§7).
- E-signature capture on a paired tablet — patient, performer and contractor, including batch signing.
- Eligibility intelligence and pre-submission validation (§9).
- Claim status lifecycle, worklists and an eGOS dashboard (§10).
- Till ↔ eGOS reconciliation and (consumed from the Business Intelligence module) PCSE payment-statement reconciliation, under / over-payment detection and the 3-month deadline ageing view.
- Per-branch configuration and the Performer / Contractor / pre-registration roles (§5).

## 2.2 Out of scope

- The NHS / PCSE wire-level transport, message schemas and PSK handshake — owned by the NHS Gateway integration (§12.2); the module consumes the Gateway contract.
- The patient's NHS-entitlement data capture — owned by the Patient module; the eGOS module reads it.
- The spectacle dispense itself and the till — owned by the Till / Dispensing module; the eGOS module embeds against its contract.
- Importing the PCSE payment statement and the reconciliation reporting surface — owned by the Business Intelligence module.
- Wales / Scotland / Northern Ireland GOS variants — England only at MVP.
- Private (non-GOS) claims.

# 3. Conceptual model

The module is built on a small set of concepts. Every screen and API call reduces to operations on them.

- **Claim** — one GOS claim of a given form type for one patient, carrying a status, a readiness checklist, the form payload, eligibility, the claimed and paid amounts, and links to its signatures and (for domiciliary) its PVN and venue.
- **Form type** — `GOS1`, `GOS3`, `GOS3_VO` (takeaway / voucher-only), `GOS4`, `GOS5`, `GOS6`. The form payload is versioned per type so NHS form revisions do not break historical records.
- **PVN (Pre-Visit Notification)** — the precursor to a GOS6: a venue and a date / time of visit, submitted to PCSE and required to be Accepted before the GOS6 can be claimed.
- **Venue** — a domiciliary location (Day Centre / Home / Nursing / Residential / Sheltered Home), to which many patients may be linked for batch visits.
- **Signature** — an immutable captured signature for a role (patient / performer / contractor) with capture metadata and the declaration version signed.
- **Status lifecycle** — the states a claim moves through (§6).
- **Readiness checklist** — the set of prerequisites that, once all met, cause a claim to submit itself (§7).

# 4. Where the eGOS module sits in the PMS

The eGOS module is not a silo; it threads through modules the practice already uses. The integration points:

| Module | What the eGOS module uses / adds |
|---|---|
| Patient module | Start a claim or PVN with patient details and the NHS-entitlement section pre-filled; view a patient's claim history. |
| Diary / Calendar module | Start a GOS1 from an appointment; the end-of-day check compares accepted claims against booked appointments. |
| Till / Dispensing module | GOS3 / GOS4 voucher value calculated live from the dispense; the EGOS payment type links the claim to the financial side and satisfies the "used in till" step; basis for till ↔ eGOS reconciliation. |
| Business Intelligence module | eGOS dashboards and worklists, PCSE statement import, payment reconciliation, under / over-payment detection, ageing and forecasting. |
| Communications module | Pushes the signing session to the paired device; patient chase for uncollected takeaway vouchers. |
| Branch / Practice settings | Per-branch eGOS configuration (licence number, ODS code, PCSE credentials + PSK, signature method, roles). |

# 5. Configuration and roles

## 5.1 Per-branch configuration

Configured once under Branch settings → Integrations → eGOS (NHS England):

- **Practice licence number** (8-digit site number) and **NHS organisation (ODS / contractor) code**.
- **PCSE credentials and Pre-Shared Key (PSK)** — provisioned on sign-up; stored as secret references, never shown in plain text.
- **Auto-populate voucher values** (on / off) — pulls GOS3 voucher amounts from the dispense.
- **Default signature method** — e-signature pad / mobile device / on-screen / external capture.
- **Active** toggle and a one-click **Test NHS connection** to confirm the link before go-live.

Multi-branch groups configure each branch separately, because the NHS contractor identity (licence number, ODS code, PSK) is per branch — every submission carries the correct identity.

## 5.2 Clinical roles

Two NHS-specific roles are modelled, matching how PCSE attributes a claim:

- **Performer** — the optometrist who carries out the sight test. Requires a **GOC number** (7–8 characters including the hyphen) on their staff record.
- **Contractor** — the NHS-contracted owner who signs vouchers for the branch(es) assigned to them.
- **Pre-registration students** — a flag that routes their completed exams to an assigned supervising performer to check and sign.

One person may hold both Performer and Contractor roles (then both signatures can be applied together). An "eGOS" capability is granted to the relevant staff roles.

# 6. Claim lifecycle

Every claim moves through a status shown everywhere it is listed:

```
 DATA ENTRY IN PROGRESS ─► READY TO CLAIM ─► SUBMITTED ─► AWAITING REVIEW ─┬─► ACCEPTED ─► PAID
        (draft)                                                            │
                                                                           └─► REJECTED / FAILED VALIDATION / ERROR
                                                                                   │
                                                                                   └─(correct)─► READY TO CLAIM
   at any time, where valid:  CANCELLED  /  CLOSED
```

- **Unfinished** = anything not yet `ACCEPTED` or `PAID`; these populate the worklists staff action.
- **Finished** = `ACCEPTED` (NHS has accepted it) or `PAID` (money reconciled against a statement).
- `REJECTED` / `FAILED VALIDATION` / `ERROR` are recoverable: the NHS reason is shown inline; staff correct and resubmit (§9.3).
- Every transition writes an immutable event (§11) for NHS post-payment verification.

# 7. Submission-readiness model (checklist → auto-submit)

Rather than relying on staff to remember to submit, a claim carries a **readiness checklist** and **submits itself** the moment every prerequisite is met. For a GOS1 the prerequisites are:

| Prerequisite | Satisfied when… |
|---|---|
| Patient signed | The patient signs on the device |
| Used in till | The NHS sight-test item is rung through the till against the EGOS payment type |
| Performer recorded | The eye exam is saved to the patient record (performer + retest code attach automatically) |
| Performer signed | The optometrist signs (individually or in a batch) |
| Contractor signed | The NHS contractor signs (individually or in a batch) |

When all are met the claim moves itself **Ready → Submitted** and the submission worker (§12) picks it up. The dashboard shows each claim's checklist so staff can see at a glance what is outstanding. No daily preparation is needed — staff simply act as each patient comes through. Different form types carry different prerequisite sets (GOS4 needs only the supplier signature; GOS3 has a two-stage patient signature — §8.2).

# 8. Core workflows

## 8.1 GOS1 — NHS sight test

1. The patient attends; the appointment is open in the Diary / Calendar module, or the patient record is open.
2. Staff select **New GOS1**. Patient demographics, performer and date pre-fill from context; eligibility pre-fills from the patient's NHS-entitlement record.
3. Staff complete the guided form: eligibility, clinical declarations, performer declaration. Validation runs as they type (§9.1).
4. Signatures are requested (§9); the claim ticks its checklist and **submits itself** when complete (§7).
5. The NHS response returns asynchronously and the status advances to Accepted (or Rejected with a reason).

## 8.2 GOS3 — optical voucher (including takeaway)

1. GOS3 is created **inside the spectacle dispense**. If the linked eye exam already issued a GOS1 and flagged a GOS3 as due, the dispense prompts to create the GOS3.
2. Eligibility carries over from the GOS1 reason where relevant (editable); each reason may require an extra field (HC2 requires the certificate number; HC3 captures the patient contribution).
3. **Live claim-value calculation:** as frame, lenses, tint, prism, small-glasses and special-facial-characteristics supplements are added, the module computes the correct voucher type and the highest legitimate claim value, shown in the dispense summary, with an "explain this value" breakdown (§14).
4. **Two-stage patient signature:** the patient signs (1 of 2) at order and (2 of 2) at collection. The pending GOS3 is not counted as a transaction until collection, so it stays off till sessions until the spectacles are collected.
5. Performer / contractor sign (individually or batched); the claim auto-submits when its checklist completes.
6. **Takeaway / GOS3_VO:** where the patient takes the voucher elsewhere, the claim is flagged as takeaway; the module tracks outstanding takeaway vouchers and provides a retrieval / chase list (§10) and a write-off path for uncollected ones near the deadline.

## 8.3 GOS4 — repair / replacement

- Same create-in-dispense workflow and supplement handling as GOS3, with a repair-element picker that drives the claim value. May also be raised from an external prescription.
- An adult claim requires an **NHS approval code**, captured on the claim.
- Lighter signing: only the supplier / contractor signs, so its readiness checklist is shorter.

## 8.4 GOS6 — domiciliary, via a PVN

1. **Create a PVN** from the patient record (patient + assigned venue pre-filled) or from reporting (blank, contractor details from branch). A PVN states the venue and the date + time, and must be raised at least 24 hours before the visit.
2. **Submit the PVN**; it must reach Accepted before a GOS6 can be claimed against it.
3. On the visit, staff create a **GOS6**; the module auto-finds the accepted PVN and fills the PVN reference and the address where the sight test took place.
4. Signatures are captured on the device at the point of care (§9); the claim completes and submits.
5. A change to the visit date / time means raising a **new PVN** rather than editing a submitted one. A PVN may be cancelled only if previously accepted; otherwise it is deleted.
6. **Venues** are managed records (Day Centre / Home / Nursing / Residential / Sheltered). Many patients can be linked to one venue; assigning a venue can temporarily set the patient's address to the venue's (restored on removal). Linking many patients to one venue powers care-home **batch visits**.

## 8.5 End-of-day check

A "Today's claims" view and dashboard tile let staff confirm that every appointment and voucher that should have produced a claim did, and that nothing is stuck in Data Entry in Progress or Rejected — comparing accepted-claim count against appointments in the diary and vouchers through the till.

## 8.6 Monthly payment reconciliation

The PCSE statement is imported (in the Business Intelligence module), matched to claims, and claims are set Paid with paid amount and date; under / over-payments (especially GOS3 / GOS4) are flagged. The imported statement is retained for the accountant. Where the NHS later exposes a statement API, the manual import is replaced by an automatic nightly sync (§14).

# 9. Signature capture, eligibility and rejection handling

## 9.1 Eligibility intelligence (rejection prevention)

NHS rejections are overwhelmingly eligibility / data errors, so the module prevents them up front:

- Eligibility reasons come from the NHS-valid list; selecting one surfaces its required fields (HC2 certificate number, Pension Credit recipient, etc.).
- Claims pre-fill from the patient record's NHS-entitlement section.
- Eligibility reasons are auto-suggested from patient data (age, recorded benefits) and carried GOS1 → GOS3 / GOS4.
- The last-exam date auto-populates from the record; "not known" is allowed and validated against NHS-held records on submission.
- The GOC number format is validated on the performer's record; retest codes are constrained to valid values.

## 9.2 Signature capture (cloud-native)

Most GOS forms need a patient signature and a performer signature; the contractor also signs. The module pushes a signing session in real time to the branch's paired device(s) — an Android tablet, an iPad, or a dedicated e-signature pad — paired once and authenticated by account / branch (no re-typing the licence number and postcode each session).

- The device presents the signatory the right view for their role (Patient / Performer / Contractor); the patient reads the declaration and signs; the signature returns to the claim instantly.
- **Batch signing:** performer and contractor signatures can be applied to a batch of claims in one action, not one-by-one.
- Proxy signing (partner / parent / guardian) is supported with the relevant details captured.
- The signature is stored immutably with capture metadata (who / when / device / declaration version).
- The same flow works off-site for domiciliary; the device need only have internet, and a poor-signal capture syncs when back online.

## 9.3 Rejection handling

- A rejected claim raises a task in the branch task list (it does not sit silently on a tab).
- The NHS rejection reason is shown inline (status history).
- Staff can edit only what was not already signed for (e.g. last-exam date, retest code) and resubmit in one click; fields the patient signed against are locked to preserve the signed declaration's integrity.

# 10. Worklists, dashboard and reporting

A live **eGOS dashboard** plus saved worklists, all filterable by date range, form type, status and branch, and all exportable / printable:

- **Unfinished claims** — need finishing or submitting.
- **Rejected / failed validation** — with the NHS reason inline and one-click correct-and-resubmit.
- **Today's claims** — the end-of-day completeness check.
- **Till voucher but no eGOS claim** — a voucher rung through the till with no claim started.
- **eGOS claim but no till voucher** — a claim with no matching till entry.
- **GOS3 takeaway outstanding / to retrieve** — vouchers to chase or write off.
- **Claimed ≠ paid** — under / over-paid claims after statement import.
- **Time-limit ageing** — claims approaching the 3-month submission deadline (as of 01/01/2024), with a write-off workflow for uncollected GOS3 takeaways.

Reporting also offers claim lists by status, date and form type for print / export, and reconciliation reports (till ↔ eGOS, claimed ↔ paid). Multi-branch groups get estate-wide views. eGOS revenue forecasting (submitted-but-unpaid pipeline, expected income) is provided in the Business Intelligence module.

# 11. Data model — entities and fields

All entities are tenant-scoped (by practice / branch).

- **EgosClaim** — patient, appointment, performer, contractor, `FormType`, `Status`, `Readiness` (the §7 checklist flags), internal and NHS references, `FormPayload` (versioned JSON for the GOS form), `ClaimedAmount`, `PaidAmount` / `PaidDate`, eligibility, `NhsApprovalCode` (GOS4), `PvnID`, `VenueID`, timestamps, created-by.
- **EgosClaimEvent** — append-only audit of every status transition (who / when / from → to / payload).
- **EgosSignature** — `ClaimID`, `Role` (patient / performer / contractor), `Stage` (GOS3 1-of-2 / 2-of-2), image reference, capture metadata, declaration version.
- **EgosPvn** — venue, internal and NHS references, status, visit date / time, contractor snapshot, patient list, links to resulting GOS6 claims.
- **EgosVenue** — name, address, postcode, premises type, contact.
- **EgosPaymentStatement / EgosPaymentLine** — imported PCSE statement header and lines, matched to claims.
- **EgosBranchConfig** — per-branch licence number, ODS code, credential / PSK secret references, signature method, flags.

GOS form fields are stored as versioned JSON validated against the schema version recorded on the row, so NHS form revisions do not break historical records.

# 12. Integration with other modules and the NHS Gateway

## 12.1 Module integrations

- **Patient module** — reads patient demographics, GP and the NHS-entitlement section; claims and PVNs are started from the patient record.
- **Till / Dispensing module** — receives voucher type / value from the dispense; the EGOS payment type satisfies the "used in till" step; till ↔ eGOS reconciliation reads till vouchers.
- **Diary / Calendar module** — start a GOS1 from an appointment; the end-of-day check reads the day's appointments.
- **Business Intelligence module** — owns the PCSE statement import, reconciliation, under / over-payment detection, ageing and forecasting.
- **Communications module** — delivers the signing-session push and patient chase.

## 12.2 The NHS Gateway (assumed-available dependency)

All NHS specifics sit behind a single internal **NHS Gateway** service, provisioned on eGOS sign-up:

- **Submission interface** — accepts the GOS form messages (GOS 1 / 3 / 4 / 5 / 6) and PVN messages (new / edit / cancel), secured with the practice PSK and identified by licence number / ODS code.
- **Status / response channel** — asynchronous accept / reject / validation responses with reason codes, mapped onto the §6 lifecycle.
- **Signing** — the patient / performer declaration content the device renders.
- **Payment statements** — the PCSE statement the practice imports (and, if and when offered, an API to retrieve it automatically).
- **Eligibility rules** — the validation rule set behind each GOS form, used for pre-submission checks.

Isolating all NHS specifics behind the Gateway means the rest of the module is built and tested against a mock Gateway now and wired to the live endpoints on sign-up without touching workflow code.

## 12.3 Submission worker

A queue-backed worker builds the NHS message, submits it via the Gateway, processes the response and advances claim status. It is idempotent (dedupes on the internal reference so a retry cannot double-claim), retries with backoff on Gateway unavailability, and dead-letters for manual review.

# 13. Security, compliance and audit

- NHS Data Security and Protection Toolkit alignment; eGOS data is UK-resident.
- The PSK and PCSE credentials are held in a secrets manager, encrypted at rest, least-privilege, with rotation support.
- Signatures are legal artefacts: stored immutably with capture metadata (who / when / device / declaration version); never editable after capture.
- An append-only audit trail records every claim / PVN transition and every NHS message, exportable for NHS post-payment verification.
- PII is minimised in logs; retention is configurable.
- Role-based access controls the eGOS capability and the Performer / Contractor roles.

# 14. Competitive analysis and differentiation

Optix is the most eGOS-mature competitor reviewed; its help and release material show a polished voucher-creation experience but stop short of the submission, domiciliary, reporting and money-management layers. The incumbent FLEX / Nova product covers the full GOS set but as a desktop application with cloud workarounds.

## 14.1 Parity targets (matched above)

- Checklist-driven auto-submit (§7).
- Voucher embedded in the dispense with live claim-value calculation (§8.2).
- Tablet e-signature, role-aware, with batch signing (§9.2).
- Performer / Contractor roles, GOC validation, pre-registration supervisor sign-off (§5.2).
- Two-stage GOS3 signature and pending-until-collection till behaviour (§8.2).
- Eligibility from the NHS-valid reason list with auto-assignment and GOS1 → GOS3 carry-over (§9.1).
- Rejection → task, edit non-signed fields, resubmit (§9.3).

## 14.2 Where competitors stop — our openings

1. **No domiciliary / GOS6 / PVN / venues** in Optix at all; no batch visits in FLEX. A large, growing care-home market.
2. **Opaque submission / tracking** in Optix — voucher-creation-centric, with PCSE transmission and live status not surfaced. We make the NHS Gateway and live status first-class.
3. **No dedicated eGOS reporting** in Optix — strong on direct debits and retention, but no eGOS dashboard, eligibility-reason breakdown or claims forecasting.
4. **Manual "move to paid"** in Optix — no automatic statement matching.
5. **No compliance / audit pack** evidenced.
6. **No AI, no voice.**

## 14.3 SmartOptics differentiators

- **Voice-first claim capture** — hands-free dictation that populates GOS fields, built on the SmartOptics streaming speech capability with an optical / GOS phrase list. Most valuable in domiciliary, where staff are gloved and have no desk. No competitor offers this.
- **Domiciliary done properly** — full PVN → GOS6 with venues, care-home batch visits and offline-capable signing.
- **Zero-rejection engineering** — the full rule set validated before submission, so rejections become rare.
- **Live money view** — claimed → accepted → paid, auto-reconciled, with under / over-paid flags, ageing to the deadline and forecast income.
- **Auto-submit and auto-reconcile end-to-end** — minimal manual touch at either end.
- **Compliance-grade audit** — immutable signature provenance and full claim history, exportable for NHS audit.
- **Estate-wide and group submission** — cross-branch aggregation with contractor-per-branch identity handled cleanly.
- **Claim-value explainability** — shows why a figure was reached (which supplements / bands / contributions), so practices can defend it in an audit.

# 15. Feature comparison matrix

Legend: ✅ full · 🟡 partial / manual · ❌ none · 🎙️ unique to SmartOptics. The SmartOptics column is the target state defined by this document.

| Capability | SmartOptics (planned) | Optix | FLEX / Nova |
|---|:---:|:---:|:---:|
| GOS1 — sight test | ✅ | ✅ | ✅ |
| GOS3 — voucher, dispense-integrated, live value calc | ✅ | ✅ | 🟡 |
| GOS3 takeaway tracking & retrieval | ✅ | 🟡 | 🟡 |
| GOS4 — repair / replacement | ✅ | ✅ | ✅ |
| GOS5 — complex / supplementary | ✅ | ❌ | ✅ |
| GOS6 — domiciliary | ✅ | ❌ | ✅ |
| PVN + venues + care-home batch visits | ✅ | ❌ | 🟡 |
| Checklist → auto-submit | ✅ | ✅ | ❌ |
| Performer / Contractor roles, GOC, pre-reg sign-off | ✅ | ✅ | 🟡 |
| Two-stage GOS3 signature (order + collection) | ✅ | ✅ | 🟡 |
| Eligibility intelligence / pre-submission validation | ✅ | 🟡 | ❌ |
| Rejection → task, edit, resubmit | ✅ | ✅ | 🟡 |
| Cloud tablet e-signature, no host app open | ✅ | ✅ | 🟡 |
| Real-time push to device (no manual refresh) | ✅ | 🟡 | ❌ |
| Batch signing (performer / contractor) | ✅ | ✅ | ❌ |
| NHS / PCSE submission + live status lifecycle | ✅ | 🟡 | ✅ |
| PCSE statement import | ✅ | 🟡 | ✅ |
| Automatic payment reconciliation / matching | ✅ | ❌ | ❌ |
| Under / over-paid detection | ✅ | ❌ | ✅ |
| 3-month deadline ageing + write-off | ✅ | ❌ | 🟡 |
| Dedicated eGOS dashboard / worklists | ✅ | 🟡 | 🟡 |
| eGOS revenue forecasting / pipeline | ✅ | ❌ | ❌ |
| Compliance-grade audit trail + export | ✅ | ❌ | 🟡 |
| Estate-wide / multi-branch claim view | ✅ | ✅ | ❌ |
| 100% cloud | ✅ | ✅ | ❌ |
| Voice-first claim capture | 🎙️ | ❌ | ❌ |

# 16. Phased delivery

1. **GOS1 happy path** — configuration, create / complete, signing, submit, status, basic worklist (proves the NHS Gateway end-to-end).
2. **GOS3 + till reconciliation** — voucher auto-population, takeaway tracking, till ↔ eGOS checks.
3. **Payments** — statement import, paid / under / over-paid reconciliation, ageing and time-limit reporting.
4. **Domiciliary** — venues, PVN lifecycle, GOS6, off-site signing.
5. **GOS4 / GOS5 + reporting polish** — remaining forms, full reporting suite, write-off workflow.

Each phase is independently shippable and reuses the Phase-1 submission, signing and worklist plumbing.

# 17. Open questions

- Q1 — Confirm the position of the eGOS module in the Top-Level Spec module development plan and its dependency sequencing against the Patient, Till / Dispensing and Business Intelligence modules.
- Q2 — Confirm the NHS Gateway contract (message set, status vocabulary, statement format) so the mock matches production.
- Q3 — Confirm whether NHS voucher receipts are folded into a Payments module ledger or remain within eGOS reconciliation.
- Q4 — Confirm the paired-device registry and real-time channel for signing, and the MVP fallback if the real-time channel is unavailable.
- Q5 — Confirm the till's EGOS payment-type contract and the dispense → voucher-value feed with the Till / Dispensing module.
- Q6 — Confirm whether estate-wide / group submission and cross-branch dashboards are MVP or a fast-follow.

# 18. Appendix — Referenced documents

- Top-Level Spec (module development plan).
- Patient Module Spec.
- Diary / Calendar Module Spec.
- Till / Dispensing Module Spec.
- Business Intelligence Module Spec.
- Communications Module Spec.
- Practice DB Schema Index.
- Source material: Optinet FLEX / Nova eGOS help articles (England overview, claims reports, checking submissions, signature webpage, signing on Android / Apple, PVN and GOS6, GOS3 takeaway retrieval, optometrist signatures, viewing all claims, management screen, voucher reconciliation); Optix / Optix 2 help documentation (Optix & Audix eGOS, GOS3, GOS4, Business Intelligence, release notes).
