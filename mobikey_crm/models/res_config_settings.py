from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    # ══════════════════════════════════════════════════════════
    #  CRM settings wise follow-up days define
    # ══════════════════════════════════════════════════════════

    sales_followup_days = fields.Integer(
        string="Sales Person Follow-Up Days",
        config_parameter='mobikey_crm.sales_followup_days',
        default=30,  # Default 30 days
    )

    aftersales_followup_days = fields.Integer(
        string="After Sales Person Follow-Up Days",
        config_parameter='mobikey_crm.aftersales_followup_days',
        default=90,  # Default 90 days
    )

    trade_in_threshold = fields.Float(string='Trade-in Threshold', default=0.0,
                                      help='Minimum margin percentage for trade-in approvals.',
                                     config_parameter='crm.lead.trade_in_threshold')