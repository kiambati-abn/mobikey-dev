from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
    mobikey_sm_discount_limit = fields.Float(
        string='Sales Manager discount limit (%)', default=2.0, required=True,
        help='Discounts above 0% and up to this percentage require Sales Manager approval.')
    mobikey_gm_discount_limit = fields.Float(
        string='Country GM discount limit (%)', default=5.0, required=True,
        help='Discounts above the Sales Manager limit and up to this percentage require Country GM approval. Higher discounts require HQ approval.')
    mobikey_minimum_margin = fields.Float(
        string='Minimum acceptable margin (%)', default=20.0, required=True,
        help='Quotation lines below this margin require Country GM commercial review.')
    mobikey_sm_ids = fields.Many2many('res.users', 'mobikey_company_sm_rel', string='Assigned Sales Managers')
    mobikey_gm_ids = fields.Many2many('res.users', 'mobikey_company_gm_rel', string='Assigned Country GMs')
    mobikey_hq_ids = fields.Many2many('res.users', 'mobikey_company_hq_rel', string='Assigned HQ approvers')
    mobikey_finance_ids = fields.Many2many('res.users', 'mobikey_company_finance_rel', string='Assigned Finance approvers')

    @api.constrains('mobikey_sm_discount_limit', 'mobikey_gm_discount_limit',
                    'mobikey_minimum_margin')
    def _check_commercial_thresholds(self):
        for company in self:
            values = (company.mobikey_sm_discount_limit, company.mobikey_gm_discount_limit,
                      company.mobikey_minimum_margin)
            if any(value < 0 or value > 100 for value in values):
                raise ValidationError(_('Discount and margin percentages must be between 0% and 100%.'))
            if company.mobikey_sm_discount_limit > company.mobikey_gm_discount_limit:
                raise ValidationError(_(
                    'The Sales Manager discount limit cannot exceed the Country GM discount limit.'
                ))

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
