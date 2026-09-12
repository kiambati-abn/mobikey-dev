"""Mobikey CRM — Configurable lookup models.

Replaces hard-coded Selection fields on crm.lead (and sale.order) with
proper Many2one relations so the picklist values can be managed at runtime
by administrators via CRM → Configuration menus.

Models
------
mobikey.vehicle.type   →  replaces vehicle_type  (Selection)
mobikey.intended.use   →  replaces intended_use   (Selection)
mobikey.budget.range   →  replaces budget_range   (Selection)
mobikey.customer.type  →  replaces customer_type  (Selection) on crm.lead + sale.order
mobikey.industry.type  →  replaces industry_type  (Selection)
mobikey.preferred.language → configurable customer language list

account.payment.term   →  extended with financing_required Boolean
"""

from odoo import fields, models


class MobikeyVehicleType(models.Model):
    _name = 'mobikey.vehicle.type'
    _description = 'Vehicle Type'
    _order = 'sequence, name'

    name = fields.Char(string='Vehicle Type', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class MobikeyIntendedUse(models.Model):
    _name = 'mobikey.intended.use'
    _description = 'Intended Use'
    _order = 'sequence, name'

    name = fields.Char(string='Intended Use', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class MobikeyBudgetRange(models.Model):
    _name = 'mobikey.budget.range'
    _description = 'Budget Range'
    _order = 'sequence, name'

    name = fields.Char(string='Budget Range', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class MobikeyCustomerType(models.Model):
    _name = 'mobikey.customer.type'
    _description = 'Customer Type'
    _order = 'sequence, name'

    name = fields.Char(string='Customer Type', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class MobikeyIndustryType(models.Model):
    _name = 'mobikey.industry.type'
    _description = 'Industry Type'
    _order = 'sequence, name'

    name = fields.Char(string='Industry Type', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class MobikeyPreferredLanguage(models.Model):
    _name = 'mobikey.preferred.language'
    _description = 'Preferred Language'
    _order = 'sequence, name'

    name = fields.Char(string='Language', required=True, translate=True)
    code = fields.Char(help='Optional short code used for reporting and integrations.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        'The preferred language code must be unique.',
    )


class AccountPaymentTerm(models.Model):
    """Extend account.payment.term with a financing flag.

    When this flag is enabled on a payment term and that term is selected
    on a quotation, the financing approval workflow is triggered.
    """
    _inherit = 'account.payment.term'

    financing_required = fields.Boolean(
        string="Financing Required",
        default=False,
        help="If checked, selecting this payment term on a quotation automatically "
             "triggers the financing approval workflow.",
    )
