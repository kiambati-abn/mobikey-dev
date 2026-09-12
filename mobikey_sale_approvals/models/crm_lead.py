from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    primary_quotation_id = fields.Many2one('sale.order', copy=False, check_company=True,
        ondelete='set null', domain="[('opportunity_id', '=', id), ('state', '!=', 'cancel')]",
        tracking=True)
    initial_expected_revenue = fields.Float(string='Manual estimate', copy=False)
    expected_revenue = fields.Float(compute='_compute_quoted_revenue', inverse='_inverse_quoted_revenue',
                                   store=True, readonly=False, compute_sudo=True)
    quotation_revenue_updated_at = fields.Datetime(compute='_compute_quoted_revenue', store=True)
    revenue_quotation_count = fields.Integer(
        string='Quotations in expected revenue', compute='_compute_quoted_revenue', store=True)
    operating_country_id = fields.Many2one(related='company_id.country_id', string='Operating country', store=True)
    first_contact_at = fields.Datetime(readonly=True, copy=False)
    first_qualified_at = fields.Datetime(readonly=True, copy=False)
    qualification_readiness = fields.Text(compute='_compute_qualification_readiness')

    @api.depends('name', 'vehicle_type', 'vehicle_condition', 'customer_type', 'company_id',
                 'team_id', 'user_id', 'phone', 'country_id', 'lead_status')
    def _compute_qualification_readiness(self):
        for lead in self:
            missing = [lead._fields[name].string for name in ('name', 'vehicle_type', 'vehicle_condition',
                'customer_type', 'company_id', 'team_id', 'user_id', 'phone', 'country_id') if not lead[name]]
            if lead.lead_status != 'qualified':
                missing.append(_('Qualified lead status'))
            lead.qualification_readiness = _('Ready to convert') if not missing else _('Still needed: %s', ', '.join(missing))

    @api.depends('order_ids.amount_total', 'order_ids.amount_untaxed', 'order_ids.state',
                 'order_ids.currency_id', 'order_ids.date_order', 'order_ids.approval_date_order',
                 'order_ids.opportunity_id',
                 'company_id.currency_id', 'company_id.mobikey_revenue_basis', 'initial_expected_revenue')
    def _compute_quoted_revenue(self):
        for lead in self:
            quotations = lead.order_ids.filtered(
                lambda quote: quote.state != 'cancel' and quote.opportunity_id == lead
            )
            if quotations:
                lead.expected_revenue = sum(
                    quote.currency_id._convert(
                        quote.amount_total if lead.company_id.mobikey_revenue_basis == 'total'
                        else quote.amount_untaxed,
                        lead.company_id.currency_id,
                        quote.company_id,
                        fields.Date.to_date(quote.approval_date_order or quote.date_order)
                        or fields.Date.context_today(lead),
                    )
                    for quote in quotations
                )
            else:
                lead.expected_revenue = lead.initial_expected_revenue
            lead.revenue_quotation_count = len(quotations)
            lead.quotation_revenue_updated_at = fields.Datetime.now()

    def _inverse_quoted_revenue(self):
        for lead in self:
            if lead.order_ids.filtered(lambda quote: quote.state != 'cancel'):
                raise ValidationError(_('Expected revenue is calculated from the active quotations.'))
            lead.initial_expected_revenue = lead.expected_revenue

    @api.constrains('primary_quotation_id', 'company_id')
    def _check_primary_quotation(self):
        for lead in self:
            if lead.primary_quotation_id and (lead.primary_quotation_id.opportunity_id != lead
                    or lead.primary_quotation_id.state == 'cancel'):
                raise ValidationError(_('Select an active quotation belonging to this opportunity.'))

    def _update_revenues_from_so(self, order):
        # Replace native increase-only, untaxed confirmation update.
        return

    def _prepare_opportunity_quotation_context(self):
        context = super()._prepare_opportunity_quotation_context()
        context.update(default_trade_in=self.trade_in, default_bank_id=self.bank_id.id,
                       default_insurance_required=self.insurance_required,
                       default_after_sales_user_id=self.after_sales_user_id.id)
        # Legacy terms are initial defaults only. The quotation becomes authoritative.
        for source, target in [('payment_terms_type', 'payment_term_id'), ('price_list', 'pricelist_id'),
                               ('delivery_location', 'warehouse_id')]:
            if self[source]:
                context['default_' + target] = self[source].id
        if self.trade_in_valuation:
            context['default_trade_in_valuation'] = self.trade_in_valuation
        if self.expected_delivery_date:
            context['default_commitment_date'] = fields.Datetime.to_datetime(self.expected_delivery_date)
        return context

    def write(self, vals):
        legacy_decisions = {name for name in vals if any(name.endswith(suffix) for suffix in
            ('_approval_status', '_approval_required', '_approved_by', '_approval_date', '_approver_ids'))}
        if legacy_decisions and not self.env.su:
            raise AccessError(_('Historical CRM approval decisions are retained read-only. Use quotation approvals.'))
        if {'first_contact_at', 'first_qualified_at'}.intersection(vals) and not self.env.su:
            raise AccessError(_('Qualification event timestamps are system-managed.'))
        for lead in self:
            updates = dict(vals)
            if vals.get('lead_status') == 'contacted' and not lead.first_contact_at:
                updates['first_contact_at'] = fields.Datetime.now()
            if vals.get('lead_status') == 'qualified' and not lead.first_qualified_at:
                updates['first_qualified_at'] = fields.Datetime.now()
            super(CrmLead, lead).write(updates)
        return True
