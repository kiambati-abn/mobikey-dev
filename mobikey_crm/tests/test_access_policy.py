from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCrmAccessPolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sales = new_test_user(cls.env, login='policy.sales', groups='sales_team.group_sale_salesman')
        cls.peer = new_test_user(cls.env, login='policy.peer', groups='sales_team.group_sale_salesman')
        cls.leader = new_test_user(cls.env, login='policy.leader', groups='sales_team.group_sale_salesman')
        cls.manager = new_test_user(cls.env, login='policy.manager', groups='sales_team.group_sale_manager')
        cls.admin = new_test_user(cls.env, login='policy.admin', groups='base.group_system')
        cls.internal = new_test_user(cls.env, login='policy.internal', groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='policy.portal', groups='base.group_portal')
        cls.team = cls.env['crm.team'].create({'name': 'Policy A', 'user_id': cls.leader.id,
            'company_id': cls.env.company.id, 'member_ids': [Command.set(cls.sales.ids)]})
        cls.other_team = cls.env['crm.team'].create({'name': 'Policy B', 'user_id': cls.manager.id,
            'company_id': cls.env.company.id})
        cls.leads = cls.env['crm.lead'].create([
            {'name': 'Policy own', 'type': 'lead', 'user_id': cls.sales.id, 'team_id': cls.team.id},
            {'name': 'Policy colleague', 'type': 'opportunity', 'user_id': cls.peer.id, 'team_id': cls.team.id},
            {'name': 'Policy unassigned team', 'type': 'lead', 'user_id': False, 'team_id': cls.team.id},
            {'name': 'Policy other team', 'type': 'opportunity', 'user_id': cls.peer.id, 'team_id': cls.other_team.id},
            {'name': 'Policy cross-team assignee', 'type': 'lead', 'user_id': cls.sales.id, 'team_id': cls.other_team.id},
            {'name': 'Policy no team', 'type': 'lead', 'user_id': False, 'team_id': False},
        ])

    def visible(self, user):
        return self.env['crm.lead'].with_user(user).search([('id', 'in', self.leads.ids)])

    def test_default_matrix_and_direct_access(self):
        self.assertEqual(set(self.visible(self.sales).ids), {self.leads[0].id, self.leads[4].id})
        self.assertEqual(set(self.visible(self.leader).ids), set(self.leads[:3].ids))
        for user in (self.manager, self.admin):
            self.assertEqual(set(self.visible(user).ids), set(self.leads.ids))
        for user in (self.internal, self.portal):
            with self.assertRaises(AccessError):
                self.leads[0].with_user(user).read(['name'])
        with self.assertRaises(AccessError):
            self.leads[1].with_user(self.sales).read(['name'])
        self.leads[1].with_user(self.leader).write({'name': 'Team edit'})
        with self.assertRaises(AccessError):
            self.leads[3].with_user(self.leader).write({'name': 'Forbidden edit'})
        with self.assertRaises(AccessError):
            self.leads[0].with_user(self.sales).unlink()

    def test_broad_group_and_follower_do_not_bypass_policy(self):
        self.sales.write({'group_ids': [
            Command.link(self.env.ref('sales_team.group_sale_salesman_all_leads').id),
            Command.link(self.env.ref('base.group_allow_export').id),
        ]})
        self.leads[3].message_subscribe(self.sales.partner_id.ids)
        self.env['ir.rule'].create({'name': 'Legacy unlimited CRM', 'model_id': self.env['ir.model']._get_id('crm.lead'),
            'groups': [Command.set(self.env.ref('sales_team.group_sale_salesman').ids)], 'domain_force': '[(1,"=",1)]'})
        self.assertEqual(set(self.visible(self.sales).ids), {self.leads[0].id, self.leads[4].id})
        with self.assertRaises(AccessError):
            self.leads[3].with_user(self.sales).export_data(['name'])
        self.assertEqual(self.env['crm.lead'].with_user(self.sales).search_count([('id', 'in', self.leads.ids)]), 2)

    def test_policy_changes_refresh_cached_permissions(self):
        policy = self.env.ref('mobikey_crm.crm_policy_sales')
        self.visible(self.leader)  # warm ir.rule cache
        policy.write({'write_scope': 'own', 'reassign_scope': 'none', 'unlink_scope': 'none'})
        self.assertEqual(len(self.visible(self.leader)), 3)
        with self.assertRaises(AccessError):
            self.leads[1].with_user(self.leader).write({'name': 'Now read only'})
        with self.assertRaises(AccessError):
            self.leads[0].with_user(self.sales).write({'user_id': self.peer.id})
        policy.write({f'{operation}_scope': 'member' for operation in ('read', 'write', 'create', 'unlink', 'reassign')})
        self.assertIn(self.leads[1], self.visible(self.sales))
        self.team.member_ids = [Command.clear()]
        self.assertNotIn(self.leads[1], self.visible(self.sales))
        policy.active = False
        self.assertFalse(self.visible(self.sales))
        self.assertFalse(self.sales.with_context(active_test=False)._mobikey_crm_scopes('reassign'))
        self.assertEqual(len(self.visible(self.admin)), 6)
        self.assertTrue(policy.message_ids)

    def test_policy_configuration_is_admin_only(self):
        policy = self.env.ref('mobikey_crm.crm_policy_sales')
        for user in (self.sales, self.leader, self.manager):
            with self.assertRaises(AccessError):
                policy.with_user(user).write({'read_scope': 'all'})
        with self.assertRaises(ValidationError):
            policy.write({'read_scope': 'own', 'write_scope': 'all'})

    def test_reassignment_and_multiple_team_leadership(self):
        self.leads[1].with_user(self.leader).write({'user_id': self.sales.id})
        self.assertIn(self.leads[1], self.visible(self.sales))
        self.other_team.user_id = self.leader
        self.assertIn(self.leads[3], self.visible(self.leader))
        self.team.user_id = self.manager
        self.assertNotIn(self.leads[1], self.visible(self.leader))
        # Reassigning an owned record is allowed, but does not leave residual access.
        self.leads[0].with_user(self.sales).write({'user_id': self.peer.id})
        self.assertNotIn(self.leads[0], self.visible(self.sales))

    def test_create_scope_and_company_boundary(self):
        self.env['crm.lead'].with_user(self.sales).create({'name': 'Own creation', 'user_id': self.sales.id})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['crm.lead'].with_user(self.sales).create({'name': 'Other creation', 'user_id': self.peer.id,
                'team_id': self.other_team.id})
        other_company = self.env['res.company'].create({'name': 'Policy Restricted Company'})
        self.sales.company_ids = [Command.link(other_company.id)]
        foreign = self.env['crm.lead'].create({'name': 'Foreign assignment', 'company_id': other_company.id,
            'user_id': self.sales.id, 'team_id': False})
        for user in (self.sales, self.manager, self.admin):
            with self.assertRaises(AccessError):
                foreign.with_user(user).with_context(allowed_company_ids=self.env.company.ids).read(['name'])
        self.assertTrue(foreign.with_user(self.sales).with_context(allowed_company_ids=other_company.ids).has_access('read'))

    def test_product_lines_follow_parent_and_reject_orphans(self):
        lines = self.env['crm.product.lines'].create([{'lead_id': lead.id} for lead in self.leads])
        self.assertEqual(set(lines.with_user(self.sales).search([('id', 'in', lines.ids)]).ids),
                         {lines[0].id, lines[4].id})
        with self.assertRaises(AccessError):
            lines[1].with_user(self.sales).read(['quantity'])
        with self.assertRaises(AccessError):
            lines[0].with_user(self.internal).read(['quantity'])
        with self.assertRaises(AccessError):
            lines[0].with_user(self.sales).write({'lead_id': self.leads[1].id})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['crm.product.lines'].with_user(self.sales).create({'quantity': 2})

    def test_activity_analysis_follows_current_lead_access(self):
        for lead in self.leads:
            lead.message_post(body='Completed activity', mail_activity_type_id=self.env.ref('mail.mail_activity_data_todo').id)
        reports = self.env['crm.activity.report'].with_user(self.sales).search([('lead_id', 'in', self.leads.ids)])
        self.assertEqual(set(reports.mapped('lead_id').ids), {self.leads[0].id, self.leads[4].id})
