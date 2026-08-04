from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # margin = fields.Float(string='Margin(%)', default=0.0, readonly=True)


