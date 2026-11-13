# Quotation → opportunity link: planned change

Recorded 13 November 2026 against `development`, commit `8678d1c`, and the
live `mobikey.odoo.com` database (Odoo 19.0+e). This is a plan plus the current
production state. It is not an implemented code change.

## Current production state (Studio interim)

A smart button on the quotation form opens the quotation's source opportunity.
It was added live, outside this repository:

| Record | Detail |
| --- | --- |
| Server action `ir.actions.server` id **779** | "Open Source Opportunity", model `sale.order`, Python code that returns a `crm.lead` form action for `record.opportunity_id` |
| Studio view `ir.ui.view` id **1967** | "Odoo Studio: sale.order.form customization". One xpath was appended inside `//div[@name='button_box']`: `<button name="779" type="action" class="oe_stat_button" icon="fa-handshake-o" string="Opportunity" invisible="not opportunity_id"/>` |

Verified on S00068 and S00062: the button appears and opens the linked
opportunity. It is hidden when `opportunity_id` is empty. At recording time, 7
of 24 quotations had an opportunity (S00055, S00056, S00058, S00059, S00060,
S00062, S00068).

## Change: move the button into code, remove Studio

Implemented in `mobikey_crm` 19.0.2.7.0 (not yet deployed):

1. `sale.order.action_open_opportunity` returns the opportunity form after a
   CRM read-access check. The stat button sits in `button_box` of
   `view_sale_order_form_inherit_vehicle_condition`, with
   `invisible="not opportunity_id"` and `groups="sales_team.group_sale_salesman"`.
2. Tests in `mobikey_crm/tests/test_view_all_role.py` cover the linked, unlinked
   and no-access cases.
3. The same release adds the **View All Opportunities** role (see
   [the access guide](CRM_ACCESS_AND_QUOTATION_CONFIGURATION.md#view-all-opportunities-role)).

Remaining steps:

4. After the module upgrade is deployed, remove the Studio interim from
   production in this order, so there is never a duplicate button:
   - delete the `button_box` xpath for `name="779"` from Studio view 1967
     (leave that view's other customizations untouched);
   - archive server action 779.
5. Check one linked and one unlinked quotation in production.

If the code ships while the Studio xpath is still present, users see two
Opportunity buttons. Step 4 must follow the deploy.

## Decision (13 November 2026): keep it simple

No new link or create feature. Linking already exists natively: the
`sale_crm` **Other Info → Opportunity** field on the quotation lets users pick
an existing opportunity in the same company.

Open point: that native field also allows inline **Create** / **Create and
edit** of an opportunity. Doing that creates an `opportunity`-type lead
directly, skipping `_validate_lead_conversion`. If Mobikey wants qualification
enforced for every opportunity, a follow-up could add `no_create` to that field
for quotations. Not changed yet.

## Assessment: creating an opportunity from a quotation

**Recommendation: no free-form "create opportunity" on quotations. Instead,
prevent unlinked quotations, and offer a guarded "link opportunity" action.**

Why unlinked quotations matter in this codebase:

- **Won guard:** `crm.lead._check_confirmed_order_before_won`
  (`mobikey_crm/models/crm_lead.py`) only counts quotations linked through
  `order_ids`. A deal quoted without a link cannot be marked Won from that
  quotation.
- **Forecast:** expected revenue comes from the opportunity's
  `primary_quotation_id` (`mobikey_sale_approvals/models/crm_lead.py`), which
  is set only for linked quotations. Unlinked quotations are missing from the
  pipeline forecast and the dashboards.
- **Financing sync:** `sale.order._mobikey_sync_opportunity_financing`
  (`mobikey_crm/models/sale_order.py`) updates the opportunity only when linked.

Why creating the opportunity from the quotation is a poor fit:

- Mobikey's process is qualify first, then quote. Lead conversion
  (`_validate_lead_conversion`) requires a Qualified status plus vehicle type,
  vehicle condition, customer type, phone, country, team and salesperson. An
  opportunity generated from a quotation would either skip qualification or
  need a duplicate qualification form on the quotation.
- It creates opportunities after the fact, already at quotation stage. That
  distorts stage-duration, lead-source and conversion metrics in
  `docs/CRM_METRIC_DICTIONARY.md`.
- It invites duplicates when the customer already has an open opportunity.

Better options, in order of preference:

1. **Process:** create quotations with the opportunity's **New Quotation**
   button, which is Odoo's normal action and already sets the link.
2. **Guarded link:** on quotations without an opportunity, offer a "Link
   opportunity" action limited to the customer's open opportunities in the
   same company.
3. **Optional enforcement (business decision):** require `opportunity_id`
   before a quotation can be submitted for approval or issued. This blocks
   walk-in or repeat-customer quotes that have no opportunity yet, so confirm
   with Mobikey before adding it.
4. **Existing data:** match the 17 unlinked quotations to opportunities by
   customer and have sales confirm each match before anything is linked.

If Mobikey still wants creation from a quotation, limit it to opening the
standard opportunity form, prefilled with customer, company, team and
salesperson, so the normal qualification fields and rules still apply. Then
link the quotation after the opportunity is saved.
