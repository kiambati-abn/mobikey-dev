from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.fields import Command


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mobikey_document_template_id = fields.Many2one(
        'mobikey.document.template',
        string='Proforma Template',
        copy=True,
        check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Controls branding and presentation only; it does not replace sales order lines.',
    )
    mobikey_company_partner_id = fields.Many2one(
        'res.partner',
        related='company_id.partner_id',
        string='Company Partner',
    )
    mobikey_delivery_terms = fields.Char(
        string='Delivery Terms',
        copy=True,
        help='Use for promises such as In Stock or Within 3 Months. The commitment date remains available separately.',
    )
    mobikey_terms_html = fields.Html(
        string='Document Terms and Conditions',
        copy=True,
        sanitize=True,
    )
    mobikey_bank_account_ids = fields.Many2many(
        'res.partner.bank',
        'mobikey_sale_order_bank_rel',
        'order_id',
        'bank_account_id',
        string='Payment Bank Accounts',
        copy=True,
    )
    mobikey_brand_ids = fields.Many2many(
        'mobikey.document.brand',
        'mobikey_sale_order_brand_rel',
        'order_id',
        'brand_id',
        string='Manufacturer Logos',
        copy=True,
        help='Used as a manual override or as brands copied from the selected template.',
    )
    mobikey_discount_total = fields.Monetary(
        string='Aggregate Line Discount',
        currency_field='currency_id',
        compute='_compute_mobikey_discount_total',
    )

    @api.depends(
        'order_line.display_type',
        'order_line.product_uom_qty',
        'order_line.price_unit',
        'order_line.discount',
    )
    def _compute_mobikey_discount_total(self):
        for order in self:
            discount_total = sum(
                line.product_uom_qty * line.price_unit * line.discount / 100.0
                for line in order.order_line
                if not line.display_type and line.discount > 0
            )
            order.mobikey_discount_total = order.currency_id.round(discount_total)

    @api.onchange('mobikey_document_template_id')
    def _onchange_mobikey_document_template_id(self):
        for order in self:
            order._apply_mobikey_document_template()

    @api.onchange('company_id')
    def _onchange_mobikey_document_company(self):
        for order in self:
            template = order.mobikey_document_template_id
            if template.company_id and template.company_id != order.company_id:
                order.mobikey_document_template_id = False
                order.mobikey_terms_html = False
                order.mobikey_bank_account_ids = False
                order.mobikey_brand_ids = False

    def _apply_mobikey_document_template(self):
        for order in self:
            template = order.mobikey_document_template_id
            if not template:
                order.mobikey_terms_html = False
                order.mobikey_bank_account_ids = False
                order.mobikey_brand_ids = False
                continue
            order.mobikey_terms_html = template.terms_html
            order.mobikey_bank_account_ids = template.bank_account_ids
            order.mobikey_brand_ids = (
                template.brand_ids if template.brand_source == 'template' else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._set_mobikey_template_defaults(vals)
        return super().create(vals_list)

    def write(self, vals):
        values = dict(vals)
        if 'mobikey_document_template_id' in values:
            self._set_mobikey_template_defaults(values)
        return super().write(values)

    @api.model
    def _set_mobikey_template_defaults(self, vals):
        template_id = vals.get('mobikey_document_template_id')
        if not template_id:
            if 'mobikey_document_template_id' in vals:
                vals.setdefault('mobikey_terms_html', False)
                vals.setdefault('mobikey_bank_account_ids', [Command.clear()])
                vals.setdefault('mobikey_brand_ids', [Command.clear()])
            return
        template = self.env['mobikey.document.template'].browse(template_id).exists()
        if not template:
            return
        vals.setdefault('mobikey_terms_html', template.terms_html)
        vals.setdefault(
            'mobikey_bank_account_ids',
            [Command.set(template.bank_account_ids.ids)],
        )
        brand_ids = template.brand_ids.ids if template.brand_source == 'template' else []
        vals.setdefault('mobikey_brand_ids', [Command.set(brand_ids)])

    @api.constrains(
        'company_id',
        'mobikey_document_template_id',
        'mobikey_bank_account_ids',
    )
    def _check_mobikey_document_company_configuration(self):
        for order in self:
            template = order.mobikey_document_template_id
            if template.company_id and template.company_id != order.company_id:
                raise ValidationError(_(
                    'The selected proforma template belongs to another company or branch.'
                ))
            invalid_accounts = order.mobikey_bank_account_ids.filtered(
                lambda account: account.partner_id != order.company_id.partner_id
            )
            if invalid_accounts:
                raise ValidationError(_(
                    'Every payment bank account must belong to the sales order company or branch.'
                ))

    def _get_mobikey_report_brands(self):
        self.ensure_one()
        template = self.mobikey_document_template_id
        if self.mobikey_brand_ids:
            return self.mobikey_brand_ids.sorted(key=lambda brand: (brand.sequence, brand.id))
        if template.brand_source == 'template':
            return template.brand_ids.sorted(key=lambda brand: (brand.sequence, brand.id))

        brands = self.env['mobikey.document.brand']
        for line in self.order_line.sorted(key=lambda order_line: (order_line.sequence, order_line.id)):
            brand = line.product_id.product_tmpl_id.mobikey_document_brand_id
            if brand and brand not in brands:
                brands |= brand
        return brands.sorted(key=lambda brand: (brand.sequence, brand.id))

    def _get_mobikey_main_product_lines(self):
        self.ensure_one()
        product_lines = self._get_order_lines_to_report().filtered(
            lambda line: not line.display_type and line.product_id
        )
        detailed_lines = product_lines.filtered('mobikey_show_product_details')
        return detailed_lines or product_lines[:1]
