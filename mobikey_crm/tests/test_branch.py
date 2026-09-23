from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged, new_test_user
from odoo.addons.mobikey_crm.models.branch import migrate_legacy_branches


@tagged('post_install', '-at_install')
class TestBranch(TransactionCase):
    def test_configuration_access_and_archive(self):
        manager = new_test_user(self.env, login='branch.manager', groups='sales_team.group_sale_manager')
        seller = new_test_user(self.env, login='branch.seller', groups='sales_team.group_sale_salesman')
        branch = self.env['mobikey.branch'].with_user(manager).create({'name': 'Showroom'})
        lead = self.env['crm.lead'].with_user(seller).create({'name': 'Walk-in', 'branch_id': branch.id})
        self.assertEqual(lead.branch_id.name, 'Showroom')
        with self.assertRaises(AccessError):
            branch.with_user(seller).write({'name': 'Changed'})
        with self.assertRaises(AccessError):
            self.env['mobikey.branch'].with_user(seller).create({'name': 'Unauthorized'})
        branch.action_archive()
        self.assertEqual(lead.branch_id, branch)
        self.assertNotIn(branch, self.env['mobikey.branch'].with_user(seller).search([]))
        other = self.env['res.company'].create({'name': 'Other branch company'})
        foreign = self.env['mobikey.branch'].create({'name': 'Foreign', 'company_id': other.id})
        self.assertNotIn(foreign, self.env['mobikey.branch'].with_user(seller).search([]))

    def test_legacy_assignments_migrate_once_including_archived_leads(self):
        lead = self.env['crm.lead'].create({'name': 'Legacy walk-in', 'active': False,
                                           'walkin_company_id': self.env.company.id})
        location = self.env['stock.location'].create({'name': 'Legacy showroom', 'usage': 'internal',
                                                     'company_id': self.env.company.id})
        location_lead = self.env['crm.lead'].create({'name': 'Legacy location', 'walkin_location': location.id})
        migrate_legacy_branches(self.env)
        self.assertEqual(lead.branch_id.name, self.env.company.name)
        self.assertEqual(location_lead.branch_id.name, 'Legacy showroom')
        self.assertEqual(location_lead.branch_id.company_id, self.env.company)
        original = lead.branch_id | location_lead.branch_id
        migrate_legacy_branches(self.env)
        self.assertEqual(original, lead.branch_id | location_lead.branch_id)
        self.assertEqual(lead.walkin_company_id, self.env.company)
