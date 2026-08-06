# Mobikey Odoo.sh Main Branch Audit

**Audit date:** 5 August 2026
**Repository:** `kiambati-abn/mobikey-dev`
**Audited branch:** `main`
**Audited commit:** `dddc59172e8be2272b58a359540a573167f15794`
**Audit type:** Read-only static code and repository audit

## Executive summary

At the time of the audit, `main`, `development`, and `staging` all pointed to the same commit. The working tree was clean and `main` was synchronized with GitHub.

The repository contains two modules:

- `mobikey_crm`: bespoke vehicle-sales CRM customization.
- `synconics_bi_dashboard`: third-party dashboard and reporting module.

The code audit is complete for the files tracked in Git. The overall system audit is not complete because database-held configuration, Odoo Studio changes, installed modules, automated actions, templates, permissions, and Odoo.sh project settings cannot be determined completely from the repository.

Quotation-template development should begin on `development` only after the stop-ship findings in this report are corrected or formally accepted. The current workflow and approval implementation should not be deployed as the basis of a final production quotation process without remediation.

## Audit limitations

The repository does not contain an Odoo runtime or database suitable for installing and exercising the modules. Validation was therefore limited to source-code inspection and static checks.

- All 26 Python files parsed successfully.
- All 56 XML files were well formed.
- No automated tests are present.
- No migration scripts are present.
- There is no reproducible local Odoo test environment in the repository.
- There is only one Git commit, so the origin, rationale, and sequence of individual changes cannot be reconstructed from version history.

Static parsing does not prove that the modules install successfully, inherited views resolve, or database workflows behave correctly.

## Intended quotation and CRM workflow

The apparent intended lifecycle is:

```text
Qualified lead
  -> CRM product lines
  -> Quotation stage
  -> Create sale.order with default lines
  -> Send quotation or proforma
  -> Automatic Negotiation stage
  -> Booking/Commitment
  -> Won
```

This lifecycle is not reliably enforced. Users can create, edit, send, or confirm quotations directly in Sales and bypass most CRM approval controls.

There are no custom quotation or proforma QWeb reports or report actions in the repository. Printed output therefore remains based on Odoo's standard report. The custom sale-order view only inserts Mobikey fields near the quotation-template selector.

## Stop-ship findings

### 1. Required CRM stages are not installed by the module

`mobikey_crm/data/crm_stage_data.xml` contains definitions for Qualified, Demo, Quotation, Negotiation, Booking, Won, and Lost roles. The file is not included in the module manifest's `data` list.

On a clean installation:

- The required role mappings are not created.
- Workflow searches can return no stage.
- Automatic stage progression becomes incomplete or unpredictable.
- Correct behavior depends on undocumented manual database configuration.

The supplied Won stage also does not set Odoo's native `is_won=True` flag. Odoo's native Won behavior identifies a Won stage through `is_won`, not the Mobikey role field. The custom Lost stage similarly does not match Odoo's native Lost behavior, which archives the opportunity and assigns loss information.

Relevant files:

- `mobikey_crm/__manifest__.py`
- `mobikey_crm/data/crm_stage_data.xml`
- `mobikey_crm/models/crm_stage.py`
- `mobikey_crm/models/crm_lead.py`

### 2. The Won button conflicts with the supplied Booking stage name

The CRM form requires the exact stage name `Booking / Commitment` before showing the Won button. The supplied stage is named `Booking/Commitment`.

This makes the Won button unavailable with the provided data and contradicts the module's stated design that stage renaming cannot break automation.

Relevant files:

- `mobikey_crm/views/crm_lead_views.xml`
- `mobikey_crm/data/crm_stage_data.xml`

### 3. Reset can cancel confirmed sales orders

The action labelled Reset to Draft searches linked sales orders using `sudo()` and cancels every order whose state is not `cancel` or `done`.

In Odoo 19, a confirmed order normally has state `sale`, so the action can cancel confirmed sales orders, not just open draft quotations. Depending on installed stock and accounting behavior, this can disrupt delivery, invoicing, commitments, and reporting.

The operation needs:

- Explicit state restrictions.
- Appropriate authorization.
- Delivery and invoice impact checks.
- A confirmation step and audit trail.
- Removal or careful restriction of `sudo()`.

Relevant file: `mobikey_crm/models/crm_lead.py`, method `action_reset_to_draft`.

### 4. Commercial approvals are bypassable

Approval statuses and approver fields are regular writable ORM fields. A `readonly` property in an Odoo form is not a server-side security control.

A user with write access to a lead may be able to use RPC, imports, API calls, or alternate screens to:

- Mark an approval as approved.
- Replace the recorded approver.
- Change discounts, products, quantities, or margins after approval.
- Create or send a quotation directly from Sales.
- Create an unlinked quotation.
- Invoke quotation actions without using the guarded CRM button.

Trade-in and financing approval actions do not enforce meaningful group authorization. Discount and margin actions include partial authorization checks, but direct field writes bypass them.

Approval controls must also be enforced on `sale.order` send and confirmation actions. An approval should be associated with a priced commercial revision so that any relevant change invalidates the previous approval.

### 5. Mixed discounts can be routed to the lowest approval tier

The implementation checks whether any line is in the Sales Manager band before checking higher bands.

For example, a quotation containing one line at 1% and another at 10% can be routed to the Sales Manager because the first condition succeeds. Approver selection also tests `discount <= 2`, which includes ordinary zero-discount lines.

Approval authority must be derived from the highest level required by any line, normally by calculating a maximum approval severity.

Relevant file: `mobikey_crm/models/crm_lead.py`, methods `_compute_approval_required`, `action_discount_approval`, and `get_approver_ids`.

### 6. Margin calculations use incompatible units and can fail

`target_margin` is labelled as a percentage. CRM calculates margins on a 0-100 scale, while the sales-order minimum-price formula treats the target as a 0-1 fraction:

```python
minimum_price = cost / (1.0 - target_margin)
```

Consequences include:

- Entering `20` for 20% produces an invalid negative denominator.
- Entering `0.20` works in the sale-order formula but is compared with CRM margin values such as `20`.
- A target value of `1` can produce division by zero.
- A 100% line discount with nonzero cost can cause another division-by-zero path.
- Sale-order margin warnings ignore the line discount.
- Currency and unit-of-measure conversions are ignored.
- Total opportunity reconditioning cost is added to every product line.

The margin convention must be normalized, constrained, documented, and tested before it is used for approval decisions.

Relevant files:

- `mobikey_crm/models/product_template.py`
- `mobikey_crm/models/crm_product_lines.py`
- `mobikey_crm/models/crm_lead.py`
- `mobikey_crm/models/sale_order.py`

### 7. Required module dependencies are missing

The customization references:

- `stock.warehouse`
- `stock.location`
- `sale_order_template_id`

The manifest does not declare `stock` or `sale_management` as dependencies. A clean installation can fail or behave differently depending on which applications happen to have been installed previously.

Relevant files:

- `mobikey_crm/__manifest__.py`
- `mobikey_crm/models/crm_lead.py`
- `mobikey_crm/views/sale_order_view.xml`

## Quotation-template design risks

### Incomplete CRM-to-quotation mapping

Quotation creation maps product, quantity, price, and discount. It does not reliably map:

- CRM `price_list` to native `pricelist_id`.
- Custom payment terms to native `payment_term_id`.
- Delivery date to commitment date.
- Delivery location to warehouse or logistics fields.
- Bank information.
- Trade-in description and valuation.
- Insurance and warranty choices.
- Financing approval details.
- Reconditioning costs.
- Customer-facing commercial notes.

A quotation template cannot compensate for missing model-to-model mappings.

### CRM product lines are too restrictive for flexible quotations

The CRM line model currently provides:

- Integer quantity only.
- Product list price as a related value.
- No proper pricelist calculation.
- No unit-of-measure selection.
- No taxes or fiscal-position handling.
- No sections or notes.
- No optional products.
- No customer-facing line description.
- No service products.

This is insufficient for flexible treatment of fees, registration, insurance, accessories, service items, and fractional quantities.

### Applying a native quotation template can replace CRM lines

Odoo Sales Management clears and rebuilds order lines when the quotation template changes. That can conflict with the Mobikey `default_order_line` values used to seed a quotation from CRM.

Possible results include:

- CRM-selected vehicle lines appearing initially and then being erased.
- Template products replacing client-selected products.
- An automatic default template changing the intended price or content.

The implementation must define whether CRM lines are preserved, merged into a template, inserted into placeholders, or regenerated after template application.

### Proforma sending may move the CRM opportunity to Negotiation

Mobikey advances an opportunity when the linked sale order becomes `sent`. Odoo uses the quotation-send workflow for normal quotation and proforma sending.

Sending a proforma may therefore move the opportunity from Quotation to Negotiation. The client must confirm whether this is the desired business event.

## Additional CRM and sales risks

### Pipeline and stage integrity

- Stage lookup is global, uses `limit=1`, and is not constrained by company or sales team.
- Duplicate stage-role assignments can result in arbitrary selection.
- There is no database uniqueness constraint for a role within the appropriate scope.
- A caller can potentially supply `mobikey_bypass_stage_guard` through RPC context.
- Adjacent Kanban movement does not enforce all linked-quotation requirements.
- Manual Quotation-to-Negotiation movement does not prove a quotation was sent.
- Stage data uses `noupdate="1"`, making subsequent corrections difficult to distribute through upgrades.

### Pricing and approval integrity

- Approved status can remain after products, targets, prices, or discounts change.
- Direct CRM product-line writes bypass lead-level write handlers.
- There are no constraints preventing negative discounts or discounts over 100%.
- Product-cost or target-margin changes can change commercial risk without generating a new approval notification.
- Approval routing uses the environment company or users' primary companies rather than consistently using the opportunity company.
- The trade-in threshold defaults to zero, so nearly every positive valuation can require elevated approval.
- Trade-in threshold documentation describes a percentage while the implementation compares an absolute monetary value.
- Creating a record does not consistently trigger financing or trade-in approval workflows.
- A multi-record write may encounter singleton assumptions.
- Finance and Country GM groups do not consistently match the permissions checked by approval methods.
- Rejected statuses exist without a complete rejection workflow.

### CRM product-line synchronization

- Product-to-sale-line matching uses product plus `limit=1`, so duplicate products can link to the wrong order line.
- Links are assigned primarily during sale-order creation and are not robustly maintained later.
- The CRM onchange writes immediately to a saved sale-order line, even if the CRM form is subsequently discarded.
- Changing `product_id` directly does not reproduce all native sale-line product onchange behavior for UoM, taxes, descriptions, or pricing.
- Truth-value checks prevent zero quantity, zero price, or zero discount from being propagated correctly.
- `lead_id` does not explicitly cascade deletion, allowing possible orphan lines.

### Revenue and conversion behavior

- The customization replaces native currency-aware `expected_revenue` with a Float.
- It searches for one arbitrary non-cancelled linked sale order.
- It assigns the tax-inclusive `amount_total` rather than a clearly defined expected or untaxed revenue value.
- Sale-order changes are not represented correctly in the declared compute dependencies.
- The computation creates repeated sale-order searches and can have poor list-view performance.
- Lead conversion requires an already-linked partner before native conversion completes, which can defeat Odoo's normal create/select-customer conversion flow.
- Company-to-country synchronization conflates the operating company's country with the customer's or lead's geographic country.

### Notifications, commission, and follow-up

- Repeated Won processing can duplicate follow-up activities and notification emails.
- Follow-up configuration values are converted to integers without robust validation or nonnegative constraints.
- `action_send_mail` resolves an empty external identifier and will fail if invoked.
- Commission authorization does not match the associated comments and user-facing error message.
- The Finance group is created but does not align consistently with margin-approval behavior.
- Commission links in external emails are relative `/web#...` links and may not work outside an authenticated browser session.
- The after-sales email greeting uses the salesperson's name while sending to an after-sales recipient.
- Commission and follow-up workflows are not idempotent.

### Security and data access

- All internal users have broad CRUD access to CRM product lines without a dedicated record rule.
- Users may access or modify product lines belonging to opportunities outside their normal responsibility.
- Form-view group restrictions do not protect cost, target-margin, or margin values through RPC/API access.
- Lookup models generally allow internal-user creation and editing, have no company scope, and have no uniqueness constraints.

### Dead or incomplete functionality

- `product_brand.py` is not imported by `models/__init__.py`.
- `views/product_brand.xml` is not loaded by the manifest.
- Product Brand has no access-control entry if it is activated.
- `sale_order_line.py` is effectively empty.
- Several lead fields are defined but absent from active views.
- Referral, sub-source, and lead-score view elements are commented out.
- Top-level discount and margin fields appear unused.
- `VEHICLE_TYPE_LABELS` appears unused.
- Several numeric fields lack realistic constraints for year, mileage, quantity, cost, and valuation.

## BI dashboard audit

The dashboard does not directly modify quotation PDFs, but it can expose or distribute CRM, quotation, sales, and accounting information and can affect instance performance.

### Access-control risks

Every internal user receives full create, write, and delete access to dashboards, charts, mail configurations, and dashboard child models through `synconics_bi_dashboard/security/ir.model.access.csv`.

Restricting menus to managers does not protect the models through RPC or API access.

The dashboard-chart record rule appears to combine model-access and company/KPI conditions incorrectly. For many charts, a company-allowed condition can make the earlier model-access branch ineffective at the chart-record level. Interactive searches against underlying business models still use the current user's access rights, but chart definitions and configuration remain too broadly exposed.

### Root scheduled execution and data leakage

Each dashboard can create a daily cron running as `base.user_root`. Scheduled message generation also uses `sudo()`.

This creates a risk that scheduled email recipients receive data broader than they could access interactively. Root execution also makes malicious or misconfigured dashboard definitions significantly more dangerous.

The scheduled-email path appears not to supply `is_dashboard=True`, while the mail-compose onchange returns early without it. Scheduled emails may therefore fail to populate charts, templates, or recipients correctly.

### Stored HTML/XSS risk

The Font Awesome icon widget accepts custom icon content. The saved value is rendered through JavaScript `markup()` and server-side `Markup` without adequate sanitization.

Because ordinary internal users have broad write access to dashboard configuration, this presents a stored HTML/script injection risk for dashboard viewers, administrators, and possibly generated email content.

Relevant files:

- `synconics_bi_dashboard/static/src/js/fa_icon_widget.js`
- `synconics_bi_dashboard/models/dashboard.py`
- `synconics_bi_dashboard/models/dashboard_chart.py`
- `synconics_bi_dashboard/wizard/mail_compose_message.py`

### Domain handling

Dashboard domain evaluation catches errors and falls back to an empty domain. An invalid restriction can therefore broaden a query to every accessible record rather than failing closed.

This can cause unexpected data disclosure and severe performance impact.

### Image rendering and external dependencies

Chart email/image generation:

- Uses `imgkit`.
- Requires an external `wkhtmltoimage` executable that is not declared in Python requirements.
- Downloads Bootstrap and Font Awesome from public CDNs during rendering.
- Depends on outbound network availability.
- Can be fragile on Odoo.sh and during offline or restricted builds.
- Expands the external-resource and possible server-side request surface.

### Export risks

- CSV and XLSX exports do not appear to neutralize values beginning with spreadsheet formula characters.
- Chart names are used for Excel worksheet names without sufficient restriction for length and invalid characters.
- Some direct calls can fail when optional export parameter dictionaries are false or absent.

### Performance risks

- Several aggregations load records and iterate in Python instead of using database `read_group` operations.
- An unlimited chart can load all matching records into memory.
- Frequent automatic refresh, including a 15-second setting, can amplify database and application load.
- Large bundled JavaScript libraries increase repository size, review burden, and browser payload.

### Lifecycle and maintenance risks

- Programmatically created cron records may remain after uninstall if cleanup hooks do not cover them.
- Dashboard records whose menus are disabled can become difficult to delete cleanly.
- Python `eval()` is used for action context instead of Odoo's `safe_eval`.
- There are no dashboard tests.
- Vendored JavaScript has no lock file, component inventory, or software bill of materials.
- The module is third-party OPL-licensed code. Evidence of lawful acquisition and the exact vendor release should be retained, and any modification or redistribution must remain within the applicable license.

## Repository and governance risks

- The repository has only one commit, preventing meaningful change-history or authorship analysis.
- `main`, `development`, and `staging` currently represent identical code rather than distinct environment states.
- There is no documented release or promotion process.
- There are no tests, migrations, installation instructions, architecture notes, or operational runbooks beyond comments in source files.
- The repository is approximately 71 MB, with much of the size attributable to third-party libraries and marketing media.
- The custom module manifest reports version `19.0.1.2.0`, while its description references scope `v1.1.0`, which makes release provenance unclear.

## Database and Odoo.sh verification still required

A sanitized production/staging database or controlled administrator access is required to verify:

- Exact Odoo edition, revision, and Odoo.sh build.
- Installed modules, particularly `sale_management`, `stock`, Studio, and PDF Quote Builder.
- Existing quotation templates and template lines.
- Studio-created or database-only inherited report views.
- Actual CRM stages, role assignments, duplicates, team restrictions, and native `is_won` values.
- Automated actions, server actions, scheduled actions, and webhooks.
- Companies, currencies, pricelists, taxes, and fiscal positions.
- Native payment terms and the custom financing flag.
- Warehouses, stock locations, and delivery configuration.
- Document layouts, company headers and footers, legal identifiers, and bank details.
- Proforma feature/access-group configuration.
- Approval users, security groups, and allowed companies.
- Trade-in and follow-up configuration parameters.
- Record rules and access-control customizations outside this repository.
- Dashboard definitions, domains, recipients, and root-owned cron jobs.
- Outgoing mail configuration and `web.base.url`.
- PDF and image-rendering behavior on Odoo.sh.
- Odoo.sh build logs, deployment settings, and environment variables.

## Recommended remediation sequence

1. Create and use a local `development` branch tracking `origin/development`.
2. Correct manifest dependencies and define a reliable stage-data migration strategy.
3. Align Won and Lost behavior with native Odoo CRM semantics.
4. Replace exact stage-name conditions with controlled functional identifiers.
5. Redesign approval enforcement around priced sale-order revisions, sending, and confirmation.
6. Normalize margin units and add discount, margin, quantity, and valuation constraints.
7. Protect or redesign reset and sales-order cancellation behavior.
8. Define a complete CRM-to-quotation field-mapping specification.
9. Decide explicitly how CRM vehicle lines merge with quotation templates, sections, notes, services, and optional products.
10. Build quotation and proforma templates only after those decisions are implemented.
11. Add module-installation, workflow, approval, multi-company, security, and report-rendering tests.
12. Harden, upgrade, isolate, or remove the BI dashboard module before trusting scheduled distribution of commercial data.

## Proposed quotation-template discovery decisions

Before implementation, the business should approve answers to the following:

- Which document is legally a quotation, and which is a proforma invoice?
- Does sending a proforma count as entering Negotiation?
- Which commercial changes invalidate an approval?
- Is approval based on line discount, total discount, margin, or all three?
- Are approval thresholds evaluated per line, per quotation, or by maximum severity?
- Should templates replace, append to, or wrap the CRM-selected vehicle lines?
- Which items are products, services, optional products, sections, or narrative text?
- How should trade-in value appear: discount, separate purchase, informational line, or settlement summary?
- Which financing, insurance, warranty, delivery, tax, and bank details must print?
- Which fields vary by Kenya, Uganda, Tanzania, company, currency, or customer type?
- Can salespeople edit template clauses, and which clauses must be locked?
- Which approval and revision evidence must appear on the final document?

## Final assessment

The current code provides a useful starting point for a vehicle-sales CRM, but the commercial workflow is not yet safe enough to serve as the authoritative control layer for flexible quotation and proforma templates.

The largest immediate concerns are missing stage installation, native CRM incompatibilities, bypassable approvals, incorrect mixed-discount routing, inconsistent margin mathematics, destructive reset behavior, incomplete CRM-to-sale-order mapping, and dashboard security.

Quotation-template work can proceed as a controlled prototype on `development`, but production deployment should follow remediation and database-level verification.
