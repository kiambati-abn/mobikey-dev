"""Bounded, administrator-managed CRM grants enforced by global record rules."""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


SCOPES = [
    ('none', 'No grant'),
    ('own', 'Assigned records'),
    ('led', 'Assigned records and teams led'),
    ('member', 'Assigned records and teams joined'),
    ('all', 'All permitted companies'),
]
OPERATIONS = ('read', 'write', 'create', 'unlink', 'reassign')


class CrmAccessPolicy(models.Model):
    _name = 'mobikey.crm.access.policy'
    _description = 'CRM Access Policy'
    _inherit = ['mail.thread']
    _order = 'name, id'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    group_id = fields.Many2one('res.groups', required=True, ondelete='restrict', tracking=True)
    read_scope = fields.Selection(SCOPES, string='View', required=True, default='own', tracking=True)
    write_scope = fields.Selection(SCOPES, string='Edit', required=True, default='own', tracking=True)
    create_scope = fields.Selection(SCOPES, string='Create', required=True, default='own', tracking=True)
    unlink_scope = fields.Selection(SCOPES, string='Delete', required=True, default='own', tracking=True)
    reassign_scope = fields.Selection(SCOPES, string='Reassign', required=True, default='own', tracking=True)

    @api.constrains('read_scope', 'write_scope', 'create_scope', 'unlink_scope', 'reassign_scope')
    def _check_scopes(self):
        for policy in self:
            allowed = {'none', 'own', policy.read_scope} if policy.read_scope != 'none' else {'none'}
            if policy.read_scope == 'all':
                allowed = {key for key, label in SCOPES}
            if any(policy[f'{op}_scope'] not in allowed for op in OPERATIONS[1:]):
                raise ValidationError(_('Modification scopes must be contained in the read scope.'))

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        self.env.registry.clear_cache()
        return result

    def write(self, vals):
        result = super().write(vals)
        self.env.registry.clear_cache()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_audit_history(self):
        raise ValidationError(_('Archive access policies instead of deleting their audit history.'))


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _mobikey_crm_scopes(self, operation):
        self.ensure_one()
        if operation not in OPERATIONS:
            raise ValueError('Unsupported CRM operation')
        if self.share or not self.has_group('base.group_user'):
            return set()
        # Keep an administrator recovery path; company rules still apply.
        if self.has_group('base.group_system'):
            return {'all'}
        policies = self.env['mobikey.crm.access.policy'].sudo().search([
            ('active', '=', True),
            ('group_id', 'in', self.all_group_ids.ids),
        ])
        return set(policies.mapped(f'{operation}_scope')) - {'none'}

    def _mobikey_crm_domain(self, operation):
        scopes = self._mobikey_crm_scopes(operation)
        if 'all' in scopes:
            return [(1, '=', 1)]
        domains = []
        if scopes:
            domains.append(fields.Domain('user_id', '=', self.id))
        if 'led' in scopes:
            domains.append(fields.Domain('team_id.user_id', '=', self.id))
        if 'member' in scopes:
            domains.append(fields.Domain('team_id.member_ids', 'in', [self.id]))
        return list(fields.Domain.OR(domains))

    def _mobikey_crm_related_domain(self, operation, lead_field='lead_id', orphans=False):
        domain = fields.Domain(lead_field, 'any', self._mobikey_crm_domain(operation))
        if orphans and 'all' in self._mobikey_crm_scopes(operation):
            domain |= fields.Domain(lead_field, '=', False)
        return list(domain)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def write(self, vals):
        if not self.env.su and {'user_id', 'team_id'} & vals.keys():
            self.check_access('write')
            changing = self.filtered(lambda lead: any(
                field in vals and lead[field].id != (vals[field] or False)
                for field in ('user_id', 'team_id')
            ))
            domain = self.env.user._mobikey_crm_domain('reassign')
            if changing and len(changing.filtered_domain(domain)) != len(changing):
                raise AccessError(_('Your CRM access policy does not allow reassigning these records.'))
        return super().write(vals)


class CrmProductLines(models.Model):
    _inherit = 'crm.product.lines'

    def write(self, vals):
        if 'lead_id' in vals and not self.env.su:
            self.check_access('write')
            if not vals['lead_id']:
                raise AccessError(_('CRM product lines must remain attached to an accessible lead.'))
            self.env['crm.lead'].browse(vals['lead_id']).check_access('write')
        return super().write(vals)
