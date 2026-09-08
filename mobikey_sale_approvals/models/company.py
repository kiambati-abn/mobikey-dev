from odoo import fields, models


class Company(models.Model):
    _inherit = 'res.company'

    mobikey_revenue_basis = fields.Selection(
        [('total', 'Including taxes'), ('untaxed', 'Excluding taxes')],
        string='Forecast quotation amount', default='total', required=True)
    mobikey_approval_checkpoint = fields.Selection(
        [('issue', 'Before customer issue and confirmation'), ('confirm', 'Before confirmation')],
        default='issue', required=True)
    mobikey_trade_in_threshold = fields.Monetary(currency_field='currency_id')
    mobikey_trade_in_configured = fields.Boolean(string='Trade-in threshold verified')
    mobikey_trade_in_authority = fields.Selection(
        [('either', 'Country GM or Finance'), ('both', 'Country GM and Finance')],
        default='either', required=True)
    mobikey_commission_milestone = fields.Selection(
        [('confirmation', 'Order confirmation'), ('invoicing', 'Fully invoiced'),
         ('payment', 'Fully paid')], string='Commission eligibility')
    mobikey_approval_days = fields.Integer(default=3, string='Approval due in days')
    mobikey_sm_ids = fields.Many2many('res.users', 'mobikey_company_sm_rel', string='Assigned Sales Managers')
    mobikey_gm_ids = fields.Many2many('res.users', 'mobikey_company_gm_rel', string='Assigned Country GMs')
    mobikey_hq_ids = fields.Many2many('res.users', 'mobikey_company_hq_rel', string='Assigned HQ approvers')
    mobikey_finance_ids = fields.Many2many('res.users', 'mobikey_company_finance_rel', string='Assigned Finance approvers')

    def _mobikey_approvers(self, role):
        self.ensure_one()
        roles = role.split('|')
        users = self.env['res.users']
        groups = {'sm': 'sales_manager', 'gm': 'country_gm', 'hq': 'hq', 'finance': 'finance'}
        for key in roles:
            assigned = self.sudo()[f'mobikey_{key}_ids']
            users |= assigned.filtered(lambda u: u.active and not u.share and self in u.company_ids
                                       and u.has_group(f'mobikey_crm.group_mobikey_{groups[key]}'))
        return users
