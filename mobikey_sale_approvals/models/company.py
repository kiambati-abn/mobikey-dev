from odoo import Command, api, fields, models, _
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
        default='either', required=True,
        help='Legacy role-based trade-in policy retained for existing approval history.')
    mobikey_trade_in_approver_ids = fields.Many2many(
        'res.users', 'mobikey_company_trade_in_approver_rel',
        string='Trade-in approvers',
        help='Select one or more named people. Any selected person can approve a new trade-in request.')
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

    @api.constrains('mobikey_trade_in_approver_ids')
    def _check_trade_in_approvers(self):
        for company in self:
            invalid = company.mobikey_trade_in_approver_ids.filtered(
                lambda user: not user.active or user.share or company not in user.company_ids
            )
            if invalid:
                raise ValidationError(_(
                    'Trade-in approvers must be active internal users with access to this company: %s',
                    ', '.join(invalid.mapped('name')),
                ))

    def _ensure_trade_in_approver_access(self):
        """A direct company assignment also grants the minimum approval-menu access."""
        group = self.env.ref('mobikey_sale_approvals.group_approver', raise_if_not_found=False)
        if group:
            self.sudo().mapped('mobikey_trade_in_approver_ids').write({
                'group_ids': [Command.link(group.id)],
            })

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._ensure_trade_in_approver_access()
        return companies

    def write(self, values):
        result = super().write(values)
        if 'mobikey_trade_in_approver_ids' in values:
            self._ensure_trade_in_approver_access()
        return result

    def _mobikey_approvers(self, role):
        self.ensure_one()
        if role == 'trade_in_pool':
            return self.sudo().mobikey_trade_in_approver_ids.filtered(
                lambda user: user.active and not user.share and self in user.company_ids
            )
        roles = role.split('|')
        users = self.env['res.users']
        groups = {
            'sm': 'mobikey_crm.group_mobikey_sales_manager',
            'gm': 'mobikey_crm.group_mobikey_country_gm',
            'hq': 'mobikey_crm.group_mobikey_hq',
            'finance': 'mobikey_crm.group_mobikey_finance',
        }
        for key in roles:
            assigned = self.sudo()[f'mobikey_{key}_ids']
            eligible_assigned = assigned.filtered(
                lambda user: user.active and not user.share and self in user.company_ids
                and user.has_group(groups[key])
            )
            if eligible_assigned:
                users |= eligible_assigned
                continue
            role_group = self.env.ref(groups[key])
            users |= self.env['res.users'].sudo().search([
                ('group_ids', 'in', [role_group.id]),
                ('active', '=', True),
                ('share', '=', False),
                ('company_ids', 'in', [self.id]),
            ])
        return users
