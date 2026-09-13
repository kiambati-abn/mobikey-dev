from odoo import Command, api, fields, models, _
from odoo.exceptions import ValidationError

APPROVER_ASSIGNMENT_FIELDS = (
    'mobikey_sm_ids', 'mobikey_gm_ids', 'mobikey_hq_ids',
    'mobikey_finance_ids', 'mobikey_trade_in_approver_ids',
)


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
        domain="[('share', '=', False), ('company_ids', 'in', [id])]",
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
        help='An overall quotation margin below this value requires Country GM approval followed by HQ approval.')
    mobikey_sm_ids = fields.Many2many(
        'res.users', 'mobikey_company_sm_rel', string='Assigned Sales Managers',
        domain="[('share', '=', False), ('company_ids', 'in', [id])]",
        help='Named approvers take precedence. Leave empty to use eligible Sales Manager users.')
    mobikey_gm_ids = fields.Many2many(
        'res.users', 'mobikey_company_gm_rel', string='Assigned Country GMs',
        domain="[('share', '=', False), ('company_ids', 'in', [id])]",
        help='Named approvers take precedence. Leave empty to use eligible Country GM users.')
    mobikey_hq_ids = fields.Many2many(
        'res.users', 'mobikey_company_hq_rel', string='Assigned HQ approvers',
        domain="[('share', '=', False), ('company_ids', 'in', [id])]",
        help='Named approvers take precedence. Leave empty to use eligible HQ users.')
    mobikey_finance_ids = fields.Many2many(
        'res.users', 'mobikey_company_finance_rel', string='Assigned Finance approvers',
        domain="[('share', '=', False), ('company_ids', 'in', [id])]",
        help='Named approvers take precedence and do not need the Finance access role. '
             'Leave empty to use eligible Finance users.')

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

    @api.constrains(*APPROVER_ASSIGNMENT_FIELDS)
    def _check_assigned_approvers(self):
        for company in self:
            for field_name in APPROVER_ASSIGNMENT_FIELDS:
                invalid = company.with_context(active_test=False)[field_name].filtered(
                    lambda user: not user.active or user.share or company not in user.company_ids
                )
                if invalid:
                    raise ValidationError(_(
                        '%(field)s must contain active internal users with access to %(company)s: '
                        '%(users)s',
                        field=company._fields[field_name].string,
                        company=company.display_name,
                        users=', '.join(invalid.mapped('name')),
                    ))

    def _ensure_assigned_approver_access(self):
        """Named assignments grant only the minimum approval-review access."""
        group = self.env.ref('mobikey_sale_approvals.group_approver', raise_if_not_found=False)
        if group:
            users = self.env['res.users']
            for field_name in APPROVER_ASSIGNMENT_FIELDS:
                users |= self.sudo().mapped(field_name)
            users.write({
                'group_ids': [Command.link(group.id)],
            })

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._ensure_assigned_approver_access()
        return companies

    def write(self, values):
        result = super().write(values)
        if set(APPROVER_ASSIGNMENT_FIELDS).intersection(values):
            self._ensure_assigned_approver_access()
        return result

    def _eligible_internal_approvers(self, users):
        self.ensure_one()
        return users.filtered(
            lambda user: user.active and not user.share and self in user.company_ids
        )

    def _mobikey_approvers(self, role):
        self.ensure_one()
        if role == 'trade_in_pool':
            return self._eligible_internal_approvers(
                self.sudo().mobikey_trade_in_approver_ids
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
            assigned = self.sudo().with_context(active_test=False)[f'mobikey_{key}_ids']
            if assigned:
                users |= self._eligible_internal_approvers(assigned)
                continue
            role_group = self.env.ref(groups[key])
            users |= self.env['res.users'].sudo().search([
                ('group_ids', 'in', [role_group.id]),
                ('active', '=', True),
                ('share', '=', False),
                ('company_ids', 'in', [self.id]),
            ])
        return users
