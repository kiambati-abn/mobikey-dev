from lxml import html as lxml_html

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
        cls.bank = cls.env['res.bank'].create({
            'name': 'Document Test Bank',
            'bic': 'DOCUTESTBIC',
        })
        cls.bank_account = cls.env['res.partner.bank'].create({
            'partner_id': cls.env.company.partner_id.id,
            'bank_id': cls.bank.id,
            'currency_id': cls.env.ref('base.USD').id,
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
            'model': 'TGA 26.360',
            'sale_ok': True,
            'list_price': 1000.0,
            'description_sale': 'Customer-facing vehicle observation.',
            'mobikey_document_brand_id': cls.brand.id,
            'mobikey_show_product_details': True,
            'mobikey_default_warranty': '24 months or 100,000 kilometres',
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
        self.assertEqual(line.mobikey_product_model, 'TGA 26.360')
        self.assertEqual(
            line.mobikey_observation,
            'Customer-facing vehicle observation.',
        )
        self.assertEqual(
            line.mobikey_warranty,
            '24 months or 100,000 kilometres',
        )
        self.assertEqual(
            [detail['label'] for detail in line.mobikey_detail_snapshot],
            ['Engine', 'Capacity'],
        )
        original_snapshot = line.mobikey_detail_snapshot
        original_model = line.mobikey_product_model
        original_observation = line.mobikey_observation
        original_warranty = line.mobikey_warranty
        self.product_template.model = 'Changed model'
        self.product_template.description_sale = 'Changed observation'
        self.product_template.mobikey_default_warranty = 'Changed warranty'
        self.product_template.mobikey_specification_line_ids[0].value = 'Electric'
        self.assertEqual(line.mobikey_detail_snapshot, original_snapshot)
        self.assertEqual(line.mobikey_product_model, original_model)
        self.assertEqual(line.mobikey_observation, original_observation)
        self.assertEqual(line.mobikey_warranty, original_warranty)

    def test_draft_observation_fallback_and_refresh(self):
        order = self._create_order()
        line = order.order_line
        line.mobikey_observation = False
        self.product_template.description_sale = 'Updated draft OBS text.'

        self.assertEqual(
            line._get_mobikey_report_observation(),
            'Updated draft OBS text.',
        )
        order.action_mobikey_refresh_document_details()
        self.assertEqual(line.mobikey_observation, 'Updated draft OBS text.')

        order.state = 'sent'
        with self.assertRaises(UserError):
            order.action_mobikey_refresh_document_details()

    def test_product_model_title_does_not_hide_model_variant(self):
        model_attribute = self.env['product.attribute'].create({
            'name': 'Model',
            'create_variant': 'always',
        })
        model_variant = self.env['product.attribute.value'].create({
            'name': 'HB4 / Flat Roof',
            'attribute_id': model_attribute.id,
        })
        variant_template = self.env['product.template'].create({
            'name': 'Variant Test Vehicle',
            'model': 'TGA 26.360',
            'sale_ok': True,
            'list_price': 1000.0,
            'mobikey_document_brand_id': self.brand.id,
            'mobikey_show_product_details': False,
            'attribute_line_ids': [Command.create({
                'attribute_id': model_attribute.id,
                'value_ids': [Command.set(model_variant.ids)],
            })],
        })
        product = variant_template.product_variant_id
        order = self._create_order(order_line=[Command.create({
            'product_id': product.id,
            'name': product.display_name,
            'product_uom_qty': 1.0,
            'product_uom_id': product.uom_id.id,
            'price_unit': 1000.0,
        })])

        self.assertEqual(order.order_line.mobikey_product_model, 'TGA 26.360')
        self.assertEqual(
            order._get_mobikey_characteristic_product_lines(),
            order.order_line,
        )
        self.assertIn(
            {'label': 'Model', 'value': 'HB4 / Flat Roof'},
            order.order_line.mobikey_detail_snapshot,
        )
        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        self.assertIn(b'TGA 26.360', report_html)
        self.assertIn(b'HB4 / Flat Roof', report_html)

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

    def test_all_characteristic_products_precede_one_commercial_section(self):
        second_main = self.product_template.copy({
            'name': 'Second Main Product',
            'model': 'MAIN MODEL TWO',
        })
        third_main = self.product_template.copy({
            'name': 'Third Main Product',
            'model': 'MAIN MODEL THREE',
        })
        extra = self.env['product.template'].create({
            'name': 'Identifiable Extra Product',
            'sale_ok': True,
            'list_price': 100.0,
            'description_sale': 'Extra sales description that must not print.',
            'mobikey_show_product_details': False,
        })
        products = (
            self.product_template.product_variant_id
            | second_main.product_variant_id
            | third_main.product_variant_id
            | extra.product_variant_id
        )
        order = self._create_order(order_line=[
            Command.create({
                'product_id': product.id,
                'name': '%s\n%s' % (
                    product.display_name,
                    product.description_sale or '',
                ),
                'product_uom_qty': 1.0,
                'product_uom_id': product.uom_id.id,
                'price_unit': product.list_price,
            })
            for product in products
        ])

        self.assertEqual(
            len(order._get_mobikey_characteristic_product_lines()),
            3,
        )
        self.assertEqual(
            order.order_line[-1]._get_mobikey_commercial_description(),
            extra.product_variant_id.display_name,
        )
        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        self.assertIn(b'MAIN MODEL TWO', report_html)
        self.assertIn(b'MAIN MODEL THREE', report_html)
        self.assertIn(b'Identifiable Extra Product', report_html)
        self.assertNotIn(b'Extra sales description that must not print.', report_html)

    def test_delivery_terms_and_date_are_both_rendered(self):
        order = self._create_order(
            mobikey_delivery_terms='Within three months',
            commitment_date='2026-09-15 08:00:00',
        )

        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        self.assertIn(b'Delivery Terms', report_html)
        self.assertIn(b'Within three months', report_html)
        self.assertIn(b'Expected Delivery Date', report_html)

    def test_bank_accounts_are_grouped_by_bank_and_currency(self):
        euro_account = self.env['res.partner.bank'].create({
            'partner_id': self.env.company.partner_id.id,
            'bank_id': self.bank.id,
            'currency_id': self.env.ref('base.EUR').id,
            'acc_number': 'MOBIKEY-EUR-TEST',
        })
        order = self._create_order(
            mobikey_bank_account_ids=[Command.set(
                (self.bank_account | euro_account).ids
            )],
        )

        groups = order._get_mobikey_bank_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['bank_name'], 'Document Test Bank')
        self.assertEqual(
            [account['currency'] for account in groups[0]['accounts']],
            ['USD', 'EUR'],
        )

    def test_header_contains_only_logos_and_uses_multi_brand_sizes(self):
        second_brand = self.env['mobikey.document.brand'].create({
            'name': 'Second Header Brand',
            'logo': self.brand.logo,
        })
        self.document_template.write({
            'brand_ids': [Command.set((self.brand | second_brand).ids)],
        })
        order = self._create_order()
        self.env.company.write({
            'city': 'Nairobi',
            'country_id': self.env.ref('base.ke').id,
        })

        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        tree = lxml_html.fromstring(report_html)
        header = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' header ')]"
        )[0]
        self.assertEqual(len(header.xpath('.//img')), 3)
        self.assertNotIn(self.env.company.name, header.text_content())
        self.assertIn('max-width: 60mm', report_html.decode())
        self.assertIn('max-width: 42mm', report_html.decode())
        self.assertIn(b'Nairobi, Kenya', report_html)

    def test_template_logo_size_choices_are_bounded(self):
        self.document_template.write({
            'issuer_logo_size': 'large',
            'manufacturer_logo_size': 'large',
        })

        single_brand = self.document_template._get_mobikey_logo_dimensions(1)
        self.assertEqual(single_brand['issuer_width'], 75)
        self.assertEqual(single_brand['issuer_height'], 21)
        self.assertEqual(single_brand['brand_width'], 60)
        self.assertEqual(single_brand['brand_height'], 19)

        four_brands = self.document_template._get_mobikey_logo_dimensions(4)
        self.assertEqual(four_brands['brand_width'], 20)
        self.assertEqual(four_brands['brand_height'], 9)

    def test_native_report_renders_custom_dispatch(self):
        order = self._create_order()

        html, report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )

        self.assertEqual(report_type, 'html')
        self.assertIn(b'Description and Product Characteristics', html)
        self.assertIn(b'Test Manufacturer', html)
        self.assertIn(b'TGA 26.360', html)
        self.assertIn(b'OBS:', html)
        self.assertIn(b'Customer-facing vehicle observation.', html)

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
        self.assertNotIn(b'Description and Product Characteristics', html)
        self.assertIn(b'Quotation', html)
