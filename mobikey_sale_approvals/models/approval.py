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
        ('rejected', 'Changes requested'), ('withdrawn', 'Withdrawn')], default='pending',
        required=True, tracking=True)
    requested_by = fields.Many2one('res.users', required=True)
    requested_at = fields.Datetime(default=fields.Datetime.now, required=True)
    notified_at = fields.Datetime()
    last_reminded_on = fields.Date()
    decided_by = fields.Many2one('res.users')
    decided_at = fields.Datetime()
    deadline = fields.Date()
    turnaround_hours = fields.Float(compute='_compute_turnaround', store=True)
    change_request = fields.Text(string='Reason for requested changes',
        help='Customer-safe explanation; never include costs or margins.')

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
            approval._notify_outcome(decision)
            approval.order_id._activate_approvals()
        return True

    def _notification_users(self, users):
        """Keep workflow notifications inside the active company user population."""
        self.ensure_one()
        return users.filtered(lambda u: u.active and not u.share and self.company_id in u.company_ids)

    def _category_label(self):
        self.ensure_one()
        return dict(self._fields['category'].selection).get(self.category, self.category)

    def _post_order_update(self, body, users=None, author=None):
        """Log on the quotation and notify only named internal users.

        Odoo chooses Inbox or email from each recipient's notification preference.
        """
        self.ensure_one()
        users = self._notification_users(users or self.env['res.users'])
        author = author or self.env.user
        return self.order_id.sudo().message_post(
            author_id=author.partner_id.id,
            body=body,
            partner_ids=users.partner_id.ids,
            subtype_xmlid='mail.mt_note',
            notify_skip_followers=True,
        )

    def _notify_users(self, users, subject, body):
        """Send a preference-aware notification without logging routine reminders."""
        self.ensure_one()
        users = self._notification_users(users)
        if users:
            self.sudo().message_notify(
                subject=subject,
                body=body,
                partner_ids=users.partner_id.ids,
                notify_skip_followers=True,
                model_description=_('Quotation approval'),
            )

    def _notify_request(self):
        self.ensure_one()
        if self.notified_at:
            return
        for user in self.assigned_user_ids:
            self.sudo().with_context(mail_activity_quick_update=True).activity_schedule('mail.mail_activity_data_todo', user_id=user.id,
                summary=_('Review quotation %s', self.order_id.name), date_deadline=self.deadline,
                note=_('Review the assigned decision in Sales approvals.'))
        url = self.get_base_url() + '/odoo/mobikey.sale.approval/' + str(self.id)
        body = Markup(
            '<p>Quotation <strong>%s</strong>, revision %s, requires %s approval.</p>'
            '<p><a href="%s">Open approval</a></p>'
        ) % (self.order_id.name, self.revision, self._category_label(), url)
        self._post_order_update(body, self.assigned_user_ids, author=self.requested_by)
        self.sudo().write({'notified_at': fields.Datetime.now()})

    def _notify_outcome(self, decision):
        self.ensure_one()
        label = self._category_label()
        if decision == 'rejected':
            body = Markup(
                '<p>Changes were requested for %s approval on quotation <strong>%s</strong>, revision %s.</p>'
                '<p><strong>Reason:</strong> %s</p>'
            ) % (label, self.order_id.name, self.revision, self.change_request)
        else:
            ready = self.category != 'commission' and all(
                approval.status == 'approved' for approval in self.order_id._current_approvals()
            )
            body = Markup(
                '<p>%s approval was approved for quotation <strong>%s</strong>, revision %s.</p>%s'
            ) % (
                label,
                self.order_id.name,
                self.revision,
                Markup('<p>The quotation is ready for customer issue.</p>') if ready else Markup(),
            )
        self._post_order_update(body, self.requested_by | self.order_id.user_id)

    def _close_activities(self):
        # Decision details are logged separately using customer-safe wording.
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
            approval._notify_users(users, _('Overdue quotation approval'),
                Markup('<p>Quotation %s is awaiting your review in Sales approvals.</p>') % approval.order_id.name)
            approval.sudo().write({'last_reminded_on': today})
