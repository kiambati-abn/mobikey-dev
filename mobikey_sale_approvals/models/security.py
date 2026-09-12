from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

FINANCIAL = 'mobikey_sale_approvals.group_financial_visibility'


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    standard_price = fields.Float(groups=FINANCIAL)
    target_margin = fields.Float(groups=FINANCIAL)
    mobikey_minimum_margin = fields.Float(
        string='Minimum acceptable margin (%)',
        company_dependent=True,
        default=0.0,
        groups=FINANCIAL,
        help='A positive value triggers Country GM approval when this product line falls below it. Zero disables the product-level rule.',
    )

    @api.constrains('mobikey_minimum_margin')
    def _check_mobikey_minimum_margin(self):
        for product in self:
            if not 0 <= product.mobikey_minimum_margin < 100:
                raise ValidationError(_('Product minimum margin must be between 0% and less than 100%.'))


class ProductProduct(models.Model):
    _inherit = 'product.product'
    standard_price = fields.Float(groups=FINANCIAL)
    avg_cost = fields.Monetary(groups=FINANCIAL)
    total_value = fields.Monetary(groups=FINANCIAL)


class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'
    price = fields.Float(groups=FINANCIAL)


class StockLot(models.Model):
    _inherit = 'stock.lot'
    standard_price = fields.Float(groups=FINANCIAL)
    avg_cost = fields.Monetary(groups=FINANCIAL)
    total_value = fields.Monetary(groups=FINANCIAL)


class StockQuant(models.Model):
    _inherit = 'stock.quant'
    value = fields.Monetary(groups=FINANCIAL, compute_sudo=True)


class StockMove(models.Model):
    _inherit = 'stock.move'
    value = fields.Monetary(groups=FINANCIAL)
    price_unit = fields.Float(groups=FINANCIAL)
    standard_price = fields.Float(groups=FINANCIAL, compute_sudo=True)
    remaining_value = fields.Monetary(groups=FINANCIAL, compute_sudo=True)
    value_manual = fields.Monetary(groups=FINANCIAL, compute_sudo=True)
    value_justification = fields.Text(groups=FINANCIAL, compute_sudo=True)
    value_computed_justification = fields.Text(groups=FINANCIAL, compute_sudo=True)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    purchase_price = fields.Float(groups=FINANCIAL, compute_sudo=True, precompute=False)
    margin = fields.Float(groups=FINANCIAL, compute_sudo=True, precompute=False)
    margin_percent = fields.Float(groups=FINANCIAL, compute_sudo=True, precompute=False)


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    margin = fields.Monetary(groups=FINANCIAL, compute_sudo=True)
    margin_percent = fields.Float(groups=FINANCIAL, compute_sudo=True)


class SaleReport(models.Model):
    _inherit = 'sale.report'
    margin = fields.Float(groups=FINANCIAL)


class CrmLead(models.Model):
    _inherit = 'crm.lead'
    margin = fields.Float(groups=FINANCIAL, copy=False)
    reconditioning_cost = fields.Float(groups=FINANCIAL, copy=False)
    vehicle_source = fields.Char(groups=FINANCIAL, copy=False)


class LegacyLine(models.Model):
    _inherit = 'crm.product.lines'
    margin = fields.Float(groups=FINANCIAL, copy=False)
