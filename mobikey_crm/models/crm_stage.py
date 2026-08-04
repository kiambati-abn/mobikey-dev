"""Mobikey CRM — crm.stage extension.

Adds ``mobikey_stage_type`` — a stable functional tag that identifies the
pipeline role of each stage independently of its display name.

WHY:
    CRM stage records are M2O and can be freely renamed by any admin.
    Querying by ``name`` (e.g. ``('name', 'ilike', 'Quotation')``) breaks the
    moment someone renames the stage.  Querying by ``mobikey_stage_type`` is
    immune to renames because the tag is set once (via data file or manually)
    and persists regardless of what the stage is called.

USAGE:
    # Find the quotation stage regardless of its display name:
    stage = env['crm.stage'].search([('mobikey_stage_type', '=', 'quotation')], limit=1)
"""

from odoo import fields, models


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    mobikey_stage_type = fields.Selection(
        selection=[
            ('qualified',    'Qualified'),
            ('demo',         'Demo / Visit / Test Drive'),
            ('quotation',    'Quotation'),
            ('negotiation',  'Negotiation'),
            ('booking',      'Booking / Commitment'),
            ('won',          'Won'),
            ('lost',         'Lost'),
        ],
        string="Mobikey Stage Role",
        index=True,
        help=(
            "Functional role of this stage in the Mobikey pipeline.  "
            "Used by all pipeline automation logic.  "
            "This value is NOT affected by renaming the stage — set it once "
            "and never change it unless the stage's business role changes."
        ),
    )
