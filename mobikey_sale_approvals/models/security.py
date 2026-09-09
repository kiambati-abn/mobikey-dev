from odoo import fields, models

FINANCIAL = 'mobikey_sale_approvals.group_financial_visibility'


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    standard_price = fields.Float(groups=FINANCIAL)
    target_margin = fields.Float(groups=FINANCIAL)


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
