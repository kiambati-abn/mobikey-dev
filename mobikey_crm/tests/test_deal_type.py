from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDealType(TransactionCase):
    def test_configurable_options_preserve_wire_values(self):
        manager = new_test_user(self.env, login='deal.manager', groups='sales_team.group_sale_manager')
        user = new_test_user(self.env, login='deal.sales', groups='sales_team.group_sale_salesman')
        option = self.env['mobikey.deal.type'].with_user(manager).create({'name': 'Corporate', 'code': 'corporate'})
        lead = self.env['crm.lead'].with_user(user).create({'name': 'Corporate deal', 'deal_type': 'corporate'})
        self.assertEqual(lead.deal_type, 'corporate')
        self.assertFalse(lead.financing_required)
        option.write({'name': 'Corporate Sales', 'sequence': 1})
        for model in ('crm.lead', 'sale.order'):
            choices = dict(self.env[model].with_user(user).fields_get(['deal_type'])['deal_type']['selection'])
            self.assertEqual(choices['corporate'], 'Corporate Sales')
            self.assertEqual(choices['financing'], 'Financing')
        self.assertEqual(lead._prepare_opportunity_quotation_context()['default_deal_type'], 'corporate')
        with self.assertRaises(ValidationError):
            option.write({'code': 'changed'})
        with self.assertRaises(ValidationError):
            option.unlink()
        with self.assertRaises(AccessError):
            option.with_user(user).write({'name': 'Unauthorized'})
        with self.assertRaises(AccessError):
            self.env['mobikey.deal.type'].with_user(user).create({'name': 'Unauthorized', 'code': 'unauthorized'})

    def test_builtin_protection_and_validation(self):
        with self.assertRaises(ValidationError):
            self.env.ref('mobikey_crm.deal_type_financing').unlink()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['mobikey.deal.type'].create({'name': 'Invalid', 'code': 'Invalid Code'})
        disposable = self.env['mobikey.deal.type'].create({'name': 'Unused', 'code': 'unused'})
        disposable.unlink()

    def test_removed_walkin_mapping_is_absent_from_form(self):
        arch = self.env['crm.lead'].get_view(view_id=self.env.ref('crm.crm_lead_view_form').id)['arch']
        self.assertNotIn('name="walkin_company_id"', arch)
        self.assertNotIn('name="available_walkin_company_ids"', arch)
