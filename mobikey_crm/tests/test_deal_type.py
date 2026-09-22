from odoo.exceptions import AccessError, ValidationError
from lxml import etree
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDealType(TransactionCase):
    def test_opportunity_lookup_edit_search_and_financing(self):
        user = new_test_user(self.env, login='deal.lookup.sales', groups='sales_team.group_sale_salesman')
        cash = self.env.ref('mobikey_crm.deal_type_cash')
        financing = self.env.ref('mobikey_crm.deal_type_financing')
        lead = self.env['crm.lead'].with_user(user).create({
            'name': 'Editable opportunity', 'type': 'opportunity', 'deal_type': 'cash',
        })
        self.assertEqual(lead.deal_type_id, cash)
        with Form(lead) as form:
            form.deal_type_id = financing
            self.assertTrue(form.financing_required)
        lead.invalidate_recordset()
        self.assertEqual(lead.deal_type, 'financing')
        self.assertEqual(lead.deal_type_id, financing)
        self.assertTrue(lead.financing_required)
        self.assertEqual(lead._prepare_opportunity_quotation_context()['default_deal_type'], 'financing')
        self.assertIn(financing.id, [item[0] for item in self.env['mobikey.deal.type'].with_user(user).name_search('Financ')])

        # A native many2one supplies Search More and checks the catalogue ACLs
        # for Create and Edit. Quick-create is disabled because code is required.
        arch = etree.fromstring(lead.get_view(view_type='form')['arch'])
        field = arch.xpath('//field[@name="deal_type_id"]')[0]
        self.assertNotEqual(field.get('readonly'), '1')
        self.assertEqual(field.get('can_create'), 'False')
        self.assertEqual(field.get('can_write'), 'False')

    def test_manager_can_add_option_and_select_it_on_opportunity(self):
        manager = new_test_user(self.env, login='deal.lookup.manager', groups='sales_team.group_sale_manager')
        with Form(self.env['mobikey.deal.type'].with_user(manager)) as option_form:
            option_form.name = 'Corporate leasing'
            option_form.code = 'corporate_leasing'
        option = option_form.record
        lead = self.env['crm.lead'].with_user(manager).create({'name': 'Corporate', 'type': 'opportunity'})
        with Form(lead) as form:
            form.deal_type_id = option
        self.assertEqual(lead.deal_type, 'corporate_leasing')
        self.assertEqual(lead.deal_type_id, option)
        arch = etree.fromstring(lead.get_view(view_type='form')['arch'])
        field = arch.xpath('//field[@name="deal_type_id"]')[0]
        self.assertEqual(field.get('can_create'), 'True')
        self.assertEqual(field.get('can_write'), 'True')

    def test_lookup_api_and_legacy_values_stay_synchronized(self):
        cash = self.env.ref('mobikey_crm.deal_type_cash')
        fleet = self.env.ref('mobikey_crm.deal_type_fleet')
        financing = self.env.ref('mobikey_crm.deal_type_financing')
        lead = self.env['crm.lead'].create({'name': 'Lookup import', 'deal_type_id': financing.id})
        self.assertEqual(lead.deal_type, 'financing')
        self.assertTrue(lead.financing_required)
        lead.write({'deal_type': 'fleet'})
        self.assertEqual(lead.deal_type_id, fleet)
        lead.write({'deal_type_id': cash.id})
        self.assertEqual(lead.deal_type, 'cash')
        copied = lead.copy()
        self.assertEqual(copied.deal_type_id, cash)
        lead.write({'deal_type_id': False})
        self.assertFalse(lead.deal_type)
        self.assertFalse(lead.deal_type_id)
        with self.assertRaises(ValidationError):
            lead.write({'deal_type': 'cash', 'deal_type_id': financing.id})
        with self.assertRaises(ValidationError):
            lead.write({'deal_type_id': 2147483647})

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
