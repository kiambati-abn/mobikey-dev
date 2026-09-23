from odoo import fields, models


class Branch(models.Model):
    _name = 'mobikey.branch'
    _description = 'Sales Branch'
    _order = 'name, id'

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company, ondelete='restrict')
    active = fields.Boolean(default=True)


def migrate_legacy_branches(env):
    """Keep historical walk-in assignments, including archived leads; safe to rerun."""
    leads = env['crm.lead'].with_context(active_test=False).search([
        ('branch_id', '=', False), '|', ('walkin_company_id', '!=', False),
        ('walkin_location', '!=', False),
    ])
    branches = env['mobikey.branch'].with_context(active_test=False)
    for lead in leads:
        company = lead.walkin_company_id or lead.walkin_location.company_id or lead.company_id or env.company
        name = lead.walkin_company_id.name or lead.walkin_location.name
        branch = branches.search([('company_id', '=', company.id), ('name', '=', name)], limit=1)
        if not branch:
            branch = branches.create({'name': name, 'company_id': company.id})
        lead.with_context(tracking_disable=True).branch_id = branch
