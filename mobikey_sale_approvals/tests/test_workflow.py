from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.modules.loading import force_demo
from odoo.tests import Form, TransactionCase, tagged, new_test_user
from odoo.tools import mute_logger


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
            'mobikey_trade_in_threshold': 1000,
            'mobikey_trade_in_approver_ids': [Command.set((cls.gm | cls.finance).ids)]})
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

        self.env.company.write({
            'mobikey_sm_discount_limit': 3,
            'mobikey_gm_discount_limit': 7,
        })
        self.assertEqual(self.quote((3,))._approval_requirements()['discount'], 'sm')
        self.assertEqual(self.quote((3.01,))._approval_requirements()['discount'], 'gm')
        self.assertEqual(self.quote((7.01,))._approval_requirements()['discount'], 'hq')

    def test_company_threshold_validation_and_margin(self):
        self.product.target_margin = 60
        order = self.quote()
        self.assertNotIn('margin', order._approval_requirements())
        self.product.product_tmpl_id.mobikey_minimum_margin = 45
        self.assertEqual(order._approval_requirements(), {'margin': 'gm'})
        self.env.company.mobikey_minimum_margin = 45
        self.assertEqual(order._approval_requirements()['margin'], 'gm')
        self.assertEqual(order._approval_requirements()['margin_hq'], 'hq')
        order.order_line.price_unit = 500
        self.assertEqual(order._approval_requirements()['margin'], 'gm')
        with self.assertRaises(ValidationError):
            self.env.company.write({
                'mobikey_sm_discount_limit': 6,
                'mobikey_gm_discount_limit': 5,
            })
        with self.assertRaises(ValidationError):
            self.env.company.mobikey_minimum_margin = 101
        with self.assertRaises(ValidationError):
            self.product.product_tmpl_id.mobikey_minimum_margin = 100

    def test_product_margin_is_company_specific_and_zero_disables_it(self):
        template = self.product.product_tmpl_id
        template.mobikey_minimum_margin = 45
        order = self.quote()
        self.assertEqual(order._approval_requirements(), {'margin': 'gm'})

        template.mobikey_minimum_margin = 0
        self.assertNotIn('margin', order._approval_requirements())

        other_company = self.env['res.company'].create({'name': 'Product threshold company'})
        template.with_company(other_company).mobikey_minimum_margin = 55
        self.assertEqual(template.mobikey_minimum_margin, 0)
        self.assertEqual(template.with_company(other_company).mobikey_minimum_margin, 55)

    def test_overall_margin_routes_gm_then_hq(self):
        self.env.company.mobikey_minimum_margin = 45
        order = self.quote()
        order.action_submit_approvals()
        approvals = order.sudo().approval_ids
        gm = approvals.filtered(lambda item: item.category == 'margin')
        hq = approvals.filtered(lambda item: item.category == 'margin_hq')
        self.assertEqual(gm.sequence, 1)
        self.assertEqual(hq.sequence, 2)
        self.assertEqual(hq.dependency_ids, gm)
        self.assertTrue(gm.notified_at)
        self.assertFalse(hq.notified_at)
        self.assertEqual(hq.workflow_state, 'queued')
        self.assertIn('Overall quotation margin: 40.00%', gm.margin_preview)

        gm.with_user(self.gm).action_approve()
        self.assertTrue(hq.notified_at)
        self.assertEqual(hq.workflow_state, 'active')
        self.assertEqual(len(hq.activity_ids), 1)
        hq.with_user(self.hq).action_approve()
        self.assertEqual(order.approval_status, 'ready')

    def test_native_stages_do_not_cancel_pending_quote(self):
        lead = self.env['crm.lead'].create({'name': 'Opportunity', 'type': 'opportunity', 'user_id': self.sales.id, 'company_id': self.env.company.id})
        order = self.quote((10,), opportunity_id=lead.id)
        order.action_submit_approvals()
        stage = self.env['crm.stage'].create({'name': 'Any native stage'})
        lead.stage_id = stage
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.approval_status, 'pending')

    def test_revenue_sums_active_quotations_and_cancellation(self):
        lead = self.env['crm.lead'].create({'name': 'Forecast', 'type': 'opportunity', 'user_id': self.sales.id, 'company_id': self.env.company.id,
                                          'expected_revenue': 500})
        first = self.quote(opportunity_id=lead.id)
        self.assertEqual(lead.primary_quotation_id, first)
        self.assertEqual(lead.expected_revenue, first.amount_total)
        second = self.quote(opportunity_id=lead.id)
        second.order_line.price_unit = 5000
        self.assertEqual(lead.expected_revenue, 6000)
        first.order_line.price_unit = 900
        self.assertEqual(lead.expected_revenue, 5900)
        first.action_cancel()
        self.assertFalse(lead.primary_quotation_id)
        self.assertEqual(lead.expected_revenue, 5000)
        self.assertEqual(lead.revenue_quotation_count, 1)
        second.action_cancel()
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
        messages_before_revision = order.message_ids
        order.action_revise_quotation()
        revision_messages = order.message_ids - messages_before_revision
        self.assertTrue(any('revision 1 was withdrawn' in message.body for message in revision_messages))
        self.assertTrue(any('Revision 2' in message.body for message in revision_messages))
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
                              (self.product, 'target_margin'),
                              (self.product.product_tmpl_id, 'mobikey_minimum_margin'),
                              (order, 'margin'),
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
        before = order.message_ids
        order.action_submit_approvals()
        approval = order.sudo().approval_ids
        first = order.message_ids - before
        order.action_submit_approvals()
        after = order.message_ids - before
        self.assertEqual(first, after)
        requests = after.filtered(lambda message: 'requires Discount approval' in message.body)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests.partner_ids, self.hq.partner_id)
        self.assertNotIn(self.partner, after.partner_ids)
        self.assertTrue(any('requires Discount approval' in message.body
                            for message in approval.message_ids))

        before_decision = order.message_ids
        before_approval_decision = approval.message_ids
        approval.with_user(self.hq).action_approve()
        outcome = (order.message_ids - before_decision).filtered(
            lambda message: 'approved Discount approval' in message.body
        )
        self.assertEqual(len(outcome), 1)
        self.assertIn(self.sales.partner_id, outcome.partner_ids)
        self.assertNotIn(self.partner, outcome.partner_ids)
        mirrored = approval.message_ids - before_approval_decision
        self.assertTrue(any('approved Discount approval' in message.body for message in mirrored))
        self.assertFalse(mirrored.partner_ids)

    def test_change_request_is_logged_and_sent_to_submitter(self):
        order = self.quote((10,))
        order.action_submit_approvals()
        approval = order.sudo().approval_ids.with_user(self.hq)
        action = approval.action_request_changes()
        self.assertEqual(action['res_model'], 'mobikey.sale.approval.request.changes')
        before = order.message_ids
        wizard = self.env['mobikey.sale.approval.request.changes'].with_user(self.hq).create({
            'approval_id': approval.id,
            'reason': 'Please confirm the customer-facing trade terms.',
        })
        wizard.action_confirm()
        outcome = (order.message_ids - before).filtered(
            lambda message: 'requested changes for Discount approval' in message.body
        )
        self.assertEqual(len(outcome), 1)
        self.assertIn('Please confirm the customer-facing trade terms.', outcome.body)
        self.assertIn(self.sales.partner_id, outcome.partner_ids)
        with self.assertRaises(AccessError):
            approval.write({'change_request': 'Changed after decision'})

    def test_change_request_dialog_requires_reason(self):
        order = self.quote((10,))
        order.action_submit_approvals()
        approval = order.sudo().approval_ids.with_user(self.hq)
        with self.assertRaises(UserError):
            approval._request_changes('   ')

    def test_trade_in_financing_and_missing_assignment(self):
        term = self.env['account.payment.term'].create({'name': 'Finance term', 'financing_required': True})
        order = self.quote(trade_in=True, trade_in_valuation=2000, payment_term_id=term.id)
        self.assertEqual(order._approval_requirements(), {
            'trade_in': 'trade_in_pool',
            'financing': 'finance',
        })
        self.env.company.mobikey_trade_in_approver_ids = False
        with self.assertRaisesRegex(UserError, 'Trade-in approvers'):
            order.action_submit_approvals()

    def test_deal_type_and_financing_terms_stay_consistent(self):
        cash_term = self.env['account.payment.term'].create({'name': 'Cash term'})
        finance_term = self.env['account.payment.term'].create({
            'name': 'Financing term', 'financing_required': True,
        })
        lead = self.env['crm.lead'].create({
            'name': 'Fleet finance', 'type': 'opportunity', 'user_id': self.sales.id,
            'company_id': self.env.company.id, 'deal_type': 'fleet',
            'financing_required': True, 'payment_terms_type': finance_term.id,
        })
        quote_context = lead._prepare_opportunity_quotation_context()
        self.assertNotIn('default_payment_term_id', quote_context)
        order = self.quote(
            opportunity_id=lead.id, deal_type='fleet', financing_required=True,
            payment_term_id=finance_term.id,
        )
        self.assertEqual(order.deal_type, 'fleet')
        self.assertTrue(order.financing_required)
        self.assertIn('financing', order._approval_requirements())

        direct = self.quote(payment_term_id=finance_term.id, deal_type='cash')
        self.assertEqual(direct.deal_type, 'financing')
        self.assertTrue(direct.financing_required)

        with self.assertRaises(ValidationError):
            order.payment_term_id = cash_term

        lead.write({'deal_type': 'financing'})
        self.assertTrue(lead.financing_required)

    def test_trade_in_approvers_are_selected_individually(self):
        reviewer = new_test_user(self.env, login='workflow.trade.in', groups='base.group_user')
        self.env.company.mobikey_trade_in_approver_ids = [Command.set(reviewer.ids)]
        self.assertTrue(reviewer.has_group('mobikey_sale_approvals.group_approver'))
        order = self.quote(trade_in=True, trade_in_valuation=500)
        order.action_submit_approvals()
        approval = order.sudo().approval_ids
        self.assertEqual(approval.assigned_user_ids, reviewer)
        approval.with_user(reviewer).action_approve()
        self.assertEqual(approval.status, 'approved')

    def test_named_gm_can_approve_financing_without_finance_role(self):
        self.assertFalse(self.gm.has_group('mobikey_crm.group_mobikey_finance'))
        self.env.company.mobikey_finance_ids = [Command.set(self.gm.ids)]
        term = self.env['account.payment.term'].create({
            'name': 'GM finance approval term', 'financing_required': True,
        })
        order = self.quote(payment_term_id=term.id)
        order.action_submit_approvals()
        approval = order.sudo().approval_ids.filtered(lambda item: item.category == 'financing')
        self.assertEqual(approval.assigned_user_ids, self.gm)
        approval.with_user(self.gm).action_approve()
        self.assertEqual(approval.status, 'approved')

    def test_named_finance_approver_gets_minimum_access_not_financial_visibility(self):
        reviewer = new_test_user(self.env, login='workflow.named.finance', groups='base.group_user')
        self.env.company.mobikey_finance_ids = [Command.set(reviewer.ids)]
        self.assertTrue(reviewer.has_group('mobikey_sale_approvals.group_approver'))
        self.assertFalse(reviewer.has_group('mobikey_sale_approvals.group_financial_visibility'))
        term = self.env['account.payment.term'].create({
            'name': 'Named finance approval term', 'financing_required': True,
        })
        order = self.quote(payment_term_id=term.id)
        order.action_submit_approvals()
        approval = order.sudo().approval_ids.filtered(lambda item: item.category == 'financing')
        approval.with_user(reviewer).action_approve()
        self.assertEqual(approval.status, 'approved')

    def test_explicit_unavailable_approver_does_not_silently_fall_back(self):
        reviewer = new_test_user(self.env, login='workflow.unavailable.finance', groups='base.group_user')
        self.env.company.mobikey_finance_ids = [Command.set(reviewer.ids)]
        reviewer.active = False
        self.assertFalse(self.env.company._mobikey_approvers('finance'))
        term = self.env['account.payment.term'].create({
            'name': 'Unavailable finance approval term', 'financing_required': True,
        })
        with self.assertRaisesRegex(UserError, 'financing'):
            self.quote(payment_term_id=term.id).action_submit_approvals()

    def test_pending_approval_keeps_its_submitted_assignee(self):
        self.env.company.mobikey_finance_ids = [Command.set(self.gm.ids)]
        term = self.env['account.payment.term'].create({
            'name': 'Frozen finance assignee term', 'financing_required': True,
        })
        order = self.quote(payment_term_id=term.id)
        order.action_submit_approvals()
        approval = order.sudo().approval_ids.filtered(lambda item: item.category == 'financing')
        self.env.company.mobikey_finance_ids = [Command.set(self.finance.ids)]
        self.assertEqual(approval.assigned_user_ids, self.gm)
        approval.with_user(self.gm).action_approve()
        self.assertEqual(approval.status, 'approved')

    def test_assignment_rejects_user_without_company_access(self):
        other_company = self.env['res.company'].create({'name': 'Restricted approver company'})
        reviewer = new_test_user(self.env, login='workflow.other.company', groups='base.group_user')
        with self.assertRaisesRegex(ValidationError, 'Assigned Finance approvers'):
            other_company.mobikey_finance_ids = [Command.set(reviewer.ids)]

    def test_finance_role_is_independent_of_commercial_role(self):
        self.gm.write({'group_ids': [Command.link(
            self.env.ref('mobikey_crm.group_mobikey_finance').id
        )]})
        self.assertTrue(self.gm.has_group('mobikey_crm.group_mobikey_country_gm'))
        self.assertTrue(self.gm.has_group('mobikey_crm.group_mobikey_finance'))

    def test_country_director_role_is_removed_and_hq_inherits_gm(self):
        self.assertFalse(self.env.ref(
            'mobikey_crm.group_mobikey_country_director', raise_if_not_found=False
        ))
        self.assertTrue(self.hq.has_group('mobikey_crm.group_mobikey_country_gm'))

    def test_submitted_legacy_trade_in_keeps_original_authority(self):
        order = self.quote(trade_in=True, trade_in_valuation=500)
        order.sudo().write({'approval_submitted': True})
        approval = self.env['mobikey.sale.approval'].sudo().create({
            'order_id': order.id,
            'revision': order.approval_revision,
            'category': 'trade_in',
            'authority': 'sm',
            'assigned_user_ids': [Command.set(self.sm.ids)],
            'requested_by': self.sales.id,
        })
        self.assertEqual(order._approval_requirements()['trade_in'], 'sm')
        self.env.company.mobikey_trade_in_approver_ids = [Command.set(self.finance.ids)]
        self.assertEqual(order._approval_requirements()['trade_in'], 'sm')
        self.assertEqual(approval.assigned_user_ids, self.sm)

    def test_financing_and_policy_are_snapshotted(self):
        term = self.env['account.payment.term'].create({
            'name': 'Snapshot finance term',
            'financing_required': True,
        })
        order = self.quote((1,), payment_term_id=term.id)
        order.action_submit_approvals()
        self.assertEqual(order.sudo().approval_policy_snapshot['discount_sm_limit'], 2.0)
        self.assertTrue(order.financing_approval_required)
        self.env.company.write({
            'mobikey_sm_discount_limit': 0.5,
            'mobikey_gm_discount_limit': 4,
            'mobikey_minimum_margin': 30,
        })
        term.financing_required = False
        self.assertEqual(order._approval_requirements()['discount'], 'sm')
        self.assertIn('financing', order._approval_requirements())
        self.assertTrue(order.financing_approval_required)
        order.action_revise_quotation()
        self.assertFalse(order.sudo().approval_policy_snapshot)
        self.assertEqual(order._approval_requirements()['discount'], 'gm')
        self.assertNotIn('financing', order._approval_requirements())

    def test_top_actions_and_multiple_current_approvals(self):
        order = self.quote((1,))
        order.action_submit_approvals()
        self.assertEqual(order.with_user(self.sm).my_actionable_approval_count, 1)
        order.with_user(self.sm).action_approve_current()
        self.assertEqual(order.sudo().approval_ids.status, 'approved')

        term = self.env['account.payment.term'].create({
            'name': 'Multiple finance term',
            'financing_required': True,
        })
        multiple = self.quote(
            trade_in=True,
            trade_in_valuation=2000,
            payment_term_id=term.id,
        )
        multiple.action_submit_approvals()
        self.assertEqual(multiple.with_user(self.finance).my_actionable_approval_count, 2)
        action = multiple.with_user(self.finance).action_review_my_approvals()
        self.assertEqual(action['domain'], [('id', 'in', multiple.with_user(self.finance)._my_actionable_approvals().ids)])

    def test_preferred_language_is_editable_and_tracked(self):
        lead = self.env['crm.lead'].with_user(self.sales).create({
            'name': 'Language preference',
            'type': 'opportunity',
        })
        swahili = self.env.ref('mobikey_crm.preferred_language_swahili')
        french = self.env['mobikey.preferred.language'].with_user(self.sales).create({
            'name': 'French', 'code': 'fr',
        })
        lead.preferred_language_id = swahili
        self.assertEqual(lead.preferred_language_id, swahili)
        lead.preferred_language_id = french
        self.assertEqual(lead.preferred_language_id, french)
        self.assertTrue(lead._fields['preferred_language_id'].tracking)

    def test_walkin_branch_uses_accessible_companies(self):
        branch = self.env['res.company'].create({
            'name': 'Walk-in Branch', 'parent_id': self.env.company.id,
        })
        self.env.user.company_ids = [Command.link(branch.id)]
        lead = self.env['crm.lead'].create({
            'name': 'Branch visit', 'type': 'opportunity', 'company_id': self.env.company.id,
            'user_id': self.sales.id, 'walkin_company_id': branch.id,
        })
        self.assertEqual(lead.walkin_company_id, branch)
        self.assertIn(branch, lead.available_walkin_company_ids)
        self.assertEqual(lead._fields['walkin_company_id'].comodel_name, 'res.company')

    def test_repeated_user_copies_receive_unique_logins(self):
        source = new_test_user(self.env, login='copy.source@example.invalid', groups='base.group_user')
        first = source.copy()
        second = source.copy()
        copied_copy = first.copy()
        self.assertEqual(first.login, 'copy.source@example.invalid (copy)')
        self.assertEqual(second.login, 'copy.source@example.invalid (copy 2)')
        self.assertEqual(copied_copy.login, 'copy.source@example.invalid (copy 3)')

        explicit = source.copy({'login': 'copy.explicit@example.invalid'})
        self.assertEqual(explicit.login, 'copy.explicit@example.invalid')

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
        self.hq.company_ids = [Command.link(other_company.id)]
        self.env.company.mobikey_hq_ids = False
        other_company.mobikey_hq_ids = self.hq
        order = self.quote((10,))
        # An assignment in another company must not fill this company's empty list.
        with self.assertRaisesRegex(UserError, 'Configure named approvers'):
            order.action_submit_approvals()
        self.assertFalse(order.approval_submitted)
        self.env.company.mobikey_hq_ids = self.hq
        before_order = order.message_ids
        order.action_submit_approvals()
        approval = order.sudo().approval_ids
        self.assertEqual(approval.assigned_user_ids, self.hq)
        self.assertEqual(len(approval.activity_ids), 1)
        self.assertTrue(any(
            'requires Discount approval' in message.body
            for message in order.message_ids - before_order
        ))
        self.assertTrue(any(
            'requires Discount approval' in message.body
            for message in approval.message_ids
        ))

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

    def test_revenue_currency_tax_and_multiple_quotations(self):
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
        self.assertAlmostEqual(lead.expected_revenue, expected + alternative.amount_untaxed)

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

    def test_snapshot_visibility_tracks_current_assignment(self):
        leader = new_test_user(self.env, login='forecast.leader', groups='sales_team.group_sale_salesman')
        replacement = new_test_user(self.env, login='forecast.replacement', groups='sales_team.group_sale_salesman')
        team = self.env['crm.team'].create({'name': 'Forecast team', 'user_id': leader.id})
        lead = self.env['crm.lead'].create({'name': 'Private forecast', 'type': 'opportunity',
            'company_id': self.env.company.id, 'user_id': self.sales.id, 'team_id': team.id,
            'expected_revenue': 500, 'probability': 40})
        self.env['mobikey.forecast.snapshot'].sudo()._cron_snapshot()
        snapshot = self.env['mobikey.forecast.snapshot'].search([('lead_id', '=', lead.id)])
        self.assertTrue(snapshot.with_user(self.sales).has_access('read'))
        self.assertTrue(snapshot.with_user(leader).has_access('read'))
        lead.user_id = replacement
        self.assertEqual(snapshot.user_id, self.sales)
        self.assertFalse(snapshot.with_user(self.sales).has_access('read'))
        self.assertTrue(snapshot.with_user(replacement).has_access('read'))
        self.sales.write({'group_ids': [Command.link(self.env.ref('sales_team.group_sale_salesman_all_leads').id)]})
        self.assertFalse(snapshot.with_user(self.sales).has_access('read'))
        lead.unlink()
        self.assertFalse(snapshot.with_user(replacement).has_access('read'))
        self.assertFalse(snapshot.with_user(leader).has_access('read'))
        manager = new_test_user(self.env, login='forecast.manager', groups='sales_team.group_sale_manager')
        self.assertTrue(snapshot.with_user(manager).has_access('read'))

    def test_reviewer_can_approve_linked_quote_without_crm_access(self):
        lead = self.env['crm.lead'].create({'name': 'Private opportunity', 'type': 'opportunity',
            'user_id': self.sales.id, 'company_id': self.env.company.id})
        order = self.quote(discounts=(1,), opportunity_id=lead.id)
        order.action_submit_approvals()
        self.assertFalse(lead.with_user(self.sm).has_access('read'))
        self.assertTrue(order.with_user(self.sm).read(['name', 'opportunity_id']))
        order.sudo().approval_ids.with_user(self.sm).action_approve()
        self.assertEqual(order.sudo().approval_ids.status, 'approved')

    def test_dynamic_deal_labels_do_not_change_approval_fingerprint(self):
        deal = self.env['mobikey.deal.type'].create({'name': 'Corporate finance', 'code': 'corporate_finance'})
        term = self.env['account.payment.term'].create({'name': 'Corporate financed', 'financing_required': True})
        order = self.quote(deal_type=deal.code, payment_term_id=term.id)
        order.action_submit_approvals()
        fingerprint = order.sudo().approval_fingerprint
        financing = order.sudo().approval_ids.filtered(lambda approval: approval.category == 'financing')
        self.assertIn('Corporate finance', financing.preview_summary)
        deal.name = 'Business finance'
        self.assertEqual(order._commercial_fingerprint(), fingerprint)
        financing.invalidate_recordset(['preview_summary'])
        self.assertIn('Business finance', financing.preview_summary)

    def test_deal_option_retained_in_approval_history_cannot_be_deleted(self):
        option = self.env['mobikey.deal.type'].create({'name': 'Historical', 'code': 'historical'})
        order = self.quote()
        self.env['mobikey.sale.approval'].sudo().create({
            'order_id': order.id, 'revision': 1, 'category': 'financing', 'authority': 'finance',
            'requested_by': self.sales.id, 'financial_snapshot': {'preview': {'deal_type': option.code}},
        })
        with self.assertRaises(ValidationError):
            option.unlink()

    def test_snapshot_is_stable(self):
        lead = self.env['crm.lead'].create({'name': 'Forecast snapshot', 'type': 'opportunity',
            'company_id': self.env.company.id, 'user_id': self.sales.id, 'expected_revenue': 500, 'probability': 40})
        self.env['mobikey.forecast.snapshot'].sudo()._cron_snapshot()
        snapshot = self.env['mobikey.forecast.snapshot'].search([('lead_id', '=', lead.id)])
        self.assertEqual(snapshot.weighted_revenue, 200)
        lead.expected_revenue = 1000
        self.assertEqual(snapshot.expected_revenue, 500)

    @mute_logger('odoo.addons.mobikey_sale_approvals.hooks')
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

    def test_finance_only_reviewer_has_no_crm_or_quotation_edit_access(self):
        reviewer = new_test_user(self.env, login='workflow.review.only', groups='base.group_user')
        self.env.company.mobikey_finance_ids = [Command.set(reviewer.ids)]
        self.assertFalse(reviewer.has_group('sales_team.group_sale_salesman'))
        self.assertFalse(reviewer.has_group('mobikey_sale_approvals.group_financial_visibility'))
        lead = self.env['crm.lead'].create({
            'name': 'Assigned to finance but no CRM role', 'user_id': reviewer.id,
            'company_id': self.env.company.id,
        })
        team = self.env['crm.team'].create({'name': 'Finance led team', 'user_id': reviewer.id})
        lead.team_id = team
        self.assertFalse(lead.with_user(reviewer).has_access('read'))
        term = self.env['account.payment.term'].create({'name': 'Review-only financing', 'financing_required': True})
        order = self.quote(payment_term_id=term.id)
        unrelated = self.quote()
        order.action_submit_approvals()
        approval = order.sudo().approval_ids
        reviewed = order.with_user(reviewer)
        self.assertTrue(reviewed.has_access('read'))
        self.assertTrue(reviewed.order_line.has_access('read'))
        # Do not let computations cached during sudo setup mask missing ACLs.
        self.env.invalidate_all()
        form = Form(reviewed)
        self.assertEqual(form.partner_id, self.partner)
        self.assertEqual(Form(reviewed.order_line).name, reviewed.order_line.name)
        self.assertFalse(self.env['account.move'].with_user(reviewer).has_access('read'))
        self.assertFalse(self.env['stock.move'].with_user(reviewer).has_access('read'))
        self.assertFalse(unrelated.with_user(reviewer).has_access('read'))
        self.assertFalse(unrelated.order_line.with_user(reviewer).has_access('read'))
        self.assertEqual(self.env['sale.order'].with_user(reviewer).search([]), reviewed)
        # Exercise the fields used by the review form, not just the decision RPC.
        self.assertTrue(approval.with_user(reviewer).read([
            'order_id', 'preview_summary', 'can_decide', 'assigned_user_ids', 'workflow_state']))
        for model in (reviewed, reviewed.order_line):
            for operation in ('write', 'create', 'unlink'):
                self.assertFalse(model.has_access(operation), (model._name, operation))
        for action in (lambda: reviewed.write({'client_order_ref': 'Not permitted'}),
                       lambda: reviewed.order_line.write({'price_unit': 1}),
                       reviewed.action_revise_quotation, reviewed.action_confirm,
                       reviewed.action_quotation_send, lambda: reviewed.write({'state': 'cancel'})):
            with self.assertRaises(AccessError):
                action()
        self.assertEqual(approval.status, 'pending')
        with self.assertRaises(AccessError):
            approval.with_user(reviewer).read(['financial_snapshot'])
        reviewed.action_approve_current()
        self.assertEqual(approval.status, 'approved')
        self.assertEqual(approval.decided_by, reviewer)

    def test_review_only_request_changes_and_assignee_checks(self):
        order = self.quote((1,))
        order.action_submit_approvals()
        approval = order.sudo().approval_ids
        unrelated = self.quote((10,))
        unrelated.action_submit_approvals()
        foreign_approval = unrelated.sudo().approval_ids
        with self.assertRaises(AccessError):
            foreign_approval.with_user(self.sm).read(['status'])
        with self.assertRaises(AccessError):
            foreign_approval.with_user(self.sm).action_approve()
        self.assertEqual(self.env['mobikey.sale.approval'].with_user(self.sm).search([]), approval)
        action = approval.with_user(self.sm).action_request_changes()
        wizard = self.env['mobikey.sale.approval.request.changes'].with_user(self.sm).with_context(
            action['context']).create({'reason': 'Please revise the payment schedule.'})
        wizard.action_confirm()
        self.assertEqual(approval.status, 'rejected')
        self.assertEqual(approval.decided_by, self.sm)
        self.assertEqual(approval.change_request, 'Please revise the payment schedule.')
        with self.assertRaises(UserError):
            approval.with_user(self.sm).action_approve()

    def test_sales_and_review_permissions_remain_independent(self):
        self.sm.group_ids = [Command.link(self.env.ref('sales_team.group_sale_salesman').id)]
        own = self.quote()
        own.sudo().user_id = self.sm
        own.with_user(self.sm).write({'client_order_ref': 'My quotation'})
        reviewed = self.quote((1,))
        reviewed.action_submit_approvals()
        self.assertTrue(reviewed.with_user(self.sm).has_access('read'))
        self.assertFalse(reviewed.with_user(self.sm).has_access('write'))
        self.assertFalse(reviewed.order_line.with_user(self.sm).has_access('write'))
        reviewed.with_user(self.sm).action_approve_current()
        self.assertEqual(reviewed.approval_status, 'ready')

    def test_review_only_company_boundary_and_revoked_membership(self):
        order = self.quote((1,))
        order.action_submit_approvals()
        approval = order.sudo().approval_ids
        other = self.env['res.company'].create({'name': 'Other review company'})
        self.sm.company_ids = [Command.link(other.id)]
        restricted = self.sm.with_context(allowed_company_ids=other.ids)
        for record in (order, approval):
            with self.assertRaises(AccessError):
                record.with_user(restricted).with_context(allowed_company_ids=other.ids).read(['id'])
        with self.assertRaises(AccessError):
            order.with_user(self.sm).with_context(allowed_company_ids=other.ids).action_approve_current()
        with self.assertRaises(AccessError):
            approval.with_user(self.sm).with_context(allowed_company_ids=other.ids).action_approve()
        self.sm.group_ids = [Command.set(self.env.ref('base.group_user').ids)]
        with self.assertRaises(AccessError):
            approval.with_user(self.sm).action_approve()
        self.assertEqual(approval.status, 'pending')

    def test_removing_inherited_sales_keeps_explicit_sales_memberships(self):
        group = self.env.ref('mobikey_sale_approvals.group_approver')
        sales_group = self.env.ref('sales_team.group_sale_salesman')
        # Reproduce the previous version's implication, then its XML upgrade.
        group.implied_ids = [Command.link(sales_group.id)]
        self.assertTrue(self.finance.has_group('sales_team.group_sale_salesman'))
        self.sm.group_ids = [Command.link(sales_group.id)]
        group.implied_ids = [Command.unlink(sales_group.id)]
        self.assertFalse(self.finance.has_group('sales_team.group_sale_salesman'))
        self.assertTrue(self.sm.has_group('sales_team.group_sale_salesman'))
        self.assertTrue(self.finance.has_group('mobikey_sale_approvals.group_approver'))

    def test_approver_menu_is_available_without_sales(self):
        visible = self.env['ir.ui.menu'].with_user(self.finance)._visible_menu_ids()
        self.assertIn(self.env.ref('mobikey_sale_approvals.approval_root').id, visible)
        self.assertIn(self.env.ref('mobikey_sale_approvals.approval_inbox').id, visible)

    def test_empty_named_pools_never_route_to_legacy_roles(self):
        company = self.env.company
        company.write({field: [Command.clear()] for field in (
            'mobikey_sm_ids', 'mobikey_gm_ids', 'mobikey_hq_ids', 'mobikey_finance_ids',
            'mobikey_trade_in_approver_ids')})
        for role in ('sm', 'gm', 'hq', 'finance', 'trade_in_pool', 'gm|hq'):
            self.assertFalse(company._mobikey_approvers(role), role)
        term = self.env['account.payment.term'].create({'name': 'Named finance required', 'financing_required': True})
        for order in (self.quote((1,)), self.quote((3,)), self.quote((10,)),
                      self.quote(payment_term_id=term.id)):
            with self.assertRaisesRegex(UserError, 'Configure named approvers'):
                order.action_submit_approvals()
            self.assertFalse(order.approval_submitted)
            self.assertFalse(order.sudo().approval_ids)

    def test_named_authorities_do_not_require_legacy_roles(self):
        reviewer = new_test_user(self.env, login='workflow.named.only', groups='base.group_user')
        for key in ('sm', 'gm', 'hq', 'finance'):
            self.env.company[f'mobikey_{key}_ids'] = [Command.set(reviewer.ids)]
            self.assertEqual(self.env.company._mobikey_approvers(key), reviewer)
        self.assertEqual(self.env.company._mobikey_approvers('gm|hq'), reviewer)
        self.assertFalse(reviewer.has_group('mobikey_sale_approvals.group_financial_visibility'))
        reviewer.group_ids = [Command.set(self.env.ref('base.group_user').ids)]
        self.assertFalse(self.env.company._mobikey_approvers('finance'))

    def test_pending_decision_survives_clearing_the_named_matrix(self):
        order = self.quote((1,))
        order.action_submit_approvals()
        approval = order.sudo().approval_ids
        original_snapshot = approval.financial_snapshot
        self.env.company.mobikey_sm_ids = [Command.clear()]
        self.assertFalse(self.env.company._mobikey_approvers('sm'))
        self.assertEqual(approval.assigned_user_ids, self.sm)
        approval.with_user(self.sm).action_approve()
        self.assertEqual(approval.status, 'approved')
        self.assertEqual(approval.financial_snapshot, original_snapshot)

    def test_commission_waits_for_named_gm_or_hq(self):
        self.env.company.write({'mobikey_commission_milestone': 'confirmation',
            'mobikey_gm_ids': [Command.clear()], 'mobikey_hq_ids': [Command.clear()]})
        order = self.quote()
        order.action_confirm()
        self.assertFalse(order.sudo().approval_ids.filtered(lambda a: a.category == 'commission'))
        reviewer = new_test_user(self.env, login='workflow.named.commission', groups='base.group_user')
        self.env.company.mobikey_hq_ids = [Command.set(reviewer.ids)]
        order._ensure_commission_approval()
        approval = order.sudo().approval_ids.filtered(lambda a: a.category == 'commission')
        self.assertEqual(approval.assigned_user_ids, reviewer)
        order._ensure_commission_approval()
        self.assertEqual(len(order.sudo().approval_ids.filtered(lambda a: a.category == 'commission')), 1)
        approval.with_user(reviewer).action_approve()
        self.assertEqual(approval.status, 'approved')

    def test_legacy_approval_selectors_are_retired(self):
        hierarchy = self.env['res.groups']._get_view_group_hierarchy()
        for suffix in ('crm', 'finance'):
            privilege = self.env.ref(f'mobikey_crm.res_groups_{suffix}_approval_privilege')
            self.assertFalse(privilege.group_ids)
            self.assertFalse(hierarchy['privileges'][privilege.id]['group_ids'])
            for category in hierarchy['categories']:
                self.assertNotIn(privilege.id, category['privilege_ids'])
        # Existing technical membership still supports submitted decisions and costs.
        self.assertTrue(self.finance.has_group('mobikey_sale_approvals.group_approver'))
        self.assertTrue(self.finance.has_group('mobikey_sale_approvals.group_financial_visibility'))
