from datetime import timedelta
import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from .security import FINANCIAL

ORDER_TERMS = {'order_line', 'partner_id', 'partner_shipping_id', 'company_id', 'currency_id',
    'pricelist_id', 'payment_term_id', 'date_order', 'validity_date', 'commitment_date',
    'warehouse_id', 'trade_in', 'trade_in_valuation', 'bank_id', 'insurance_required', 'deal_type',
    'mobikey_delivery_terms', 'note'}
LINE_TERMS = {'product_id', 'product_uom_qty', 'product_uom_id', 'price_unit', 'discount',
    'tax_ids', 'purchase_price', 'reconditioning_cost', 'target_margin_snapshot', 'name',
    'mobikey_observation', 'mobikey_warranty', 'mobikey_product_model', 'mobikey_detail_snapshot',
    'mobikey_show_product_details', 'is_downpayment', 'display_type'}
CONTROLLED = {'approval_revision', 'approval_submitted', 'approval_fingerprint',
              'approval_ids', 'handover_created', 'first_issued_at', 'approval_date_order', 'legacy_confirmed_order'}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    approval_revision = fields.Integer(default=1, readonly=True, copy=False)
    approval_submitted = fields.Boolean(readonly=True, copy=False)
    approval_fingerprint = fields.Char(readonly=True, copy=False, groups=FINANCIAL)
    approval_date_order = fields.Datetime(readonly=True, copy=False)
    approval_ids = fields.One2many('mobikey.sale.approval', 'order_id', readonly=True, copy=False)
    approval_status = fields.Selection([('draft', 'Prepare offer'), ('ready', 'Ready to issue'),
        ('pending', 'Approval pending'), ('rejected', 'Changes requested')],
        compute='_compute_approval_status', compute_sudo=True)
    trade_in = fields.Boolean(string='Trade-in included')
    trade_in_valuation = fields.Monetary()
    bank_id = fields.Many2one('res.bank', string='Financing bank')
    insurance_required = fields.Boolean()
    after_sales_user_id = fields.Many2one('res.users', check_company=True,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]")
    handover_created = fields.Boolean(copy=False, readonly=True)
    first_issued_at = fields.Datetime(copy=False, readonly=True)
    legacy_confirmed_order = fields.Boolean(copy=False, readonly=True,
        help='Order was already confirmed at cutover. Historical commitment; no new approval is inferred.')

    def action_import_legacy_products(self):
        self._lock_approval()
        for order in self:
            if order.state != 'draft' or order.approval_submitted or order.order_line:
                raise UserError(_('Legacy products can only be imported into an empty draft quotation.'))
            lead = order.opportunity_id
            if not lead.product_line_ids:
                raise UserError(_('There are no historical CRM product lines to import.'))
            # The user selects the target quotation explicitly; never append duplicates.
            values = {'order_line': [(0, 0, {'product_id': line.product_id.id,
                'product_uom_qty': line.quantity, 'price_unit': line.price_unit, 'discount': line.discount})
                for line in lead.product_line_ids if line.product_id]}
            order.write(values)
            if order.order_line:
                order.order_line[:1].sudo().reconditioning_cost = lead.sudo().reconditioning_cost
        return True

    def copy(self, default=None):
        # copy_data is public/RPC-callable: it must never return financial values
        # to a salesperson. Carry private line costs only after normal ACL-checked
        # duplication has created the new quotation.
        copies = super().copy(default)
        if not default or 'order_line' not in default:
            for source, target in zip(self, copies):
                for old_line, new_line in zip(source._get_copiable_order_lines(), target.order_line):
                    new_line.sudo().write({'reconditioning_cost': old_line.sudo().reconditioning_cost,
                                          'vehicle_source': old_line.sudo().vehicle_source})
        return copies

    def _lock_approval(self):
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM sale_order WHERE id IN %s ORDER BY id FOR UPDATE',
                            [tuple(self.ids)])
        self.invalidate_recordset()

    def _commercial_payload(self):
        self.ensure_one()
        order = self.sudo()
        payload = {name: (order[name].ids if isinstance(order[name], models.BaseModel) else order[name])
                   for name in sorted(ORDER_TERMS - {'order_line'}) if name in order._fields}
        if order.state == 'sale' and order.approval_date_order:
            payload['date_order'] = order.approval_date_order
        payload['lines'] = [{name: (line[name].ids if isinstance(line[name], models.BaseModel) else line[name])
                            for name in sorted(LINE_TERMS) if name in line._fields}
                           for line in order.order_line.filtered(lambda l: not l.is_downpayment).sorted('id')]
        return json.loads(json.dumps(payload, default=str))

    def _commercial_fingerprint(self):
        return hashlib.sha256(json.dumps(self._commercial_payload(), sort_keys=True).encode()).hexdigest()

    def _approval_requirements(self):
        """Return safe category/authority pairs; financial inputs never leave this method."""
        self.ensure_one()
        order = self.sudo().with_company(self.company_id)
        lines = order.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)
        requirements = {}
        discount = max(lines.mapped('discount'), default=0)
        if discount > 0:
            requirements['discount'] = 'sm' if discount <= 2 else 'gm' if discount <= 5 else 'hq'
        for line in lines:
            cost = line.purchase_price * line.product_uom_qty + line.reconditioning_cost
            revenue = line.price_subtotal
            profit = revenue - cost
            margin = 100 * profit / revenue if revenue else 0
            if profit < 0 or margin < line.target_margin_snapshot:
                requirements['margin'] = 'gm'
        if order.payment_term_id.financing_required:
            requirements['financing'] = 'finance'
        if order.trade_in:
            if order.trade_in_valuation <= 0:
                raise ValidationError(_('Enter a positive trade-in valuation.'))
            if not order.company_id.mobikey_trade_in_configured:
                raise UserError(_('An administrator must verify the company trade-in threshold.'))
            value = order.currency_id._convert(order.trade_in_valuation, order.company_id.currency_id,
                                               order.company_id, fields.Date.to_date(order.date_order))
            if value <= order.company_id.mobikey_trade_in_threshold:
                requirements['trade_in'] = 'sm'
            elif order.company_id.mobikey_trade_in_authority == 'both':
                requirements.update(trade_in='gm', trade_in_finance='finance')
            else:
                requirements['trade_in'] = 'gm|finance'
        return requirements

    def _current_approvals(self):
        self.ensure_one()
        return self.sudo().approval_ids.filtered(lambda a: a.revision == self.approval_revision
                    and a.category != 'commission' and a.status != 'withdrawn')

    @api.depends('approval_submitted', 'approval_revision', 'approval_ids.status',
                 'order_line.discount', 'order_line.price_subtotal', 'payment_term_id', 'trade_in')
    def _compute_approval_status(self):
        for order in self:
            approvals = order._current_approvals()
            if not order.approval_submitted:
                try:
                    order.approval_status = 'draft' if order._approval_requirements() else 'ready'
                except (UserError, ValidationError):
                    order.approval_status = 'draft'
            elif any(a.status == 'rejected' for a in approvals):
                order.approval_status = 'rejected'
            elif any(a.status != 'approved' for a in approvals):
                order.approval_status = 'pending'
            else:
                order.approval_status = 'ready'

    def action_submit_approvals(self):
        self._lock_approval()
        for order in self:
            if order.state not in ('draft', 'sent'):
                raise UserError(_('Only quotations can be submitted.'))
            if order.approval_submitted:
                continue
            requirements = order._approval_requirements()
            assignments = {category: order.company_id._mobikey_approvers(role)
                           for category, role in requirements.items()}
            missing = [category for category, users in assignments.items() if not users]
            if missing:
                raise UserError(_('Configure eligible company approvers for: %s', ', '.join(missing)))
            super(SaleOrder, order.sudo()).write({'approval_submitted': True,
                'approval_date_order': order.date_order,
                'approval_fingerprint': order._commercial_fingerprint()})
            for category, role in requirements.items():
                self.env['mobikey.sale.approval'].sudo().create({
                    'order_id': order.id, 'revision': order.approval_revision, 'category': category,
                    'authority': role, 'assigned_user_ids': [(6, 0, assignments[category].ids)],
                    'financial_snapshot': order._commercial_payload(),
                    'requested_by': self.env.uid,
                    'deadline': fields.Date.today() + timedelta(days=max(1, order.company_id.mobikey_approval_days)),
                })
            order._activate_approvals()
        return True

    def _activate_approvals(self):
        for order in self:
            approvals = order._current_approvals()
            discount_pending = any(a.category == 'discount' and a.status != 'approved' for a in approvals)
            for approval in approvals.filtered(lambda a: a.status == 'pending' and not a.notified_at):
                if approval.category != 'margin' or not discount_pending:
                    approval._notify_request()

    def action_revise_quotation(self):
        self._lock_approval()
        for order in self:
            if order.state not in ('draft', 'sent'):
                raise UserError(_('Confirmed orders cannot be revised through quotation approvals.'))
            if order.sudo().transaction_ids.filtered(lambda tx: tx.state in ('pending', 'authorized', 'done')):
                raise UserError(_('Resolve the quotation payment transaction before revising the offer.'))
            order._withdraw_approvals()
            super(SaleOrder, order.sudo()).write({'approval_revision': order.approval_revision + 1,
                'approval_submitted': False, 'approval_fingerprint': False, 'state': 'draft'})
        return True

    def _withdraw_approvals(self):
        for approval in self.sudo().approval_ids.filtered(lambda a: a.status in ('pending', 'approved', 'rejected')):
            # Historical decisions retain their decision-maker and timestamp.
            approval.write({'status': 'withdrawn'})
            approval._close_activities()

    def _check_commercial_approval(self, issue=False):
        for order in self:
            if order.state == 'cancel':
                raise UserError(_('This quotation has been cancelled.'))
            if order.state == 'sale' and order.legacy_confirmed_order:
                continue
            if issue and order.company_id.mobikey_approval_checkpoint != 'issue':
                continue
            requirements = order._approval_requirements()
            if not requirements:
                continue
            approvals = order._current_approvals()
            if (not order.approval_submitted or order.sudo().approval_fingerprint != order._commercial_fingerprint()
                    or set(approvals.mapped('category')) != set(requirements)
                    or any(a.status != 'approved' or a.authority != requirements[a.category] for a in approvals)):
                raise UserError(_('Complete quotation approvals for the current revision before proceeding.'))

    def action_quotation_send(self):
        self._check_commercial_approval(issue=True)
        return super().action_quotation_send()

    def action_confirm(self):
        self._lock_approval()
        self._check_commercial_approval()
        result = super().action_confirm()
        for order in self:
            if order.opportunity_id:
                other = order.opportunity_id.order_ids.filtered(lambda o: o != order and o.state == 'sale')
                if not other:
                    order.opportunity_id.primary_quotation_id = order
            order._create_handover()
            order._ensure_commission_approval()
        return result

    def _commission_eligible(self):
        self.ensure_one()
        milestone = self.company_id.mobikey_commission_milestone
        if not milestone or self.state != 'sale':
            return False
        if milestone == 'confirmation':
            return True
        invoices = self.invoice_ids.filtered(lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted')
        if self.invoice_status != 'invoiced' or not invoices:
            return False
        return milestone == 'invoicing' or all(inv.payment_state == 'paid' for inv in invoices)

    def _ensure_commission_approval(self):
        for order in self:
            if (order.legacy_confirmed_order and order.opportunity_id.primary_quotation_id == order
                    and order.opportunity_id.commission_approval_status == 'approved'):
                continue  # Retained CRM decision is historical evidence, not a new approval.
            if not order._commission_eligible() or order.sudo().approval_ids.filtered(lambda a: a.category == 'commission'):
                continue
            users = order.company_id._mobikey_approvers('gm|hq')
            if not users:
                continue  # Daily retry after the administrator assigns the company approvers.
            approval = self.env['mobikey.sale.approval'].sudo().create({
                'order_id': order.id, 'revision': order.approval_revision,
                'category': 'commission', 'authority': 'gm|hq',
                'assigned_user_ids': [(6, 0, users.ids)], 'requested_by': order.user_id.id or self.env.uid,
                'deadline': fields.Date.today() + timedelta(days=max(1, order.company_id.mobikey_approval_days))})
            approval._notify_request()

    @api.model
    def _cron_commission(self):
        orders = self.search([('state', '=', 'sale'), ('company_id.mobikey_commission_milestone', '!=', False)])
        orders._ensure_commission_approval()

    def _create_handover(self):
        for order in self.filtered(lambda o: not o.handover_created):
            if order.after_sales_user_id:
                order.activity_schedule('mail.mail_activity_data_todo', user_id=order.after_sales_user_id.id,
                    summary=_('Customer handover'), note=_('Coordinate delivery and after-sales support.'))
            if order.user_id:
                days = int(self.env['ir.config_parameter'].sudo().get_param('mobikey_crm.sales_followup_days', 30))
                order.activity_schedule('mail.mail_activity_data_call', user_id=order.user_id.id,
                    summary=_('Post-sale customer follow-up'), date_deadline=fields.Date.today() + timedelta(days=days))
            super(SaleOrder, order.sudo()).write({'handover_created': True})

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('state', 'draft') != 'draft' for vals in vals_list):
            raise UserError(_('Create a draft quotation, then use the normal send or confirmation action.'))
        if any(CONTROLLED.intersection(vals) for vals in vals_list) and not self.env.su:
            raise AccessError(_('Approval control fields are managed by workflow actions.'))
        orders = super().create(vals_list)
        for order in orders:
            super(SaleOrder, order.sudo()).write({'approval_date_order': order.date_order})
            lead = order.opportunity_id
            if lead and not lead.primary_quotation_id and order.state != 'cancel':
                lead.primary_quotation_id = order
        return orders

    def write(self, vals):
        if CONTROLLED.intersection(vals) and not self.env.su:
            raise AccessError(_('Approval control fields are managed by workflow actions.'))
        confirming = vals.get('state') == 'sale' and not (set(vals) - {'state', 'date_order'})
        if ORDER_TERMS.intersection(vals) and not confirming:
            self._lock_approval()
            if any(self.mapped('approval_submitted')):
                raise UserError(_('Use Revise quotation before changing commercial terms.'))
        if vals.get('state') == 'sale':
            self._check_commercial_approval()
        elif vals.get('state') == 'sent':
            self._check_commercial_approval(issue=True)
        if vals.get('state') == 'cancel':
            self._withdraw_approvals()
        previous_leads = self.mapped('opportunity_id')
        result = super().write(vals)
        if 'date_order' in vals and not confirming:
            for order in self.filtered(lambda o: o.state in ('draft', 'sent')):
                super(SaleOrder, order.sudo()).write({'approval_date_order': order.date_order})
        if vals.get('state') in ('sent', 'sale'):
            self._check_commercial_approval(issue=vals['state'] == 'sent')
        if vals.get('state') == 'sent':
            for order in self.filtered(lambda o: not o.first_issued_at):
                super(SaleOrder, order.sudo()).write({'first_issued_at': fields.Datetime.now()})
        if 'opportunity_id' in vals or vals.get('state') == 'cancel':
            for lead in previous_leads:
                if lead.primary_quotation_id in self and (lead.primary_quotation_id.opportunity_id != lead
                                                         or lead.primary_quotation_id.state == 'cancel'):
                    lead.write({'primary_quotation_id': False, 'initial_expected_revenue': 0})
            for order in self.filtered(lambda o: o.state != 'cancel' and o.opportunity_id):
                if not order.opportunity_id.primary_quotation_id:
                    order.opportunity_id.primary_quotation_id = order
        return result

    def unlink(self):
        for order in self:
            if order.opportunity_id.primary_quotation_id == order:
                order.opportunity_id.write({'primary_quotation_id': False, 'initial_expected_revenue': 0})
        return super().unlink()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    reconditioning_cost = fields.Monetary(groups=FINANCIAL, copy=False,
        help='Total additional cost for this line, allocated once (not per unit).')
    target_margin_snapshot = fields.Float(compute='_compute_target_margin_snapshot', store=True,
        readonly=False, precompute=False, compute_sudo=True, groups=FINANCIAL, copy=False)
    vehicle_year = fields.Integer()
    vehicle_mileage = fields.Float(string='Mileage (km / hours)')
    vehicle_source = fields.Char(groups=FINANCIAL, copy=False)

    @api.depends('price_subtotal', 'product_uom_qty', 'purchase_price', 'reconditioning_cost')
    def _compute_margin(self):
        for line in self:
            line.margin = line.price_subtotal - line.purchase_price * line.product_uom_qty - line.reconditioning_cost
            line.margin_percent = line.margin / line.price_subtotal if line.price_subtotal else 0

    @api.depends('product_id')
    def _compute_target_margin_snapshot(self):
        for line in self:
            line.target_margin_snapshot = line.product_id.target_margin

    @api.constrains('discount', 'product_uom_qty', 'reconditioning_cost', 'target_margin_snapshot',
                    'is_downpayment', 'product_id')
    def _check_commercial_values(self):
        for line in self.sudo().filtered(lambda l: not l.display_type):
            if line.is_downpayment and (line.product_id or line.product_uom_qty or line.reconditioning_cost or line.discount):
                raise ValidationError(_('A technical down-payment line cannot contain quoted products, quantities, discounts or costs.'))
            if not 0 <= line.discount <= 100 or line.product_uom_qty < 0 or line.reconditioning_cost < 0:
                raise ValidationError(_('Discount must be 0–100%; quantity and reconditioning cost must be non-negative.'))
            if not 0 <= line.target_margin_snapshot < 100:
                raise ValidationError(_('Target margin must be between 0% and less than 100%.'))

    def _check_editable_revision(self):
        orders = self.filtered(lambda l: not l.is_downpayment).mapped('order_id')
        if orders:
            orders._lock_approval()
        if any(orders.mapped('approval_submitted')):
            raise UserError(_('Use Revise quotation before changing its lines.'))

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env['sale.order'].browse([v['order_id'] for v in vals_list if v.get('order_id')])
        if orders:
            orders._lock_approval()
            technical_only = all(v.get('is_downpayment') and not v.get('product_id')
                and not v.get('product_uom_qty') and not v.get('discount') and not v.get('reconditioning_cost')
                for v in vals_list)
            if any(orders.mapped('approval_submitted')) and not technical_only:
                raise UserError(_('Use Revise quotation before adding lines.'))
        return super().create(vals_list)

    def write(self, vals):
        if 'is_downpayment' in vals and any(line.is_downpayment != vals['is_downpayment'] for line in self):
            raise UserError(_('The technical down-payment marker cannot be changed on an existing line.'))
        if LINE_TERMS.intersection(vals) or 'order_id' in vals:
            self._check_editable_revision()
            if vals.get('order_id'):
                destination = self.env['sale.order'].browse(vals['order_id'])
                destination._lock_approval()
                if destination.approval_submitted:
                    raise UserError(_('The destination quotation is submitted for approval.'))
        return super().write(vals)

    def unlink(self):
        self._check_editable_revision()
        return super().unlink()
