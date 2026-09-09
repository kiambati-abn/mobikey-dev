# Mobikey quotation workflow

CRM captures customer need and qualification; native stage movement, Won and Lost remain available. Sales order lines own the offer. An exception-free quotation can be sent/confirmed without an artificial submission step.

An exception quotation follows **prepare → submit → approve → issue → confirm**. Use **Revise quotation** to withdraw the previous revision and edit commercial terms. Decisions remain in history. Discount precedes commercial margin review. Approval never sends or confirms the offer automatically.

## Company configuration

Under **Settings → Companies → Sales approvals**, set the amount basis, approval checkpoint, trade-in policy/threshold and assigned internal approvers. An assignment is valid only when the user has the requisite role and access to that company. Higher roles can be assigned to a lower-level approval. Country Director is retained only as a legacy group for membership review; the active hierarchy is Sales Manager → Country GM → HQ, with Finance separate.

The implementation defaults to tax-inclusive forecast revenue, approval before customer issue and confirmation, and either GM or Finance for high-value trade-ins. These are configurable recommendations, not confirmed production policy. Trade-in submission requires explicit threshold verification. Commission eligibility stays disabled until the company selects confirmation, full invoicing or full payment. Approval deadlines default to three days and can be changed per company.

Costs, target margins, cost snapshots, reconditioning costs, supplier prices, inventory valuation and margin measures require **Financial cost and margin visibility**. GM/HQ/Finance and system administrators inherit it; Sales Manager does not. Calculations run internally without granting that permission to salespeople. Reconditioning cost is a total per quotation line, allocated once. Product cost and target margin are snapshotted; master-data edits do not silently change a submitted offer.

## Forecast and reporting

The first linked quotation becomes the opportunity's primary quotation. Alternatives do not inflate expected revenue. Amount increases/decreases update the forecast, using company currency and the quote's pricing date. The first accepted quotation becomes authoritative. Where several confirmed orders exist, keep an explicit primary selection; native confirmed sales totals remain separate. Cancelling/unlinking/deleting the source clears its sourced value. The user can select a replacement or enter a new estimate.

**Sales → Reporting → Forecast history** holds daily immutable snapshots. **Approval turnaround** reports decisions by category/status and elapsed hours. Native CRM reporting supplies stage history and weighted forecasting. The lead form shows operating country separately from customer geography and a qualification readiness summary.

Approval emails use explicit internal recipients, queued delivery and revision-based deduplication. Margin requests activate after discount approval. Resolved/withdrawn requests close their activities; overdue requests receive at most one reminder per day. Dashboard sharing emails contain login-required links so each recipient opens the report with their own permissions.

## Coordinated installation / upgrade

1. Back up the database and filestore and rehearse against a controlled staging copy. Review installed Studio rules, automated actions and inherited views first; disable superseded approval automations during cutover.
2. Upgrade `mobikey_crm` and install `mobikey_sale_approvals` in the same maintenance operation. Upgrade `synconics_bi_dashboard` as well. Keep `mobikey_sale_documents` installed. Do not deploy the CRM change alone.
3. Review company configuration and legacy Country Director memberships; do not blindly grant GM authority. Preserve financial permissions required for genuine accounting/inventory duties without giving them to ordinary sales users.
4. The install hook preserves stored estimates, selects a quotation only when unambiguous, copies historical lines only into an empty uniquely identified draft, preserves historical CRM decisions and flags existing confirmed commitments. It quarantines identifiable unsent legacy CRM approval requests for recipient review rather than deleting evidence. It does not validate pending quotations using old CRM approvals.
5. Reconcile logged ambiguous opportunity IDs. An empty linked draft has **Import historical CRM products** for an explicit target selection. Review quantities, pricing, terms and costs before submitting. Existing populated quotations are never appended to automatically.
6. Inspect existing queued mail, historical attachments/shared reports, Studio actions, live portal/payment providers and access groups. Existing artifacts or third-party privileged methods are not retroactively secured by model field restrictions.
7. Demonstrate the salesperson, SM, GM, HQ, Finance and customer flows in staging before production cutover. A rollback restores the paired database/filestore backup and previous addon versions; do not uninstall approval history as a rollback method.

Legacy fields remain available in the administrator's historical CRM approvals tab. Already-confirmed orders remain printable as historical commitments; this marker does not approve drafts or new revisions. No production data or external mail is changed by editing this repository.

## Reproducible checks

`odoo-lab.toml` pins Odoo 19 and the existing `requirements.txt` dependency. Run:

```sh
~/odoo-lab/bin/odoo-lab --project /home/ocean/Mobikey-Production build
~/odoo-lab/bin/odoo-lab --project /home/ocean/Mobikey-Production test
```

The runner creates a disposable database and retains its logs. Workflow tests include ordinary-user quoting and financial access, role/company routing, revision invalidation, revenue, notifications, reports/composer, commission configuration and actual portal requests. Document tests use the supported confirmation-only policy to isolate editable draft layout fixtures; workflow tests cover the stricter issue policy separately.

The final local run passed all 48 tests. See the [validation record](/home/ocean/Mobikey-Production/docs/CRM_IMPLEMENTATION_VALIDATION_2026-09-08.md) for evidence and scope limits.

## Remaining live-data work

Staging access and final policy choices are still required. Source-catalogue normalisation, detailed historical data repair, role-specific dashboard layouts, performance measurements on production-sized data, profitability artifact review, and predictive scoring calibration depend on that data. Native reports and the new snapshot/approval reporting provide the implementation foundation; this release does not claim historical reconstruction or predictive-model validation.
