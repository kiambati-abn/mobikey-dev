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

The default sales policy uses **Assigned records and teams led**. An ordinary salesperson who leads no teams consequently sees only assigned records. Leadership comes from the native Sales Team's Team Leader field. Being a Commercial Approval Sales Manager is not the same as being a CRM manager or a team leader.

Each policy is attached to an Odoo group and has independent read, edit, create, delete and reassignment scopes. Supported scopes are **No grant**, **Assigned records**, **Assigned records and teams led**, **Assigned records and teams joined**, and **All permitted companies**. Modification scopes must be contained in that policy's read scope.

Policies are additive: all active policies for a user's effective groups apply, including inherited groups. **No grant** contributes nothing; it does not revoke another policy's grant. For a read-only team leader, keep read scope at teams led and change write scope to assigned records; independently choose creation and reassignment scopes. Review all of the user's effective policies when reducing access. Archive a policy to stop its grants; keep its chatter history. Administrators alone can edit policies. Changes are tracked in chatter and invalidate Odoo's access-rule cache.

Company rules always apply separately. The fixed administrator recovery rule does not bypass company restrictions. Odoo's superuser and explicit internal `sudo()` operations retain their native framework behavior.

Global CRM policy rules prevent native All Documents and other broad group rules from widening the configured scope. Compatible group grants allow team leaders to exercise their policy despite Odoo's native own-record restriction. Policy enforcement covers searches, reads, edits, creation and deletion through the ORM, including RPC/import/export paths. Reassignment is checked against the original record as well as normal write permissions. A salesperson allowed to reassign their own lead loses access after assigning it to someone else unless a different policy still grants access.

CRM product lines require a CRM sales role (or administrator) and an accessible parent. Ordinary users cannot create orphan lines or move a line to a lead they cannot edit. CRM activity analysis follows the current lead. Historical forecasts retain their original salesperson/team/amounts, but visibility follows the current linked lead. Deleted-lead snapshots are visible only to users with an all-record read scope within their permitted companies. Forecast records remain immutable.

Common changes within these scopes require configuration and refreshing the client form. A new business dimension, such as territory-specific grants or different policies per lead stage, requires a deliberate code extension and regression tests. Arbitrary Python/domain expressions are not exposed in the policy editor.

## Existing access groups and remaining live checks

| Repository group / configuration | Treatment |
|---|---|
| Sales Manager, Country GM, HQ, Finance | Retained: used by quotation approval routing. Labels explicitly identify quotation approvals. |
| Quotation approver | Retained: supplies minimum review access for named approvers. |
| Financial cost and margin visibility | Retained: protects financial fields separately from CRM visibility. |
| Legacy Country Director | Existing `19.0.2.3.0` migration retires it while preserving Sales Manager access; no automatic GM promotion. |
| Legacy margin-warning ACL | Installation hook and the new `19.0.1.5.0` upgrade migration disable this known obsolete grant when present. |
| Broad CRM product-line ACL | Changed from all internal users to CRM sales users, with parent-record and company restrictions. |
| Native All Documents role | Retained for other sales behavior; cannot bypass the CRM policy. |

The source audit does not prove which custom groups, Studio rules or user memberships exist in a live database. Before production rollout, inventory active CRM rules and ACLs, effective user groups, sales-team leaders/members and enabled companies. Remove only confirmed obsolete custom grants. Do not delete active approval roles by their names alone.

Named approver assignment currently adds the quotation-approver group. Removing the assignment does not automatically remove that group. Review memberships against assignments in all companies and pending approvals before removal; an existing submitted approval deliberately retains its original assignees. This change does not infer authority revocation or automatically remove those memberships.

Unrelated CRM lookup tables currently allow internal users to create/edit values. Those existing permissions are unchanged; Deal Types use the narrower permissions requested here.

## Deal Types

Open **CRM → Configuration → Deal Types**. CRM managers and administrators can add, rename and reorder options; other internal users can only read/select them.

The `deal_type` field remains a string-valued Selection on both `crm.lead` and `sale.order`. Both get choices from `mobikey.deal.type`. The existing integration codes remain `cash`, `financing`, `lease`, and `fleet`. Codes are unique, lowercase identifiers and cannot change after creation. Labels can change without changing stored codes or approval fingerprints. Built-in choices cannot be deleted; custom choices cannot be deleted while referenced by leads, quotations or retained approval previews.

The `financing` code retains its existing financing behavior even if its label changes. New choices classify deals; they do not silently add a new approval policy. Existing Financing Required and financing payment-term controls continue to work. Approval previews resolve configurable labels while leaving their stored commercial snapshots unchanged.

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
