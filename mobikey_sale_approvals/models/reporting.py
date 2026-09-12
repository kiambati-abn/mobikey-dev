from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class ForecastSnapshot(models.Model):
    _name = 'mobikey.forecast.snapshot'
    _description = 'Daily opportunity forecast'
    _order = 'snapshot_date desc, id desc'

    snapshot_date = fields.Date(required=True, index=True)
    lead_id = fields.Many2one('crm.lead', ondelete='set null', index=True)
    opportunity_name = fields.Char()
    company_id = fields.Many2one('res.company', required=True)
    currency_id = fields.Many2one('res.currency', required=True)
    user_id = fields.Many2one('res.users')
    team_id = fields.Many2one('crm.team')
    stage_name = fields.Char()
    active = fields.Boolean(default=True)
    probability = fields.Float()
    expected_revenue = fields.Monetary()
    weighted_revenue = fields.Monetary()
    expected_close = fields.Date()
    primary_quotation_name = fields.Char()
    quotation_revision = fields.Integer()
    rate_date = fields.Date()
    amount_basis = fields.Char()
    _daily_unique = models.Constraint('UNIQUE(snapshot_date, lead_id)', 'One forecast per opportunity per day.')

    @api.model
    def _cron_snapshot(self):
        today = fields.Date.today()
        existing = self.search([('snapshot_date', '=', today)]).mapped('lead_id').ids
        leads = self.env['crm.lead'].search([('type', '=', 'opportunity'), ('id', 'not in', existing),
                                          ('company_id', '!=', False), ('probability', '<', 100)])
        for lead in leads:
            quote = lead.primary_quotation_id
            self.create({'snapshot_date': today, 'lead_id': lead.id, 'opportunity_name': lead.name,
                'company_id': lead.company_id.id, 'currency_id': lead.company_id.currency_id.id,
                'user_id': lead.user_id.id, 'team_id': lead.team_id.id, 'stage_name': lead.stage_id.name,
                'probability': lead.probability, 'expected_revenue': lead.expected_revenue,
                'weighted_revenue': lead.expected_revenue * lead.probability / 100,
                'expected_close': lead.date_deadline, 'primary_quotation_name': quote.name,
                'quotation_revision': quote.approval_revision,
                'rate_date': fields.Date.to_date(quote.date_order) if quote else today,
                'amount_basis': lead.company_id.mobikey_revenue_basis if quote else 'estimate'})

    def write(self, vals):
        raise AccessError(_('Forecast snapshots are immutable.'))

    def unlink(self):
        raise AccessError(_('Forecast snapshots are retained for historical reporting.'))
