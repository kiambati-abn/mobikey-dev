"""Commercial classifications shared with quotation documents."""
from odoo import fields, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    vehicle_condition = fields.Selection(
        selection=[
            ('new', 'New'),
            ('used', 'Used'),
            ('either', 'Either'),
        ],
        string='Vehicle Condition',
    )
    customer_type = fields.Many2one(
        'mobikey.customer.type',
        string="Customer Type",
        tracking=True,
    )

    deal_type = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('financing', 'Financing'),
            ('lease', 'Lease'),
            ('fleet', 'Fleet'),
        ], string="Deal Type")

