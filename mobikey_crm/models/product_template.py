from odoo import  api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    model = fields.Char(string='Model')
    target_margin = fields.Float(string='Target Margin (%)')

