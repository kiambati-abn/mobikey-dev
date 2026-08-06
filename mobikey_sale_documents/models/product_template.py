from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    mobikey_document_brand_id = fields.Many2one(
        'mobikey.document.brand',
        string='Manufacturer Brand',
        ondelete='restrict',
    )
    mobikey_show_product_details = fields.Boolean(
        string='Show Detailed Specifications',
        help='Force a characteristics block even when the product has no selected variant attributes or ordered specifications.',
    )
    mobikey_quotation_description = fields.Html(
        string='Quotation Description',
        translate=True,
        sanitize=True,
        help='Customer-facing description printed after the product specifications.',
    )
    mobikey_default_warranty = fields.Text(
        string='Default Warranty Terms',
        translate=True,
        help='Default warranty copied to new sales order lines.',
    )
    mobikey_specification_line_ids = fields.One2many(
        'mobikey.product.specification',
        'product_tmpl_id',
        string='Quotation Specifications',
        copy=True,
    )


class MobikeyProductSpecification(models.Model):
    _name = 'mobikey.product.specification'
    _description = 'Product Quotation Specification'
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one(
        'product.template',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Specification', required=True, translate=True)
    value = fields.Text(required=True, translate=True)
    unit = fields.Char(translate=True)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mobikey_show_product_details = fields.Boolean(
        string='Show Product Details',
        compute='_compute_mobikey_product_document_values',
        store=True,
        readonly=False,
        precompute=True,
    )
    mobikey_product_model = fields.Char(
        string='Document Model',
        compute='_compute_mobikey_product_document_values',
        store=True,
        readonly=False,
        precompute=True,
        copy=True,
        help='Product model snapshotted for the document characteristics heading.',
    )
    mobikey_observation = fields.Text(
        string='OBS / Sales Description',
        compute='_compute_mobikey_product_document_values',
        store=True,
        readonly=False,
        precompute=True,
        copy=True,
        help='Product Sales Description snapshotted for the OBS section.',
    )
    mobikey_warranty = fields.Text(
        string='Warranty Terms',
        compute='_compute_mobikey_product_document_values',
        store=True,
        readonly=False,
        precompute=True,
    )
    mobikey_quotation_description = fields.Html(
        string='Quotation Description',
        compute='_compute_mobikey_product_document_values',
        store=True,
        readonly=False,
        precompute=True,
        sanitize=True,
    )
    mobikey_detail_snapshot = fields.Json(
        string='Product Detail Snapshot',
        compute='_compute_mobikey_detail_snapshot',
        store=True,
        readonly=False,
        precompute=True,
        copy=True,
        help='Technical details copied when the product configuration changes, so previously issued documents remain stable.',
    )

    @api.depends('product_id')
    def _compute_mobikey_product_document_values(self):
        for line in self:
            values = line._get_mobikey_product_document_values()
            for field_name, value in values.items():
                line[field_name] = value

    def _get_mobikey_product_document_values(self):
        self.ensure_one()
        template = self.product_id.product_tmpl_id
        return {
            'mobikey_show_product_details': bool(
                template and template.mobikey_show_product_details
            ),
            'mobikey_product_model': (
                template.model or self.product_id.display_name
            ) if template else False,
            'mobikey_observation': template.description_sale if template else False,
            'mobikey_warranty': (
                template.mobikey_default_warranty if template else False
            ),
            'mobikey_quotation_description': (
                template.mobikey_quotation_description if template else False
            ),
        }

    @api.depends(
        'product_id',
        'product_no_variant_attribute_value_ids',
        'product_custom_attribute_value_ids.custom_value',
        'product_custom_attribute_value_ids.custom_product_template_attribute_value_id',
    )
    def _compute_mobikey_detail_snapshot(self):
        for line in self:
            line.mobikey_detail_snapshot = line._get_mobikey_live_details()

    def _get_mobikey_live_details(self):
        """Build the ordered product details to snapshot on the sales line."""
        self.ensure_one()
        if not self.product_id:
            return []

        details = []

        selected_values = (
            self.product_id.product_template_attribute_value_ids
            | self.product_no_variant_attribute_value_ids
        )
        selected_values = selected_values.sorted(
            key=lambda value: (
                value.attribute_line_id.sequence,
                value.attribute_line_id.id,
                value.product_attribute_value_id.sequence,
                value.id,
            )
        )
        for value in selected_values:
            details.append({
                'label': value.attribute_id.name,
                'value': value.name,
            })

        custom_values = self.product_custom_attribute_value_ids.sorted(
            key=lambda value: (
                value.custom_product_template_attribute_value_id.attribute_line_id.sequence,
                value.custom_product_template_attribute_value_id.attribute_line_id.id,
                value.id,
            )
        )
        for custom_value in custom_values:
            template_value = custom_value.custom_product_template_attribute_value_id
            details.append({
                'label': template_value.attribute_id.name,
                'value': custom_value.custom_value,
            })

        specifications = self.product_id.product_tmpl_id.mobikey_specification_line_ids.sorted(
            key=lambda specification: (specification.sequence, specification.id)
        )
        for specification in specifications:
            value = specification.value
            if specification.unit:
                value = f'{value} {specification.unit}'
            details.append({
                'label': specification.name,
                'value': value,
            })

        return details

    def _get_mobikey_detail_rows(self):
        """Return snapshotted attribute/specification pairs in two columns."""
        self.ensure_one()
        details = list(self.mobikey_detail_snapshot or [])
        if not details and self.order_id.state == 'draft':
            details = self._get_mobikey_live_details()

        half = (len(details) + 1) // 2
        return [
            (
                details[index],
                details[index + half] if index + half < len(details) else False,
            )
            for index in range(half)
        ]

    def _get_mobikey_commercial_description(self):
        """Return the identifying first line without the appended Sales Description."""
        self.ensure_one()
        first_line = next(
            (line.strip() for line in (self.name or '').splitlines() if line.strip()),
            False,
        )
        return first_line or self.product_id.display_name

    def _get_mobikey_report_observation(self):
        """Use live product text only while a draft snapshot is still empty."""
        self.ensure_one()
        if self.mobikey_observation:
            return self.mobikey_observation
        if self.order_id.state == 'draft' and self.product_id:
            return self.product_id.product_tmpl_id.description_sale
        return False

    def _has_mobikey_characteristics(self):
        """Whether this line should receive its own characteristics block."""
        self.ensure_one()
        return bool(
            self.mobikey_show_product_details
            or self.mobikey_detail_snapshot
            or (
                self.order_id.state == 'draft'
                and self._get_mobikey_live_details()
            )
        )
