from odoo import models, fields,api


class CRMProductLines(models.Model):
    _name = 'crm.product.lines'
    _description = 'CRM Product Lines'

    lead_id = fields.Many2one('crm.lead',string='Lead')
    product_id = fields.Many2one('product.product', string='Product', domain=[('type', '!=', 'service')])
    model_id =  fields.Char(string='Model', related='product_id.model')
    category_id =  fields.Many2one( 'product.category', string='Category', related='product_id.categ_id')
    quantity = fields.Integer(string='Quantity', default=1)
    price_unit = fields.Float(string='Unit Price', related='product_id.list_price')
    discount = fields.Float(string='Discount (%)', default=0.0)
    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    margin = fields.Float(string='Margin(%)', default=0.0,store=True)


    # Historical snapshot only; never write through to quotation lines.
