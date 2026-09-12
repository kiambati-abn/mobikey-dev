# Quotation and Proforma Invoice Template Analysis

**Analysis date:** 6 August 2026
**Branch:** `development`
**Scope:** Requirements, sample documents, existing code, and Odoo 19 document architecture
**Change type:** Read-only analysis; no application-code fixes or implementation

**Implementation addendum:** An initial implementation now exists on the
`development` branch in `mobikey_sale_documents`. The analysis below records the
pre-implementation baseline and design decisions; operating instructions and
current limitations are maintained in the addon's `README.md`.

Following the clarified requirement for a simple native workflow, the initial
implementation does not replace Odoo's report actions or email templates. It
conditionally dispatches the native quotation/proforma wrappers to the selected
branded layout and falls back to Odoo's standard layout when no presentation
template is selected.

## Executive summary

The requested quotation and proforma document system is feasible. The recommended solution is a structured, versioned, company-aware QWeb proforma report with a dedicated document-template selector on the sales order.

The immediate objective is not to remediate the wider findings in `MAIN_BRANCH_AUDIT.md`. It is to provide a flexible document layer in which:

- A salesperson selects a document template on a sales order.
- Printing produces the selected branded proforma-invoice format.
- The output uses live sales-order prices, quantities, discounts, taxes, totals, customer information, payment terms, validity, delivery terms, warranties, bank accounts, terms, and signatures.
- Dealer and manufacturer logos are configurable.
- More than one vehicle or manufacturer can appear on the same document.
- Authorized business users can maintain logos and commercial text without editing QWeb or XML.
- The output follows the supplied Excel-derived examples while improving their consistency, maintainability, and presentation.

A proforma should remain based on `sale.order`; it should not create, or present itself as, a posted accounting invoice. Odoo 19 already treats a proforma as a sale-order report rendered using proforma context and a proforma title.

## Supplied-document analysis

The following documents were reviewed visually, including both pages of every PDF:

- `docs/TEMPLATE SDF.pdf`
- `docs/TEMPLATE_HYUNDAI.pdf`
- `docs/TEMPLATE_MAN.pdf`
- `docs/TEMPLATE_FOTON.pdf`

### Shared document structure

The examples generally use the following structure:

1. Dealer and manufacturer branding.
2. Salesperson and customer details.
3. Proforma reference, issue date, and document status.
4. Main-product specifications arranged in two columns.
5. A general product description.
6. Commercial conditions.
7. Totals and VAT.
8. Payment bank accounts.
9. Detailed legal terms.
10. Supplier and customer signature blocks.
11. Issuing-company footer and page numbers.

The MAN document additionally includes financing text, a large branded banner, and marketing photographs.

### Inconsistencies requiring correction

The examples are useful layout references, but they should not be treated as authoritative commercial content:

- Some documents use A4 while others use US Letter.
- The commercial section often states a 15-day validity while the legal clause states 8 days.
- Commercial payment terms can state a 20/80 split while the legal terms state 100% advance.
- A legal clause restricts payment to EUR even on documents denominated in TZS or USD.
- Some payment-condition and warranty fields are blank or contain `0`.
- Dealer names, manufacturer-logo placement, bank lists, company footers, and typography are inconsistent.
- The samples contain spelling mistakes such as “COMERCIAL,” “Acount,” and “Chassi.”
- Some content appears positioned to fit Excel cells rather than to flow naturally as document content.

The replacement must use one authoritative source for each commercial value so that the summary, totals, and contractual clauses cannot contradict one another.

## Recommended Odoo architecture

### Use a custom dynamic QWeb report

The principal output should be a custom QWeb report. QWeb supports variable sales-order data, conditional blocks, repeated products, arbitrary numbers of specifications and manufacturer logos, reusable subtemplates, company-aware fields, translations, and automatic pagination.

Odoo's PDF Quote Builder can be used as an optional complement for marketing covers, brochures, manufacturer material, or static promotional pages. It should not be the primary implementation for this requirement because form-field PDFs are poorly suited to:

- Arbitrary numbers of products and specification rows.
- Dynamic two-column specification sections.
- Multiple manufacturer logos.
- Variable-length contractual conditions.
- Fully dynamic tax and commercial summaries.
- Content that must reflow safely across pages.

### Separate print design from native quotation templates

Add a dedicated field such as `mobikey_document_template_id` to `sale.order` rather than using `sale_order_template_id` as the only print selector.

The responsibilities should be separated as follows:

- `sale_order_template_id`: native Odoo commercial-content template for products, sections, notes, optional products, validity, and native terms.
- `mobikey_document_template_id`: document layout, branding, manufacturer-logo behavior, banks, legal terms, signatory configuration, and optional marketing content.

Native quotation templates can insert or replace commercial content. Using the native field only to select a print design risks modifying or replacing vehicle lines generated from CRM.

If the business insists on a single selector, quotation templates would require an explicit mode such as `layout_only` or `content_and_layout`, together with carefully defined line-merging behavior. A separate document-template field remains the safer recommendation.

### Retain the native proforma workflow

The custom report should use `sale.order` as its source and integrate with Odoo's native proforma behavior:

- Provide a clear **Print Proforma Invoice** action.
- Use the custom report as the attachment produced by **Send PRO-FORMA Invoice**.
- Preserve native customer, currency, pricelist, tax, payment-term, and order calculations.
- Do not generate an `account.move` merely to obtain a proforma layout.

If quotations will also be required later, the same document-template system can render either a Quotation or Proforma title based on the selected action and report context.

## Recommended data mapping

| Requirement | Recommended source |
| --- | --- |
| Dealer logo and legal details | `sale.order.company_id`, with controlled template overrides where required |
| Manufacturer logos | Unique product brands derived from main sales lines, with manual override and ordering |
| Customer details | `partner_id`, invoicing address, delivery address, and customer VAT/TIN |
| True product variants | Selected product-variant attribute values |
| Technical characteristics | Separate ordered product-specification records |
| General product description | Dedicated customer-facing quotation description |
| Quantity, unit price, and line discount | Native `sale.order.line` fields |
| Subtotal, taxes, and grand total | Native Odoo tax totals |
| Payment conditions | Native `payment_term_id` |
| Delivery | Native commitment date plus optional delivery-promise text |
| Proforma validity | Native `validity_date` |
| Warranty | Per-main-product sales-line warranty snapshot |
| Bank details | Selected `res.partner.bank` records scoped to issuer and currency |
| Terms and conditions | Versioned company, branch, or document-template terms |
| Signatories | Access-controlled signatory records and customer signature block |
| Footer | Issuing company or branch legal details and dynamic page numbering |

## Product specifications and variants

Technical specifications should not all be modeled as Odoo product variants.

Attributes such as color, drivetrain, transmission choice, or body configuration may represent genuine sellable variants. Engine specifications, axle ratings, dimensions, fuel capacity, gross weight, emission class, and warranty usually describe a product without creating a separate inventory variant.

Making every specification a variant would create unnecessary product combinations and increase catalog complexity.

The recommended product specification structure is an ordered model containing:

- Product template.
- Optional specification section or category.
- Label.
- Value.
- Unit.
- Sequence.
- Customer-document visibility.

The report should display true selected variant attributes first, followed by the additional ordered technical specifications. The QWeb report can distribute the combined list into two balanced columns while preserving the business-defined sequence.

A dedicated customer-facing description should follow the attributes and specifications. This avoids printing internal sales notes or relying on an unsuitable website description.

## Multiple products and manufacturer brands

The implementation must not assume that exactly one manufacturer logo exists.

For an order containing a lorry chassis and a trailer from different manufacturers:

- Each main product receives its own specification and description block.
- Unique manufacturer brands are collected from the main products.
- One brand can be displayed prominently.
- Multiple brands can be displayed in a compact, wrapping logo row.
- The document template can choose header logos, per-product logos, or both.
- An authorized user can manually add, remove, or reorder displayed brands where automatic derivation is not appropriate.

This avoids creating a separate document template for every possible manufacturer combination.

Sales-order lines should have a clear document role, for example:

- Main vehicle or equipment.
- Accessory or implement.
- Service or fee.
- Commercial adjustment or discount.

This permits specification sections for primary products while retaining every priced item in the commercial table.

## Commercial conditions

### Sales lines and totals

The commercial table should be driven exclusively by `sale.order.line` and native Odoo totals. It should support:

- Line description.
- Quantity and unit of measure.
- Unit price.
- Line discount.
- Taxes.
- Tax-excluded subtotal.
- Tax total.
- Tax-included grand total.
- Currency-aware monetary formatting.
- Sections and notes where appropriate.

The report must not recalculate tax or totals independently from Odoo.

### Aggregate discount

“Aggregate discount” is ambiguous and requires a business decision. It can mean either:

1. A summary showing the combined monetary effect of all existing line discounts; or
2. A true additional order-level percentage or fixed discount.

For the initial document implementation, the safe behavior is to calculate and display a summary of discounts already represented by actual order lines.

Odoo 19 can implement a global discount by inserting a negative order line. However, the native value does not automatically recalculate when products are subsequently added or removed. A new independent order-level commercial discount should not be introduced as part of report formatting without separate approval, tax, accounting, and approval-workflow analysis.

### Payment terms

Use the native `sale.order.payment_term_id`. Native payment terms support installment definitions and printable explanatory text. The custom CRM field `payment_terms_type` is not currently mapped reliably to this sales-order field, so users may initially need to verify or enter the sales-order payment term directly.

### Delivery

The examples use both exact dates and descriptive promises such as “IN STOCK” and “3 Months.” These cannot be represented reliably by one Date field.

Use:

- Native `commitment_date` for a committed calendar date; and
- A controlled delivery-promise text or delivery-term selection for wording such as “In stock” or “Within three months.”

The report should apply a documented precedence rule when both are present.

### Proforma validity

Use the native `validity_date`. A template may define the default number of validity days, after which the sales order stores the resulting date.

Contract terms should reference the stored validity date or calculated duration rather than containing a separately typed number such as “8 days.”

### Warranty

The current CRM only provides a `warranty_included` Boolean, which cannot express “1 year / 2,000 hours” or different warranties for a chassis, body, trailer, and accessory.

Warranty should be stored per main sales-order line, defaulted from the product, and editable before issue. The order line should hold a snapshot so later changes to the product master do not alter an already issued proforma.

## Company, branch, footer, and bank details

### Issuing entity and branch

Odoo 19 supports parent companies and branches with entity-specific addresses and logos. If Mobikey's organizational structure is configured using native Odoo branches, the order's active company or branch should drive:

- Issuer name.
- Address.
- Tax identifiers.
- Logo.
- Contact information.
- Terms.
- Bank accounts.
- Footer.

A warehouse or stock location should not be treated as the legal issuing branch unless the business has explicitly established that mapping.

### Bank accounts

The existing CRM field `bank_id` uses `res.bank`, which identifies a bank institution but does not represent a company's payable account details.

Payment details should use `res.partner.bank` and should be filtered by:

- Issuing company or branch.
- Currency.
- Active status.
- Optional document-template applicability.

The template may select one or several accounts. Account holder, account number, bank name, branch, currency, SWIFT/BIC, and other required routing data should be printed from structured fields rather than a free-text block.

### Footer

The footer should use the legal issuer's information and include dynamic `page / total pages` numbering. A single standard page format should be approved, preferably A4 unless stakeholders require otherwise.

## Signatures

The requirement distinguishes at least three possible concepts:

- Empty supplier and customer signature blocks for wet signing.
- Stored internal signatory names, roles, signature images, and company stamp.
- Odoo portal online signature used by the customer to accept an order.

These are not interchangeable.

The recommended design supports up to two configured supplier signatories plus a customer signature block. Reusable scanned signatures and stamps must have restricted access and must not print before the relevant authorization. Odoo's native customer online signature can remain available for portal acceptance, but it does not replace the need for configurable printed signatory blocks.

## Editable templates and historical integrity

Salespeople should select templates, but template editing should be restricted to a document-template manager or administrator.

Editable configuration should include:

- Dealer-logo override.
- Manufacturer-logo display strategy.
- Colors and typography options.
- Header and footer text.
- Bank accounts.
- Terms and conditions.
- Signatories.
- Optional marketing pages.
- Default validity and warranty wording.

Users should not be expected to edit raw QWeb.

Template editability creates a historical-document risk: changing a logo, bank account, term, or product specification could alter an old proforma when it is reprinted.

The implementation should therefore use one or both of the following:

- Versioned document templates and terms; and
- A commercial snapshot stored on the sales order when the document is issued.

The rendered PDF should also be attached to the sales order when sent, preserving the actual issued artifact.

## Existing repository impact at the time of analysis

At the time of the baseline review, the repository contained no custom sale-order report action, report directory, document-template model, or quotation/proforma QWeb implementation.

Relevant findings include:

- `mobikey_crm/__manifest__.py` does not declare `sale_management` or `stock`, although the module already references related functionality.
- `mobikey_crm/models/sale_order.py` contains only vehicle condition, customer type, deal type, margin-warning behavior, CRM-line linking, and sent-state workflow behavior.
- `mobikey_crm/models/product_template.py` contains only `model` and `target_margin`; it has no active brand or specification structure.
- `mobikey_crm/models/product_brand.py` exists but is not imported by `models/__init__.py`, its view is not loaded by the manifest, and no active product-brand relation is available.
- `mobikey_crm/models/sale_order_line.py` is effectively empty.
- `mobikey_crm/models/crm_lead.py` transfers only product, quantity, unit price, and discount when creating quotation lines.
- CRM payment terms, delivery details, pricelist, bank information, warranty, and other commercial fields are not fully mapped to the sales order.
- `mobikey_crm/views/sale_order_view.xml` merely positions three custom fields beside the native quotation-template selector.

### Recommended module boundary

Implement the document feature as a separate module, tentatively named `mobikey_sale_documents`, instead of placing all functionality inside the existing CRM module.

Likely components are:

- Manifest with explicit Odoo dependencies.
- Document-template and template-version models.
- Manufacturer-brand model and logo configuration.
- Ordered product-specification models.
- Sale-order and sale-order-line document fields.
- Company or branch document settings.
- Access controls and record rules.
- Sales-order and product views.
- QWeb report action, main template, and reusable subtemplates.
- Integration with native Send PRO-FORMA Invoice behavior.
- Report, multi-product, multi-company, tax, currency, and access-control tests.

## Risks and decisions requiring stakeholder confirmation

1. **Meaning of “client logo”:** The analysis interprets this as the Mobikey/dealer or issuing-company logo, because the examples show dealer branding and manufacturer branding rather than the buyer's logo.
2. **Document types:** Confirm whether only proforma invoices are required or whether quotations and proformas must both use this system.
3. **Print selector:** Confirm acceptance of a dedicated Document Template field rather than overloading Odoo's native commercial quotation-template field.
4. **Branch model:** Confirm whether branches are native Odoo company branches, warehouses, or another business structure.
5. **Aggregate discount:** Confirm whether it means a displayed total of existing discounts or a new commercial order-level discount.
6. **Delivery promise:** Define supported choices and how descriptive delivery commitments interact with exact dates.
7. **Signatories:** Define whether the document needs blank signature lines, printed names, scanned signatures, a stamp, two internal signatories, portal acceptance, or a combination.
8. **Terms ownership:** Each legal entity or branch must approve its final terms, tax wording, identifiers, bank accounts, and jurisdiction.
9. **Brand selection:** Confirm whether manufacturer logos should be derived automatically from products, manually selected, or automatically derived with manual override.
10. **Document numbering:** Confirm whether the proforma uses the sales-order reference or requires a distinct controlled number sequence.
11. **Page format:** Approve A4 or another standard; the supplied examples mix A4 and US Letter.
12. **Language:** Confirm whether customer-language translation is required for specifications, descriptions, and terms.

## Known interaction with the existing workflow

The current `sale.order.write()` implementation advances a linked CRM opportunity to Negotiation whenever the sales order enters the `sent` state. Sending the new proforma through Odoo's normal workflow may therefore advance the opportunity even though the wider workflow defects are not being remediated in this phase.

The new report must not imply that pricing, discount, margin, or other approvals have been enforced unless those controls are later remediated separately.

## Recommended delivery sequence

1. Obtain stakeholder decisions for document semantics, branches, discounts, signatures, numbering, and legal content.
2. Confirm the Odoo 19 edition and whether PDF Quote Builder is installed.
3. Define the document-template, brand, specification, bank-selection, and snapshot data models.
4. Implement the QWeb proforma report with reusable header, specification, commercial, terms, signature, and footer subtemplates.
5. Add the Document Template selector and configuration views.
6. Integrate printing and native proforma email attachment generation.
7. Import and clean the approved terms, banks, logos, product descriptions, and specifications.
8. Test single-product, multiple-product, multiple-brand, multi-page, multi-company/branch, multi-currency, tax, discount, and long-content cases.
9. Obtain stakeholder review of rendered PDFs before production promotion.

## Conclusion

The requirement is understood and technically achievable. The preferred result is a structured, versioned QWeb proforma system that:

- Uses a dedicated selectable document template.
- Preserves native Odoo sales-order calculations.
- Separates print design from commercial line templates.
- Supports an arbitrary number of main products and manufacturer brands.
- Distinguishes genuine product variants from ordered technical specifications.
- Uses company- and branch-aware legal details, banks, terms, and footers.
- Supports controlled signatories and optional online acceptance.
- Preserves the exact content of issued documents through snapshots, versions, and stored PDF attachments.

Quotation-template development can proceed on `development` as an isolated document feature, while the broader audit findings remain formally acknowledged and scheduled for later remediation.

## Authoritative Odoo 19 references

- [Quotation templates](https://www.odoo.com/documentation/19.0/applications/sales/sales/sales_quotations/quote_template.html)
- [PDF Quote Builder](https://www.odoo.com/documentation/19.0/applications/sales/sales/sales_quotations/pdf_quote_builder.html)
- [Dynamic PDF fields](https://www.odoo.com/documentation/19.0/applications/sales/sales/sales_quotations/pdf_quote_builder/dynamic_text.html)
- [QWeb reports](https://www.odoo.com/documentation/19.0/developer/reference/backend/reports.html)
- [Odoo 19 sale-order report source](https://github.com/odoo/odoo/blob/19.0/addons/sale/report/ir_actions_report_templates.xml)
- [Product variants](https://www.odoo.com/documentation/19.0/applications/sales/sales/products_prices/products/variants.html)
- [Discounts](https://www.odoo.com/documentation/19.0/applications/sales/sales/products_prices/prices/discounts.html)
- [Payment terms](https://www.odoo.com/documentation/19.0/applications/finance/accounting/customer_invoices/payment_terms.html)
- [Quotation deadlines](https://www.odoo.com/documentation/19.0/applications/sales/sales/sales_quotations/deadline.html)
- [Companies and branches](https://www.odoo.com/documentation/19.0/applications/general/companies.html)
- [Proforma invoices](https://www.odoo.com/documentation/19.0/applications/sales/sales/invoicing/proforma.html)
