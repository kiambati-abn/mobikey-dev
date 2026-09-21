"""Commercial classifications shared with quotation documents."""
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

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
    financing_required = fields.Boolean(
        string='Financing Required',
        tracking=True,
        help='When enabled, only payment terms configured as Financing Required can be used.',
    )

    def _mobikey_financing_values(self, vals, creating=False):
        self.ensure_one()
        values = dict(vals)
        policy_changed = creating or bool(
            {'deal_type', 'financing_required', 'payment_term_id'} & values.keys()
        )
        if not policy_changed:
            return values
        deal_type = values.get('deal_type', self.deal_type)
        term = (
            self.env['account.payment.term'].browse(values.get('payment_term_id'))
            if 'payment_term_id' in values else self.payment_term_id
        )
        if deal_type == 'financing' or (term and term.financing_required):
            values['financing_required'] = True
        if term and term.financing_required and deal_type in (False, 'cash'):
            values['deal_type'] = 'financing'
        return values

    @api.model_create_multi
    def create(self, vals_list):
        empty = self.new({})
        orders = super().create([
            empty._mobikey_financing_values(vals, creating=True) for vals in vals_list
        ])
        orders._mobikey_sync_opportunity_financing()
        return orders

    def write(self, vals):
        result = True
        for order in self:
            result = super(SaleOrder, order).write(order._mobikey_financing_values(vals)) and result
        self._mobikey_sync_opportunity_financing()
        return result

    def _mobikey_sync_opportunity_financing(self):
        for order in self.filtered(lambda item: item.opportunity_id and item.financing_required):
            lead = order.opportunity_id
            values = {'financing_required': True}
            if order.payment_term_id.financing_required and lead.deal_type in (False, 'cash'):
                values['deal_type'] = 'financing'
            if any(lead[name] != value for name, value in values.items()):
                lead.sudo().write(values)

    @api.onchange('deal_type')
    def _onchange_mobikey_deal_type(self):
        if self.deal_type == 'financing':
            self.financing_required = True
            if self.payment_term_id and not self.payment_term_id.financing_required:
                self.payment_term_id = False
                return {'warning': {
                    'title': _('Financing payment terms required'),
                    'message': _('Select payment terms configured as Financing Required.'),
                }}

    @api.onchange('payment_term_id')
    def _onchange_mobikey_payment_term(self):
        if self.payment_term_id.financing_required:
            self.financing_required = True
            if self.deal_type in (False, 'cash'):
                self.deal_type = 'financing'

    @api.onchange('financing_required')
    def _onchange_mobikey_financing_required(self):
        if self.financing_required and self.payment_term_id and not self.payment_term_id.financing_required:
            self.payment_term_id = False
            return {'warning': {
                'title': _('Financing payment terms required'),
                'message': _('The previous payment terms were removed because they are not enabled for financing.'),
            }}

    @api.constrains('financing_required', 'payment_term_id')
    def _check_mobikey_financing_payment_term(self):
        for order in self:
            if (order.financing_required and order.payment_term_id
                    and not order.payment_term_id.financing_required):
                raise ValidationError(_(
                    'Only payment terms configured as Financing Required can be used on a financing quotation.'
                ))
