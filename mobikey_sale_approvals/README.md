# Mobikey quotation workflow

CRM captures customer need and qualification; native stage movement, Won and Lost remain available. Sales order lines own the offer. An exception-free quotation can be sent/confirmed without an artificial submission step.

An exception quotation follows **prepare → submit → approve → issue → confirm**. Use **Revise quotation** to withdraw the previous revision and edit commercial terms. Decisions remain in history. Discount precedes commercial margin review. Approval never sends or confirms the offer automatically.

## Company configuration

Under **Settings → Companies → Sales approvals**, set the Sales Manager discount limit, Country GM discount limit, overall minimum acceptable margin, amount basis and approval checkpoint. A non-empty company assignment is authoritative: the workflow uses exactly those active internal users with access to the company, regardless of their business-role access setting. This allows, for example, a Country GM named as a Finance approver to decide financing without replacing the user's commercial role with Finance. When an assignment is empty, the workflow falls back to active users with the matching role and company access. Every named approver receives the minimum quotation-review access automatically; assignment alone does not grant financial cost and margin visibility. Defaults are 2%, 5% and 20% respectively. Discounts above the GM limit route to HQ. An overall quotation margin below the company minimum routes first to the Country GM and then to HQ. The commercial hierarchy is Sales Manager → Country GM → HQ, with Finance as a separate access setting.

The implementation defaults to tax-inclusive forecast revenue and approval before customer issue and confirmation. New trade-in submissions use the company's named approver pool. Any selected person can complete the request; legacy threshold and role fields remain in the database only to preserve existing approval history. Commission eligibility stays disabled until the company selects confirmation, full invoicing or full payment. Approval deadlines default to three days and can be changed per company.

Costs, threshold snapshots, product minimum margins, reconditioning costs, supplier prices, inventory valuation and margin measures require **Financial cost and margin visibility**. GM/HQ/Finance and system administrators inherit it; Sales Manager does not. Calculations run internally without granting that permission to salespeople. Reconditioning cost is a total per quotation line, allocated once. Set **Minimum acceptable margin (%)** on a product for the active company; zero disables its line-level rule. Product breaches route to the Country GM. Company and product thresholds are snapshotted at submission; later changes apply to new or revised submissions without silently changing a submitted offer. The old Target Margin field remains historical compatibility data.

## Forecast and reporting

Expected revenue is the sum of every linked non-cancelled quotation and order. Amount increases/decreases update the forecast using company currency and each quote's pricing date. Cancelling, unlinking or deleting a quotation removes its amount. A manual estimate is available only when the opportunity has no active quotation. The historical primary-quotation link is retained but no longer controls forecasting.

**Sales → Reporting → Forecast history** holds daily immutable snapshots. **Approval turnaround** reports decisions by category/status and elapsed hours. Native CRM reporting supplies stage history and weighted forecasting. The lead form shows operating country separately from customer geography and a qualification readiness summary.

Approval notifications use explicit internal recipients and each user's Odoo notification preference. Every workflow event is logged on both the quotation and approval chatter, while only the quotation event notifies recipients. Margin requests activate after discount approval; an HQ margin request stays queued until the Country GM approves. Resolved/withdrawn requests close their activities; overdue requests receive at most one reminder per day. The approval form shows category-specific values captured at submission. Dashboard sharing emails contain login-required links so each recipient opens the report with their own permissions.

Deal Type and Financing Required are visible on opportunities and quotations. Selecting Financing enables Financing Required; Fleet and Lease may also retain financing. Payment Terms are maintained only on quotations because one opportunity can have several offers with different terms. When financing is required, only payment terms marked **Financing Required** are valid. A financing-enabled quotation term updates the linked opportunity, and payment terms remain the approval trigger.

The Qualification tab records the accessible company or branch where the customer walked in. Preferred Languages are configurable under **CRM → Configuration → Preferred Languages** and can also be added from the qualification field.

## Coordinated installation / upgrade

1. Back up the database and filestore and rehearse against a controlled staging copy. Review installed Studio rules, automated actions and inherited views first; disable superseded approval automations during cutover.
2. Upgrade `mobikey_crm` and install `mobikey_sale_approvals` in the same maintenance operation. Upgrade `synconics_bi_dashboard` as well. Keep `mobikey_sale_documents` installed. Do not deploy the CRM change alone.
3. Review company approver assignments and role memberships. The upgrade retires legacy Country Director membership by retaining its previously implied Sales Manager access; it does not grant Country GM authority. Preserve financial permissions required for genuine accounting/inventory duties without giving them to ordinary sales users.
4. The install hook preserves stored estimates, selects a quotation only when unambiguous, copies historical lines only into an empty uniquely identified draft, preserves historical CRM decisions and flags existing confirmed commitments. It quarantines identifiable unsent legacy CRM approval requests for recipient review rather than deleting evidence. It does not validate pending quotations using old CRM approvals.
5. Reconcile logged ambiguous opportunity IDs manually. Review quantities, pricing, terms and costs before submitting. Existing populated quotations are never appended to automatically.
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
