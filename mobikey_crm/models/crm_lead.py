"""Mobikey CRM — custom fields and conversion logic for crm.lead.

Covers:
    4.2  Pipeline Smart Fields (custom fields on opportunity)
    8.1  Core Lead Fields (extended lead form)
    9.1  Field Mapping on Conversion (auto-computed values)
    9.2  Conversion Blockers (validation before lead → opportunity)
    10.0 Controlled Stage Progression (state-machine pipeline)
"""

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

# ── Lookup tables ──────────────────────────────────────────────

PURCHASE_TIMEFRAME_DAYS = {
    'immediate': 30,  # Immediate  → today + 30 days
    'short': 60,  # 1–3 months → today + 60 days
    'medium': 120,  # 3–6 months → today + 120 days
    'long': 180,  # > 6 months → today + 180 days
}

VEHICLE_TYPE_LABELS = {
    'truck': 'Truck',
    'pickup': 'Pickup',
    'machine': 'Machine',
    'bus': 'Bus',
    'tractor': 'Tractor',
}

APPROVAL_STATUS = [
    ('not_required', 'Not Required'),
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]

# ── Allowed stage transitions ──────────────────────────────────
# Keys = current stage type; values = set of allowed next stage types.
# This is the single source of truth for the state machine.
_ALLOWED_TRANSITIONS = {
    'qualified': {'demo', 'quotation'},  # branching: demo_required decides
    'demo': {'quotation'},
    'quotation': {'negotiation'},
    'negotiation': {'booking'},
    'booking': {'won', 'lost'},
    'won': {'lost'},  # correction: won ↔ lost allowed
    'lost': {'won'},
}


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ══════════════════════════════════════════════════════════
    #  4.2  Pipeline Smart Fields  /  8.1  Core Lead Fields
    # ══════════════════════════════════════════════════════════

    # ── Identification & Location ────────────────────────────

    # mobikey_country_id = fields.Many2one('res.country',
    #                                      string="Country",
    #                                      tracking=True,
    #                                      help="Operating country. Drives company assignment and sales team routing.",
    #                                      )
    city_region = fields.Char(string="City / Region")
    preferred_language = fields.Selection(
        selection=[('en', 'English'), ('sw', 'Swahili')],
        string="Preferred Language",
        default='en',
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
        compute='_compute_financing_required',
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

    # ── Commercial Terms (Smart Fields) ──────────────────────

    payment_terms_type = fields.Many2one(
        'account.payment.term',
        string="Payment Terms",
    )
    expected_delivery_date = fields.Date(string="Expected Delivery Date")
    sales_region = fields.Char(string="Sales Region")
    # delivery_location = fields.Char(string="Delivery Location")
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

    # ── Disqualification ─────────────────────────────────────

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

    ### Commercial Details
    deal_type = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('financing', 'Financing'),
            ('lease', 'Lease'),
            ('fleet', 'Fleet'),
        ], string="Deal Type")
    bank_id = fields.Many2one('res.bank', string="Bank")
    expected_revenue = fields.Float(
        string="Expected Revenue",
        compute='_compute_expected_revenue',
        readonly=True,
        help="Auto-computed as the sum of (unit price × quantity × (1 − discount %)) "
             "across all product lines.",
    )
    # expected_revenue = fields.Float(string="Expected Revenue")
    price_list = fields.Many2one('product.pricelist', string='Price List')
    discount = fields.Float(string="Discount (%)")
    margin = fields.Float(string="Margin (%)")
    year = fields.Integer(string='Year')
    mileage = fields.Float(string='Mileage(KM/Hr)')
    vehicle_source = fields.Char(string='Vehicle Source')
    reconditioning_cost = fields.Float(string='Reconditioning Cost')

    # ── Stage type mirror — used in view invisible= expressions ──────────
    # This field reflects stage_id.mobikey_stage_type onto the lead record.
    # Visibility of all header buttons is driven by this field, NOT by
    # stage_id.name — making buttons immune to stage renames.
    mobikey_current_stage_type = fields.Selection(
        related='stage_id.mobikey_stage_type',
        string="Current Stage Type",
        store=False,
        readonly=True,
    )
    product_line_ids = fields.One2many('crm.product.lines', 'lead_id', string='Product Lines')

    insurance_required = fields.Boolean(string="Insurance Required")
    warranty_included = fields.Boolean(string="Warranty Included")

    # ══════════════════════════════════════════════════════════
    #  APPROVAL WORKFLOW — Required Flags (system-managed)
    # ══════════════════════════════════════════════════════════

    discount_approval_required = fields.Boolean(
        string="Discount Approval Required",
        compute='_compute_approval_required',
        default=False,
        tracking=True,
        store=True,
        help="Auto-set by the system when a non-zero discount is entered.",
    )
    margin_approval_required = fields.Boolean(
        string='Margin Approval Required',
        default=False,
        # compute='_compute_margin_approval_required',
        compute='_compute_approval_required',
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

    # ── Approval Status ───────────────────────────────────────

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

    # ── Approved By ───────────────────────────────────────────

    discount_approved_by = fields.Many2one(
        'res.users', string="Discount Approved By", readonly=True)
    margin_approved_by = fields.Many2one(
        'res.users', string="Margin Approved By", readonly=True)
    trade_in_approved_by = fields.Many2one(
        'res.users', string="Trade-In Approved By", readonly=True)
    financing_approved_by = fields.Many2one(
        'res.users', string="Financing Approved By", readonly=True)

    # ── Approver Ids (M2M) ────────────────────────────────────
    # Explicit relation table names to avoid ORM naming collisions.

    discount_approver_ids = fields.Many2many(
        'res.users',
        relation='crm_lead_discount_approver_rel',
        column1='lead_id', column2='user_id',
        string="Discount Approvers",
        readonly=True,
        compute='_compute_approval_required',
        help="Auto-populated with group members authorised to approve this discount level.",
    )
    margin_approver_ids = fields.Many2many(
        'res.users',
        relation='crm_lead_margin_approver_rel',
        column1='lead_id', column2='user_id',
        # compute='_compute_margin_approval_required',
        compute='_compute_approval_required',
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

    # ── Approval Date ─────────────────────────────────────────

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


    #-----------------------------commission approval flow----------------------

    # ─────────────────────────────────────────────
    # Commission Approval (Post-WON)
    # ─────────────────────────────────────────────

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

    # commission_director_status = fields.Selection(
    #     APPROVAL_STATUS,
    #     string="Finance Approval (Country Director)",
    #     default='not_required',
    #     tracking=True,
    #     readonly=True
    # )

    # commission_director_approved_by = fields.Many2one(
    #     'res.users',
    #     string="Director Approved By",
    #     readonly=True
    # )

    # commission_director_approval_date = fields.Datetime(
    #     string="Director Approval Date",
    #     readonly=True
    # )

    @api.depends('payment_terms_type', 'payment_terms_type.financing_required')
    def _compute_financing_required(self):
        """Mirror the financing_required flag from the selected payment term."""
        for rec in self:
            rec.financing_required = bool(
                rec.payment_terms_type and rec.payment_terms_type.financing_required
            )

    @api.depends(
        'product_line_ids.price_unit',
        'product_line_ids.quantity',
        'product_line_ids.discount',
        'product_line_ids.product_id.list_price',
        'product_line_ids.product_id.standard_price',
        'product_line_ids.product_id.target_margin',
    )

    @api.depends('product_line_ids.price_unit', 'product_line_ids.quantity', 'product_line_ids.discount')
    def _compute_expected_revenue(self):
        """Auto-compute expected revenue from product lines.

        Formula: Σ (price_unit × quantity × (1 − discount / 100))
        Dependencies on standard_price and target_margin ensure the field
        recomputes when product cost or target margin is updated.
        """
        for rec in self:
            rev = 0
            if rec.product_line_ids:
                existing_sale_order = self.env['sale.order'].search([('opportunity_id','=',rec.id),('state','!=','cancel')], limit=1)
                rec.expected_revenue = existing_sale_order.amount_total if existing_sale_order else 0
            else:
                rec.expected_revenue = 0

            # for line in rec.product_line_ids:
            #     sale_price = line.price_unit - (line.price_unit * (line.discount / 100.0))
            #     profit_price = sale_price - line.product_id.standard_price
            #     rev += line.quantity * profit_price
            # rec.expected_revenue = rev
            # rec.expected_revenue = sum(
            #     line.price_unit * line.quantity * (1.0 - line.discount / 100.0)
            #     for line in rec.product_line_ids
            # )

    @api.depends('product_line_ids.margin','product_line_ids.discount', 'product_line_ids.product_id.target_margin')
    def _compute_approval_required(self):

        group_hq = self.env.ref('mobikey_crm.group_mobikey_hq', raise_if_not_found=False)
        group_finance = self.env.ref('mobikey_crm.group_mobikey_finance', raise_if_not_found=False)
        group_cd = self.env.ref('mobikey_crm.group_mobikey_country_director', raise_if_not_found=False)
        group_sm = self.env.ref('mobikey_crm.group_mobikey_sales_manager', raise_if_not_found=False)


        for rec in self:
            lines = rec.product_line_ids


            if not lines:
                rec.margin_approval_required = False
                rec.discount_approval_required = False
                rec.margin_approval_status = 'not_required'
                rec.discount_approval_status = 'not_required'
                rec.margin_approver_ids = [(5, 0, 0)]
                rec.discount_approver_ids = [(5, 0, 0)]
                continue

            ### Condition From Discount Approval
            sales_manager = any((0 < line.discount <= 2) for line in lines)
            country_dic_discount = any(line.discount > 2 and line.discount <= 5 for line in lines)
            hq_discount = any(line.discount > 5 for line in lines)

            if sales_manager or country_dic_discount or hq_discount:
                if rec.discount_approval_status not in ['pending', 'approved']:  # Don't override if already approved
                    rec.discount_approval_required = True
                    rec.discount_approval_status = 'pending'
                    if sales_manager and group_sm:
                        rec.discount_approver_ids |= group_sm.user_ids
                    elif country_dic_discount and group_cd:
                        rec.discount_approver_ids |= group_cd.user_ids
                    elif hq_discount and group_hq:
                        rec.discount_approver_ids |= group_hq.user_ids
                    else:
                        rec.discount_approver_ids = [(5, 0, 0)]
                else:
                    rec.discount_approver_ids = [(5, 0, 0)]
            else:
                rec.discount_approver_ids = [(5, 0, 0)]

            # Check conditions Margin Approval Required:
            negative_margin = any(line.margin < 0 for line in lines)
            below_target = any( line.margin < line.product_id.target_margin for line in lines)

            if rec.margin_approval_status not in ['pending','approved']:  # Don't override if already approved
                rec.margin_approval_required = negative_margin or below_target
                rec.margin_approval_status = ('pending' if rec.margin_approval_required else 'not_required')

                users = self.env['res.users']
                if rec.margin_approval_required:
                    if negative_margin:
                        if group_hq:
                            users |= group_hq.user_ids
                        if group_cd:
                            users |= group_cd.user_ids
                    elif below_target and group_cd:
                        users = group_cd.user_ids

                    rec.margin_approver_ids = [(6, 0, users.ids)]
                else:
                    rec.margin_approver_ids = [(5, 0, 0)]
            else:
                rec.margin_approver_ids = [(5, 0, 0)] if not rec.margin_approver_ids else rec.margin_approver_ids

    ### Used For Email Template to get the URL of the record
    def get_record_url(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/web#id={self.id}&model={self._name}&view_type=form"

    ### Trade-In Approval Button Action
    def action_trade_in_approval(self):
        for rec in self:
            if rec.trade_in_approval_status == 'pending':
                rec.trade_in_approval_status = 'approved'
                rec.trade_in_approved_by = self.env.user.id
                rec.trade_in_approval_date = fields.Datetime.now()
                rec.trade_in_approval_required = False

    ### Financial Approval Button Action
    def action_financial_approval(self):
        for rec in self:
            if rec.financing_required and rec.financing_approval_status == 'pending':
                rec.financing_approval_status = 'approved'
                rec.financing_approved_by = self.env.user.id
                rec.financing_approval_date = fields.Datetime.now()
                rec.financing_approval_required = False

    ### Discount Approved Button Action
    def action_discount_approval(self):
        for rec in self:
            lines = rec.product_line_ids
            user = self.env.user
            if any((line.discount > 0 and line.discount <= 2) for line in lines):
                if not user.has_group('mobikey_crm.group_mobikey_sales_manager'):
                    raise UserError("Only Sales Manager can approve discounts above 5%.")
            elif any((line.discount <= 5 and line.discount > 2) for line in lines):
                if not user.has_group('mobikey_crm.group_mobikey_country_director'):
                    raise UserError("Only Country Director can approve discounts above 2% and up to 5%.")
            elif any(line.discount > 5 for line in lines):
                if not user.has_group('mobikey_crm.group_mobikey_hq'):
                    raise UserError("Only HQ can approve discounts more than 5%.")

            if rec.discount_approval_status == 'pending':
                rec.discount_approval_status = 'approved'
                rec.discount_approved_by = self.env.user.id
                rec.discount_approval_date = fields.Datetime.now()
                rec.discount_approval_required = False

    def action_margin_approval(self):
        for rec in self:
            if rec.discount_approval_status == 'pending':
                raise UserError("Please resolve the pending discount approval before approving margin.")
            lines = rec.product_line_ids
            negative_margin = any(line.margin < 0 for line in lines)
            below_target = any(
                line.margin < line.product_id.target_margin
                for line in lines
            )
            user = self.env.user

            # Case 1: Negative margin → Only HQ & Finance can approve
            if negative_margin:
                if not (
                    user.has_group('mobikey_crm.group_mobikey_hq') or
                    user.has_group('mobikey_crm.group_mobikey_country_director')
                ):
                    raise UserError("Only HQ or Director can approve negative margins.")

            # Case 2: Below target margin → Only Country Director can approve
            elif below_target:
                if not user.has_group('mobikey_crm.group_mobikey_country_director'):
                    raise UserError("Only Country Director can approve margins below target.")

            elif not negative_margin and not below_target:
                raise UserError("You do not have permission to approve margins.")

            if rec.margin_approval_status == 'pending':
                rec.margin_approval_status = 'approved'
                rec.margin_approved_by = self.env.user.id
                rec.margin_approval_date = fields.Datetime.now()
                rec.margin_approval_required = False

    # ══════════════════════════════════════════════════════════
    #  Onchange helpers
    # ══════════════════════════════════════════════════════════

    @api.onchange('contact_name', 'partner_name', 'vehicle_type')
    def _onchange_auto_lead_title(self):
        """Auto-suggest lead title: [Customer] – [Vehicle Type].

        Only fires when both a customer identifier and a vehicle type are
        present.  The user can always overwrite the generated title.
        """
        customer = self.partner_name or self.contact_name
        vtype_label = self.vehicle_type.name if self.vehicle_type else ''
        if customer and vtype_label:
            self.name = f"{customer} – {vtype_label}"

    @api.onchange('lead_status')
    def _onchange_lead_status_clear_disqualification(self):
        """Clear disqualification fields when status changes away from disqualified."""
        if self.lead_status != 'disqualified':
            self.disqualification_reason = False
            self.disqualification_notes = False

    # ══════════════════════════════════════════════════════════
    #  Stage helpers
    # ══════════════════════════════════════════════════════════

    def _get_stage_by_type(self, stage_type):
        """Return the crm.stage record whose mobikey_stage_type matches stage_type."""
        return self.env['crm.stage'].search(
            [('mobikey_stage_type', '=', stage_type)], limit=1,
        )

    def _require_stage(self, stage_type):
        """Like _get_stage_by_type but raises a clear UserError if not found."""
        stage = self._get_stage_by_type(stage_type)
        if not stage:
            stage_labels = dict(
                self.env['crm.stage']._fields['mobikey_stage_type'].selection
            )
            raise UserError(_(
                "No CRM stage is configured with the Mobikey role '%(role)s'.\n\n"
                "Go to CRM → Configuration → Stages, open the correct stage, "
                "and set its 'Mobikey Stage Role' field.",
                role=stage_labels.get(stage_type, stage_type),
            ))
        return stage

    def _has_linked_quotation(self):
        """Return True if at least one sale.order is linked to this opportunity."""
        self.ensure_one()
        return bool(
            self.env['sale.order'].sudo().search(
                [('opportunity_id', '=', self.id), ('state', 'not in', ['cancel'])], limit=1,
            )
        )

    # ══════════════════════════════════════════════════════════
    #  10.0  Stage progression actions
    # ══════════════════════════════════════════════════════════

    def action_next_stage(self):
        """Qualified → next stage (branching on demo_required).

        Flow:
            demo_required=True   →  Demo/Visit/Test Drive
            demo_required=False  →  Quotation  (requires linked quotation)
            demo_required=False  →  UserError  (no quotation linked yet)
        """
        for rec in self:
            if rec.mobikey_current_stage_type != 'qualified':
                raise UserError(_("'Next' is only available from the Qualified stage."))

            if rec.demo_required:
                target = rec._require_stage('demo')
            else:
                if not rec._has_linked_quotation():
                    raise UserError(_(
                        "No quotation is linked to this opportunity.\n\n"
                        "Please create a quotation first, then click Next again."
                    ))
                target = rec._require_stage('quotation')

            rec.with_context(mobikey_bypass_stage_guard=True).write(
                {'stage_id': target.id}
            )

    def action_move_to_quotation(self):
        """Demo → Quotation.  Requires a linked quotation to exist."""
        for rec in self:
            if rec.mobikey_current_stage_type != 'demo':
                raise UserError(_(
                    "'Move to Quotation' is only available from the "
                    "Demo/Visit/Test Drive stage."
                ))
            if not rec._has_linked_quotation():
                raise UserError(_(
                    "No quotation is linked to this opportunity.\n\n"
                    "Please create a quotation first, then move to Quotation."
                ))
            target = rec._require_stage('quotation')
            rec.with_context(mobikey_bypass_stage_guard=True).write(
                {'stage_id': target.id}
            )

    def action_move_to_negotiation(self):
        """Quotation → Negotiation (manual, without sending email)."""
        for rec in self:
            if rec.mobikey_current_stage_type != 'quotation':
                raise UserError(_(
                    "'Move to Negotiation' is only available from the Quotation stage."
                ))
            target = rec._require_stage('negotiation')
            rec.with_context(mobikey_bypass_stage_guard=True).write(
                {'stage_id': target.id}
            )

    def action_move_to_booking(self):
        """Negotiation → Booking/Commitment."""
        for rec in self:
            if rec.mobikey_current_stage_type != 'negotiation':
                raise UserError(_(
                    "'Move to Booking' is only available from the Negotiation stage."
                ))
            target = rec._require_stage('booking')
            rec.with_context(mobikey_bypass_stage_guard=True).write(
                {'stage_id': target.id}
            )

    def action_reset_to_draft(self):
        """Reset to Qualified stage and cancel all open quotations.

        This is the ONLY supported backward movement in the pipeline.
        """
        qualified_stage = self._require_stage('qualified')
        for rec in self:
            open_quotations = self.env['sale.order'].sudo().search([
                ('opportunity_id', '=', rec.id),
                ('state', 'not in', ('cancel', 'done')),
            ])
            if open_quotations:
                open_quotations.action_cancel()

            rec.with_context(mobikey_bypass_stage_guard=True).write(
                {'stage_id': qualified_stage.id}
            )

    # ── Override native Won / Lost so they bypass the stage guard ────────

    def action_set_won(self):
        return super(
            CrmLead, self.with_context(mobikey_bypass_stage_guard=True)
        ).action_set_won()

    def action_set_lost(self, **kwargs):
        return super(
            CrmLead, self.with_context(mobikey_bypass_stage_guard=True)
        ).action_set_lost(**kwargs)

    def get_approver_ids(self, approvers_name=None):
        group_hq = self.env.ref('mobikey_crm.group_mobikey_hq', raise_if_not_found=False)
        group_finance = self.env.ref('mobikey_crm.group_mobikey_finance', raise_if_not_found=False)
        group_cd = self.env.ref('mobikey_crm.group_mobikey_country_director', raise_if_not_found=False)
        group_sm = self.env.ref('mobikey_crm.group_mobikey_sales_manager', raise_if_not_found=False)

        users = self.env['res.users']
        lines = self.product_line_ids

        ### Discount Approvers
        if approvers_name == 'discount':
            if any(line.discount <= 2 for line in lines) and group_sm:
                users |= group_sm.user_ids
            elif any(line.discount > 2 and line.discount <= 5 for line in lines) and group_cd:
                users |= group_cd.user_ids
            elif any(line.discount > 5 for line in lines) and group_hq:
                users |= group_hq.user_ids

        elif approvers_name == 'margin':
            negative_margin = any(line.margin < 0 for line in lines)
            below_target = any((line.margin > 0 and line.margin < line.product_id.target_margin) for line in lines )
            if negative_margin:
                if group_hq:
                    users |= group_hq.user_ids
                if group_cd:
                    users |= group_cd.user_ids
            elif below_target and group_cd:
                users = group_cd.user_ids
        users = users.filtered(lambda x:x.company_id.id == self.env.company.id)
        return users

    # ══════════════════════════════════════════════════════════
    #  10.0  Stage guard (write override)
    # ══════════════════════════════════════════════════════════

    def _prepare_financing_approval(self, vals):
        """Trigger financing approval when a payment term with financing_required=True
        is selected on the opportunity.

        Watches for changes to `payment_terms_type`.  The `financing_required`
        Boolean on crm.lead is now a *computed* field derived from the payment
        term, so we inspect the new term directly here rather than reading the
        legacy Boolean from vals.
        """
        if 'payment_terms_type' not in vals:
            return

        group_finance = self.env.ref(
            'mobikey_crm.group_mobikey_finance',
            raise_if_not_found=False
        )

        payment_term_id = vals.get('payment_terms_type')
        if payment_term_id:
            payment_term = self.env['account.payment.term'].browse(payment_term_id)
            financing_needed = payment_term.financing_required
        else:
            financing_needed = False

        if financing_needed:
            vals['financing_approval_required'] = True
            vals['financing_approval_status'] = 'pending'

            user_ids = group_finance.user_ids if group_finance else self.env['res.users']
            user_ids = user_ids.filtered(
                lambda u: u.company_id.id == self.env.company.id
            )

            vals['financing_approver_ids'] = [(6, 0, user_ids.ids)] if user_ids else [(5, 0, 0)]
        else:
            vals.update({
                'financing_approval_status': 'not_required',
                'financing_approver_ids': [(5, 0, 0)],
                'financing_approval_required': False,
            })

    def _prepare_trade_in_approval(self, vals):
        if 'trade_in_valuation' not in vals:
            return

        group_sm = self.env.ref(
            'mobikey_crm.group_mobikey_sales_manager',
            raise_if_not_found=False
        )
        group_cd = self.env.ref(
            'mobikey_crm.group_mobikey_country_director',
            raise_if_not_found=False
        )
        group_finance = self.env.ref(
            'mobikey_crm.group_mobikey_finance',
            raise_if_not_found=False
        )

        valuation = vals.get('trade_in_valuation')

        if valuation and self.trade_in and valuation > 0:
            vals['trade_in_approval_required'] = True
            vals['trade_in_approval_status'] = 'pending'

            threshold = float(
                self.env['ir.config_parameter']
                .sudo()
                .get_param('crm.lead.trade_in_threshold', default=0.0)
            )

            users = self.env['res.users']

            if valuation <= threshold:
                users = group_sm.user_ids if group_sm else users
            else:
                if group_cd:
                    users |= group_cd.user_ids
                if group_finance:
                    users |= group_finance.user_ids

            users = users.filtered(
                lambda u: u.company_id.id == self.env.company.id
            )

            if users:
                vals['trade_in_approver_ids'] = [(6, 0, users.ids)]
            else:
                vals['trade_in_approver_ids'] = [(5, 0, 0)]

        else:
            vals.update({
                'trade_in_approval_status': 'not_required',
                'trade_in_approver_ids': [(5, 0, 0)],
                'trade_in_approval_required': False,
            })

    def _sync_country_from_company(self, vals):
        if not vals.get('company_id'):
            return

        company = self.env['res.company'].browse(vals['company_id'])
        if company.country_id:
            vals['country_id'] = company.country_id.id

    def _check_stage_progression(self, vals):

        if not vals.get('stage_id'):
            return

        if self.env.context.get('mobikey_bypass_stage_guard'):
            return

        new_stage = self.env['crm.stage'].browse(vals['stage_id'])
        new_type = new_stage.mobikey_stage_type

        if not new_type:
            return

        opportunities = self.filtered(lambda r: r.type == 'opportunity')

        for record in opportunities:
            current_type = record.stage_id.mobikey_stage_type

            if not current_type:
                continue

            if current_type == new_type:
                continue

            allowed_next = _ALLOWED_TRANSITIONS.get(current_type, set())

            if new_type not in allowed_next:
                raise UserError(_(
                    "Moving from '%(from_stage)s' to '%(to_stage)s' directly "
                    "is not permitted.\n\n"
                    "Use the action buttons at the top of the form to advance "
                    "the opportunity. To go backward, use 'Reset to Draft'.",
                    from_stage=record.stage_id.name,
                    to_stage=new_stage.name,
                ))

    def _check_margin_value_update(self, vals):
        if 'product_line_ids' in vals and self.product_line_ids:
            commands = vals.get('product_line_ids', [])

            if any('discount' in command[2] for command in commands if len(command) == 3):
                vals['discount_approval_required'] = True
                vals['discount_approval_status'] = 'pending'

            for command in commands:
                if len(command) == 3 and command[2].get('discount', 0) > 0:
                    line_record = self.env['crm.product.lines'].browse(command[1])
                    discount = command[2]['discount']
                    cost_price = line_record.product_id.standard_price
                    sale_price = line_record.product_id.list_price
                    sale_price = sale_price - (sale_price * (discount / 100))
                    margin =((sale_price - cost_price)/ sale_price) * 100 if cost_price else 100
                    if margin < line_record.product_id.target_margin:
                        vals['margin_approval_required'] = True
                        vals['margin_approval_status'] = 'pending'
                        break

    def write(self, vals):
        """Guard stage_id changes for opportunities + sync mobikey_country + margin approval flow."""
        ### Margin Approval Handle after Approved
        self._check_margin_value_update(vals)

        ### Financing Approval Work
        self._prepare_financing_approval(vals)

        ### Trade-In Approval Work
        self._prepare_trade_in_approval(vals)

        # 1️⃣ Sync country from company
        self._sync_country_from_company(vals)

        # -------------------------------------------------
        # 2️⃣ Stage progression guard (before write)
        # -------------------------------------------------
        self._check_stage_progression(vals)

        # -------------------------------------------------
        # 3️⃣ Store old approval status (before write)
        # -------------------------------------------------
        old_margin_status = {rec.id: rec.margin_approval_status for rec in self}
        old_discount_status = {rec.id: rec.discount_approval_status for rec in self}
        old_financing_status = {rec.id: rec.financing_approval_status for rec in self}
        old_trade_in_status = {rec.id: rec.trade_in_approval_status for rec in self}

        # -------------------------------------------------
        # 5️⃣ Prevent stage change if approval pending
        # (After write ensures correct final state check)
        # -------------------------------------------------
        if vals.get('stage_id'):
            pending_records = self.filtered(lambda r: r.margin_approval_status == 'pending' or r.discount_approval_status == 'pending' or r.financing_approval_status == 'pending' or r.trade_in_approval_status == 'pending')
            if pending_records:
                raise ValidationError(
                    _("Cannot change stage while approval is pending. "
                      "Please resolve the Pending approval first.")
                )

        res = super().write(vals)



        # -------------------------------------------------
        # 6️⃣ Send email only when status becomes 'pending'
        # -------------------------------------------------

        self._handle_trade_in_approval(vals, old_trade_in_status)
        self._handle_financing_approval(vals, old_financing_status)
        self._handle_discount_approval(vals, old_discount_status)
        self._handle_margin_approval(vals, old_margin_status)

        return res

    ### Handle Trade-In Approval
    def _handle_trade_in_approval(self, vals, old_status):
        if vals.get('trade_in_approval_status') != 'pending':
            return

        template = self.env.ref( 'mobikey_crm.email_template_trade_in_approval', raise_if_not_found=False )
        if not template:
            return

        for rec in self.filtered(lambda r: r.trade_in_approval_status == 'pending' and r.trade_in_approver_ids and old_status.get(r.id) != 'pending'):
            for approver in rec.trade_in_approver_ids:
                if not approver.partner_id:
                    continue

                template.with_context(approver_name=approver.name).send_mail(
                    rec.id,
                    force_send=False,
                    email_values={
                        'recipient_ids': [(6, 0, [approver.partner_id.id])],
                    }
                )

    ### Handle Financing Approval
    def _handle_financing_approval(self, vals, old_status):
        if vals.get('financing_approval_status') != 'pending':
            return

        template = self.env.ref('mobikey_crm.email_template_financing_approval',raise_if_not_found=False)
        if not template:
            return

        for rec in self.filtered( lambda r: r.financing_approval_status == 'pending' and r.financing_approver_ids and old_status.get(r.id) != 'pending'):
            for approver in rec.financing_approver_ids:
                if not approver.partner_id:
                    continue

                template.with_context( approver_name=approver.name).send_mail(
                    rec.id,
                    force_send=False,
                    email_values={
                        'recipient_ids': [(6, 0, [approver.partner_id.id])],
                    }
                )

    ### Handle Discount Approval
    def _handle_discount_approval(self, vals, old_status):
        if vals.get('discount_approval_status') != 'pending':
            return

        template = self.env.ref( 'mobikey_crm.email_template_discount_approval', raise_if_not_found=False)
        if not template:
            return

        for rec in self.filtered( lambda r: (r.discount_approval_status == 'pending' or r.discount_approval_status == 'approved') and old_status.get(r.id) != 'pending'):
            approvers = rec.get_approver_ids(approvers_name='discount')
            if not approvers:
                continue

            if not rec.discount_approver_ids:
                rec.write({'discount_approver_ids': [(6, 0, approvers.ids)]})

            for approver in approvers:
                if not approver.partner_id:
                    continue

                template.with_context( approver_name=approver.name ).send_mail(
                    rec.id,
                    force_send=False,
                    email_values={
                        'recipient_ids': [(6, 0, [approver.partner_id.id])],
                    }
                )


    ### Handle Margin Approval
    def _handle_margin_approval(self, vals, old_status):
        if 'margin_approval_status' not in vals:
            return

        template = self.env.ref('mobikey_crm.email_template_margin_approval',raise_if_not_found=False)
        if not template:
            return

        for rec in self.filtered( lambda r: (r.margin_approval_status == 'pending' or r.margin_approval_status == 'approved') and old_status.get(r.id) != 'pending' ):
            approvers = rec.margin_approver_ids or rec.get_approver_ids(approvers_name='margin')
            if not approvers:
                continue

            if not rec.margin_approver_ids:
                rec.write({'margin_approver_ids': [(6, 0, approvers.ids)]})

            for approver in approvers:
                if not approver.partner_id:
                    continue

                template.with_context(approver_name=approver.name).send_mail(
                    rec.id,
                    force_send=False,
                    email_values={
                        'recipient_ids': [(6, 0, [approver.partner_id.id])],
                    }
                )

    # ══════════════════════════════════════════════════════════
    #  Create — country sync
    # ══════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'company_id' in vals:
                company = self.env['res.company'].browse(vals['company_id'])
                country = company.country_id
                if country:
                    vals['country_id'] = country.id
        return super().create(vals_list)

    # ══════════════════════════════════════════════════════════
    #  9.2  Conversion Blockers
    # ══════════════════════════════════════════════════════════

    def _validate_lead_conversion(self):
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
            if not lead.partner_id:
                errors.append(_("Customer (linked partner) is required before conversion."))
            if not lead.vehicle_type:
                errors.append(_("Vehicle Type is required before conversion."))
            if not lead.vehicle_condition:
                errors.append(_("Vehicle Condition is required before conversion."))
            if not lead.customer_type:
                errors.append(_("Customer Type is required before conversion."))
            if not lead.company_id:
                errors.append(_("Company is required before conversion."))
            if not lead.team_id:
                errors.append(_("Sales Team is required before conversion."))
            if not lead.user_id:
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

    # ══════════════════════════════════════════════════════════
    #  9.1  Field Mapping on Conversion
    # ══════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════
    #  Override: convert_opportunity
    # ══════════════════════════════════════════════════════════

    def convert_opportunity(self, partner, user_ids=False, team_id=False):
        leads = self.filtered(lambda r: r.type == 'lead')
        if leads:
            leads._validate_lead_conversion()
        result = super().convert_opportunity(
            partner=partner, user_ids=user_ids, team_id=team_id,
        )
        self._apply_conversion_field_mapping()
        return result

    def action_sale_quotations_new(self):
        quotation_button_action = super().action_sale_quotations_new()
        for rec in self:
            if rec.margin_approval_status == 'pending' or rec.discount_approval_status == 'pending' or rec.trade_in_approval_status == 'pending'  or rec.financing_approval_status == 'pending' :
                raise UserError(_(
                    "Cannot create quotation while approval is pending. "
                    "Please Approve the Pending approval first."
                ))
        return quotation_button_action

    def action_new_quotation(self):
        action = super().action_new_quotation()

        # Inject your custom defaults
        action['context'] = dict(action.get('context', {}))

        if self.product_line_ids:
            action['context'].update({
                'default_order_line': [
                    (0, 0, {
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.quantity,
                        'price_unit': line.price_unit,
                        'discount': line.discount,
                        # 'margin': line.margin,
                    }) for line in self.product_line_ids
                ]
            })
        return action

    def action_send_mail(self):
        template = self.env.ref("")
        email_values = {'email_from': self.env.user.email}
        template.send_mail(self.id, force_send=True, email_values=email_values)

    #Inherit won button for activity_call and activity_todo type activity create and mail send
    def action_set_won_rainbowman(self):
        res = super().action_set_won_rainbowman()


        config_parameter = self.env['ir.config_parameter'].sudo()
        sales_followup_days = int(config_parameter.get_param('mobikey_crm.sales_followup_days',default=30))
        aftersales_followup_days = int(config_parameter.get_param('mobikey_crm.aftersales_followup_days',default=90))

        activity_todo = self.env.ref('mail.mail_activity_data_todo')
        activity_call = self.env.ref('mail.mail_activity_data_call')

        today = fields.Date.today()

        for lead in self:
            if not lead.user_id:
                continue

            #Follow up call for salesperson
            if lead.user_id:
                # +30 Days Sales Follow-up call
                self.env['mail.activity'].create({
                    'res_model_id': self.env['ir.model']._get_id('crm.lead'),
                    'res_id': lead.id,
                    'activity_type_id': activity_call.id,
                    'summary': f'Sales Follow-up for {lead.name}',
                    'user_id': lead.user_id.id,
                    'date_deadline': today + timedelta(days=sales_followup_days),
                })


            #Mail create and follow up call for after sales user
            if lead.after_sales_user_id:

                #Todo_Type activity craete for delivery handover after sales user
                self.env['mail.activity'].create({
                    'res_model_id': self.env['ir.model']._get_id('crm.lead'),
                    'res_id': lead.id,
                    'activity_type_id': activity_todo.id,
                    'summary': f'Delivery Handover for {lead.name}',
                    'user_id': lead.after_sales_user_id.id,
                    # 'date_deadline': today + timedelta(days=30),
                })

                #Mail Create for delivery handover after sales users
                self.env['mail.mail'].create({
                    'subject': f'Delivery Handover for {lead.name}',
                    'body_html': f"""
                        <p>Hello {lead.user_id.name},</p>
                        <p>Delivery handover activity created for <b>{lead.name}</b>.</p>
                    """,
                    'email_to': lead.after_sales_user_id.partner_id.email,
                }).send()


                # +90 Days Aftersales Follow-up
                self.env['mail.activity'].create({
                    'res_model_id': self.env['ir.model']._get_id('crm.lead'),
                    'res_id': lead.id,
                    'activity_type_id': activity_call.id,
                    'summary': f'Aftersales Satisfaction Call for {lead.name}',
                    'user_id': lead.after_sales_user_id.id,
                    'date_deadline': today + timedelta(days=aftersales_followup_days),
                })

            # commission approvers status
            lead.write({
                'commission_approval_status': 'pending',
            })

            # ────────── Dynamic commission approvers ──────────

            # Country Director and HQ users whose company is in the same country as the opportunity
            approval_users = self.env['res.users'].search([]).filtered(
                lambda u: (u.has_group('mobikey_crm.group_mobikey_country_director') or u.has_group('mobikey_crm.group_mobikey_hq')) and lead.company_id.id in u.company_ids.ids
            )

            # Add pending approvers dynamically
            pending_approvers = []
            if lead.commission_approval_status == 'pending':
                pending_approvers += [u.name for u in approval_users]

            # Post chatter message
            if pending_approvers:
                # ────────── Post static chatter message ──────────
                lead.message_post(
                    body=_(
                        "Opportunity marked as WON. "
                        "Commission approval required from: HQ or Country Director"
                    )
                )

            # Send approval emails
            # Combine all emails into one string, ignoring empty ones
            all_emails = ','.join(filter(None, (approval_users).mapped('partner_id.email')))
            if all_emails:
                self.env['mail.mail'].sudo().create({
                    'subject': f'Commission Approval Required for {lead.name}',
                    'body_html': f"""
                         <p>Hello,</p>
                         <p>Opportunity <b>{lead.name}</b> requires your commission approval.</p>
                         <p>
                             <a href="/web#id={lead.id}&model=crm.lead&view_type=form"
                                style="padding:8px 12px; background-color:#0d6efd; color:white; text-decoration:none; border-radius:4px;">
                                Approve
                             </a>
                         </p>
                     """,
                    'email_to': all_emails,
                }).send()

        return res



    #commision approval for gm

    def action_approve_commission(self):
        for rec in self:
            allowed_groups = [
                'mobikey_crm.group_mobikey_hq',
                'mobikey_crm.group_mobikey_country_director',
                'base.group_system'
            ]
            if not any(self.env.user.has_group(group) for group in allowed_groups):
                raise UserError("Only Country GM can approve Commercial Approval.")

            if rec.commission_approval_status != 'pending':
                raise UserError("Commission approval is not pending.")

            rec.write({
                'commission_approval_status': 'approved',
                'commission_approved_by': self.env.user.id,
                'commission_approval_date': fields.Datetime.now()
            })

            rec.message_post(body=_("Commission approved by %s") % self.env.user.name)

    #crm lead --> sale order link
    def _prepare_opportunity_quotation_context(self):
        context = super()._prepare_opportunity_quotation_context()

        # add  custom field
        context.update({
            'default_vehicle_condition': self.vehicle_condition,
            'default_customer_type': self.customer_type.id,
            'default_deal_type': self.deal_type,

        })

        return context
