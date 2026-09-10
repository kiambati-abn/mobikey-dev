from odoo import fields, models


class SaleApprovalRequestChanges(models.TransientModel):
    _name = 'mobikey.sale.approval.request.changes'
    _description = 'Request quotation approval changes'

    approval_id = fields.Many2one(
        'mobikey.sale.approval', required=True, readonly=True, ondelete='cascade')
    reason = fields.Text(
        string='Customer-safe explanation', required=True,
        help='Explain what the salesperson should change. Do not include internal costs or margins.')

    def action_confirm(self):
        self.ensure_one()
        return self.approval_id._request_changes(self.reason)
