from lxml import etree

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged


@tagged('post_install', '-at_install')
class TestInvoicePermissions(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sales = new_test_user(cls.env, login='invoice.sales', groups='sales_team.group_sale_salesman')
        cls.billing = new_test_user(cls.env, login='invoice.billing',
            groups='sales_team.group_sale_salesman_all_leads,account.group_account_invoice')
        cls.reviewer = new_test_user(cls.env, login='invoice.reviewer',
            groups='mobikey_sale_approvals.group_approver')
        cls.product_a.write({'type': 'service', 'invoice_policy': 'order', 'taxes_id': [Command.clear()]})
        cls.env.company.mobikey_minimum_margin = 0
        cls.product_a.product_tmpl_id.mobikey_minimum_margin = 0

    def order(self):
        order = self.env['sale.order'].with_user(self.sales).create({
            'partner_id': self.partner_a.id, 'user_id': self.sales.id,
            'order_line': [Command.create({
                'product_id': self.product_a.id, 'product_uom_qty': 1, 'price_unit': 1000,
                'tax_ids': [Command.clear()],
            })],
        })
        self.assertFalse(order._approval_requirements())
        order.action_confirm()
        return order

    def wizard(self, order, user, method):
        return self.env['sale.advance.payment.inv'].with_user(user).create({
            'sale_order_ids': [Command.set(order.ids)],
            'advance_payment_method': method, 'amount': 10, 'fixed_amount': 100,
        })

    def test_sales_cannot_invoice_through_regular_or_down_payment_routes(self):
        order = self.order()
        original_lines = order.order_line.ids
        with self.assertRaises(AccessError):
            order._create_invoices()
        for method in ('delivered', 'percentage', 'fixed'):
            wizard = self.wizard(order, self.sales, method)
            with self.assertRaises(AccessError):
                wizard.create_invoices()
        self.assertEqual(order.order_line.ids, original_lines)
        self.assertFalse(order.sudo().invoice_ids)

    def test_billing_can_create_regular_and_down_payment_invoices(self):
        for method in ('delivered', 'percentage', 'fixed'):
            order = self.order()
            self.wizard(order, self.billing, method).create_invoices()
            invoice = order.sudo().invoice_ids
            self.assertEqual(len(invoice), 1)
            self.assertEqual(invoice.move_type, 'out_invoice')
            self.assertEqual(invoice.state, 'draft')
            self.assertEqual(invoice.amount_total, 1000 if method == 'delivered' else 100)
            # No new mandatory approval was introduced for rule-free orders.
            self.assertFalse(order.approval_submitted)

    def test_approver_role_does_not_grant_invoice_creation(self):
        order = self.order()
        self.assertFalse(self.env['account.move'].with_user(self.reviewer).has_access('create'))
        with self.assertRaises(AccessError):
            order.with_user(self.reviewer)._create_invoices()
        with self.assertRaises(AccessError):
            self.env['account.move'].with_user(self.reviewer).create({
                'move_type': 'out_invoice', 'partner_id': self.partner_a.id,
            })

    def test_form_and_batch_buttons_follow_rights_without_cache_leakage(self):
        action = str(self.env.ref('sale.action_view_sale_advance_payment_inv').id)
        # Alternate users against the same registry/view cache.
        for user, allowed in ((self.billing, True), (self.sales, False), (self.billing, True)):
            for view, view_type, expected in (
                ('sale.view_order_form', 'form', 2), ('sale.sale_order_tree', 'list', 1),
            ):
                result = self.env['sale.order'].with_user(user).get_view(
                    view_id=self.env.ref(view).id, view_type=view_type,
                )
                arch = etree.fromstring(result['arch'])
                buttons = arch.xpath('//button[@type="action"][@name=$name]', name=action)
                self.assertEqual(len(buttons), expected if allowed else 0)
            bindings = self.env['ir.actions.actions'].with_user(user).get_bindings('sale.order')
            self.assertEqual(int(action) in [item['id'] for item in bindings.get('action', [])], allowed)

    def test_new_accounting_grant_and_revocation_apply_immediately(self):
        order = self.order()
        group = self.env.ref('account.group_account_invoice')
        self.sales.group_ids = [Command.link(group.id)]
        self.assertTrue(self.env['account.move'].with_user(self.sales).has_access('create'))
        self.assertEqual(len(order._create_invoices()), 1)
        another = self.order()
        already_open_wizard = self.wizard(another, self.sales, 'percentage')
        self.sales.group_ids = [Command.unlink(group.id)]
        with self.assertRaises(AccessError):
            already_open_wizard.create_invoices()
