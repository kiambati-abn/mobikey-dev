from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.modules.loading import force_demo
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged('post_install', '-at_install')
class TestQuotationWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sales = new_test_user(cls.env, login='workflow.sales', groups='sales_team.group_sale_salesman')
        cls.sm = new_test_user(cls.env, login='workflow.sm', groups='mobikey_crm.group_mobikey_sales_manager')
        cls.gm = new_test_user(cls.env, login='workflow.gm', groups='mobikey_crm.group_mobikey_country_gm')
        cls.hq = new_test_user(cls.env, login='workflow.hq', groups='mobikey_crm.group_mobikey_hq')
        cls.finance = new_test_user(cls.env, login='workflow.finance', groups='mobikey_crm.group_mobikey_finance')
        cls.env.company.write({'mobikey_sm_ids': [Command.set(cls.sm.ids)],
            'mobikey_gm_ids': [Command.set(cls.gm.ids)], 'mobikey_hq_ids': [Command.set(cls.hq.ids)],
            'mobikey_finance_ids': [Command.set(cls.finance.ids)], 'mobikey_trade_in_configured': True,
            'mobikey_trade_in_threshold': 1000})
        cls.partner = cls.env['res.partner'].create({'name': 'Customer', 'email': 'customer@example.invalid'})
        cls.product = cls.env['product.product'].create({'name': 'Vehicle', 'list_price': 1000,
            'standard_price': 600, 'target_margin': 20, 'taxes_id': [Command.clear()]})

    def quote(self, discounts=(0,), **values):
        return self.env['sale.order'].with_user(self.sales).create({
            'partner_id': self.partner.id, 'user_id': self.sales.id,
            'order_line': [Command.create({'product_id': self.product.id, 'product_uom_qty': 1,
                'price_unit': 1000, 'discount': discount, 'tax_ids': [Command.clear()]}) for discount in discounts],
            **values})

    def test_discount_boundaries_and_mixed_lines(self):
        for discount, role in [(0, None), (2, 'sm'), (2.01, 'gm'), (5, 'gm'), (5.01, 'hq')]:
            order = self.quote((discount,))
            self.assertEqual(order._approval_requirements().get('discount'), role)
        self.assertEqual(self.quote((1, 10))._approval_requirements()['discount'], 'hq')

    def test_native_stages_do_not_cancel_pending_quote(self):
        lead = self.env['crm.lead'].create({'name': 'Opportunity', 'type': 'opportunity', 'user_id': self.sales.id, 'company_id': self.env.company.id})
        order = self.quote((10,), opportunity_id=lead.id)
        order.action_submit_approvals()
        stage = self.env['crm.stage'].create({'name': 'Any native stage'})
        lead.stage_id = stage
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.approval_status, 'pending')

    def test_revenue_primary_alternatives_and_cancellation(self):
        lead = self.env['crm.lead'].create({'name': 'Forecast', 'type': 'opportunity', 'user_id': self.sales.id, 'company_id': self.env.company.id,
                                          'expected_revenue': 500})
        first = self.quote(opportunity_id=lead.id)
        self.assertEqual(lead.primary_quotation_id, first)
        self.assertEqual(lead.expected_revenue, first.amount_total)
        second = self.quote(opportunity_id=lead.id)
        second.order_line.price_unit = 5000
        self.assertEqual(lead.expected_revenue, 1000)
        first.order_line.price_unit = 900
        self.assertEqual(lead.expected_revenue, 900)
        first.action_cancel()
        self.assertFalse(lead.primary_quotation_id)
        self.assertEqual(lead.expected_revenue, 0)

    def test_revision_permissions_and_notifications(self):
        order = self.quote((10,))
        order.action_submit_approvals()
        approval = order.sudo().approval_ids
        snapshot = approval.financial_snapshot
        with self.assertRaises(AccessError):
            approval.with_user(self.sales).read(['financial_snapshot'])
        self.assertEqual(approval.assigned_user_ids, self.hq)
        self.assertEqual(len(approval.activity_ids), 1)
        with self.assertRaises(AccessError):
            approval.with_user(self.sales).action_approve()
        with self.assertRaises(AccessError):
            approval.with_user(self.hq).write({'status': 'approved'})
        approval.with_user(self.hq).action_approve()
        with self.assertRaises(UserError):
            order.order_line.discount = 15
        order.action_revise_quotation()
        order.order_line.discount = 15
        self.assertEqual(approval.financial_snapshot, snapshot)
        with self.assertRaises(UserError):
            approval.with_user(self.hq).action_approve()
        order.action_submit_approvals()
        self.assertEqual(len(order.sudo().approval_ids), 2)
        copy = order.copy()
        self.assertFalse(copy.approval_submitted)
        self.assertFalse(copy.sudo().approval_ids)

    def test_financial_fields_are_not_readable(self):
        order = self.quote()
        for record, field in [(self.product, 'standard_price'), (self.product.product_tmpl_id, 'standard_price'),
                              (self.product, 'avg_cost'), (self.product, 'total_value'),
                              (self.product, 'target_margin'), (order, 'margin'),
                              (order.order_line, 'purchase_price'), (order.order_line, 'margin_percent')]:
            with self.assertRaises(AccessError):
                record.with_user(self.sales).read([field])
        self.assertNotIn('standard_price', self.product.with_user(self.sales).fields_get())
        self.assertNotIn('margin', order.with_user(self.sm).fields_get())
        self.assertEqual(order.order_line.with_user(self.sales).price_unit, 1000)
        with self.assertRaises(AccessError):
            self.env['product.product'].with_user(self.sales).search_count([('standard_price', '>', 0)])
        with self.assertRaises(AccessError):
            self.env['sale.order.line'].with_user(self.sales)._read_group([], [], ['margin:sum'])
        self.assertNotIn('price', self.env['product.supplierinfo'].with_user(self.sales).fields_get())
        self.assertNotIn('value', self.env['stock.move'].with_user(self.sales).fields_get())
        self.assertNotIn('standard_price', self.env['stock.lot'].with_user(self.sales).fields_get())

    def test_notifications_exclude_customer_and_are_deduplicated(self):
        order = self.quote((10,))
        before = self.env['mail.mail'].sudo().search([])
        order.action_submit_approvals()
        first = self.env['mail.mail'].sudo().search([]) - before
        order.action_submit_approvals()
        after = self.env['mail.mail'].sudo().search([]) - before
        self.assertEqual(first, after)
        requests = after.filtered(lambda mail: mail.subject == 'Quotation approval request')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests.recipient_ids, self.hq.partner_id)
        self.assertFalse(requests.email_to)
        self.assertFalse(requests.email_cc)
        self.assertNotIn(self.partner, after.recipient_ids)

    def test_trade_in_financing_and_missing_assignment(self):
        term = self.env['account.payment.term'].create({'name': 'Finance term', 'financing_required': True})
        order = self.quote(trade_in=True, trade_in_valuation=2000, payment_term_id=term.id)
        self.assertEqual(order._approval_requirements(), {'trade_in': 'gm|finance', 'financing': 'finance'})
        self.env.company.mobikey_trade_in_authority = 'both'
        self.assertEqual(order._approval_requirements()['trade_in_finance'], 'finance')
        self.env.company.mobikey_finance_ids = False
        with self.assertRaises(UserError):
            order.action_submit_approvals()

    def test_no_exception_confirmation_and_handover(self):
        self.product.is_storable = True
        order = self.quote(after_sales_user_id=self.sales.id)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        activities = order.activity_ids
        order.sudo()._create_handover()
        self.assertEqual(order.activity_ids, activities)

    def test_confirmed_downpayment_section_does_not_invalidate_approval(self):
        order = self.quote((10,))
        order.action_submit_approvals()
        order.sudo().approval_ids.with_user(self.hq).action_approve()
        order.action_confirm()
        order._create_down_payment_section_line_if_needed()
        order._check_commercial_approval()
        with self.assertRaises(UserError):
            order.order_line.filtered('product_id').write({'is_downpayment': True})

    def test_direct_state_create_is_not_an_approval_bypass(self):
        with self.assertRaises(UserError):
            self.quote((10,), state='sale')
        with self.assertRaises(UserError):
            self.env['sale.order'].with_user(self.sales).with_context(install_demo=True).create({
                'partner_id': self.partner.id,
                'state': 'sent',
            })

    def test_odoo_demo_loader_can_create_non_draft_orders(self):
        order = self.env['sale.order'].sudo().with_context(install_demo=True).create({
            'partner_id': self.partner.id,
            'state': 'sent',
        })
        self.assertEqual(order.state, 'sent')

    def test_force_demo_loads_with_approval_workflow(self):
        force_demo(self.env)
        self.assertTrue(self.env.ref('stock.warehouse_company_1').exists())
        self.assertTrue(self.env.ref('stock.product_cable_management_box').exists())
        self.assertTrue(self.env.ref('sale.sale_order_4').exists())
        self.assertTrue(self.env.ref('sale_management.sale_order_template_1').exists())
        self.assertTrue(self.env.ref(
            'sale_pdf_quote_builder.sale_pdf_header_demo_page'
        ).exists())

    def test_confirmation_preserves_quotation_pricing_date(self):
        order = self.quote(date_order='2026-01-15 10:00:00')
        quote_date = order.date_order
        order.action_confirm()
        self.assertEqual(order.approval_date_order, quote_date)

    def test_company_authority_is_checked(self):
        other_company = self.env['res.company'].create({'name': 'Other country'})
        self.env.company.mobikey_hq_ids = False
        other_company.mobikey_hq_ids = self.hq
        with self.assertRaises(UserError):
            self.quote((10,)).action_submit_approvals()

    def test_discount_precedes_margin_and_zero_price_is_safe(self):
        order = self.quote((2,))
        order.order_line.sudo().purchase_price = 1100
        order.action_submit_approvals()
        approvals = order.sudo().approval_ids
        margin = approvals.filtered(lambda a: a.category == 'margin')
        with self.assertRaises(UserError):
            margin.with_user(self.gm).action_approve()
        approvals.filtered(lambda a: a.category == 'discount').with_user(self.sm).action_approve()
        margin.with_user(self.gm).action_approve()
        zero = self.quote()
        zero.order_line.price_unit = 0
        self.assertIn('margin', zero._approval_requirements())

    def test_confirmation_signature_and_issue_are_gated(self):
        order = self.quote((10,))
        for action in [order.action_confirm, order.action_quotation_send,
                       lambda: order.sudo().write({'signature': 'dGVzdA=='}),
                       lambda: order.write({'state': 'sale'})]:
            with self.assertRaises(UserError):
                action()
        order.action_submit_approvals()
        order.sudo().approval_ids.with_user(self.hq).action_approve()
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_report_and_composer_check_before_output(self):
        order = self.quote((10,))
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_qweb_html('sale.action_report_saleorder', order.ids)
        wizard = self.env['mail.compose.message'].with_user(self.sales).create({
            'model': 'sale.order', 'res_ids': str(order.ids), 'composition_mode': 'comment',
            'partner_ids': [Command.set(self.partner.ids)], 'body': 'Customer quotation'})
        with self.assertRaises(UserError):
            wizard._action_send_mail()

    def test_revenue_currency_tax_and_primary_switch(self):
        lead = self.env['crm.lead'].create({'name': 'Currency forecast', 'type': 'opportunity',
            'company_id': self.env.company.id, 'user_id': self.sales.id})
        foreign = self.env.ref('base.EUR')
        foreign.active = True
        pricelist = self.env['product.pricelist'].create({'name': 'Foreign offer', 'currency_id': foreign.id})
        tax = self.env['account.tax'].create({'name': 'Test tax', 'amount': 10, 'type_tax_use': 'sale'})
        order = self.quote(opportunity_id=lead.id, pricelist_id=pricelist.id)
        order.order_line.tax_ids = tax
        expected = foreign._convert(order.amount_total, self.env.company.currency_id,
                                    self.env.company, order.date_order.date())
        self.assertAlmostEqual(lead.expected_revenue, expected)
        self.env.company.mobikey_revenue_basis = 'untaxed'
        expected = foreign._convert(order.amount_untaxed, self.env.company.currency_id,
                                    self.env.company, order.date_order.date())
        self.assertAlmostEqual(lead.expected_revenue, expected)
        alternative = self.quote(opportunity_id=lead.id)
        lead.primary_quotation_id = alternative
        self.assertEqual(lead.expected_revenue, alternative.amount_untaxed)

    def test_commission_requires_configured_milestone(self):
        order = self.quote()
        order.action_confirm()
        self.assertFalse(order.sudo().approval_ids)
        self.env.company.mobikey_commission_milestone = 'confirmation'
        order.sudo()._ensure_commission_approval()
        commission = order.sudo().approval_ids
        self.assertEqual(commission.category, 'commission')
        commission.with_user(self.gm).action_approve()
        order.sudo()._ensure_commission_approval()
        self.assertEqual(order.sudo().approval_ids, commission)

    def test_snapshot_is_stable(self):
        lead = self.env['crm.lead'].create({'name': 'Forecast snapshot', 'type': 'opportunity',
            'company_id': self.env.company.id, 'user_id': self.sales.id, 'expected_revenue': 500, 'probability': 40})
        self.env['mobikey.forecast.snapshot'].sudo()._cron_snapshot()
        snapshot = self.env['mobikey.forecast.snapshot'].search([('lead_id', '=', lead.id)])
        self.assertEqual(snapshot.weighted_revenue, 200)
        lead.expected_revenue = 1000
        self.assertEqual(snapshot.expected_revenue, 500)

    def test_cutover_preserves_history_and_does_not_duplicate_lines(self):
        from ..hooks import post_init_hook
        lead = self.env['crm.lead'].create({'name': 'Historical opportunity', 'type': 'opportunity',
            'company_id': self.env.company.id, 'user_id': self.sales.id,
            'discount_approval_status': 'approved', 'discount_approved_by': self.hq.id,
            'product_line_ids': [Command.create({'product_id': self.product.id, 'quantity': 2, 'discount': 1})]})
        order = self.quote(opportunity_id=lead.id, order_line=[])
        queued = self.env['mail.mail'].sudo().create({'model': 'crm.lead', 'res_id': lead.id,
            'subject': 'Trade In Approval Request', 'body_html': '<p>Legacy request</p>',
            'email_to': 'customer@example.invalid'})
        post_init_hook(self.env)
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_uom_qty, 2)
        self.assertEqual(lead.discount_approval_status, 'approved')
        self.assertFalse(order.sudo().approval_ids)
        self.assertEqual(queued.state, 'cancel')
        post_init_hook(self.env)
        self.assertEqual(len(order.order_line), 1)
