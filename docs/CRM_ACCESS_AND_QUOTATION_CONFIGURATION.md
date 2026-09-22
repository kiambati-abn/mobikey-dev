# CRM access and quotation configuration

This change adds configurable CRM access scopes, administrator/manager-maintained Deal Types, and consistent rendered quotation terms. It removes Walk-in / Branch from the CRM form while retaining historical field values. It does not deploy to or audit a production database.

## Access policy

Open **CRM → Configuration → CRM Access Policies** as an administrator. Model permissions still determine whether a user can use CRM or delete records. An access policy limits which records those permissions cover; it does not grant access to unrelated applications.

| Default role | Read, edit, create and reassign scope | Deletion |
|---|---|---|
| Salesperson | Assigned records, including explicit assignments across teams | Existing Odoo model permission; ordinary salespeople cannot delete leads |
| Sales team leader | Assigned records plus every lead/opportunity in teams they lead, including unassigned records | Existing Odoo model permission |
| CRM manager | All records within the companies currently enabled for that user | Existing Odoo model permission |
| Administrator | All records within enabled companies; fixed recovery access | Existing Odoo model permission |
| Other internal / portal users | No CRM grant by default | No CRM grant |

The default sales policy uses **Assigned records and teams led**. An ordinary salesperson who leads no teams consequently sees only assigned records. Leadership comes from the native Sales Team's Team Leader field. Being a named quotation approver or holding a legacy approval group is not the same as being a CRM manager or a team leader.

Each policy is attached to an Odoo group and has independent read, edit, create, delete and reassignment scopes. Supported scopes are **No grant**, **Assigned records**, **Assigned records and teams led**, **Assigned records and teams joined**, and **All permitted companies**. Modification scopes must be contained in that policy's read scope.

Policies are additive: all active policies for a user's effective groups apply, including inherited groups. **No grant** contributes nothing; it does not revoke another policy's grant. For a read-only team leader, keep read scope at teams led and change write scope to assigned records; independently choose creation and reassignment scopes. Review all of the user's effective policies when reducing access. Archive a policy to stop its grants; keep its chatter history. Administrators alone can edit policies. Changes are tracked in chatter and invalidate Odoo's access-rule cache.

Company rules always apply separately. The fixed administrator recovery rule does not bypass company restrictions. Odoo's superuser and explicit internal `sudo()` operations retain their native framework behavior.

Global CRM policy rules prevent native All Documents and other broad group rules from widening the configured scope. Compatible group grants allow team leaders to exercise their policy despite Odoo's native own-record restriction. Policy enforcement covers searches, reads, edits, creation and deletion through the ORM, including RPC/import/export paths. Reassignment is checked against the original record as well as normal write permissions. A salesperson allowed to reassign their own lead loses access after assigning it to someone else unless a different policy still grants access.

CRM product lines require a CRM sales role (or administrator) and an accessible parent. Ordinary users cannot create orphan lines or move a line to a lead they cannot edit. CRM activity analysis follows the current lead. Historical forecasts retain their original salesperson/team/amounts, but visibility follows the current linked lead. Deleted-lead snapshots are visible only to users with an all-record read scope within their permitted companies. Forecast records remain immutable.

Common changes within these scopes require configuration and refreshing the client form. A new business dimension, such as territory-specific grants or different policies per lead stage, requires a deliberate code extension and regression tests. Arbitrary Python/domain expressions are not exposed in the policy editor.

## Existing access groups and remaining live checks

| Repository group / configuration | Treatment |
|---|---|
| Sales Manager, Country GM, HQ, Finance | Retained as technical Legacy Access groups to preserve existing access and submitted decisions. They no longer route new approvals or provide Commercial/Finance Approval selectors on the normal user form. |
| Quotation approver | Retained: supplies minimum review access for named approvers. |
| Financial cost and margin visibility | Retained: protects financial fields separately from CRM visibility. |
| Legacy Country Director | Existing `19.0.2.3.0` migration retires it while preserving Sales Manager access; no automatic GM promotion. |
| Legacy margin-warning ACL | Installation hook and the new `19.0.1.5.0` upgrade migration disable this known obsolete grant when present. |
| Broad CRM product-line ACL | Changed from all internal users to CRM sales users, with parent-record and company restrictions. |
| Native All Documents role | Retained for other sales behavior; cannot bypass the CRM policy. |

The source audit does not prove which custom groups, Studio rules or user memberships exist in a live database. Before production rollout, inventory active CRM rules and ACLs, effective user groups, sales-team leaders/members and enabled companies. Remove only confirmed obsolete custom grants. Do not delete active approval roles by their names alone.

Named approver assignment currently adds the quotation-approver group. Removing the assignment does not automatically remove that group. Review memberships against assignments in all companies and pending approvals before removal; an existing submitted approval deliberately retains its original assignees. This change does not infer authority revocation or automatically remove those memberships.

Unrelated CRM lookup tables currently allow internal users to create/edit values. Those existing permissions are unchanged; Deal Types use the narrower permissions requested here.

## Approvers without CRM or Sales access

From `mobikey_sale_approvals` version **19.0.1.6.0**, the **Quotation approver** group implies only **Internal User**, not the standard Sales user group. Named company approvers receive this group automatically. They can use **Quotation Approvals → My approvals**, read assigned approval records and their quotations/lines, and approve or request changes. Opening a quotation as an approval-only user selects dedicated read-only quotation and line review forms with commercial lines, payment/financing details and terms, avoiding dependencies on accounting or warehouse permissions. The existing Sales menu shortcut and full quotation form remain available to users who also have Sales access.

Approval-only users cannot create, edit, delete, revise, confirm or send quotations through the sales workflow. Being an approver does not grant CRM lead/opportunity or forecast access, even if a lead is assigned to that person or they lead its team. Separate Sales/CRM groups and CRM policies grant that access when required. Users who also sell retain their ordinary Sales permissions; being assigned an approval adds read access to that quotation, not edit access.

Decision actions authorize the active internal assignee, allowed company, current revision, activation and prior steps, then lock the quotation and recheck before recording the decision. This path requires quotation read access rather than commercial write access. Decisions retain the actual acting user and timestamp. Public quotation shortcuts use the caller's permissions, including company restrictions.

Configure **Company → Sales approvals → Assigned Finance approvers** (and the other named lists) as the approval matrix. Named reviewers need no legacy Finance/GM/HQ role. **Financial cost and margin visibility** remains separate; named assignment does not grant it. Existing Finance/GM/HQ memberships retain their financial visibility for compatibility, but no longer supply fallback approvers. Remove those technical memberships only after reviewing pending decisions and independent financial-access requirements. Pending decisions retain their submitted assignees when the matrix changes.

Upgrade the approvals module to apply the group implication removal, read-only ACLs/rules and new menu. Odoo 19 keeps explicit group memberships separate from inherited membership: this change removes Sales access inherited only through the approver group, while preserving Sales permissions explicitly assigned to users or inherited through other roles. Review those remaining memberships for finance-only staff; the upgrade deliberately does not guess which explicit assignments are accidental. Existing custom ACLs and record rules can also grant additional permissions and require a live audit.

Removing a person from the company matrix does not remove their approver group or revoke historical/pending assignments. To revoke decision access immediately, remove all group memberships that confer **Quotation approver**, or deactivate the user. Company access restrictions still apply. Do not delete approval history.

## Named-only approval routing

From `mobikey_sale_approvals` **19.0.1.7.0**, every new approval recipient comes exclusively from **Company → Sales approvals → Assigned approvers** (or **Trade-in approvers**). Populate the relevant Sales Manager, Country GM, HQ and Finance lists for each company. Only active internal users with company access and the Quotation approver permission are eligible; saving named assignments supplies that permission. Existing legacy role memberships are never copied automatically into the matrix.

An empty or unavailable required list blocks quotation submission with a message identifying the company and affected approvals. New commission approvals use the union of the company's named GM and HQ lists; when neither has an eligible reviewer, the existing daily commission retry waits for configuration. Trade-in requests continue to use their named pool. No path falls back to user-role membership.

**Commercial Approval** and **Finance Approval** no longer appear as selectors in the normal user permissions form. Their former groups retain their XML identifiers, memberships and implied access under **Legacy Access** names, without user-form privileges. They remain inspectable as technical groups. This preserves existing financial access and the permission needed to act on submitted approvals; hiding the selectors does not revoke those permissions. Financial visibility is still managed independently through **Financial cost and margin visibility** and is not granted by named assignment.

Submitted approvals retain their original assignees, snapshot, sequence and history even when a named list is changed or cleared. Retiring routing does not cancel outstanding decisions. Upgrade **mobikey_crm** (19.0.2.5.1) and **mobikey_sale_approvals** (19.0.1.7.0), refresh the user form, and configure required named lists before submitting new quotations. Both modules' group definitions remove the old selectors, so later independent upgrades do not restore them.

## Deal Types

Open **CRM → Configuration → Deal Types**. CRM managers and administrators can add, rename and reorder options; other internal users can only read/select them.

On the opportunity, **Customer need → Deal Type** now uses a searchable lookup with native **Search More**. Managers and administrators can use **Create and Edit** to supply the label and permanent code, or open an existing option to edit its label. Ordinary sales users can change their opportunity's selection but cannot change the catalogue. Quick creation is disabled because every new option needs a permanent code.

The `deal_type` field remains a string-valued Selection on both `crm.lead` and `sale.order`. The opportunity's `deal_type_id` is an editable lookup onto that existing code, with no stored-value conversion. Both models get choices from `mobikey.deal.type`. The existing integration codes remain `cash`, `financing`, `lease`, and `fleet`. Codes are unique, lowercase identifiers and cannot change after creation. Labels can change without changing stored codes or approval fingerprints. Built-in choices cannot be deleted; custom choices cannot be deleted while referenced by leads, quotations or retained approval previews.

The `financing` code retains its existing financing behavior even if its label changes. New choices classify deals; they do not silently add a new approval policy. Existing Financing Required and financing payment-term controls continue to work. Approval previews resolve configurable labels while leaving their stored commercial snapshots unchanged.

## Invoice creation permissions

From `mobikey_sale_approvals` **19.0.1.8.0**, **Create Invoice** is available only when the current user has creation access on `account.move` (Journal Entry). Standard Invoicing/Billing permissions supply this; a Quotation approver or Sales role alone does not. The form's regular/down-payment buttons, the sales-order list's batch invoicing button, and the Action menu's **Create invoice(s)** shortcut follow the same access check. Users also need the appropriate access to the source sales orders. Native privileged invoice generation remains in place after the new caller permission check.

The server also checks this permission before the Sales invoice and down-payment wizard routes run, preventing direct calls from bypassing the hidden buttons. The check uses effective model access rather than a fixed list of user roles, so future legitimate ACL grants are respected. Existing quotation approval thresholds and checkpoints are unchanged: this update does not introduce mandatory manual approval for quotations that trigger no approval rules.

Upgrade `mobikey_crm` to **19.0.2.6.0** and `mobikey_sale_approvals` to **19.0.1.8.0**, then reload the application to apply these changes.

## Quotation styling reference

| Element | Typeface / weight | Size | Color and spacing |
|---|---|---|---|
| Terms body | Arial, regular; Helvetica then sans-serif fallback | 10 pt | Template body color, default `#222222`; line-height 1.3 |
| Terms section bar | Arial, bold, uppercase | 10.75 pt | White text on default `#323C48`; line-height 1.2 |
| Blue and Green section bar | Same | 10.75 pt | White text on `#305496` |
| Clause headings (`h1`–`h6`) | Arial, bold | 10 pt | Active primary color; line-height 1.3; 2 mm vertical margins |

Section-bar padding is 1.4 mm vertical / 1.8 mm horizontal; margins are 5 mm above and 2.5 mm below. Custom palettes keep their configured colors and contrasting section-bar text. Font availability on the PDF server determines which declared fallback is embedded.

Native quotation `note` remains the source of legal text. The Mobikey report normalizes fonts, sizes, colors and line spacing on a rendering copy, preserving paragraphs, lists, links, tables, bold and italics. It never saves the normalized copy back to the quotation. Native reports for quotations without a Mobikey document template remain unchanged.

## Upgrade and verification

Back up the target database and filestore. Rehearse on a staging copy, then upgrade `mobikey_crm`, `mobikey_sale_approvals`, and `mobikey_sale_documents` together. Restart Odoo workers with the new code. New policy and Deal Type defaults use `noupdate`, so later upgrades preserve administrator edits instead of resetting the matrix or labels. Existing Deal Type strings, walk-in values, legal text and approval snapshots require no conversion.

Use the pinned local runtime:

```bash
~/odoo-lab/bin/odoo-lab --project /home/ocean/Mobikey-Production test
```

Coverage includes own/team/all scopes, additional broad legacy grants, direct reads and exports, company switching, policy changes, team leadership/membership changes, reassignment, product lines, activity analysis, forecasts, dashboard totals, option configuration permissions, financing and approval fingerprints, and both quotation report routes.

For production acceptance, repeat the role matrix using actual representative user accounts and their inherited permissions, then inspect real short and multipage quotations. Source and isolated test results cannot certify database-only customizations.

## Validation results — 21 September 2026

- Full four-module regression run: **95 tests, zero failures or errors**.
- Follow-up CRM and legacy-cutover checks on the final code: **20 tests, zero failures or errors**.
- Final document checks after the pagination refinement: **26 tests, zero failures or errors**. Short clause introductions remain with their headings; long paragraphs and tables can still flow across pages.
- Upgraded an isolated database from repository commit `b7418d6`, with an existing approved quotation, linked lead, fleet classification, walk-in history and native terms. Values, approval status, financial snapshot and commercial fingerprint were preserved.
- Repeated the upgrade after changing the sales policy and Fleet label. Both administrator changes survived, and no duplicate default options were created.
- Seeded the known obsolete margin-warning ACL in the isolated database, ran the new migration, and verified that it became inactive.
- Rendered four actual A4 PDFs with wkhtmltopdf: a one-page Mobikey quotation, a four-page Mobikey proforma, a one-page Blue and Green proforma, and a four-page Blue and Green quotation. All ten rendered pages were visually inspected after the final change, with no clipped text, overlapping footers or isolated clause headings in these samples. Both long documents include Clause 30. Source terms deliberately contained conflicting Georgia/Courier fonts and colors, headings, bold, italics, a link, numbered clauses and a table.
- PDF font inspection found DejaVu Sans and DejaVu Sans Bold, the installed server's fallback for Arial/Helvetica. This matches the rest of the sample report. Arial is the declared CSS choice, not an assurance that Arial is installed on a deployment server.

Logs from this session are retained under `/tmp/mobikey-policy-upgrade/` (`08_final_tests.log`, `10_legacy_migration.log`, `14_document_tests.log`, and upgrade fixture logs). These are local validation artifacts, not a production audit.

## Approval separation validation — 22 September 2026

- Final four-module regression on the upgraded isolated database: **102 tests, zero failures or errors**. Python/XML parsing and `git diff --check` also passed.
- Verified approval-only users can read assigned quotations/lines, approve and request changes, but cannot edit/revise/confirm/send/cancel quotations, access unrelated records, or read CRM leads even when assigned to them or their led team. Company switching and revoked approver membership remain enforced.
- Cleared ORM caches before testing quotation and line form reads; both forms open without Journal Entry or Stock Move access. A separate fresh-process verification also passed, avoiding cached privileged computations masking missing permissions.
- Rehearsed an upgrade from commit `a250fd6` with named finance reviewers, an explicit Sales+Finance user, pending and completed decisions, commercial fingerprints and financial snapshots. Sales access inherited only through the approver group disappeared; explicitly assigned Sales access remained. The original pending decision was approved by its finance reviewer after upgrade without CRM/Sales access.
- Repeated upgrades preserved the original completed decision's approver/timestamp and the submitted snapshots/fingerprint. No production database or live user memberships were changed.
- Final logs are local temporary artifacts under `/tmp/mobikey-approver-upgrade/`: `08_final_regression.log` and `09_final_verify.log`. These results covered the initial `19.0.1.6.0` separation. The named-only routing update below supersedes that release; review existing explicit Sales and legacy approval-role memberships for finance-only users as described above.

## Routing retirement validation — 22 September 2026

- Final regression across CRM, approvals, documents and dashboard: **107 tests, zero failures or errors**. Python/XML parsing and `git diff --check` passed.
- Verified every empty named authority pool returns no approvers despite eligible legacy-role users; new discount and financing requests stop before creating any approval records. A named assignment in another company does not fill the current company's empty list.
- Verified named internal users need no legacy role, revoked approval permission makes them ineligible for new routing, and commission requests wait for named GM/HQ configuration without using legacy roles.
- Verified the native user-form permission hierarchy excludes both former Commercial Approval and Finance Approval selectors, while existing technical group memberships still supply the permissions needed for submitted decisions.
- Upgraded an isolated database from commit `a250fd6` containing pending and completed Finance approvals created by the former fallback. Original group memberships, financial visibility, submitted snapshot/fingerprint, completed approver and timestamp were preserved. The original pending approval remained actionable after upgrade.
- In a fresh process, a new financing request with an empty named list was rejected despite the user's Finance legacy group. Adding the user to the company's named Finance list allowed submission and approval. Logs: `/tmp/mobikey-routing-retirement/04_final_tests.log` and `05_verify.log`.
- No production database was changed. Populate required company lists before rollout, then upgrade `mobikey_crm` to **19.0.2.5.1** and `mobikey_sale_approvals` to **19.0.1.7.0**.

## Invoice permissions and Deal Type lookup validation — 22 September 2026

- Final regression: **110 CRM/approval/document tests plus 5 dashboard tests**, zero failures or errors. Python/XML parsing and `git diff --check` passed.
- Sales-only and approval-only users cannot generate invoices through the guarded Sales routes. Billing users created actual regular, percentage-down-payment and fixed-down-payment draft invoices. Denied requests did not create invoices or add sales-order lines.
- Both form buttons, the list button, and the Action-menu shortcut follow effective invoice creation access. Alternating users did not leak cached privileged buttons. Revoking billing rights blocked submission of a previously opened wizard.
- Native opportunity Form tests cover choosing financing, saving/reloading its canonical code, searching options, catalogue creation by a manager, and ordinary users' read-only catalogue permissions. Direct imports, clearing a selection, copying a lead and rejecting inconsistent code/lookup pairs were also checked.
- Upgraded an isolated database from commit `a250fd6` with an existing custom Deal Type, a financing lead and an approved quotation. Original classification codes, approval fingerprint, financial snapshot, decision author and timestamp survived. Editing the opportunity's lookup correctly enabled financing without changing its existing approved quotation.
- Quotation approval requirements and checkpoints were not changed. Tests confirm a billing user can still invoice a confirmed order with no approval-triggering terms, without adding a manual approval requirement.
- Local logs: `/tmp/mobikey-invoice-deal-fix/04_regression.log`, `05_verify.log`, and `06_dashboard.log`. No production database was changed. Current versions are **19.0.2.6.0** for CRM and **19.0.1.8.0** for approvals.
