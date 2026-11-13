from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCrmViewAllRole(TransactionCase):
    """The View All Opportunities role widens CRM reads without manager rights."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env['res.company'].create({'name': 'View-all other company'})
        cls.gm = new_test_user(
            cls.env, login='viewall.gm',
            groups='sales_team.group_sale_salesman_all_leads,mobikey_crm.group_crm_view_all',
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        )
        cls.all_docs = new_test_user(
            cls.env, login='viewall.alldocs', groups='sales_team.group_sale_salesman_all_leads',
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        )
        cls.sales = new_test_user(cls.env, login='viewall.sales', groups='sales_team.group_sale_salesman')
        cls.peer = new_test_user(cls.env, login='viewall.peer', groups='sales_team.group_sale_salesman')
        cls.team = cls.env['crm.team'].create({
            'name': 'View-all team', 'user_id': cls.peer.id, 'company_id': cls.company.id,
        })
        cls.gm_team = cls.env['crm.team'].create({
            'name': 'GM team', 'user_id': cls.gm.id, 'company_id': cls.company.id,
        })
        cls.leads = cls.env['crm.lead'].create([
            {'name': 'Peer opportunity', 'type': 'opportunity', 'user_id': cls.peer.id,
             'team_id': cls.team.id, 'company_id': cls.company.id},
            {'name': 'Unassigned lead', 'type': 'lead', 'user_id': False,
             'team_id': False, 'company_id': cls.company.id},
            {'name': 'GM team opportunity', 'type': 'opportunity', 'user_id': cls.sales.id,
             'team_id': cls.gm_team.id, 'company_id': cls.company.id},
        ])
        cls.foreign_lead = cls.env['crm.lead'].create({
            'name': 'Other company opportunity', 'type': 'opportunity', 'user_id': False,
            'team_id': False, 'company_id': cls.other_company.id,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'View-all customer'})

    def visible(self, user):
        ids = (self.leads | self.foreign_lead).ids
        return self.env['crm.lead'].with_user(user).search([('id', 'in', ids)])

    def test_role_sees_all_company_leads_without_manager_rights(self):
        self.assertFalse(self.gm.has_group('sales_team.group_sale_manager'))
        self.assertEqual(self.visible(self.gm), self.leads)
        self.leads[0].with_user(self.gm).read(['name', 'expected_revenue'])
        with self.assertRaises(AccessError):
            self.foreign_lead.with_user(self.gm).read(['name'])
        # Native "All Documents" alone still follows the default team-led policy.
        self.assertFalse(self.visible(self.all_docs))

    def test_role_keeps_edit_reassign_and_delete_narrow(self):
        with self.assertRaises(AccessError):
            self.leads[0].with_user(self.gm).write({'name': 'Not allowed'})
        with self.assertRaises(AccessError):
            self.leads[0].with_user(self.gm).write({'user_id': self.gm.id})
        self.leads[2].with_user(self.gm).write({'name': 'Team led edit'})
        with self.assertRaises(AccessError):
            self.leads[2].with_user(self.gm).unlink()
        for model in ('crm.stage', 'crm.team', 'mobikey.crm.access.policy'):
            self.assertFalse(self.env[model].with_user(self.gm).has_access('write'), model)

    def test_opportunity_smart_button_respects_access(self):
        own_lead = self.env['crm.lead'].create({
            'name': 'Own opportunity', 'type': 'opportunity', 'user_id': self.sales.id,
        })
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'user_id': self.sales.id, 'opportunity_id': own_lead.id,
        })
        action = order.with_user(self.sales).action_open_opportunity()
        self.assertEqual((action['res_model'], action['res_id']), ('crm.lead', own_lead.id))

        unlinked = self.env['sale.order'].create({'partner_id': self.partner.id, 'user_id': self.sales.id})
        self.assertFalse(unlinked.with_user(self.sales).action_open_opportunity())

        hidden = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'user_id': self.sales.id, 'opportunity_id': self.leads[0].id,
        })
        with self.assertRaises(AccessError):
            hidden.with_user(self.sales).action_open_opportunity()
        action = hidden.with_user(self.gm).action_open_opportunity()
        self.assertEqual(action['res_id'], self.leads[0].id)

    def test_button_in_quotation_form(self):
        arch = self.env['sale.order'].with_user(self.sales).get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('action_open_opportunity', arch)
