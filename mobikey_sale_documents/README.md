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
   becomes the characteristics heading. OBS is displayed by default; disable
   **Display OBS by Default** only for products whose Sales Description should not
   appear in quotation and proforma documents.
4. In **Sales > Configuration > Proforma Templates**, create a template for a
   company/branch and configure its dealer logo override, manufacturer-logo
   strategy, visible logo-size choices, color scheme, bank accounts,
   footer, and signatories. Logo sizes are displayed as radio choices in the
   template's **Branding** group. Appearance colors use visual pickers and a live
   palette preview. An optional text watermark can label every page, for example
   **Original**, **Copy**, or **Draft**. **Restore Scheme Defaults** returns the
   selected Mobikey or Blue and Green preset to its maintained values.

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

- Selecting a document template copies its bank accounts, fixed brand choices,
  and optional watermark to the quotation. They remain editable on the draft
  quotation, and later template changes do not alter its watermark.
- Terms and Conditions always use Odoo's native sales-order terms. A selected
  Quotation Template's terms take precedence over company defaults exactly as they
  do in Odoo's standard quotation, and their stored HTML formatting is rendered
  without custom splitting or typography overrides.
- Product specifications, description, and warranty are snapshotted on the sales
  line so later product-master edits do not silently change an issued document.
  Empty draft OBS values fall back to the current product Sales Description; the
  explicit refresh action updates every product snapshot before issue. **Display
  OBS** can be disabled on an individual quotation line without hiding its model,
  specifications, or warranty.
- The product Model heading and a variant attribute also named Model are separate;
  both are printed when both are present.
- Every product line with selected variant attributes, ordered specifications,
  visible OBS, or warranty prints its own characteristics block. Services and
  simple extras without those document details remain identifiable only in the
  consolidated commercial table.
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
  OBS block, native Odoo terms formatting, and a readable two-line company footer.
  The footer reserves 24 mm, places a clear 3.5 mm gap below its primary-color
  separator, and keeps page numbering right aligned.
- The Mobikey preset uses dark slate `#323C48` and red `#D32D49`; the previous blue
  `#305496` and green `#A9D08E` palette remains available as an alternative. Primary
  and accent are the only required colors. Blank body, muted, or light-background
  overrides use safe neutral or generated fallbacks, and foreground text is selected
  for contrast on configurable colored backgrounds.
- Structured section headings are grouped with only their first meaningful content
  block. The short Payment, Delivery and Validity section and commercial totals
  stay together as complete print blocks. Native terms retain Odoo's own flowing
  HTML rather than being split or re-serialized by the branded report, with widow
  and orphan protection for page transitions.
- Optional template watermarks use a restrained diagonal text layer behind the
  body on every page. The setting is snapshotted onto the quotation when the
  template is selected. It applies only to the custom Mobikey layout; native Odoo
  quotations and proformas never receive the watermark.
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

The automated suite exercises the PDF entrypoint for representative branded
quotation and proforma documents plus the native quotation fallback. Odoo test
environments that disable PDF conversion return fully rendered HTML from that
entrypoint; the suite validates that fallback instead. Before staging or production
rollout, also render realistic one-, two-, and multi-product PDFs with long
specifications, commercial descriptions, payment notes, banks, and terms to
visually confirm pagination, footer clearance, logo sizing, fonts, tax localization,
and the configured wkhtmltopdf/Chromium report engine.
