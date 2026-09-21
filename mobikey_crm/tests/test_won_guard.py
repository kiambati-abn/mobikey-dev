from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestOpportunityWonGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Won Guard Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'Won Guard Vehicle',
            'list_price': 1000,
            'taxes_id': [Command.clear()],
        })
        cls.won_stage = cls.env['crm.stage'].create({
            'name': 'Won Guard Stage',
            'is_won': True,
        })
        cls.salesperson = new_test_user(
            cls.env,
            login='won.guard.salesperson',
            groups='sales_team.group_sale_salesman',
        )

    def _lead(self, name='Won Guard Opportunity'):
        return self.env['crm.lead'].create({
            'name': name,
            'type': 'opportunity',
            'partner_id': self.partner.id,
        })

    def _quotation(self, lead):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'opportunity_id': lead.id,
            'order_line': [Command.create({
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': 1000,
                'tax_ids': [Command.clear()],
            })],
        })

    def _assert_won_blocked(self, lead):
        with self.assertRaisesRegex(UserError, 'no confirmed quotation'):
            lead.write({'stage_id': self.won_stage.id})

    def test_won_blocked_without_quotation(self):
        self._assert_won_blocked(self._lead())

    def test_native_won_action_is_blocked_without_quotation(self):
        lead = self._lead()

        with self.assertRaisesRegex(UserError, 'no confirmed quotation'):
            lead.action_set_won()

    def test_won_blocked_with_draft_sent_or_cancelled_quotation(self):
        for state in ('draft', 'sent', 'cancel'):
            lead = self._lead('Opportunity with %s quotation' % state)
            quotation = self._quotation(lead)
            if state == 'sent':
                quotation.write({'state': 'sent'})
            elif state == 'cancel':
                quotation.action_cancel()
            self._assert_won_blocked(lead)

    def test_won_allowed_with_confirmed_quotation(self):
        lead = self._lead()
        self._quotation(lead).action_confirm()

        lead.write({'stage_id': self.won_stage.id})

        self.assertEqual(lead.stage_id, self.won_stage)
        self.assertEqual(lead.probability, 100)

    def test_unrelated_confirmed_quotation_does_not_allow_won(self):
        lead = self._lead('Opportunity without its own confirmed quotation')
        other_lead = self._lead('Other opportunity')
        self._quotation(other_lead).action_confirm()

        self._assert_won_blocked(lead)

    def test_opportunity_cannot_be_created_in_won_stage(self):
        with self.assertRaisesRegex(UserError, 'cannot be created as Won'):
            self.env['crm.lead'].create({
                'name': 'Direct Won Opportunity',
                'type': 'opportunity',
                'stage_id': self.won_stage.id,
            })

    def test_trusted_demo_load_can_mark_opportunity_won(self):
        lead = self._lead()

        lead.with_context(install_demo=True).action_set_won()

        self.assertEqual(lead.probability, 100)
        self.assertTrue(lead.stage_id.is_won)

    def test_normal_user_cannot_spoof_demo_load_context(self):
        lead = self._lead()
        lead.user_id = self.salesperson

        with self.assertRaisesRegex(UserError, 'no confirmed quotation'):
            lead.with_user(self.salesperson).with_context(install_demo=True).write({
                'stage_id': self.won_stage.id,
            })
