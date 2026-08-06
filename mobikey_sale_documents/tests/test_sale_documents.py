from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMobikeySaleDocuments(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({
            'name': 'Document Test Customer',
        })
        cls.brand = cls.env['mobikey.document.brand'].create({
            'name': 'Test Manufacturer',
            'logo': (
                b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC'
                b'AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
            ),
        })
        cls.bank_account = cls.env['res.partner.bank'].create({
            'partner_id': cls.env.company.partner_id.id,
            'acc_number': 'MOBIKEY-DOCUMENT-TEST',
        })
        cls.document_template = cls.env['mobikey.document.template'].create({
            'name': 'Test Branded Proforma',
            'company_id': cls.env.company.id,
            'brand_source': 'template',
            'brand_ids': [Command.set(cls.brand.ids)],
            'bank_account_ids': [Command.set(cls.bank_account.ids)],
            'terms_html': '<p>Test commercial terms.</p>',
        })
        cls.product_template = cls.env['product.template'].create({
            'name': 'Test Vehicle',
            'sale_ok': True,
            'list_price': 1000.0,
            'mobikey_document_brand_id': cls.brand.id,
            'mobikey_show_product_details': True,
            'mobikey_default_warranty': '24 months',
            'mobikey_quotation_description': '<p>Customer-facing vehicle description.</p>',
            'mobikey_specification_line_ids': [
                Command.create({
                    'sequence': 10,
                    'name': 'Engine',
                    'value': 'Diesel',
                }),
                Command.create({
                    'sequence': 20,
                    'name': 'Capacity',
                    'value': '30',
                    'unit': 'tonnes',
                }),
            ],
        })

    def _create_order(self, order_model=None, **extra_values):
        product = self.product_template.product_variant_id
        if order_model is None:
            order_model = self.env['sale.order']
        values = {
            'partner_id': self.customer.id,
            'company_id': self.env.company.id,
            'mobikey_document_template_id': self.document_template.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'name': product.display_name,
                'product_uom_qty': 2.0,
                'product_uom_id': product.uom_id.id,
                'price_unit': 1000.0,
                'discount': 10.0,
            })],
        }
        values.update(extra_values)
        return order_model.create(values)

    def test_template_values_and_discount_are_copied(self):
        order = self._create_order()

        self.assertEqual(order.mobikey_terms_html, self.document_template.terms_html)
        self.assertEqual(order.mobikey_bank_account_ids, self.bank_account)
        self.assertEqual(order.mobikey_brand_ids, self.brand)
        self.assertEqual(order.mobikey_discount_total, 200.0)

    def test_product_detail_values_are_snapshotted(self):
        order = self._create_order()
        line = order.order_line

        self.assertTrue(line.mobikey_show_product_details)
        self.assertEqual(line.mobikey_warranty, '24 months')
        self.assertEqual(
            [detail['label'] for detail in line.mobikey_detail_snapshot],
            ['Engine', 'Capacity'],
        )
        original_snapshot = line.mobikey_detail_snapshot
        self.product_template.mobikey_specification_line_ids[0].value = 'Electric'
        self.assertEqual(line.mobikey_detail_snapshot, original_snapshot)

    def test_product_brands_support_multi_brand_orders(self):
        second_brand = self.env['mobikey.document.brand'].create({
            'name': 'Test Trailer Manufacturer',
            'logo': self.brand.logo,
        })
        trailer = self.env['product.product'].create({
            'name': 'Test Trailer',
            'sale_ok': True,
            'list_price': 500.0,
            'mobikey_document_brand_id': second_brand.id,
        })
        product_brand_template = self.document_template.copy({
            'name': 'Automatic Product Brands',
            'brand_source': 'order',
            'brand_ids': [Command.clear()],
        })
        order = self._create_order(
            mobikey_document_template_id=product_brand_template.id,
        )
        order.write({
            'order_line': [Command.create({
                'product_id': trailer.id,
                'name': trailer.display_name,
                'product_uom_qty': 1.0,
                'product_uom_id': trailer.uom_id.id,
                'price_unit': 500.0,
            })],
        })

        self.assertEqual(order._get_mobikey_report_brands(), self.brand | second_brand)

    def test_cross_company_template_is_rejected(self):
        other_company = self.env['res.company'].create({'name': 'Other Company'})
        self.env.user.write({'company_ids': [Command.link(other_company.id)]})
        allowed_companies = [self.env.company.id, other_company.id]
        other_template = self.document_template.with_context(
            allowed_company_ids=allowed_companies,
        ).copy({
            'name': 'Other Company Proforma',
            'company_id': other_company.id,
            'bank_account_ids': [Command.clear()],
        })
        order_model = self.env['sale.order'].with_context(
            allowed_company_ids=allowed_companies,
        )

        with self.assertRaises(UserError):
            self._create_order(
                order_model=order_model,
                mobikey_document_template_id=other_template.id,
            )

    def test_native_report_renders_custom_dispatch(self):
        order = self._create_order()

        html, report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )

        self.assertEqual(report_type, 'html')
        self.assertIn(b'Description and Main Product Characteristics', html)
        self.assertIn(b'Test Manufacturer', html)

        proforma_html, proforma_report_type = (
            self.env['ir.actions.report']._render_qweb_html(
                'sale.action_report_pro_forma_invoice',
                order.ids,
            )
        )
        self.assertEqual(proforma_report_type, 'html')
        self.assertIn(b'Proforma Invoice', proforma_html)

    def test_native_report_is_retained_without_selection(self):
        order = self._create_order(mobikey_document_template_id=False)

        html, report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )

        self.assertEqual(report_type, 'html')
        self.assertNotIn(b'Description and Main Product Characteristics', html)
        self.assertIn(b'Quotation', html)
