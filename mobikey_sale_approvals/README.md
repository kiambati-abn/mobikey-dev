# Mobikey quotation workflow

CRM captures customer need and qualification; native stage movement, Won and Lost remain available. Sales order lines own the offer. An exception-free quotation can be sent/confirmed without an artificial submission step.

An exception quotation follows **prepare → submit → approve → issue → confirm**. Use **Revise quotation** to withdraw the previous revision and edit commercial terms. Decisions remain in history. Discount precedes commercial margin review. Approval never sends or confirms the offer automatically.

## Company configuration

Under **Settings → Companies → Sales approvals**, set the Sales Manager discount limit, Country GM discount limit, minimum acceptable margin, amount basis and approval checkpoint. The company assignment fields can narrow a role to named people. When a role's company list has no eligible person, the workflow uses active internal users who have the matching approval access right and access to that company. Select one or more named people in **Trade-in approvers**; any selected person can approve a new trade-in request. The trade-in assignment grants the minimum quotation-approver access automatically. Defaults are 2%, 5% and 20% respectively. Discounts above the GM limit route to HQ; margins below the company minimum route to the Country GM. Higher roles can be assigned to a lower-level approval. Country Director is retained only as a legacy group for membership review; the active hierarchy is Sales Manager → Country GM → HQ, with Finance separate.

The implementation defaults to tax-inclusive forecast revenue and approval before customer issue and confirmation. New trade-in submissions use the company's named approver pool. Any selected person can complete the request; legacy threshold and role fields remain in the database only to preserve existing approval history. Commission eligibility stays disabled until the company selects confirmation, full invoicing or full payment. Approval deadlines default to three days and can be changed per company.

Costs, threshold snapshots, legacy product target margins, reconditioning costs, supplier prices, inventory valuation and margin measures require **Financial cost and margin visibility**. GM/HQ/Finance and system administrators inherit it; Sales Manager does not. Calculations run internally without granting that permission to salespeople. Reconditioning cost is a total per quotation line, allocated once. Company discount and margin thresholds are snapshotted at submission; later configuration changes apply to new or revised submissions without silently changing a submitted offer. Product target margins remain only as historical compatibility fields.

## Forecast and reporting

The first linked quotation becomes the opportunity's primary quotation. Alternatives do not inflate expected revenue. Amount increases/decreases update the forecast, using company currency and the quote's pricing date. The first accepted quotation becomes authoritative. Where several confirmed orders exist, keep an explicit primary selection; native confirmed sales totals remain separate. Cancelling/unlinking/deleting the source clears its sourced value. The user can select a replacement or enter a new estimate.

**Sales → Reporting → Forecast history** holds daily immutable snapshots. **Approval turnaround** reports decisions by category/status and elapsed hours. Native CRM reporting supplies stage history and weighted forecasting. The lead form shows operating country separately from customer geography and a qualification readiness summary.

Approval notifications use explicit internal recipients and each user's Odoo notification preference. Every workflow event is logged on both the quotation and approval chatter, while only the quotation event notifies recipients. Margin requests activate after discount approval. Resolved/withdrawn requests close their activities; overdue requests receive at most one reminder per day. Dashboard sharing emails contain login-required links so each recipient opens the report with their own permissions.

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

The full local suite must pass before deployment. See the [validation record](/home/ocean/Mobikey-Production/docs/CRM_IMPLEMENTATION_VALIDATION_2026-09-08.md) for evidence and scope limits.

## Remaining live-data work

Staging access and final policy choices are still required. Source-catalogue normalisation, detailed historical data repair, role-specific dashboard layouts, performance measurements on production-sized data, profitability artifact review, and predictive scoring calibration depend on that data. Native reports and the new snapshot/approval reporting provide the implementation foundation; this release does not claim historical reconstruction or predictive-model validation.
