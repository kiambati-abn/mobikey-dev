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
    margin = fields.Float(string='Margin(%)', default=0.0, compute='_compute_margin',store=True)

    @api.depends('product_id','discount')
    def _compute_margin(self):
        for record in self:
            if record.product_id:
                cost_price = record.product_id.standard_price
                selling_price = record.price_unit
                sale_price = selling_price - (selling_price * (record.discount / 100))
                margin =((sale_price - cost_price)/ sale_price) * 100 if cost_price else 100
                record.margin = margin

            else:
                record.margin = 0.0



    @api.onchange('product_id', 'quantity', 'price_unit', 'discount')
    def _onchange_fields(self):
        if not self.sale_order_line_id:
            return
        vals = {}
        if self.product_id:
            vals['product_id'] = self.product_id.id
        if self.quantity:
            vals['product_uom_qty'] = self.quantity
        if self.price_unit:
            vals['price_unit'] = self.price_unit
        if self.discount:
            vals['discount'] = self.discount
        if vals:
            self.sale_order_line_id.write(vals)


