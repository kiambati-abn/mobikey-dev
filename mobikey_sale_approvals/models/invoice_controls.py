"""Use accounting creation rights for invoices generated from Sales, too."""
from lxml import etree

from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list') and not self.env['account.move'].has_access('create'):
            # Filter the returned view, not the shared cached architecture. This
            # covers both form buttons and the list's batch invoicing button,
            # including future ACL grants without hard-coding a group list.
            arch = etree.fromstring(result['arch'])
            action_id = str(self.env.ref('sale.action_view_sale_advance_payment_inv').id)
            for button in arch.xpath('//button[@type="action"][@name=$name]', name=action_id):
                button.getparent().remove(button)
            result = dict(result, arch=etree.tostring(arch, encoding='unicode'))
        return result

    def _create_invoices(self, grouped=False, final=False, date=None):
        # Native Sales allows this through sudo even without accounting rights.
        # Check the caller before native invoice/line creation has any effects.
        self.env['account.move'].check_access('create')
        return super()._create_invoices(grouped=grouped, final=final, date=date)


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _create_invoices(self, sale_orders):
        # Down payments bypass sale.order._create_invoices and create directly
        # with sudo, so both wizard routes need this independent entry check.
        self.env['account.move'].check_access('create')
        return super()._create_invoices(sale_orders)


class IrActionsActions(models.Model):
    _inherit = 'ir.actions.actions'

    @api.model
    def get_bindings(self, model_name):
        result = super().get_bindings(model_name)
        if model_name == 'sale.order' and not self.env['account.move'].has_access('create'):
            action_id = self.env.ref('sale.action_view_sale_advance_payment_inv').id
            result = dict(result, action=[
                action for action in result.get('action', []) if action['id'] != action_id
            ])
        return result
