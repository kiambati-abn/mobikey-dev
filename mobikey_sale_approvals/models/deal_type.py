from odoo import models, _
from odoo.exceptions import ValidationError


class DealType(models.Model):
    _inherit = 'mobikey.deal.type'

    def _check_historical_usage(self):
        super()._check_historical_usage()
        self.env['mobikey.sale.approval'].flush_model(['financial_snapshot'])
        self.env.cr.execute('''
            SELECT 1 FROM mobikey_sale_approval
            WHERE financial_snapshot #>> '{preview,deal_type}' = ANY(%s)
            LIMIT 1
        ''', [self.mapped('code')])
        if self.env.cr.fetchone():
            raise ValidationError(_('A Deal Type retained in approval history cannot be deleted.'))
