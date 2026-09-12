from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .security import FINANCIAL


class SaleApproval(models.Model):
    _name = 'mobikey.sale.approval'
    _description = 'Quotation approval decision'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'category'
    _order = 'revision desc, sequence asc, id asc'

    order_id = fields.Many2one('sale.order', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, index=True)
    revision = fields.Integer(required=True)
    category = fields.Selection([('discount', 'Discount'), ('margin', 'Commercial review'),
        ('margin_hq', 'Commercial review (HQ)'),
        ('financing', 'Financing'), ('trade_in', 'Trade-in'), ('trade_in_finance', 'Trade-in finance'),
        ('commission', 'Commission')], required=True)
    authority = fields.Char(required=True)
    authority_label = fields.Char(compute='_compute_authority_label', string='Required authority')
    sequence = fields.Integer(string='Step', default=1, required=True, readonly=True, index=True)
    dependency_ids = fields.Many2many(
        'mobikey.sale.approval', 'mobikey_sale_approval_dependency_rel',
        'approval_id', 'dependency_id', string='Prior approvals', readonly=True)
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
    can_decide = fields.Boolean(compute='_compute_can_decide')
    workflow_state = fields.Selection([
        ('queued', 'Queued'), ('active', 'Awaiting decision'), ('approved', 'Approved'),
        ('rejected', 'Changes requested'), ('withdrawn', 'Withdrawn'),
    ], compute='_compute_workflow_state', string='Workflow state')
    preview_summary = fields.Text(
        compute='_compute_preview_summary', compute_sudo=True,
        groups='mobikey_sale_approvals.group_approver')
    margin_preview = fields.Text(
        compute='_compute_preview_summary', compute_sudo=True, groups=FINANCIAL)
    change_request = fields.Text(string='Reason for requested changes',
        help='Customer-safe explanation; never include costs or margins.')

    _revision_category_unique = models.Constraint('UNIQUE(order_id, revision, category)',
        'Only one decision per quotation revision and category is allowed.')

    @api.depends('requested_at', 'decided_at')
    def _compute_turnaround(self):
        for rec in self:
            rec.turnaround_hours = ((rec.decided_at - rec.requested_at).total_seconds() / 3600
                                    if rec.decided_at else 0)

    @api.depends('status', 'notified_at')
    def _compute_workflow_state(self):
        for approval in self:
            approval.workflow_state = (
                approval.status if approval.status != 'pending'
                else 'active' if approval.notified_at else 'queued'
            )

    @api.depends('authority')
    def _compute_authority_label(self):
        labels = {
            'sm': _('Sales Manager'),
            'gm': _('Country GM'),
            'hq': _('HQ'),
            'finance': _('Finance'),
            'gm|hq': _('Country GM or HQ'),
            'trade_in_pool': _('Trade-in approvers'),
        }
        for approval in self:
            approval.authority_label = labels.get(approval.authority, approval.authority)

    @api.depends('category', 'financial_snapshot')
    def _compute_preview_summary(self):
        deal_labels = dict(self.env['sale.order']._fields['deal_type'].selection)
        for approval in self:
            preview = (approval.sudo().financial_snapshot or {}).get('preview', {})
            currency = preview.get('currency') or ''
            common = [
                _('Customer: %s', preview.get('customer') or '-'),
                _('Salesperson: %s', preview.get('salesperson') or '-'),
                _('Quotation total: %(amount).2f %(currency)s',
                  amount=preview.get('amount_total') or 0.0, currency=currency),
            ]
            if approval.category == 'discount':
                discounts = preview.get('discount_lines') or []
                common.extend([
                    _('Maximum line discount: %.2f%%', max(
                        (line.get('discount') or 0.0 for line in discounts), default=0.0)),
                    _('Company limits: Sales Manager %.2f%%; Country GM %.2f%%',
                      preview.get('discount_sm_limit') or 0.0,
                      preview.get('discount_gm_limit') or 0.0),
                ])
            elif approval.category == 'financing':
                common.extend([
                    _('Deal type: %s', deal_labels.get(preview.get('deal_type'), '-') or '-'),
                    _('Payment terms: %s', preview.get('payment_term') or '-'),
                    _('Financing bank: %s', preview.get('bank') or '-'),
                ])
            elif approval.category in ('trade_in', 'trade_in_finance'):
                common.append(_('Trade-in valuation: %(amount).2f %(currency)s',
                                amount=preview.get('trade_in_valuation') or 0.0,
                                currency=currency))
            elif approval.category in ('margin', 'margin_hq'):
                common.append(_('Submitted margin information is shown below.'))
            approval.preview_summary = '\n'.join(common)

            margin = preview.get('margin') or {}
            breached = [line for line in margin.get('lines', []) if line.get('product_breach')]
            margin_lines = [
                _('Overall quotation margin: %(actual).2f%% (company minimum: %(limit).2f%%)',
                  actual=margin.get('overall_margin') or 0.0,
                  limit=margin.get('company_limit') or 0.0),
            ]
            margin_lines.extend(_(
                '%(product)s: %(actual).2f%% margin (product minimum: %(limit).2f%%)',
                product=line.get('product') or '-', actual=line.get('margin') or 0.0,
                limit=line.get('product_limit') or 0.0,
            ) for line in breached)
            if approval.category == 'margin_hq':
                gm = approval.order_id.sudo()._current_approvals().filtered(
                    lambda item: item.category == 'margin'
                )[:1]
                margin_lines.append(_(
                    'Country GM decision: %(status)s%(person)s',
                    status=dict(gm._fields['status'].selection).get(gm.status, gm.status) if gm else _('Pending'),
                    person=_(' by %s', gm.decided_by.display_name) if gm and gm.decided_by else '',
                ))
            approval.margin_preview = '\n'.join(margin_lines) if approval.category in ('margin', 'margin_hq') else False

    @api.depends_context('uid')
    @api.depends('status', 'revision', 'notified_at', 'assigned_user_ids',
                 'dependency_ids.status', 'order_id.approval_revision')
    def _compute_can_decide(self):
        user = self.env.user
        for approval in self:
            administrator = approval.category == 'commission' and user.has_group('base.group_system')
            approval.can_decide = bool(
                approval.status == 'pending'
                and approval.notified_at
                and all(dependency.status == 'approved' for dependency in approval.sudo().dependency_ids)
                and approval.revision == approval.order_id.approval_revision
                and (administrator or (
                    user in approval.assigned_user_ids
                    and user in approval.company_id._mobikey_approvers(approval.authority)
                ))
            )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_('Use Submit for approval on the quotation.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError(_('Use the approval decision actions.'))
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
                if any(dependency.status != 'approved' for dependency in approval.sudo().dependency_ids):
                    raise UserError(_('Complete the prior approval steps first.'))

    def action_approve(self):
        return self._decide('approved')

    def action_request_changes(self):
        self.ensure_one()
        self._check_decision_authority()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Request changes'),
            'res_model': 'mobikey.sale.approval.request.changes',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'mobikey_sale_approvals.approval_request_changes_form'
            ).id,
            'target': 'new',
            'context': {'default_approval_id': self.id},
        }

    def _request_changes(self, reason):
        self.ensure_one()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('Enter a customer-safe explanation for the requested changes.'))
        self._check_decision_authority()
        self.sudo().write({'change_request': reason})
        return self._decide('rejected')

    def _decide(self, decision):
        self.mapped('order_id')._lock_approval()
        self.invalidate_recordset()
        self._check_decision_authority()
        for approval in self:
            approval.sudo().with_context(tracking_disable=True).write({
                'status': decision,
                'decided_by': self.env.uid,
                'decided_at': fields.Datetime.now(),
            })
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

    def _post_approval_update(self, body, author=None):
        """Mirror the durable audit message without sending a second notification."""
        self.ensure_one()
        author = author or self.env.user
        return self.sudo().message_post(
            author_id=author.partner_id.id,
            body=body,
            subtype_xmlid='mail.mt_note',
            notify_skip_followers=True,
        )

    def _post_workflow_update(self, body, users=None, author=None):
        self.ensure_one()
        self._post_approval_update(body, author=author)
        return self._post_order_update(body, users=users, author=author)

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
            '<p>Quotation <strong>%s</strong>, revision %s, step %s, requires %s approval.</p>'
            '<p><strong>Assigned to:</strong> %s</p>'
            '<p><a href="%s">Open approval</a></p>'
        ) % (
            self.order_id.name,
            self.revision,
            self.sequence,
            self._category_label(),
            ', '.join(self.assigned_user_ids.mapped('name')),
            url,
        )
        self._post_workflow_update(body, self.assigned_user_ids, author=self.requested_by)
        self.sudo().write({'notified_at': fields.Datetime.now()})

    def _notify_outcome(self, decision):
        self.ensure_one()
        label = self._category_label()
        if decision == 'rejected':
            body = Markup(
                '<p>%s requested changes for %s approval on quotation <strong>%s</strong>, revision %s.</p>'
                '<p><strong>Reason:</strong> %s</p>'
            ) % (self.decided_by.name, label, self.order_id.name, self.revision, self.change_request)
        else:
            ready = self.category != 'commission' and all(
                approval.status == 'approved' for approval in self.order_id._current_approvals()
            )
            body = Markup(
                '<p>%s approved %s approval for quotation <strong>%s</strong>, revision %s.</p>%s'
            ) % (
                self.decided_by.name,
                label,
                self.order_id.name,
                self.revision,
                Markup('<p>The quotation is ready for customer issue.</p>') if ready else Markup(),
            )
        self._post_workflow_update(body, self.requested_by | self.order_id.user_id)

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
