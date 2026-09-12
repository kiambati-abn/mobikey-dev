"""CRM qualification. Legacy commercial columns are retained for migration only.

Stage movement, Won/Lost and quotation creation use native Odoo behaviour.
"""
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

PURCHASE_TIMEFRAME_DAYS = {'immediate': 30, 'short': 60, 'medium': 120, 'long': 180}
APPROVAL_STATUS = [('not_required', 'Not Required'), ('pending', 'Pending'),
                   ('approved', 'Approved'), ('rejected', 'Rejected')]

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    city_region = fields.Char(string="City / Region")

    preferred_language = fields.Selection(
        selection=[('en', 'English'), ('sw', 'Swahili')],
        string="Preferred Language",
        default='en',
        tracking=True,
    )

    customer_type = fields.Many2one(
        'mobikey.customer.type',
        string="Customer Type",
        tracking=True,
    )

    industry_type = fields.Many2one(
        'mobikey.industry.type',
        string="Industry",
    )

    is_fleet_customer = fields.Boolean(string="Fleet Customer")

    vehicle_type = fields.Many2one(
        'mobikey.vehicle.type',
        string="Vehicle Type",
        tracking=True,
    )

    vehicle_condition = fields.Selection(
        selection=[
            ('new', 'New'),
            ('used', 'Used')
        ],
        string="Vehicle Condition",
        default='new'
    )

    intended_use = fields.Many2one(
        'mobikey.intended.use',
        string="Intended Use",
    )

    demo_required = fields.Boolean(string="Demo Required")

    purchase_timeframe = fields.Selection(
        selection=[
            ('immediate', 'Immediate (≤ 1 month)'),
            ('short', '1–3 months'),
            ('medium', '3–6 months'),
            ('long', '> 6 months'),
        ],
        string="Purchase Timeframe",
    )

    financing_required = fields.Boolean(
        string="Financing Required",

        store=True,
        tracking=True,
        help="Automatically set when the selected payment term has 'Financing Required' enabled.",
    )

    trade_in = fields.Boolean(string="Trade-In Available", tracking=True)

    trade_in_valuation = fields.Float(string="Trade-In Valuation")

    budget_range = fields.Many2one(
        'mobikey.budget.range',
        string="Budget Range",
    )

    payment_terms_type = fields.Many2one(
        'account.payment.term',
        string="Legacy Payment Terms",
        copy=False,
        help="Historical compatibility field. Set payment terms on each quotation.",
    )

    expected_delivery_date = fields.Date(string="Expected Delivery Date")

    sales_region = fields.Char(string="Sales Region")

    delivery_location = fields.Many2one('stock.warehouse', string="Delivery Location", domain="[('company_id', '=', company_id)]")

    sub_source = fields.Char(string="Sub-Source / Campaign")

    referral_name = fields.Char(string="Referral Name")

    walkin_location = fields.Many2one(comodel_name="stock.location", string="Walk-in Location / Branch")

    lead_score = fields.Integer(string="Lead Score", default=0, readonly=True)

    lead_status = fields.Selection(
        selection=[
            ('new', 'New'),
            ('contacted', 'Contacted'),
            ('qualified', 'Qualified'),
            ('disqualified', 'Disqualified'),
        ],
        string="Lead Status",
        default='new',
        tracking=True,
        help="Qualification status of the lead. Must reach 'Qualified' before "
             "conversion to opportunity is allowed.",
    )

    disqualification_reason = fields.Selection(
        selection=[
            ('no_budget', 'No budget'),
            ('wrong_product', 'Wrong product'),
            ('financing_impossible', 'Financing impossible'),
            ('not_decision_maker', 'Not decision maker'),
            ('outside_territory', 'Outside territory'),
            ('duplicate', 'Duplicate lead'),
            ('not_serious', 'Not serious'),
        ],
        string="Disqualification Reason",
    )

    disqualification_notes = fields.Text(
        string="Disqualification Notes",
    )

    status_name = fields.Char(related="stage_id.name")

    partner_id = fields.Many2one(
        'res.partner', string='Customer', check_company=True, index=True, tracking=10,
        help="Linked partner (optional). Usually created when converting the lead. You can find a partner by its Name, TIN, Email or Internal Reference.")

    deal_type = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('financing', 'Financing'),
            ('lease', 'Lease'),
            ('fleet', 'Fleet'),
        ], string="Deal Type")

    def _mobikey_financing_values(self, vals, creating=False):
        self.ensure_one()
        values = dict(vals)
        policy_changed = creating or bool({'deal_type', 'financing_required'} & values.keys())
        if not policy_changed:
            return values
        deal_type = values.get('deal_type', self.deal_type)
        if deal_type == 'financing':
            values['financing_required'] = True
        return values

    @api.model_create_multi
    def create(self, vals_list):
        empty = self.new({})
        return super().create([
            empty._mobikey_financing_values(vals, creating=True) for vals in vals_list
        ])

    def write(self, vals):
        result = True
        for lead in self:
            result = super(CrmLead, lead).write(lead._mobikey_financing_values(vals)) and result
        return result

    @api.onchange('deal_type')
    def _onchange_mobikey_deal_type(self):
        if self.deal_type == 'financing':
            self.financing_required = True

    bank_id = fields.Many2one('res.bank', string="Bank")

    price_list = fields.Many2one('product.pricelist', string='Price List')

    discount = fields.Float(string="Discount (%)")

    margin = fields.Float(string="Margin (%)")

    year = fields.Integer(string='Year')

    mileage = fields.Float(string='Mileage(KM/Hr)')

    vehicle_source = fields.Char(string='Vehicle Source')

    reconditioning_cost = fields.Float(string='Reconditioning Cost')

    mobikey_current_stage_type = fields.Selection(
        related='stage_id.mobikey_stage_type',
        string="Current Stage Type",
        store=False,
        readonly=True,
    )

    product_line_ids = fields.One2many('crm.product.lines', 'lead_id', string='Product Lines')

    insurance_required = fields.Boolean(string="Insurance Required")

    warranty_included = fields.Boolean(string="Warranty Included")

    discount_approval_required = fields.Boolean(
        string="Discount Approval Required",

        default=False,
        tracking=True,
        store=True,
        help="Auto-set by the system when a non-zero discount is entered.",
    )

    margin_approval_required = fields.Boolean(
        string='Margin Approval Required',
        default=False,
        # compute='_compute_margin_approval_required',

        store=True,
        help="Auto-set by the system based on margin value.")

    trade_in_approval_required = fields.Boolean(
        string="Trade-In Approval Required",
        default=False,
        readonly=True,
        tracking=True,
        help="Auto-set when Trade-In Available is checked.",
    )

    financing_approval_required = fields.Boolean(
        string="Financing Approval Required",
        default=False,
        readonly=True,
        tracking=True,
        help="Auto-set when Financing Required is checked.",
    )

    discount_approval_status = fields.Selection(
        APPROVAL_STATUS, string="Discount Approval Status",
        default='not_required', readonly=True, tracking=True,
    )

    margin_approval_status = fields.Selection(
        APPROVAL_STATUS, string="Margin Approval Status",
        default='not_required', readonly=True, tracking=True,
    )

    trade_in_approval_status = fields.Selection(
        APPROVAL_STATUS, string="Trade-In Approval Status",
        default='not_required', readonly=True, tracking=True,
    )

    financing_approval_status = fields.Selection(
        APPROVAL_STATUS, string="Financing Approval Status",
        default='not_required', readonly=True, tracking=True,
    )

    discount_approved_by = fields.Many2one(
        'res.users', string="Discount Approved By", readonly=True)

    margin_approved_by = fields.Many2one(
        'res.users', string="Margin Approved By", readonly=True)

    trade_in_approved_by = fields.Many2one(
        'res.users', string="Trade-In Approved By", readonly=True)

    financing_approved_by = fields.Many2one(
        'res.users', string="Financing Approved By", readonly=True)

    discount_approver_ids = fields.Many2many(
        'res.users',
        relation='crm_lead_discount_approver_rel',
        column1='lead_id', column2='user_id',
        string="Discount Approvers",
        readonly=True,

        help="Auto-populated with group members authorised to approve this discount level.",
    )

    margin_approver_ids = fields.Many2many(
        'res.users',
        relation='crm_lead_margin_approver_rel',
        column1='lead_id', column2='user_id',
        # compute='_compute_margin_approval_required',

        string="Margin Approvers",
        readonly=True,
    )

    trade_in_approver_ids = fields.Many2many(
        'res.users',
        relation='crm_lead_trade_in_approver_rel',
        column1='lead_id', column2='user_id',
        string="Trade-In Approvers",
        readonly=True,
    )

    financing_approver_ids = fields.Many2many(
        'res.users',
        relation='crm_lead_financing_approver_rel',
        column1='lead_id', column2='user_id',
        string="Financing Approvers",
        readonly=True,
    )

    discount_approval_date = fields.Datetime(
        string="Discount Approval Date", readonly=True)

    margin_approval_date = fields.Datetime(
        string="Margin Approval Date", readonly=True)

    trade_in_approval_date = fields.Datetime(
        string="Trade-In Approval Date", readonly=True)

    financing_approval_date = fields.Datetime(
        string="Financing Approval Date", readonly=True)

    after_sales_user_id = fields.Many2one('res.users', string='After Sales User',
                                          help="""After Sales Person Used In Pipeline.""")

    commission_approval_status = fields.Selection(
        APPROVAL_STATUS,
        string="Commission Approval Status",
        default='not_required',
        tracking=True,
        readonly=True
    )

    commission_approved_by = fields.Many2one(
        'res.users',
        string="Commission Approved By",
        readonly=True
    )

    commission_approval_date = fields.Datetime(
        string="Commission Approval Date",
        readonly=True
    )

    def _validate_lead_conversion(self, user_ids=False, team_id=False):
        """Validate mandatory prerequisites before lead → opportunity conversion.

        All errors are collected and presented at once so the user can fix
        everything in a single pass rather than hitting errors one by one.

        Raises:
            ValidationError: if any blocker condition is unmet.
        """
        for lead in self:
            errors = []
            if not lead.name:
                errors.append(_("Lead title is required before conversion."))
            if not lead.vehicle_type:
                errors.append(_("Vehicle Type is required before conversion."))
            if not lead.vehicle_condition:
                errors.append(_("Vehicle Condition is required before conversion."))
            if not lead.customer_type:
                errors.append(_("Customer Type is required before conversion."))
            if not lead.company_id:
                errors.append(_("Company is required before conversion."))
            if not lead.team_id and not team_id:
                errors.append(_("Sales Team is required before conversion."))
            if not lead.user_id and not user_ids:
                errors.append(_("Salesperson is required before conversion."))
            if not lead.phone:
                errors.append(_("Phone number is required before conversion."))
            if not lead.country_id:
                errors.append(_("Country (UG / KE / TZ) is required before conversion."))
            if lead.lead_status != 'qualified':
                current_label = dict(
                    lead._fields['lead_status'].selection
                ).get(lead.lead_status, lead.lead_status)
                errors.append(_(
                    "Lead Status must be 'Qualified' before conversion. "
                    "Current status: %(status)s",
                    status=current_label,
                ))

            if errors:
                bullet_list = '\n'.join(f"  • {e}" for e in errors)
                raise ValidationError(_(
                    "Cannot convert lead \"%(name)s\" to opportunity:\n\n%(errors)s",
                    name=lead.name,
                    errors=bullet_list,
                ))

    def _apply_conversion_field_mapping(self):
        for lead in self:
            vals = {}
            customer_name = (
                    lead.partner_id.name or lead.partner_name or lead.contact_name or ''
            )
            vehicle_label = lead.vehicle_type.name if lead.vehicle_type else ''
            if customer_name and vehicle_label:
                vals['name'] = f"{customer_name} – {vehicle_label}"
            if lead.purchase_timeframe and not lead.date_deadline:
                days = PURCHASE_TIMEFRAME_DAYS.get(lead.purchase_timeframe, 90)
                vals['date_deadline'] = (
                        fields.Date.context_today(lead) + timedelta(days=days)
                )
            if vals:
                lead.write(vals)

    def convert_opportunity(self, partner, user_ids=False, team_id=False):
        leads = self.filtered(lambda r: r.type == 'lead')
        if leads:
            leads._validate_lead_conversion(user_ids=user_ids, team_id=team_id)
        result = super().convert_opportunity(
            partner=partner, user_ids=user_ids, team_id=team_id,
        )
        self._apply_conversion_field_mapping()
        return result

    def _prepare_opportunity_quotation_context(self):
        context = super()._prepare_opportunity_quotation_context()

        # add  custom field
        context.update({
            'default_vehicle_condition': self.vehicle_condition,
            'default_customer_type': self.customer_type.id,
            'default_deal_type': self.deal_type,
            'default_financing_required': self.financing_required,

        })

        return context
