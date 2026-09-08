import json
from odoo import Command
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestApprovalPortal(HttpCase):
    def test_existing_token_cannot_issue_sign_or_pay_unapproved_offer(self):
        partner = self.env['res.partner'].create({'name': 'Portal approval customer'})
        product = self.env['product.product'].create({'name': 'Portal approval product'})
        order = self.env['sale.order'].create({'partner_id': partner.id,
            'order_line': [Command.create({'product_id': product.id, 'price_unit': 1000,
                                          'product_uom_qty': 1, 'discount': 10})]})
        token = order._portal_ensure_token()
        response = self.url_open(f'/my/orders/{order.id}?access_token={token}')
        self.assertNotIn(b'Portal approval product', response.content)
        for suffix, params in [('accept', {'name': 'Customer', 'signature': 'dGVzdA=='}), ('transaction', {})]:
            params.update(access_token=token)
            response = self.url_open(f'/my/orders/{order.id}/{suffix}', data=json.dumps({
                'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params}),
                headers={'Content-Type': 'application/json'})
            payload = response.json()
            self.assertTrue(payload.get('error') or payload.get('result', {}).get('error'))
        order.invalidate_recordset()
        self.assertFalse(order.signature)
        self.assertFalse(order.transaction_ids)
        self.assertEqual(order.state, 'draft')
