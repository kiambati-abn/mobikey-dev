# Mobikey Sale Documents

This Odoo 19 addon adds configurable branded quotation and proforma invoice
layouts while retaining Odoo's normal sales workflow and its standard quotation
templates.

## Administrator setup

1. Install **Mobikey Sale Documents** on the development database.
2. In **Sales > Configuration > Manufacturer Brands**, create each vehicle,
   chassis, or trailer brand and upload its logo.
3. On each product's **Quotation Details** tab, choose its manufacturer brand,
   add ordered specifications, maintain the standard Sales Description used for
   OBS, and configure default warranty terms. The existing product **Model** field
   becomes the characteristics heading. Products with selected variants or ordered
   specifications receive a characteristics block automatically; use **Show
   Detailed Specifications** to force one for any other product.
4. In **Sales > Configuration > Proforma Templates**, create a template for a
   company/branch and configure its dealer logo override, manufacturer-logo
   strategy, visible logo-size choices, color scheme, bank accounts, terms,
   footer, and signatories. Logo sizes are displayed as radio choices in the
   template's **Branding** group. Appearance colors use visual pickers and a live
   palette preview. **Restore Scheme Defaults** returns the selected Mobikey or
   Blue and Green preset to its maintained values.

Only Sales Managers can maintain brands and document templates. Salespeople can
read and select them.

## Salesperson flow

1. Create a quotation and select products as usual.
2. Fill prices, quantities, discounts, payment terms, validity, delivery, and
   any order-specific details.
3. Select **Proforma Template** on the quotation.
4. If product master data changed after the lines were added, use **Refresh Product
   Document Details** while the quotation is still a draft.
5. Use Odoo's normal **Print** or **Send** actions.

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
  Empty draft OBS values fall back to the current product Sales Description; the
  explicit refresh action updates every product snapshot before issue.
- The product Model heading and a variant attribute also named Model are separate;
  both are printed when both are present.
- Every product line with selected variant attributes or ordered specifications
  prints its own characteristics block. The manual product-detail option remains
  an override for model/OBS/warranty-only products. Services and simple extras
  without document details remain identifiable only in the consolidated commercial
  table.
- Delivery terms and the expected delivery date are independent and print together
  when both are populated. Payment details use a readable striped 30/70 layout.
  Bank accounts use a 42/58 bank-information and account-number layout and remain
  grouped by bank and currency without repeating the bank name.
- The report header contains logos only. The document summary lists the reference,
  quotation/proforma date, optional validity date, customer reference, and
  salesperson in that order. Issuer location and legal details are kept in the
  footer rather than repeated beside the document date.
- Dealer and manufacturer logo sizes are selectable on each document template.
  Manufacturer **Automatic** sizing is recommended because it caps and wraps
  mixed-brand headers safely. Compact, Standard, and Large options preserve each
  image's aspect ratio.
- For crisp PDF output, upload tightly cropped transparent PNG artwork without
  empty margins, ideally around 1024 x 300 px for a wide logo. The report never
  stretches or crops the image.
- Printed body text uses a readable 10 pt baseline, borderless two-column product
  characteristics and commercial conditions with faint alternating rows, a shaded
  OBS block, 9 pt terms, and a readable two-line company footer. The footer reserves
  about 20 mm, has a primary-color separator, and keeps page numbering right aligned.
- The Mobikey preset uses dark slate `#323C48` and red `#D32D49`; the previous blue
  `#305496` and green `#A9D08E` palette remains available as an alternative. Primary
  and accent are the only required colors. Blank body, muted, or light-background
  overrides use safe neutral or generated fallbacks, and foreground text is selected
  for contrast on configurable colored backgrounds.
- Major headings are grouped with only their first meaningful content block. This
  prevents orphan headings without forcing long product, commercial, bank, or terms
  sections onto a new page in their entirety.
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

The automated suite renders representative branded quotation and proforma PDFs,
plus the native quotation fallback. Before staging or production rollout, also
render realistic one-, two-, and multi-product documents with long specifications,
commercial descriptions, payment notes, banks, and terms to visually confirm
pagination, footer clearance, logo sizing, fonts, tax localization, and the
configured wkhtmltopdf/Chromium report engine.
