from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .security import FINANCIAL


class SaleApproval(models.Model):
    _name = 'mobikey.sale.approval'
    _description = 'Quotation approval decision'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'category'
    _order = 'id desc'

    order_id = fields.Many2one('sale.order', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, index=True)
    revision = fields.Integer(required=True)
    category = fields.Selection([('discount', 'Discount'), ('margin', 'Commercial review'),
        ('financing', 'Financing'), ('trade_in', 'Trade-in'), ('trade_in_finance', 'Trade-in finance'),
        ('commission', 'Commission')], required=True)
    authority = fields.Char(required=True)
    financial_snapshot = fields.Json(readonly=True, groups=FINANCIAL,
        help='Immutable commercial and cost inputs captured when this revision was submitted.')
    assigned_user_ids = fields.Many2many('res.users', string='Assigned approvers', readonly=True)
    status = fields.Selection([('pending', 'Pending'), ('approved', 'Approved'),
        ('rejected', 'Changes requested'), ('withdrawn', 'Withdrawn')], default='pending', required=True)
    requested_by = fields.Many2one('res.users', required=True)
    requested_at = fields.Datetime(default=fields.Datetime.now, required=True)
    notified_at = fields.Datetime()
    last_reminded_on = fields.Date()
    decided_by = fields.Many2one('res.users')
    decided_at = fields.Datetime()
    deadline = fields.Date()
    turnaround_hours = fields.Float(compute='_compute_turnaround', store=True)
    change_request = fields.Text(help='Customer-safe explanation; never include costs or margins.')

    _revision_category_unique = models.Constraint('UNIQUE(order_id, revision, category)',
        'Only one decision per quotation revision and category is allowed.')

    @api.depends('requested_at', 'decided_at')
    def _compute_turnaround(self):
        for rec in self:
            rec.turnaround_hours = ((rec.decided_at - rec.requested_at).total_seconds() / 3600
                                    if rec.decided_at else 0)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_('Use Submit for approval on the quotation.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if set(vals) - {'change_request'}:
                raise AccessError(_('Use the approval decision actions.'))
            self._check_decision_authority()
        return super().write(vals)

    def unlink(self):
        raise AccessError(_('Approval history cannot be deleted.'))

    def _check_decision_authority(self):
        for approval in self:
            approval.check_access('read')
            user = self.env.user
            administrator = approval.category == 'commission' and user.has_group('base.group_system')
            if not administrator and (user.share or approval.company_id not in user.company_ids
                    or user not in approval.assigned_user_ids
                    or user not in approval.company_id._mobikey_approvers(approval.authority)):
                raise AccessError(_('You are not an assigned eligible approver for this company.'))
            order = approval.order_id
            if approval.status != 'pending' or approval.revision != order.approval_revision:
                raise UserError(_('This approval is no longer pending for the current revision.'))
            if approval.category == 'commission' and not order._commission_eligible():
                raise UserError(_('The order no longer meets the commission eligibility milestone.'))
            if approval.category != 'commission':
                if not order.approval_submitted or order.sudo().approval_fingerprint != order._commercial_fingerprint():
                    raise UserError(_('The quotation has changed; submit a new revision.'))
                if approval.category == 'margin' and any(a.category == 'discount' and a.status != 'approved'
                                                        for a in order._current_approvals()):
                    raise UserError(_('Resolve discount approval first.'))

    def action_approve(self):
        return self._decide('approved')

    def action_request_changes(self):
        if any(not a.change_request for a in self):
            raise UserError(_('Enter a customer-safe explanation for the requested changes.'))
        return self._decide('rejected')

    def _decide(self, decision):
        self.mapped('order_id')._lock_approval()
        self.invalidate_recordset()
        self._check_decision_authority()
        for approval in self:
            approval.sudo().write({'status': decision, 'decided_by': self.env.uid,
                                   'decided_at': fields.Datetime.now()})
            approval._close_activities()
            approval.order_id._activate_approvals()
            if decision == 'rejected':
                approval._notify_outcome(_('Changes requested. Open the quotation to review the request.'))
            elif approval.category == 'commission':
                approval._notify_outcome(_('Commission approval has been recorded.'))
            elif all(a.status == 'approved' for a in approval.order_id._current_approvals()):
                approval._notify_outcome(_('The quotation is approved and ready for customer issue.'))
        return True

    def _queue_notification(self, users, subject, body):
        """Explicit internal recipients only; no template defaults or followers."""
        self.ensure_one()
        users = users.filtered(lambda u: u.active and not u.share and self.company_id in u.company_ids)
        for user in users:
            self.env['mail.mail'].sudo().create({
                'subject': subject, 'body_html': body,
                'email_from': self.company_id.partner_id.email_formatted or self.env.user.email_formatted,
                'email_to': False, 'email_cc': False,
                'recipient_ids': [(6, 0, [user.partner_id.id])], 'auto_delete': False,
            })

    def _notify_request(self):
        self.ensure_one()
        if self.notified_at:
            return
        for user in self.assigned_user_ids:
            self.sudo().with_context(mail_activity_quick_update=True).activity_schedule('mail.mail_activity_data_todo', user_id=user.id,
                summary=_('Review quotation %s', self.order_id.name), date_deadline=self.deadline,
                note=_('Review the assigned decision in Sales approvals.'))
        url = self.get_base_url() + '/odoo/mobikey.sale.approval/' + str(self.id)
        body = Markup('<p>Quotation %s requires your review.</p><p><a href="%s">Open approval</a></p>') % (self.order_id.name, url)
        self._queue_notification(self.assigned_user_ids, _('Quotation approval request'), body)
        self.sudo().write({'notified_at': fields.Datetime.now()})

    def _notify_outcome(self, text):
        self._queue_notification(self.requested_by | self.order_id.user_id,
            _('Quotation %s: approval update', self.order_id.name), Markup('<p>%s</p>') % text)

    def _close_activities(self):
        # No financial feedback copied to quotation chatter.
        self.sudo().activity_ids.unlink()

    @api.model
    def _cron_remind(self):
        today = fields.Date.today()
        approvals = self.search([('status', '=', 'pending'), ('notified_at', '!=', False),
            ('deadline', '<', today), '|', ('last_reminded_on', '=', False), ('last_reminded_on', '<', today)])
        for approval in approvals:
            approval.order_id._lock_approval()
            approval.invalidate_recordset()
            if approval.status != 'pending' or approval.last_reminded_on == today:
                continue
            users = approval.assigned_user_ids & approval.company_id._mobikey_approvers(approval.authority)
            approval._queue_notification(users, _('Overdue quotation approval'),
                Markup('<p>Quotation %s is awaiting your review in Sales approvals.</p>') % approval.order_id.name)
            approval.sudo().write({'last_reminded_on': today})
