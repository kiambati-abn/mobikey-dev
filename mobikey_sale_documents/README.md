# Mobikey Sale Documents

This Odoo 19 addon adds configurable branded quotation and proforma invoice
layouts while retaining Odoo's normal sales workflow and its standard quotation
templates.

## Administrator setup

1. Install **Mobikey Sale Documents** on the development database.
2. In **Sales > Configuration > Manufacturer Brands**, create each vehicle,
   chassis, or trailer brand and upload its logo.
3. On each product's **Quotation Details** tab, choose its manufacturer brand,
   add ordered specifications, a customer-facing description, and warranty.
4. In **Sales > Configuration > Proforma Templates**, create a template for a
   company/branch and configure its dealer logo override, manufacturer-logo
   strategy, colors, bank accounts, terms, footer, and signatories.

Only Sales Managers can maintain brands and document templates. Salespeople can
read and select them.

## Salesperson flow

1. Create a quotation and select products as usual.
2. Fill prices, quantities, discounts, payment terms, validity, delivery, and
   any order-specific details.
3. Select **Proforma Template** on the quotation.
4. Use Odoo's normal **Print** or **Send** actions.

If a Proforma Template is selected, the native quotation or proforma report
action renders the branded document. If it is empty, Odoo renders its unchanged
standard quotation/proforma layout. Odoo's existing **Quotation Template** field
is still available and continues to control order-line presets; it is independent
from this addon’s presentation template.

For mixed-brand orders, choose a template with **Brands from Products**. The
header then shows the distinct brands assigned to the order's products, such as
a lorry chassis manufacturer and a trailer manufacturer. Salespeople can also
override the manufacturer logos on the quotation's **Proforma Details** tab.

## Important behavior

- Selecting a document template copies its terms, bank accounts, and fixed brand
  choices to the quotation. They remain editable on the draft quotation.
- Product specifications, description, and warranty are snapshotted on the sales
  line so later product-master edits do not silently change an issued document.
- The normal Odoo report actions and mail templates are not replaced. Uninstalling
  this addon restores standard rendering without leaving rewritten report actions.
- Bank accounts are restricted to the sales-order company/branch. Templates are
  deliberately company-specific because legal details, payment instructions, and
  signatory authority should not be shared implicitly across companies.
- The first header logo is interpreted as the issuing dealer/company logo, matching
  the supplied samples. If "client logo" means the buying customer's logo, that is
  a different data requirement and should be confirmed before rollout.
- Product details and copied commercial text are stable on the quotation. Branding,
  signatory, and bank master data remain live; the PDF/message attachment produced
  when a document is sent is the authoritative historical artifact.

## Development verification

Run the addon tests in an Odoo 19 development database, for example with the
repository on the addons path:

```text
odoo-bin -d <development_database> -i mobikey_sale_documents --test-enable --stop-after-init
```

Before staging or production rollout, render both quotation and proforma PDFs
with realistic long specifications and terms to confirm pagination, logo sizing,
fonts, tax localization, and the configured wkhtmltopdf/Chromium report engine.
