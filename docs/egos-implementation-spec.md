# eGOS Module — Specification & How It Works in the SmartOptics PMS

**Status:** Draft for review
**Audience:** Product, engineering, clinical/operations
**Scope:** What the eGOS (NHS England electronic General Ophthalmic Services) module does and how it works end-to-end inside SmartOptics, a 100% cloud-based PMS.

> **Assumption (per direction):** The NHS / PCSE interfaces — claim submission, PVN messaging, signing, status responses and payment statements — are all **available and provisioned** once the practice has signed up for eGOS. This spec therefore treats the NHS link as a working dependency (an "NHS Gateway" the PMS talks to) and concentrates on the **PMS behaviour, workflows and screens**. The NHS interface contract is summarised in §11 as an assumed-available dependency, not an open question.

---

## 1. What the module is for

eGOS lets a practice run the entire NHS GOS claim process inside SmartOptics — create, sign, submit, track, reconcile and report — with no paper and no separate NHS portal. It supports the standard England GOS forms:

| Form    | What it claims for                                          | Key dependency |
|---------|------------------------------------------------------------|----------------|
| GOS1    | NHS-funded sight test                                      | — (everyday, high volume) |
| GOS3    | Optical voucher towards spectacles (incl. **takeaway**)    | Dispensed order / voucher value |
| GOS3_VO | Voucher-only ("takeaway") variant                          | Patient takes voucher elsewhere |
| GOS4    | Repair / replacement of spectacles                        | — |
| GOS5    | Complex / supplementary                                   | — |
| GOS6    | Domiciliary (home / care-home) sight test                 | An **accepted PVN** |
| PVN     | Pre-Visit Notification (precedes a GOS6)                  | A **venue** + visit date/time |

---

## 2. Where eGOS lives in the PMS

eGOS is not a silo — it threads through modules the practice already uses. The integration points:

```
        ┌──────────────────────────────────────────────────────────┐
        │                     SmartOptics PMS                      │
        │                                                          │
        │  Patient Record ─────┐                                   │
        │   • start a claim    │                                   │
        │   • create a PVN     │     ┌────────────────────┐        │
        │   • capture signature├────►│      eGOS core      │       │
        │                      │     │  • claims engine    │  XML  │   ┌──────────────┐
        │  Appointments/Diary ─┤     │  • PVN engine       │◄─────►│   │ NHS Gateway  │
        │   • claim from appt  │     │  • status worklists │       │   │ (PCSE) —      │
        │   • end-of-day check │     │  • reconciliation   │       │   │ assumed live  │
        │                      │     │  • signing service  │       │   └──────────────┘
        │  Till / Dispensing ──┤     └────────────────────┘        │
        │   • voucher value    │              ▲                    │
        │   • payment type     │              │                    │
        │                      │              │                    │
        │  Business Intelligence / Reporting ─┘                    │
        │   • worklists, payments import, exports                  │
        │                                                          │
        │  Branch Setup → Integrations (eGOS config)               │
        └──────────────────────────────────────────────────────────┘
```

| PMS module | What eGOS adds / uses |
|---|---|
| **Patient Record** | Start a claim or PVN with patient details pre-filled; eligibility capture; signature request; view a patient's claim history. |
| **Appointments / Diary** | Start a GOS1 straight from the appointment; end-of-day "did every appointment get claimed?" check. |
| **Till / Dispensing / Invoicing** | GOS3 voucher value flows from the dispensed order; voucher used as a till payment type; basis for till↔eGOS reconciliation. |
| **Business Intelligence / Reporting** | eGOS worklists and "popular searches", PCSE statement import, payment reconciliation, exports/printouts. |
| **Branch Setup → Integrations** | Per-branch eGOS configuration (licence no, org code, credentials, signature method). |

---

## 3. One-time setup (per branch)

Before claiming, a branch is configured once under **Setup → Branch → Integrations → eGOS (NHS England)**:

- **Practice licence number** (8-digit site number) and **NHS organisation/contractor code**.
- **PCSE credentials + Pre-Shared Key (PSK)** — provisioned on sign-up; stored as secret references, never shown in plain text.
- **Auto-populate voucher values** (on/off) — pulls GOS3 voucher amounts from the dispensed order.
- **Default signature method**: e-signature pad / mobile device / on-screen / external capture.
- **Active** toggle and a one-click **"Test NHS connection"** to confirm the link is live before go-live.
- **Permissions & clinical roles**: an "eGOS" capability is granted to relevant staff roles, and two NHS-specific roles are modelled (matching how PCSE attributes a claim):
  - **Performer** — the optometrist who does the sight test. Requires a **GOC number** (7–8 chars incl. hyphen) on their staff record.
  - **Contractor** — the NHS-contracted owner who signs vouchers for the branch(es) assigned to them.
  - **Pre-registration students** — a flag that routes their completed exams to an assigned **supervising performer** to check and sign.
  One person can hold both Performer and Contractor roles (then both signatures can be applied together).

Multi-branch groups configure each branch separately, because the NHS contractor identity (licence no / org code / PSK) is per branch — every submission carries the correct identity.

---

## 4. Claim lifecycle (as staff see it)

Every claim moves through a status the PMS shows everywhere it's listed:

```
 DATA ENTRY IN PROGRESS ─► READY TO CLAIM ─► SUBMITTED ─► AWAITING REVIEW ─┬─► ACCEPTED ─► PAID
        (draft)                                                            │
                                                                           └─► REJECTED / FAILED VALIDATION / ERROR
                                                                                   │
                                                                                   └─(correct)─► READY TO CLAIM
   any time, if appropriate:  CANCELLED  /  CLOSED
```

- **Unfinished** = anything not yet `ACCEPTED` or `PAID`. These are what staff chase — they populate the worklists.
- **Finished** = `ACCEPTED` (NHS has accepted it) or `PAID` (money reconciled against a statement).
- **Rejected / Failed Validation / Error** are recoverable: the NHS reason is shown inline; staff correct and resubmit.
- Every status change is written to an immutable audit trail (who, when, from→to) for NHS post-payment verification.

---

## 5. Core workflows (how it actually works day to day)

### 5.0 Submission-readiness model (checklist → auto-submit)
Rather than making staff remember to "press submit", a claim carries a **readiness checklist** and **submits itself automatically** the moment every prerequisite is met (this matches the best-in-class competitor pattern — see §13 — and removes a whole class of "forgot to submit" errors). For a GOS1 the prerequisites are:

| Prerequisite        | Satisfied when… |
|---------------------|-----------------|
| Patient signed      | Patient signs on the device |
| Used in till        | The NHS sight-test item is rung through the till against the eGOS payment type |
| Performer recorded  | The eye exam is saved to the patient record (performer + retest code attach automatically) |
| Performer signed    | The optometrist signs (individually or as part of a batch) |
| Contractor signed   | The NHS contractor signs (individually or as part of a batch) |

When all are ticked, the claim moves itself **Ready → Submitted** and is picked up by the submission worker. The eGOS dashboard shows each claim's checklist so staff can see at a glance what's still outstanding. **No daily prep** is needed — staff simply act as each patient comes through. Different form types have different prerequisite sets (e.g. GOS4 needs only the supplier signature; GOS3 has a two-stage patient signature — see below).

### 5.1 GOS1 — NHS sight test (the everyday path)
1. Patient attends; the appointment is open in the diary, or the patient record is open.
2. Staff click **New eGOS claim → GOS1**. Patient demographics, performer and date pre-fill from context.
3. Staff complete the guided GOS1 form: eligibility (e.g. age, benefit/HC2/HC3), clinical declarations, performer declaration. Validation runs as they type.
4. **Request signatures** — patient signs the eligibility declaration, performer signs theirs (see §6). Signatures attach to the claim.
5. The claim becomes **Ready to Claim**; staff **Submit**. It goes to **Submitted → Awaiting Review** and the PMS hands it to the NHS Gateway.
6. The NHS response comes back asynchronously and the status advances to **Accepted** (or Rejected with a reason).

### 5.2 GOS3 — optical voucher (incl. takeaway)
1. GOS3 is created **inside the spectacle dispense**. If the linked eye exam already issued a GOS1 and flagged that a GOS3 is due, the dispense **prompts** "create the GOS3 now?".
2. **Eligibility carries over** from the GOS1 reason where relevant (editable); each reason may require an extra field (e.g. HC2 requires the HC certificate number; HC3 captures the patient contribution).
3. **Real-time claim-value calculation:** as the user adds frame, lenses, tint, prism, small-glasses and special-facial-characteristics supplements, the module **computes the correct voucher type and the highest legitimate claim value live**, shown in the dispense summary. (This is table-stakes parity with the leading competitor; we add an "explain this value" breakdown — see §13.)
4. **Two-stage patient signature:** the patient signs **(1 of 2) at order** and **(2 of 2) at collection** to acknowledge receipt of the spectacles. The pending GOS3 is **not counted as a transaction** until collection, so it stays off till sessions/transactional reports until the specs are actually collected.
5. Performer/contractor sign (individually or batched); the claim auto-submits when its checklist completes.
6. **Takeaway / GOS3_VO:** where the patient takes the voucher to spend elsewhere, the claim is flagged as takeaway; the module tracks outstanding takeaway vouchers and provides a **retrieval/chase list** (see §7) and a write-off path for uncollected ones near the deadline.

### 5.2b GOS4 — repair / replacement
- Same create-in-dispense workflow and supplement handling as GOS3, with a **repair-element picker** that drives the claim value. Can also be raised from an **external prescription**.
- For an **adult** claim, an **NHS approval code** is required (obtained from the local NHS/PCSE validation route) and captured on the claim.
- Lighter signing: **only the supplier/contractor signs** (no performer signature needed), so its readiness checklist is shorter.

### 5.3 GOS6 — domiciliary, via a PVN
1. **Create a PVN** from the patient record (patient + assigned venue pre-filled) or from Reporting (blank, contractor details from branch). A PVN states the **venue** and the **date + time** of the visit and must be raised **≥24h before** the visit.
2. **Submit the PVN**; it must reach **Accepted** before a GOS6 can be claimed.
3. On the visit, staff create a **GOS6**; the module **auto-finds the accepted PVN** and fills the PVN reference and "address where the sight test took place".
4. Capture signatures on the device at the point of care (§6), complete and submit.
5. **If the visit date/time changes → raise a NEW PVN** and attach that to the GOS6 (the module steers staff down this path rather than editing a submitted PVN). A PVN can only be cancelled if previously accepted; otherwise it is deleted.
6. **Venues** are managed records (Day Centre / Home / Nursing / Residential / Sheltered). Many patients can be assigned to one venue; assigning a venue can temporarily set the patient's address to the venue's (restored on removal).

### 5.4 End-of-day check
- A **Today's Claims** view (and dashboard tile) lets staff confirm every appointment/voucher that should have produced a claim actually did, and that nothing is stuck in **Data Entry in Progress** or **Rejected**. Compare accepted-claim count against appointments in the diary and vouchers through the till.

### 5.5 Monthly payment reconciliation
- Import the **PCSE statement** (the practice downloads it; the module ingests it). The module matches statement lines to claims, sets them **Paid** with `paid_amount`/`paid_date`, and flags **under/overpayments** (especially GOS3/4 where paid value can differ from claimed).
- The imported statement is retained (e.g. for the accountant).
- *(Improvement, if the NHS exposes a statement API: replace the manual import with automatic nightly sync — see §10.)*

---

## 6. Signature capture in the PMS (cloud-native)

Most GOS forms need a **patient** signature (declaration) and a **performer** signature. SmartOptics replaces the legacy "open a signature webpage and press Refresh List" polling model with a real-time cloud flow:

1. From the open claim, staff click **Request signature**.
2. The PMS **pushes a signing session in real time** to the branch's paired device(s) — an Android tablet, an iPad (Safari), or a dedicated e-signature pad. No manual list-refresh, no re-typing licence-no + postcode each time; devices are **paired once** and authenticated by account/branch.
3. The device shows the patient the relevant declarations/eligibility reasons; the patient reads, accepts and signs. The performer signs likewise.
4. The signature returns to the claim **instantly** and is stored immutably with capture metadata (who/when/device/declaration version).
5. The branch default method is configurable; any claim can override it. The same flow works **off-site** for domiciliary — the device just needs internet (offline handling in §9).

**Role-aware signing & batching.** The signing device presents the signatory the right view for their role — **Patient**, **Performer**, **Contractor**. Performer and contractor signatures can be applied to a **batch** of claims in one action (select claims → sign the batch), not one-by-one, which is how a busy practice clears a day's claims in seconds. Proxy signing (partner/parent/guardian) is supported with the relevant details captured. Pre-registration students' exams route to their supervising performer to sign.

### 6.1 Eligibility intelligence (rejection prevention)
NHS rejections are overwhelmingly eligibility/data errors, so the module prevents them up front:
- Eligibility reasons come from the **NHS-valid list**; selecting one surfaces its required fields (HC2 cert number, Pension Credit recipient, etc.).
- The patient record holds a dedicated **NHS entitlement** section (why this patient — and, where relevant, another person — is entitled); claims pre-fill from it.
- Eligibility reasons are **auto-suggested** from patient data (age, recorded benefits) and **carried GOS1 → GOS3/4**.
- **Last-exam date** auto-populates from the record; "not known" is allowed and validated against NHS-held records on submission.
- **GOC number** format is validated on the performer's record; **retest codes** are constrained to valid values.

### 6.2 Rejection handling
- A rejected claim raises a **task** in the branch task list (it doesn't just sit silently on a tab).
- The NHS rejection reason is shown inline (status history).
- Staff can **edit only what wasn't already signed for** (e.g. last-exam date, retest code) and **resubmit** in one click; fields the patient signed against are locked to preserve the signed declaration's integrity.

---

## 7. Worklists, management screen & reporting

The cloud successor to the FLEX "eGOS widget" + "popular searches" is a live **eGOS dashboard** plus saved worklists, all filterable by date range, form type, status and branch, and all exportable/printable:

- **Unfinished claims** — need finishing or submitting (not yet Accepted/Paid).
- **Rejected / failed validation** — with the NHS reason inline and one-click correct-and-resubmit.
- **Today's claims** — end-of-day completeness check.
- **Till voucher but no eGOS claim** — voucher put through the till with no claim started (missing claim).
- **eGOS claim but no till voucher** — claim exists with no matching till entry (missing till payment).
- **GOS3 takeaway outstanding / to retrieve** — vouchers to chase or write off.
- **Claimed ≠ paid** — under/overpaid claims (GOS3/4) after statement import.
- **Time-limit ageing** — claims approaching the **3-month** submission deadline (as of 01/01/2024), with a write-off workflow for uncollected GOS3 takeaways.

Reporting also offers claim lists by specific status(es), date and form type for print/export, and reconciliation reports (till↔eGOS, claimed↔paid). Multi-branch groups get estate-wide views.

---

## 8. Data model (summary)

All tenant-scoped (by `practice`/`branch`):

- **`egos_claim`** — patient, appointment, performer, contractor, `form_type`, `status`, `readiness` (the §5.0 checklist flags), internal + NHS refs, `form_payload` (versioned JSON for the GOS form), `claimed_amount`, `paid_amount/date`, eligibility, `nhs_approval_code?` (GOS4), timestamps, `pvn_id?`, `venue_id?`.
- **`egos_claim_event`** — append-only audit of every transition.
- **`egos_signature`** — `claim_id`, `role` (patient/performer/contractor), `stage?` (GOS3 1-of-2 / 2-of-2), image ref, capture metadata, declaration version.
- **`egos_pvn`** — venue, internal + NHS refs, status, visit date/time, contractor snapshot, patient list, links to resulting GOS6 claims.
- **`egos_venue`** — name, address, postcode, premises type, contact.
- **`egos_payment_statement` / `egos_payment_line`** — imported PCSE statement, matched to claims.
- **`egos_practice_config`** — per-branch licence no, org code, credential/PSK secret refs, signature method, flags.

GOS form fields are stored as **versioned JSON** validated against the schema version recorded on the row, so NHS form revisions don't break historical records.

---

## 9. Operational behaviour & edge cases

- **Async submission:** submitting a claim/PVN never blocks the user. A background worker builds the NHS message, submits it, processes the NHS response and advances status; the PMS surfaces status changes live.
- **Idempotent submit:** dedupe on the internal ref so a retry can never double-claim.
- **NHS link briefly unavailable:** queue and retry with backoff; nothing is lost, and the claim simply shows as pending until acknowledged.
- **Off-site / poor signal (domiciliary):** the signing client captures locally and syncs the claim when back online; the claim is shown as "captured, pending submission".
- **Date/time change on a PVN:** the module forces the "new PVN" path rather than editing a submitted one.
- **Form-version drift:** claims validate against the schema version stored on the claim, not "latest".
- **3-month deadline:** proactively surfaced; uncollected GOS3 takeaways can be written off via a managed workflow.

---

## 10. Why this is better than the legacy (FLEX/Nova) experience

| Legacy constraint | SmartOptics (cloud) |
|---|---|
| Signatures need the desktop app open; domiciliary needs dial-in | Signing session is pushed to any paired device; no host app required |
| Signature webpage: re-enter licence-no + postcode, press "Refresh List" | Paired authenticated devices, real-time push, no polling |
| Per-practice signature URL to bookmark | One app, tenant-scoped sessions |
| Status only as fresh as the last manual "refresh claims" | Worker keeps status live |
| Monthly CSV import is the only payment path | CSV import now, automatic statement sync when the NHS API allows |
| Reconciliation = monthly "popular search" sweeps | Continuous, real-time till↔eGOS matching with instant flags |
| Reports run on a single local DB | Estate-wide multi-branch reporting |
| **No voice** | **Voice-driven form entry** using SmartOptics' existing Azure Speech stack (the optical/GOS phrase list already covers `GOS`, `GOS one/three/six`, `voucher`, `domiciliary`, `HC2`, `HC3`) — dictate findings, fields populate |
| Validation failures found after an NHS round-trip | Pre-submission validation against the NHS ruleset → rejections become rare |

---

## 11. Assumed-available NHS dependency (the "NHS Gateway")

Per the working assumption, the following are provided once the practice is signed up for eGOS, and the PMS consumes them through a single internal **NHS Gateway** service:

- **Submission interface** — accepts the GOS form messages (GOS1/3/4/5/6) and PVN messages (new / edit / cancel), secured with the practice's PSK and identified by licence no / org code.
- **Status/response channel** — asynchronous accept/reject/validation responses with reason codes, mapped onto the §4 lifecycle.
- **Signing** — the patient/performer declaration content and signing flow the device renders.
- **Payment statements** — the PCSE statement the practice imports (and, if/when offered, an API to retrieve it automatically).
- **Eligibility rules** — the validation ruleset behind each GOS form, used for pre-submission checks.

Engineering note: isolating all NHS specifics behind the Gateway service means the rest of the PMS (patient record, claims engine, worklists, reconciliation) is built and testable against a mock Gateway now, and wired to the live NHS endpoints on sign-up without touching the workflow code.

---

## 12. Phased delivery

1. **GOS1 happy path** — config, create/complete, signing, submit, status, basic worklist (proves the Gateway end-to-end).
2. **GOS3 + till reconciliation** — voucher auto-population, takeaway tracking, till↔eGOS checks.
3. **Payments** — statement import, paid/under/overpaid reconciliation, ageing/time-limit reporting.
4. **Domiciliary** — venues, PVN lifecycle, GOS6, off-site signing.
5. **GOS4/5 + reporting polish** — remaining forms, full reporting suite, write-off workflow.

Each phase is independently shippable and reuses the Phase-1 submission, signing and worklist plumbing.

---

## 13. Competitive analysis (Optix) & how SmartOptics differentiates

Optix is the most eGOS-mature competitor reviewed. Its help/release docs show a polished **voucher-creation** experience but stop short of the submission, domiciliary, reporting and money-management layers. This section records what to **match** and where to **win**.

### 13.1 What Optix does well — parity targets (now reflected above)
- **Checklist-driven auto-submit** — a voucher submits itself once its tasks are complete ("5 tasks": patient signed, used in till, performer recorded, performer signed, contractor signed). *Adopted in §5.0.*
- **Voucher embedded in the dispense with real-time claim-value calculation** — picks the correct voucher type and the highest legitimate value as products are added. *§5.2.*
- **Tablet PWA signing app, role-aware (patient / performer / contractor) with batch signing.** *§6.*
- **Performer & Contractor roles, GOC-number validation, pre-registration supervisor sign-off.** *§3, §6.*
- **Two-stage GOS3 signature** (order 1-of-2, collection 2-of-2) and **pending-until-collection** till behaviour. *§5.2.*
- **Eligibility from the NHS-valid reason list**, auto-assignment, GOS1→GOS3 carry-over, HC2 cert / HC3 contribution handling. *§6.1.*
- **Rejection → branch task, edit only non-signed fields, resubmit.** *§6.2.*
- **Dedicated EGOS till payment type**, auto-matched and locked at cash-up. *§5.*

### 13.2 Where Optix stops — our openings
1. **No domiciliary / GOS6 / PVN / venues** — absent from 18 months of Optix release notes and all help docs. A large, growing care-home market left uncovered.
2. **Submission/tracking infrastructure is opaque** — Optix docs are voucher-*creation*-centric; PCSE transmission and live claim status aren't surfaced. We make the **NHS Gateway + live status lifecycle** first-class.
3. **No dedicated eGOS reporting** — Optix BI is strong on Direct Debits, retention and stock, but has **no eGOS dashboard, no eligibility-reason breakdown, no claims forecasting**.
4. **No eGOS revenue forecasting** — Optix forecasts Direct-Debit income but not the eGOS pipeline.
5. **Manual "move to Paid"** — reconciliation against the bank/statement is a manual step; **no auto-matching**.
6. **No compliance/audit pack** — no evidence of immutable signature provenance or claim audit export for NHS post-payment verification.
7. **No AI / no voice.**

### 13.3 SmartOptics differentiators (beyond parity)
**A. Voice-first claim capture — our standout.** Hands-free chairside dictation that populates GOS fields, built on the streaming Azure Speech stack this repo already runs (the phrase list already biases `GOS`, `GOS one/three/six`, `voucher`, `domiciliary`, `HC2`, `HC3`). Highest-value precisely where competitors are weakest — **domiciliary** (gloved, no desk, in a care home).

**B. Domiciliary done properly.** Full PVN → GOS6 with venues, many-patients-per-venue care-home **batch visits**, and offline-capable signing. The segment Optix ignores entirely.

**C. Zero-rejection engineering.** The full PCSE ruleset validated **before** submission, plus eligibility intelligence (§6.1), so rejections become rare rather than corrected after a round-trip.

**D. Live money view.** A single eGOS dashboard showing claimed → accepted → paid, **auto-reconciled** against statements, with under/overpaid flags, **ageing to the 3-month deadline**, and **forecast income** — turning claims from an admin chore into managed cashflow.

**E. Auto-submit *and* auto-reconcile, end-to-end.** Checklist auto-submit on the front (§5.0) and automatic statement matching on the back (§5.5) — minimal manual touch at either end, versus Optix's manual "move to Paid".

**F. Compliance-grade audit.** Immutable signature provenance + complete claim history, queryable and exportable for NHS audit — a genuine differentiator for multi-site groups and post-payment verification.

**G. Estate-wide & group submission.** Cross-branch aggregation and dashboards with contractor-per-branch identity handled cleanly, for multiples and domiciliary providers operating at scale.

**H. Claim-value explainability.** Beyond "highest value", show **why** (which supplements/bands/contributions produced the figure) so practices trust it and can defend it in an audit. *(Referenced from §5.2.)*

### 13.4 Net positioning
Match Optix on the slick **front-of-house voucher + signing** experience (so we're never behind on the daily workflow), then win on the parts Optix doesn't do: **domiciliary, end-to-end NHS submission + reconciliation, eGOS-specific reporting/forecasting, compliance audit, and voice** — the last being something no competitor in this market currently offers.
