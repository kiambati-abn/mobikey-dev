# Mobikey CRM and Sales: consolidated recommendation

Prepared 7 September 2026 against `development`, commit `6553fa4`.

This document consolidates the user's requirements and the source-code review. It is a design recommendation, not an implemented change or proof of production behaviour. The live database, installed Enterprise/Studio modules, group memberships, email queue, automated actions, currencies, thresholds, and portal/payment configuration have not been inspected. Existing audit documents are historical context; current source code and the user's latest requirements take precedence.

## Recommendation and scope

Retain Odoo's native CRM stage movement. Make the sales quotation the authoritative commercial offer, with a focused custom approval module, explicit internal notifications, quotation-based expected revenue, and server-side restrictions on costs and margins. Retain the existing branded quotation/proforma module and native Sales document states.

Improve analytics by defining reliable metrics, recording missing business milestones and forecast snapshots, correcting dashboard calculation risks, and providing reports appropriate to each role. Reuse native Odoo reporting and the existing BI module before considering another analytics platform.

Confirmed user requirements:

- Normal Odoo stage movement instead of custom progression buttons.
- Products and commercial approvals belong on quotations rather than CRM.
- Retain the current approval matrix; replace Country Director with Country GM.
- Approval requests go to relevant approvers; customers must not receive internal approval notifications.
- Expected revenue updates from a quotation's amount once the quotation is made.
- Ordinary salespeople may see selling prices, but not costs or margins.

Design choices awaiting answers:

| Decision | Working recommendation; not a confirmed policy |
|---|---|
| Quotation amount for expected revenue | Full total including taxes, following the user's wording. Tax-exclusive subtotal is an alternative requiring an explicit decision. |
| Approval checkpoint | Before official customer issue and order confirmation. Draft preparation remains available. |
| Above-threshold trade-in authority | Either Country GM or Finance, preserving the existing single-decision structure. Separate mandatory decisions from both would change the matrix. |
| Commission eligibility milestone | To be selected: order confirmation, invoicing, or full payment. Do not infer eligibility solely from a freely movable CRM Won stage. |

Additional configuration to resolve during implementation: actual trade-in thresholds and currencies by company, approver assignments and delegates, reminder deadlines, treatment of multiple genuinely additive orders, and cost snapshot/revaluation policy. Do not invent production values.

## Proposed operating flow

1. Capture customer need, qualify the lead, assign ownership, and schedule activities in CRM.
2. Move the opportunity using native Kanban dragging, the native stage bar, and native Won/Lost actions. Keep useful pipeline stage names.
3. Create a linked draft quotation using Odoo's normal action. Create products and commercial terms on Order Lines and the quotation.
4. The first linked quotation becomes the primary quotation for expected revenue. Later alternatives do not silently replace or add to it.
5. Submit the prepared offer for required approvals. A no-exception offer requires no artificial approval step.
6. Notify the assigned approvers. Resolve discount before margin; other applicable categories can proceed independently where permitted.
7. Issue the approved offer using native sending and existing branded quotation/proforma reports, subject to the selected approval checkpoint.
8. Confirm the customer-accepted quotation. Approval alone does not send, confirm, cancel, reserve stock, or create a customer commitment.
9. Manage handover and eligible commission on the order or linked operational records. CRM shows useful summaries.

CRM stage changes must not cancel quotations/orders, approve commercial exceptions, or create commission eligibility. CRM Won and confirmed sales remain separate reporting concepts; use an exception report for mismatches. Retain qualification checks separately from stage movement, with a visible readiness checklist and correct interaction with native customer conversion.

Remove the custom transition graph, stage-write restrictions, pending-approval stage block, stage progression buttons, CRM Reset to Draft, exact-name Won condition, and custom sent-to-Negotiation automation. Preserve native protections for archived/lost records. Audit existing stage roles and native outcome configuration; do not blindly load the unused stage seed file and create duplicates.

## Approval matrix to retain

| Category | Condition | Authority after role consolidation |
|---|---|---|
| Discount | Zero | No discount approval |
| Discount | Greater than 0%, up to 2% inclusive | Sales Manager, or authorised higher level |
| Discount | Greater than 2%, up to 5% inclusive | Country GM, or HQ |
| Discount | Greater than 5% | HQ |
| Margin | Non-negative and at/above product target | No margin approval |
| Margin | Non-negative and below product target | Country GM, or HQ through hierarchy |
| Margin | Negative | Country GM or HQ |
| Financing | Selected payment term requires financing | Finance |
| Trade-in | Trade-in included; positive valuation at/below configured threshold | Sales Manager, or authorised higher level |
| Trade-in | Valuation above configured threshold | Country GM or Finance, pending confirmation of either-versus-both policy |
| Commission | Agreed eligibility milestone reached | Country GM or HQ; existing system-administrator exception retained separately unless explicitly changed |

The hierarchy is Sales Manager -> Country GM -> HQ. Finance remains separate. Retain approval authority without emailing every user who inherits it. The current code permits self-approval where the requester already has the requisite authority; changing that requires a separate policy decision.

Calculate the highest required discount tier across all relevant quotation lines. A 1% line plus a 10% line requires HQ; do not require three sequential discount tiers. Margin rules use target margin and negative-margin detection, not the discount percentage bands. Resolve discount before margin, while allowing the same authorised person to make both decisions. Zero margin below a positive target must route consistently, including notifications.

Correct the existing calculation, routing, and permission defects rather than copying them unchanged. Use one margin formula with consistent percentage units, discounted selling prices, company/currency/UoM handling, agreed reconditioning-cost allocation, and zero-price handling. Establish sensible quantity/discount/target constraints. Approval functions must verify identity, role, company, current revision, and pending state on the server.

Each approval decision belongs to a specific quotation revision and category. Store the requirement, authority, assigned approvers, decision, decision-maker, timestamp, and reason. Material changes invalidate affected decisions without destroying history. A change that alters discounted revenue/cost can invalidate both discount and margin decisions; a payment-term change affects financing. Internal notes should not restart approvals. Copied quotations never inherit valid decisions from their source. Once submitted, require an explicit revision/resubmission path for commercial edits; stale approval links must not approve the new revision.

Keep the native quotation/order `state`; approval status is separate. Centralise checks for all agreed issue/confirmation paths, including direct Sales actions, imports/integrations, reports, customer portal access, signature and payment initiation. Ensure checks occur before customer-facing side effects. A draft label alone does not prevent access through an existing portal token. Cancellation/withdrawal must remain possible without first obtaining commercial approval. Avoid automatic order cancellation when a quotation revision or CRM stage changes.

## Implementation choice: focused custom Sales module

Use a narrowly scoped addon, provisionally `mobikey_sale_approvals`, to own the matrix, approval records, commercial revision handling, and internal notifications. Extend existing Sales models; reuse Odoo groups, activities, queued mail, chatter, and existing document rendering. Keep CRM-specific fields and revenue integration organised separately within the existing CRM addon or a small integration layer; avoid circular dependencies.

Studio is viable for conditional button approvals and already supplies decision history and user interaction. It is not integrated with the current repository's approval implementation. Adding company routing, line aggregation, commercial revision validation, and multiple issue paths would still require custom code. Studio's higher-step approval and Exclusive Approval semantics need care to preserve this matrix. If live discovery reveals established Studio approval rules, assess them before retirement; never maintain two independently editable decision systems. No generic workflow engine or separate manual approval request application is needed.

## Notification policy

| Event | Recipient and behaviour |
|---|---|
| Submission | Actual assigned eligible internal approvers for actionable categories; activity and one queued request per event/recipient |
| Discount resolved | Notify margin approver when margin becomes actionable |
| Changes requested / rejected | Requester/responsible salesperson; actionable explanation with restricted financial details removed |
| Final commercial approval | One ready-to-issue notification to requester/responsible salesperson |
| Overdue request | Outstanding approvers, then configured escalation; stop reminders after resolution |
| Missing approver configuration | Requester and designated approval administrator; explicit blocked state, no silent skip |
| Revision / cancellation | Withdraw obsolete requests and close old activities; notify affected approvers only when useful |
| Customer document issue | Normal customer quotation/proforma communication only |

Authority is distinct from assignment. Resolve active internal users with the necessary approval authority and company access; use actual country/company assignments, not the operator's active company or each user's default company alone. Email addresses must come from those validated users. Do not derive request recipients from customers, quotation followers, salesperson ownership, or suggested recipients. Salespeople who are not assigned approvers receive outcomes/correction tasks, not approval requests.

The four existing templates enable `use_default_to=True`, while handlers replace only `recipient_ids`. Odoo can also generate `email_to`; that survives the override and can include a customer email. This is a source-supported delivery path, not proof of which live messages used it. Disable default recipients on approval templates and explicitly clear unintended To/CC values. Audit existing queued approval messages during remediation so previously generated recipients are not assumed fixed by a template change. Preserve evidence; do not send test emails externally.

Keep detailed cost/margin discussion on restricted internal approval records. A normal internal note on a quotation may still be visible to internal salespeople who can read that quotation. Provide a safe summary on the quotation and CRM. Audit reply routing and existing attachments, not just initial email recipients. Use event/revision/category/recipient deduplication, reliable queue handling, visible delivery failures, and valid login-required links. No approval happens merely by opening an email link.

## Expected revenue policy

Retain an initial manual estimate before a quotation exists. On first quotation save, populate an explicit primary-quotation link and synchronise expected revenue with the chosen amount basis. Display the source and update date, and make the sourced amount read-only in the UI and controlled on the server.

Recalculate for actual amount changes, primary selection, line edits, taxes if using total, currency/date/company changes, linking/unlinking, and relevant order lifecycle events. Use the existing opportunity-to-order relationship; remove the dependency on CRM product lines. Convert into opportunity company currency with a defined date, preferably quotation date for the initial policy. Keep this update independent of approval state: an unapproved draft is still a forecast, not a confirmed sale.

Alternative quotes must not inflate the forecast. Select a primary replacement explicitly or through a clearly defined revision action. On acceptance, make the accepted offer authoritative. If multiple confirmed orders genuinely belong to one opportunity, agree an additive-order policy rather than arbitrarily choosing one. On cancellation/removal of the source, exclude its current quoted value and explicitly request another source or a manual estimate; preserve history. Marking CRM Lost can preserve historical deal value while native probability/outcome reporting represents the loss.

Odoo already has a limited revenue update on order confirmation: it raises expected revenue to the untaxed order value when the order and opportunity company currencies match and the old estimate is lower. The new synchronisation must deliberately replace/coordinate that behaviour, so confirmation cannot introduce a conflicting value or prevent downward revisions. Native confirmed-order totals remain separate and should not be relabelled as quotation totals.

## Cost and margin confidentiality

Ordinary salesperson accounts must have no read or write access to product costs, quotation cost snapshots, margin amount/percentage, target margins, reconditioning/internal costs, computed minimum prices, or detailed margin approval reasons. Selling prices, discounts, quantities, taxes, totals, expected revenue, and safe approval status remain available. Product model/specification information is commercial content and should remain available to salespeople.

Create an explicit financial-visibility permission, assigned to authorised Country GM/HQ/Finance users and controlled administrators. Sales Manager does not receive it by default merely through discount approval authority. Preserve necessary permissions for actual accounting/inventory duties through reviewed role assignments. No ordinary salesperson should obtain the financial permission through accidental group inheritance or unrelated manager access.

Apply model-field restrictions to both `product.template` and `product.product` cost, custom target margins and cost fields, `sale.order.line.purchase_price`, line/order margin fields, legacy CRM cost/margin fields during migration, and independent reporting measures such as `sale.report.margin`. Protect related computed fields and custom method outputs. Cost/margin calculations still run internally with tightly scoped access and correct company context; do not grant cost access to a salesperson to make quotation calculations succeed.

Review access through forms, list views, variants, exports, read APIs, filters/aggregates, pricing helpers, reports, vendor prices/purchase documents, inventory valuation, dashboard definitions, scheduled report distribution, chatter, and attachments. Hiding a widget is not a confidentiality control. Do not expose minimum prices or detailed approval thresholds through warnings that disclose protected financial information. General approval status necessarily communicates that review is needed; it must not return the protected numbers.

The current BI addon creates scheduled jobs as the root user and uses elevated mail composition. Review its rendering/distribution privileges and recipient checks before allowing financial dashboards to be scheduled. Previously created reports or attachments do not become protected automatically when source fields are restricted; include them in the access review.

## Analytics and reporting recommendations

The code captures useful customer, vehicle, territory, source, and commercial information. Its custom analytical maturity is strongest in describing the current pipeline and weakest in explaining delays, preserving historical forecasts, and ensuring consistent metric definitions. Native Odoo already supplies Pipeline Analysis, marketing attribution, forecasting, and predictive lead scoring. Their actual configuration and data quality remain unverified. The BI addon supports many chart types, exports, comparisons, and scheduled distribution, but this repository seeds only a generic “My Dashboard”; additional configured dashboards may exist in the database.

### Define each metric before building dashboards

Maintain a metric dictionary specifying the population, record grain, date basis, currency/tax basis, exclusions, owner, calculation, and supporting drill-down. Distinguish these measures:

| Measure | Recommended definition |
|---|---|
| Open pipeline value | Sum of expected revenue for open opportunities, using the primary quotation or initial estimate |
| Weighted forecast | Sum of opportunity expected revenue multiplied by probability / 100; reuse native prorated revenue and do not weight twice |
| Active quotation value | Selected current offers; exclude superseded revisions and mutually exclusive alternatives |
| Confirmed sales | Confirmed sales orders, independent of CRM Won |
| Invoiced value | Posted customer invoices with an explicit credit-note treatment |
| Collections | Payments allocated to the relevant receivables, with an agreed reporting date |
| Closed-opportunity win rate | Won / (won + lost), using a defined closed-date population; show no data when the denominator is zero |
| Lead-to-sale conversion | Outcomes for a defined lead-creation cohort; distinguish immature/open leads from completed outcomes |
| Quotation conversion | Accepted offer families relative to issued offer families for a defined population; draft saves and revisions do not become independent offers |

Do not sum alternative quotes or duplicate opportunity amounts through joins to multiple product or approval lines. Product-mix revenue should come from line-level measures; opportunity counts should remain distinct. Invoice/payment reporting needs verified links and compatible date/currency definitions rather than assuming the CRM alone contains those facts. The pending total-versus-subtotal decision for expected revenue remains unresolved and must be reflected consistently in labels and comparisons.

### Capture lifecycle and approval events

A current-stage chart shows the present distribution, not actual progression through a funnel. Native stage movement can skip or revisit stages. Reuse native stage tracking where it supports the required analysis, and distinguish current stage, first arrival, total time across repeat visits, and reopen events. Add missing milestones for first meaningful customer contact, qualification, first official quotation issue, and acceptance. Define what counts as meaningful contact; saving a record or sending an internal approval email must not count.

The existing approval fields include decision dates but do not provide a dedicated request-and-cycle record for each submission. During the approval redesign, record submission, assignment, decision, withdrawal, and resubmission by quotation revision and category. Report pending requests, median and upper-percentile turnaround, overdue work, rejection/resubmission rates, and delay by responsible function. Distinguish time waiting for approval from time waiting for the customer. Build this history as part of the workflow rather than trying to reconstruct every cycle later from the latest status. Preserve known historical events without inventing dates for gaps.

### Improve classification and attribution

Separate operating company/country from customer geography. The current company-change helper overwrites `country_id` with company country, which can distort customer-geography reporting. Review the UTM source catalogue: Website, NGO, and Government Tender describe different dimensions. Maintain channel, campaign, customer segment, and sales process separately; normalise duplicates and preserve attribution through conversion and quotation creation. Control lookup maintenance so routine user edits do not fragment categories.

Report source quality through qualification and eventual sales, not just lead volume. Marketing ROI additionally requires expenditure data and an attribution policy; do not present lead counts as ROI. Add a data-quality view for missing owner, source, expected close date, next activity, key classifications, and primary quotation where applicable.

### Preserve forecast history

Introduce a daily or weekly forecast snapshot, with cadence selected during implementation. Record opportunity, owner/team, operating company, stage/outcome, expected close date, probability, value, amount basis, currency/rate date, and primary quotation/revision. Restrict snapshot access consistently with its source data. Snapshot values must remain stable when the live record changes.

Use snapshots for forecast-versus-actual comparison, closing-date slippage, pipeline movement, and historical salesperson/team attribution. Current data alone cannot establish what management forecast at an earlier date. Define an additive-order policy where needed, and distinguish retrospective corrections from changes known at the snapshot time.

### Correct dashboard calculation and performance risks

| Finding in the BI code | Required improvement |
|---|---|
| `get_tile_data` limits records before counting/summing | Full-population totals must not use display limits; label top-N rankings explicitly |
| Monetary tiles sum raw values and apply a company-currency display format | Use currency-normalised measures or separate currency groups; changing the symbol is not conversion |
| Percentage comparison calculates previous / current | Label this as a ratio, or use (current - previous) / previous for growth; define zero-baseline behaviour |
| Invalid filter expressions return an empty domain | Display a configuration error and withhold the result instead of silently broadening the population |
| Several chart paths load records and aggregate in Python | Profile realistic data volumes; use access-aware database aggregation for suitable stored measures and avoid repeated per-record searches |

Every displayed KPI must reconcile to its drill-down and state its date range, currency, and amount basis. Ensure aggregation, exports, and scheduled distribution preserve company and financial-field permissions. Changing the calculation strategy must not introduce elevated reporting access. Do not claim a production performance problem without measurement; the code indicates scaling risks to test.

### Start with three focused dashboards

| Audience | Recommended content |
|---|---|
| Salesperson | Own opportunities, expected revenue, overdue activities, missing next actions, expiring quotations, and safe approval status; no costs or margins |
| Sales Manager | Team pipeline, weighted forecast, stage ageing, conversion, follow-up exceptions, and approval bottlenecks; no financial-cost access by default |
| Authorised Country GM / HQ / Finance | Relevant country/company performance, forecast versus confirmed sales, customer/product mix, approval turnaround, and restricted profitability where authorised |

Evaluate native predictive lead scoring after validating outcome data, configuration, and representative history. Check whether predicted probability bands correspond to observed win rates on later outcomes before relying on them for prioritisation. The custom `lead_score` currently has no calculation; hide or retire that placeholder rather than displaying a second unexplained score. Do not introduce new predictive models before demonstrating a gap in native capability.

Deliver metric definitions and data corrections first, workflow events and forecast snapshots alongside the quotation redesign, then dashboards, and finally predictive evaluation. Business targets, reminder thresholds, snapshot cadence, and ROI inputs require configuration; no production values are assumed here.

## Field ownership appendix

“Copy” means initialise a quotation once; subsequent quotation changes do not overwrite customer qualification information. Internal cost fields remain restricted in their new location.

| Existing CRM field | Recommended destination / treatment |
|---|---|
| `partner_id` | Keep linked customer in CRM and native quotation customer field |
| `city_region` | CRM/customer; consolidate with native city/state where equivalent |
| `preferred_language` | CRM/customer language; reuse native language where feasible |
| `customer_type` | CRM/customer classification; initialise existing quotation field |
| `industry_type` | CRM/customer |
| `is_fleet_customer` | CRM/customer; actual units on quotation lines |
| `vehicle_type` | CRM interest; actual products on quotation lines |
| `vehicle_condition` | CRM preference; initialise existing quotation condition, per line where mixed offers require it |
| `intended_use` | CRM qualification; optionally copy relevant delivery/specification instructions |
| `demo_required` | CRM activity planning, independent of stage restrictions |
| `purchase_timeframe` | CRM buying intent and suggested close date |
| `budget_range` | CRM qualification |
| `financing_required` | Optional CRM interest flag; quotation requirement derived from its payment terms |
| `trade_in` | CRM interest; quotation decides actual inclusion |
| `trade_in_valuation` | Quotation, company/currency-aware valuation and approval |
| `payment_terms_type` | Replace with native quotation `payment_term_id` |
| `expected_delivery_date` | Quotation promise in `commitment_date`; distinct CRM requested date only if useful |
| `sales_region` | CRM territory; optional sales reporting copy |
| `delivery_location` | Existing field means warehouse: map to quotation `warehouse_id`; delivery address separately in `partner_shipping_id` |
| `sub_source` | CRM; native campaign where equivalent |
| `referral_name` | CRM attribution |
| `walkin_location` | CRM enquiry branch; review stock-location relationship against actual branches |
| `lead_score` | CRM only; hide or retire until meaningful scoring exists |
| `lead_status` | Leads only; retain qualification without duplicating opportunity stage |
| `disqualification_reason` | Leads; use native Lost reasons for opportunity losses |
| `disqualification_notes` | CRM |
| `deal_type` | Quotation final terms; optional initial CRM preference; distinguish fleet classification from payment method |
| `bank_id` | Quotation Financing Bank; distinct from dealer receiving bank accounts |
| `expected_revenue` | CRM, sourced from explicit primary quotation after its creation |
| `price_list` | Replace with native quotation `pricelist_id` |
| Header `discount` | Retire duplicate; quotation line discounts and calculated summary |
| Header `margin` | Retire duplicate; restricted quotation calculation |
| `year` | Offered vehicle master/unit and quotation-line snapshot |
| `mileage` | Offered unit and line snapshot; distinguish kilometres/hours |
| `vehicle_source` | Vehicle/unit origin; restricted internal quotation information if required |
| `reconditioning_cost` | Restricted unit/quotation-line cost, allocated once |
| `product_line_ids` | Replace with native quotation `order_line` |
| `insurance_required` | Quotation coverage; service line when priced |
| `warranty_included` | Existing per-line warranty text; derived summary only if needed |
| `after_sales_user_id` | Sales order owns fulfilment responsibility; optional CRM summary |
| `status_name` | Retire with name-dependent stage button logic |
| `mobikey_current_stage_type` | Retire if no retained role-based reporting use |
| `discount_approval_required/status/approver_ids/approved_by/approval_date` | Quotation approval records and computed summaries |
| `margin_approval_required/status/approver_ids/approved_by/approval_date` | Restricted quotation approval records; safe salesperson summary |
| `financing_approval_required/status/approver_ids/approved_by/approval_date` | Quotation approval records and computed summaries |
| `trade_in_approval_required/status/approver_ids/approved_by/approval_date` | Quotation approval records and computed summaries |
| `commission_approval_status`, `commission_approved_by`, `commission_approval_date` | Order/linked commission record; preserve history; trigger milestone pending |

Approval-family rows abbreviate the existing five corresponding fields: required flag, status, approver list, approved-by user, and approval date; their actual identifiers use the existing category prefixes.

| Existing CRM product-line field | Replacement |
|---|---|
| `lead_id` | Native sale order `opportunity_id` link |
| `product_id` | Native order-line product |
| `model_id` | Product model and existing document snapshot |
| `category_id` | Product category; optional quotation display |
| `quantity` | Native `product_uom_qty` and unit of measure |
| `price_unit` | Native quotation price, using pricelist rules |
| `discount` | Native order-line discount |
| `margin` | Restricted quotation-line calculation |
| `sale_order_line_id` | Retire synchronisation link after migration |

Keep/reuse existing Sales fields `vehicle_condition`, `customer_type`, and `deal_type`. Restrict or replace `margin_warning` and `margin_warning_msg`; salespeople see a general commercial review status. Keep product `model` and `target_margin` on products, with financial access only for the latter. Keep lookup models and payment-term financing configuration. Retain follow-up interval settings; move trade-in thresholds to company/currency-aware approval settings. Keep existing proforma templates, brands, bank accounts, document-status snapshots, delivery terms, native payment/validity dates, specifications, OBS, and warranty snapshots. Do not build a second Products tab alongside native Order Lines.

## Migration and delivery sequence

1. Inspect a controlled database copy: installed versions, Studio rules, custom views/actions, existing stage configuration, user roles, actual email recipients, portal/payment flows, threshold/currency settings, dashboard configuration, and data completeness. Agree the metric dictionary and reporting date/currency definitions.
2. Correct approval recipient generation and financial-data exposure in the existing flow. Review already queued messages and generated financial artifacts. This can be prioritised without waiting for the full redesign.
3. Implement the focused Sales approvals, secure calculations, notification rules, and commercial checkpoints. Capture approval-cycle and missing sales-milestone events at their source. Retain old historical fields temporarily.
4. Map current CRM product/term data to the appropriate quotation. Do not duplicate existing order lines or copy one opportunity approval onto every alternative. Preserve original approver/timestamp/history; require fresh approval where the approved commercial revision cannot be established.
5. Reconcile Country Director and Country GM definitions and actual memberships. Preserve historical identities and existing higher-level authority; do not blindly merge every old account into privileged access.
6. Switch quotation ownership and expected revenue synchronisation, restoring native CRM movement in the same coordinated release. Start forecast snapshots at the agreed cadence. Remove duplicate active approval automation so both systems cannot send requests or disagree.
7. Correct dashboard calculation/filtering risks and configure the three role-appropriate dashboards using reconciled measures. Reuse native reports, verify drill-downs and access restrictions, and profile realistic volumes. Evaluate predictive scoring only after establishing adequate data quality and history.
8. Validate scenarios below, reconcile counts/amounts, demonstrate the salesperson and approver experience, then stage the rollout with a backup and rollback procedure. Historical columns are removed only after reconciliation, not in the initial cutover.

## Acceptance checks

| Area | Evidence required before release |
|---|---|
| CRM movement | Native forward/backward stage changes work while commercial approvals are pending; no linked order is cancelled; native Lost/restore works |
| Product handoff | Lines, payment terms, pricing, delivery, and document details are correct without duplicate entry |
| Discount | 0%, 2%, just above 2%, 5%, just above 5%, and mixed 1%/10% route correctly |
| Margin | At target, below target, zero, negative, zero selling price, cost/UoM/currency changes, and reconditioning allocation produce correct results |
| Permissions | Wrong role/company, direct writes, stale decisions, and portal/public users cannot approve |
| Revision | Material edits invalidate affected approvals; old history remains; copied quotes have no valid inherited decisions; concurrent edits/approvals cannot accept stale terms |
| Notifications | Customer/follower/ordinary salesperson excluded from requests; correct assignees; no duplicates; correct sequencing; missing approver and mail failure visible |
| Revenue | First draft, amount increase/decrease, taxes, currency conversion, alternatives, confirmation, cancellation, relinking, and imports produce the defined forecast |
| Confidentiality | Ordinary salesperson cannot retrieve cost/margin from templates/variants, API, exports, reports, dashboards, emails, chatter, attachments, or pricing helpers; normal quoting works |
| Issue controls | Selected policy enforced before external side effects on email, PDF/proforma, existing portal links, signature, payment and direct confirmation |
| Documents | Existing branded and native fallback reports still render correctly with no internal financial details |
| Handover | One set of activities per defined milestone; reopen/re-win does not duplicate activities or restart commission accidentally |
| Migration | Existing commercial records and histories reconcile; no unwanted privilege expansion, duplicate quotations, or duplicate notifications |
| Metric definitions | Pipeline, weighted forecast, active offers, confirmed sales, invoices and collections remain distinct; totals reconcile to the defined date/tax/currency basis and drill-down |
| Funnel and attribution | Skipped/repeated stages, reopen events, lead cohorts and quotation revisions do not inflate conversion; customer geography remains distinct from operating country |
| Approval analytics | Submission-to-decision durations and resubmissions reconcile to recorded events; missing historical dates are marked unknown |
| Forecast history | Snapshots retain historical amount, probability, close date and owner after live changes; later actuals can be compared without rewriting the past |
| Dashboard calculations | Mixed currencies are not summed raw, totals are not truncated by ranking limits, comparison percentages have the correct definition, and invalid domains show errors |
| Analytics permissions and scale | Financial fields remain inaccessible to ordinary salespeople in aggregates, exports and scheduled reports; representative-volume performance is measured |
| Predictive evaluation | Native probabilities are assessed against representative later outcomes; the unused custom score is not presented as a functioning model |

## Source references

- [Current CRM fields, calculations, approvals and lifecycle methods](/home/ocean/Mobikey-Production/mobikey_crm/models/crm_lead.py)
- [Current CRM line synchronisation and margin](/home/ocean/Mobikey-Production/mobikey_crm/models/crm_product_lines.py)
- [Current Sales warning and stage automation](/home/ocean/Mobikey-Production/mobikey_crm/models/sale_order.py)
- [Current roles](/home/ocean/Mobikey-Production/mobikey_crm/security/groups.xml)
- [Current default-recipient approval template](/home/ocean/Mobikey-Production/mobikey_crm/data/discount_email_template.xml)
- [Existing document module](/home/ocean/Mobikey-Production/mobikey_sale_documents/README.md)
- [Odoo 19 native CRM interface](https://github.com/odoo/odoo/blob/19.0/addons/crm/views/crm_lead_views.xml): stage interface and native outcome controls.
- [Odoo 19 Studio approval documentation](https://github.com/odoo/documentation/blob/19.0/content/applications/studio/approval_rules.rst): conditional button steps, ordering, exclusive approval and decision history.
- [Odoo 19 Sales/CRM order hook](https://github.com/odoo/odoo/blob/19.0/addons/sale_crm/models/sale_order.py) and [CRM integration](https://github.com/odoo/odoo/blob/19.0/addons/sale_crm/models/crm_lead.py): native links, confirmed totals and limited revenue update.
- [Odoo 19 field security](https://github.com/odoo/documentation/blob/19.0/content/developer/reference/backend/security.rst): field-level groups and explicit read/write restrictions.
- [Odoo 19 Sales margin report](https://github.com/odoo/odoo/blob/19.0/addons/sale_margin/report/sale_report.py): separate margin measure in Sales reporting.
- [Odoo 19 mail template generation](https://github.com/odoo/odoo/blob/19.0/addons/mail/models/mail_template.py) and [default recipients](https://github.com/odoo/odoo/blob/19.0/addons/mail/models/models.py): generated recipients and email-value overrides.
- [Odoo 19 Sales portal](https://github.com/odoo/odoo/blob/19.0/addons/sale/controllers/portal.py): token access, document rendering, signatures and payment-related flows.
- [CRM reporting filters](/home/ocean/Mobikey-Production/mobikey_crm/views/crm_lead_views.xml:398) and [source catalogue](/home/ocean/Mobikey-Production/mobikey_crm/data/utm_source_data.xml): existing segmentation and attribution setup.
- [BI dashboard seed](/home/ocean/Mobikey-Production/synconics_bi_dashboard/data/dashboard_data.xml:4): generic dashboard shipped in this checkout.
- [BI totals and currency display](/home/ocean/Mobikey-Production/synconics_bi_dashboard/models/dashboard_chart.py:1841), [comparison percentage](/home/ocean/Mobikey-Production/synconics_bi_dashboard/models/dashboard_chart.py:1935), and [filter evaluation](/home/ocean/Mobikey-Production/synconics_bi_dashboard/models/dashboard_chart.py:1244): calculation and configuration findings.
- [Odoo 19 Pipeline Analysis](https://www.odoo.com/documentation/19.0/applications/sales/crm/performance/win_loss.html) and [marketing attribution](https://www.odoo.com/documentation/19.0/applications/sales/crm/track_leads/marketing_attribution.html): native reporting to reuse.
- [Odoo 19 forecast documentation](https://github.com/odoo/documentation/blob/19.0/content/applications/sales/crm/performance/forecast_report.rst): expected-close grouping and probability-weighted revenue.
- [Odoo 19 predictive lead scoring](https://github.com/odoo/documentation/blob/19.0/content/applications/sales/crm/track_leads/lead_scoring.rst): native probability modelling and configuration.

Research supports the architectural recommendation. Actual coverage and compatibility must be established against the installed database and addons. No application code or external records were changed for this recommendation.


## Implementation update — 8 September 2026

The core workflow is now implemented locally in `mobikey_sale_approvals`, with coordinated CRM and BI changes. The original analysis above remains the design record; its original statement that no application code was changed describes the analysis stage.

Implemented: native CRM movement; quotation-owned commercial fields and revision approvals; company assignments and Country GM routing; internal queued notifications; protected financial inputs and approval snapshots; primary-quotation revenue; confirmation/issue/portal/payment checks; confirmation-based handover; configurable commission eligibility; qualification milestones; immutable forecast snapshots; approval reporting; BI total/currency/comparison/filter corrections; and permission-checked dashboard links instead of privileged emailed report images. Historical CRM columns are retained and the cutover hook handles only unambiguous mappings.

See [implementation and rollout instructions](/home/ocean/Mobikey-Production/mobikey_sale_approvals/README.md) and the [metric dictionary](/home/ocean/Mobikey-Production/docs/CRM_METRIC_DICTIONARY.md). The test runner uses a disposable Odoo 19 database; no production deployment has occurred.

Company-level policy defaults follow the working recommendations above and remain configurable. Commission eligibility is disabled until a milestone is chosen. Production thresholds, user assignments and the unresolved policy questions still require confirmation. Staging discovery, historical cleanup, final dashboard layouts, realistic-volume profiling and predictive calibration remain live-data work; they are not represented as completed by the code changes.
