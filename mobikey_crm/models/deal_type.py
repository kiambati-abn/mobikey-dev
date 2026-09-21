"""Configurable labels with stable wire values and financing semantics."""
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


BUILTIN_CODES = {'cash', 'financing', 'lease', 'fleet'}


class DealType(models.Model):
    _name = 'mobikey.deal.type'
    _description = 'Deal Type'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, copy=False, help='Permanent integration code, e.g. corporate_sale.')
    sequence = fields.Integer(default=10)
    _code_unique = models.Constraint('UNIQUE(code)', 'Deal Type codes must be unique.')

    @api.constrains('code')
    def _check_code(self):
        for option in self:
            if not re.fullmatch(r'[a-z][a-z0-9_]*', option.code or ''):
                raise ValidationError(_('Use a lowercase code starting with a letter, with letters, digits or underscores.'))

    @api.model
    def _selection(self):
        # Labels are not confidential; portal/report consumers need the same choices.
        return [(option.code, option.name) for option in self.sudo().search([])]

    def write(self, vals):
        if 'code' in vals and any(option.code != vals['code'] for option in self):
            raise ValidationError(_('A Deal Type code cannot be changed. Rename its label instead.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_referenced(self):
        if any(option.code in BUILTIN_CODES for option in self):
            raise ValidationError(_('Built-in Deal Types cannot be deleted.'))
        for model in ('crm.lead', 'sale.order'):
            if self.env[model].sudo().with_context(active_test=False).search_count([
                ('deal_type', 'in', self.mapped('code')),
            ], limit=1):
                raise ValidationError(_('A Deal Type used by a lead or quotation cannot be deleted.'))
        self._check_historical_usage()

    def _check_historical_usage(self):
        """Extension point for modules retaining independent commercial history."""
