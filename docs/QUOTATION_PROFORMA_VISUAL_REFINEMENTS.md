# Quotation and Proforma Visual Refinements

**Recommendation date:** 7 August 2026  
**Branch:** `development`  
**Status:** Agreed recommendations for later implementation  
**Related analysis:** `docs/QUOTATION_PROFORMA_TEMPLATE_ANALYSIS.md`

## Objective

Refine the custom Mobikey quotation and proforma invoice so that it is easy to
read, visually consistent with Mobikey's brand, and reliable when content flows
across multiple PDF pages. The native Odoo quotation must remain available when
no Mobikey document template is selected.

## 1. Template color controls

### Recommended configuration

Primary and accent should be the only required color choices. Advanced colors
may be exposed as optional overrides, but leaving them blank must produce a
complete and readable palette automatically.

The template configuration should provide:

- A visual color picker for each configurable color, using Odoo's `color`
  widget instead of requiring users to type hexadecimal values.
- A color-scheme selection such as **Mobikey Brand**, **Blue and Green**, and
  **Custom**.
- Primary color.
- Accent color.
- Optional body-text color.
- Optional muted-text color.
- Optional light-background color.
- A small palette preview.
- A way to restore the selected scheme's defaults.

Do not provide independent color controls for individual cells. Colors should
be controlled at document-template level so that the report remains consistent.
Each manufacturer-specific template may have its own palette.

### Automatic fallback behavior

When only primary and accent are supplied:

| Document element | Color source |
| --- | --- |
| Section headings, product titles, key totals | Primary |
| Highlights and selected header treatments | Accent |
| Large light panels | Automatically generated accent tint |
| Alternating rows | Automatically generated extra-light accent stripe |
| Body text | Safe neutral fallback, `#222222` |
| Muted text | Safe neutral fallback, `#666666` |
| Necessary separators | Safe light-grey fallback, `#DADBDF` |
| Text on colored backgrounds | Automatically selected black or white based on contrast |

The existing accent-tint and accent-stripe generation should be retained and
extended to any new optional color settings.

### Recommended Mobikey preset

The client's website primarily uses a dark slate and Mobikey red. The preferred
quotation palette is:

- Primary: `#323C48`
- Accent: `#D32D49`
- Body text: `#222222`
- Muted text: `#666666`
- Light background: `#F0F1F3`
- Minimal separator: `#DADBDF`

Red should be used selectively for emphasis. Large areas should use a generated
light tint rather than the full accent color.

The existing `#305496` blue and `#A9D08E` green combination may remain as an
alternative preset. The green is not a principal color on the current Mobikey
website and should not be the default Mobikey brand preset unless the business
confirms a separate brand purpose for it.

## 2. Product characteristics

Product characteristics should retain their borderless two-column arrangement.
They should use faint alternating rows rather than boxes:

- No outer border.
- No vertical borders.
- No border around each characteristic.
- Alternating white and automatically generated accent-stripe backgrounds.
- Sufficient row padding and readable text size.
- Product model remains the title of each product's characteristics block.
- The distinct **Model** variant attribute must still appear in the ordered
  characteristics when present.

Each main product with visible variants or specifications receives its own
characteristics section. All product-characteristic sections appear before the
single combined commercial section.

## 3. Commercial conditions presentation

The commercial section should follow the same calm, faint-row visual language
as the characteristics section. It should remain a semantic table internally
because quantities and financial values require dependable alignment, but it
must not look like a boxed spreadsheet.

Recommended presentation:

- No outer box.
- No vertical borders.
- Alternating white and very light accent-tinted line rows.
- At most a `0.1 mm` light-grey horizontal separator between lines.
- Column headings on a light accent background with primary-colored text.
- Product descriptions left aligned.
- Quantity, unit price, discount, taxes, and amount right aligned.
- Long descriptions wrap without disturbing numeric alignment.
- Section and note lines remain borderless and visually distinct.
- Totals receive a slightly stronger top separator and bold text.
- Native Odoo sales-line values, taxes, currencies, and totals remain the only
  financial source of truth.

## 4. Document reference and dates

Remove the company city from the line before the quotation/proforma date. The
issuing company's location already belongs in the footer and should not be
duplicated in the document information block.

The upper summary should use this order:

1. Reference.
2. Quotation Date or Proforma Date, depending on the report context.
3. Validity Date, when present.
4. Customer Reference and salesperson, where applicable.

The validity date should also remain in the **Payment, Delivery and Validity**
section. This deliberate duplication makes the deadline immediately visible
while keeping the complete commercial conditions together. If no validity date
is set, its summary row must be hidden.

Delivery terms and expected delivery date remain separate values. Neither may
overwrite or suppress the other.

## 5. Section pagination

A section heading must never be left by itself at the bottom of a PDF page.
Odoo's PDF renderer may not reliably honor `page-break-after: avoid` on a
standalone `div`, so the heading must be grouped with the first meaningful
content block.

Create a reusable section-lead pattern that keeps together:

- Product heading and its first characteristic rows.
- Commercial heading and the column header plus first commercial line.
- Payment/Delivery/Validity heading and its first row.
- Bank References heading and the first bank group.
- Terms and Conditions heading and its first paragraph or content block.
- Signatures heading and the signature area.

Only the heading and initial content should be protected from splitting. Do not
prevent an entire large section from breaking across pages, because that would
create excessive blank space. Individual compact bank groups and signature
blocks may remain `page-break-inside: avoid` where they can reasonably fit on one
page.

## 6. Footer visibility and spacing

The footer contains important company and legal information and must be treated
as readable content rather than small decoration.

Recommended footer layout:

- Reserve approximately `20–22 mm` for the footer.
- Maintain approximately `4 mm` of clear space between body content and the
  footer.
- Add one `0.3–0.4 mm` separator line in the primary color across the page.
- Add `2–2.5 mm` padding below the separator.
- Company name: `10.5 pt`, bold.
- Address, telephone, email, tax identifiers, and optional footer note: `10 pt`
  with approximately `1.3` line height.
- Document reference and page numbering: `9.5 pt`, right aligned.
- No surrounding box, cell borders, or vertical rules.
- Use dark neutral text for legibility; do not render the complete footer in the
  accent color.

A concise two-line arrangement is preferred:

```text
MOBIKEY TRUCK & BUS LTD · Nairobi, Kenya · Postal/address information
Telephone · Email · PIN/VAT                         S00022 · Page 1 / 3
```

### Paper-format caution

The custom layout currently dispatches through Odoo's native sales report
action. Changing that action's paper format could also change the retained
default Odoo quotation. Footer margin or paper-format changes must therefore be
tested against both paths and must not unintentionally alter the native layout.

## 7. Verification criteria

Before committing the implementation:

- Render quotation and proforma PDFs with one, two, and several main products.
- Test short and long characteristics, descriptions, payment terms, bank lists,
  and terms and conditions.
- Force every major section to begin near the bottom of a page and verify that
  no heading is orphaned.
- Verify that the footer never overlaps body content and is readable on every
  page.
- Verify the custom Mobikey output when a template is selected.
- Verify the unchanged native Odoo output when no Mobikey template is selected.
- Test primary/accent-only configuration and every preset.
- Test blank optional colors and confirm their fallbacks.
- Test light and dark custom colors and confirm readable foreground contrast.
- Run the module's automated test suite and render representative PDFs before
  committing.

