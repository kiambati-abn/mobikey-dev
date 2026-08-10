from lxml import html as lxml_html

from odoo.exceptions import UserError, ValidationError
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
            'color_scheme': 'blue_green',
            'primary_color': '#305496',
            'accent_color': '#A9D08E',
            'body_text_color': '#222222',
            'muted_text_color': '#666666',
            'light_background_color': '#E5F1DD',
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

    def test_template_payment_brand_values_and_discount_are_copied(self):
        order = self._create_order()

        self.assertFalse(order.mobikey_terms_html)
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

    def test_display_obs_is_enabled_by_default(self):
        product_template = self.env['product.template'].create({
            'name': 'Default OBS Product',
            'sale_ok': True,
            'description_sale': 'Visible by default.',
        })
        product = product_template.product_variant_id
        order = self._create_order(order_line=[Command.create({
            'product_id': product.id,
            'name': product.display_name,
            'product_uom_qty': 1.0,
            'product_uom_id': product.uom_id.id,
            'price_unit': 100.0,
        })])

        self.assertTrue(product_template.mobikey_show_product_details)
        self.assertTrue(order.order_line.mobikey_show_product_details)
        self.assertEqual(
            order.order_line._get_mobikey_report_observation(),
            'Visible by default.',
        )

    def test_disabling_obs_keeps_specs_and_warranty_visible(self):
        order = self._create_order()
        line = order.order_line
        line.mobikey_show_product_details = False

        self.assertFalse(line._get_mobikey_report_observation())
        self.assertTrue(line._has_mobikey_characteristics())
        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        self.assertNotIn(b'Customer-facing vehicle observation.', report_html)
        self.assertIn(b'Engine', report_html)
        self.assertIn(b'Diesel', report_html)
        self.assertIn(b'24 months or 100,000 kilometres', report_html)

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
        tree = lxml_html.fromstring(report_html)
        rows = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-payment-row ')]"
        )
        self.assertGreaterEqual(len(rows), 2)
        self.assertIn('background: #FFFFFF', rows[0].attrib['style'])
        self.assertIn('background: #F2F8EE', rows[1].attrib['style'])

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

        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        self.assertIn(b'Account Numbers', report_html)
        self.assertIn(b'Account Holder:', report_html)
        self.assertIn(b'MOBIKEY-DOCUMENT-TEST', report_html)
        self.assertIn(b'MOBIKEY-EUR-TEST', report_html)
        tree = lxml_html.fromstring(report_html)
        bank_groups = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-bank-group ')]"
        )
        self.assertEqual(len(bank_groups), 1)
        self.assertFalse(bank_groups[0].xpath('.//table'))

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
        footer = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' footer ')]"
        )[0]
        self.assertEqual(len(header.xpath('.//img')), 3)
        self.assertFalse(header.xpath('.//table'))
        self.assertFalse(footer.xpath('.//table'))
        self.assertIn('min-height: 24mm', footer.attrib['style'])
        self.assertIn('line-height: 1.35', footer.attrib['style'])
        footer_content = footer.xpath('./div')[0]
        self.assertIn('padding-top: 3.5mm', footer_content.attrib['style'])
        self.assertNotIn(self.env.company.name, header.text_content())
        self.assertIn('height: 23mm; line-height: 23mm', report_html.decode())
        self.assertIn('max-width: 60mm', report_html.decode())
        self.assertIn('max-width: 42mm', report_html.decode())
        self.assertIn('background: #E5F1DD', report_html.decode())
        article = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' article ')]"
        )[0]
        self.assertNotIn('Nairobi, Kenya', article.text_content())
        self.assertIn('Nairobi', footer.text_content())
        self.assertIn('Kenya', footer.text_content())

    def test_template_logo_size_and_color_choices_are_bounded(self):
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
        self.assertEqual(
            self.document_template._get_mobikey_accent_tint(),
            '#E5F1DD',
        )
        self.assertEqual(
            self.document_template._get_mobikey_accent_stripe(),
            '#F2F8EE',
        )

    def test_color_schemes_fallbacks_and_contrast_are_complete(self):
        mobikey_template = self.document_template.copy({
            'name': 'Mobikey Brand Colors',
            'color_scheme': 'mobikey',
        })
        mobikey_template.action_restore_color_scheme_defaults()

        self.assertEqual(mobikey_template.primary_color, '#323C48')
        self.assertEqual(mobikey_template.accent_color, '#D32D49')
        self.assertEqual(mobikey_template.light_background_color, '#F0F1F3')
        self.assertIn('Primary', mobikey_template.palette_preview)
        self.assertIn('#323C48', mobikey_template.palette_preview)
        self.assertEqual(
            mobikey_template._get_mobikey_palette()['primary_foreground'],
            '#FFFFFF',
        )

        mobikey_template.write({
            'color_scheme': 'custom',
            'primary_color': '#FFFFFF',
            'accent_color': '#000000',
            'body_text_color': False,
            'muted_text_color': False,
            'light_background_color': False,
        })
        palette = mobikey_template._get_mobikey_palette()
        self.assertEqual(palette['body'], '#222222')
        self.assertEqual(palette['muted'], '#666666')
        self.assertEqual(palette['light_background'], '#B2B2B2')
        self.assertEqual(palette['stripe'], '#D9D9D9')
        self.assertEqual(palette['primary_foreground'], '#000000')
        self.assertEqual(palette['accent_foreground'], '#FFFFFF')

        mobikey_template.color_scheme = 'blue_green'
        mobikey_template._onchange_color_scheme()
        self.assertEqual(mobikey_template.primary_color, '#305496')
        self.assertEqual(mobikey_template.accent_color, '#A9D08E')
        self.assertEqual(mobikey_template.light_background_color, '#E5F1DD')

    def test_document_summary_order_and_validity_visibility(self):
        order = self._create_order(
            validity_date='2026-08-31',
            client_order_ref='CUSTOMER-REF-42',
        )

        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        tree = lxml_html.fromstring(report_html)
        summary = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-party-column ')][1]"
        )[0].text_content()
        labels = [
            'Reference:',
            'Quotation Date:',
            'Validity Date:',
            'Customer Reference:',
            'Salesperson:',
        ]
        positions = [summary.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))

        order.validity_date = False
        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        self.assertNotIn(b'Validity Date:', report_html)

    def test_section_leads_group_headings_with_initial_content(self):
        order = self._create_order(
            payment_term_id=self.env.ref('account.account_payment_term_30days').id,
            validity_date='2026-08-31',
        )
        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        tree = lxml_html.fromstring(report_html)
        leads = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-section-lead ')]"
        )
        lead_text = [' '.join(lead.text_content().split()) for lead in leads]
        self.assertTrue(any(
            'Commercial Conditions' in text and 'Description' in text
            for text in lead_text
        ))
        self.assertTrue(any(
            'Payment, Delivery and Validity' in text and 'Payment Conditions' in text
            for text in lead_text
        ))
        self.assertTrue(any(
            'Bank References' in text and 'Document Test Bank' in text
            for text in lead_text
        ))
        self.assertTrue(any(
            'Signatures' in text and self.customer.name in text
            for text in lead_text
        ))
        payment_sections = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-payment-section ')]"
        )
        self.assertEqual(len(payment_sections), 1)
        payment_text = ' '.join(payment_sections[0].text_content().split())
        self.assertIn('Payment Conditions', payment_text)
        self.assertIn('Quotation Validity', payment_text)
        rendered_html = report_html.decode()
        self.assertIn('display: inline-block', rendered_html)
        self.assertIn('page-break-inside: avoid !important', rendered_html)

    def test_native_terms_override_legacy_terms_and_preserve_html(self):
        quotation_template = self.env['sale.order.template'].create({
            'name': 'Native Terms Template',
            'note': (
                '<p><strong>Native quotation terms</strong></p>'
                '<ol><li>First structured clause.</li>'
                '<li>Second structured clause.</li></ol>'
            ),
        })
        order = self._create_order(
            sale_order_template_id=quotation_template.id,
        )
        order.write({
            'mobikey_terms_html': '<p>Legacy Mobikey terms must not render.</p>',
        })

        self.assertEqual(order.note, quotation_template.note)
        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        tree = lxml_html.fromstring(report_html)
        native_terms = tree.xpath("//*[@name='order_note']")
        self.assertEqual(len(native_terms), 1)
        self.assertIn('mobikey-terms-content', native_terms[0].classes)
        self.assertIn('Native quotation terms', native_terms[0].text_content())
        self.assertEqual(len(native_terms[0].xpath('.//ol/li')), 2)
        self.assertNotIn(b'Legacy Mobikey terms must not render.', report_html)
        self.assertFalse(tree.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-terms ')]"
        ))

    def test_characteristic_rows_are_borderless_and_faintly_striped(self):
        self.env['mobikey.product.specification'].create({
            'product_tmpl_id': self.product_template.id,
            'sequence': 30,
            'name': 'Wheelbase',
            'value': '3900',
            'unit': 'mm',
        })
        order = self._create_order()

        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        tree = lxml_html.fromstring(report_html)
        rows = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-spec-row ')]"
        )
        self.assertEqual(len(rows), 2)
        self.assertIn('background: #FFFFFF', rows[0].attrib['style'])
        self.assertIn('background: #F2F8EE', rows[1].attrib['style'])
        self.assertFalse(tree.xpath("//div[contains(@class, 'mobikey-spec-grid')]//table"))

    def test_commercial_rows_are_semantic_aligned_and_faintly_striped(self):
        second_product = self.product_template.copy({
            'name': 'Second Commercial Product',
        }).product_variant_id
        order = self._create_order()
        order.write({'order_line': [Command.create({
            'product_id': second_product.id,
            'name': (
                'A long customer-facing product description that should wrap '
                'without changing the numeric column alignment.'
            ),
            'product_uom_qty': 1.0,
            'product_uom_id': second_product.uom_id.id,
            'price_unit': 500.0,
        })]})

        report_html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )
        tree = lxml_html.fromstring(report_html)
        commercial_tables = tree.xpath(
            "//table[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-commercial-table ')]"
        )
        self.assertGreaterEqual(len(commercial_tables), 2)
        header = commercial_tables[0].xpath('.//thead')[0]
        self.assertIn('background: #E5F1DD', header.attrib['style'])
        self.assertIn('color: #305496', header.attrib['style'])
        self.assertNotIn('border', header.attrib['style'])
        rows = tree.xpath(
            "//tr[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-commercial-item ')]"
        )
        self.assertEqual(len(rows), 2)
        self.assertIn('background: #FFFFFF', rows[0].attrib['style'])
        self.assertIn('background: #F2F8EE', rows[1].attrib['style'])
        self.assertTrue(all('border' not in row.attrib['style'] for row in rows))
        self.assertTrue(all(row.xpath('./td[contains(@class, "mobikey-number")]') for row in rows))
        totals = tree.xpath(
            "//table[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-totals-table ')]"
        )[0]
        self.assertNotIn('border', totals.attrib['style'])
        totals_block = totals.getparent()
        self.assertIn('mobikey-totals-block', totals_block.classes)
        self.assertNotIn('float', totals_block.attrib.get('style', ''))

        title = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-party-column ')][1]/div[1]"
        )[0]
        self.assertNotIn('border', title.attrib['style'])

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
        rendered_html = html.decode()
        self.assertIn('font-size: 10pt; line-height: 1.3', rendered_html)
        self.assertIn('background: #305496; color: #FFFFFF', rendered_html)
        self.assertIn('background: #E5F1DD', rendered_html)
        self.assertIn('mobikey-spec-row', rendered_html)
        self.assertIn('font-size: 10pt; line-height: 1.3', rendered_html)
        self.assertIn(
            'border-top: 0.35mm solid #305496; padding-top: 3.5mm',
            rendered_html,
        )

        proforma_html, proforma_report_type = (
            self.env['ir.actions.report']._render_qweb_html(
                'sale.action_report_pro_forma_invoice',
                order.ids,
            )
        )
        self.assertEqual(proforma_report_type, 'html')
        self.assertIn(b'Proforma Invoice', proforma_html)

    def test_optional_watermark_renders_in_custom_reports(self):
        self.assertFalse(self.document_template.watermark_enabled)
        self.assertFalse(
            self.document_template._get_mobikey_watermark_text()
        )
        plain_order = self._create_order()
        html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            plain_order.ids,
        )
        tree = lxml_html.fromstring(html)
        self.assertFalse(tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-watermark ')]"
        ))
        plain_content = tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-report-content ')]"
        )
        self.assertEqual(len(plain_content), 1)
        self.assertNotIn(
            'mobikey-report-content-watermarked',
            plain_content[0].classes,
        )

        self.document_template.write({
            'watermark_enabled': True,
            'watermark_text': 'Original',
        })
        order = self._create_order()
        self.assertEqual(
            self.document_template._get_mobikey_watermark_text(),
            'Original',
        )
        self.assertTrue(order.mobikey_watermark_enabled)
        self.assertEqual(order.mobikey_watermark_text, 'Original')
        self.document_template.watermark_text = 'Copy'
        self.assertEqual(order._get_mobikey_watermark_text(), 'Original')
        for report_name in (
            'sale.action_report_saleorder',
            'sale.action_report_pro_forma_invoice',
        ):
            report_html, report_type = (
                self.env['ir.actions.report']._render_qweb_html(
                    report_name,
                    order.ids,
                )
            )
            self.assertEqual(report_type, 'html')
            tree = lxml_html.fromstring(report_html)
            watermarks = tree.xpath(
                "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-watermark ')]"
            )
            self.assertEqual(len(watermarks), 1)
            self.assertEqual(watermarks[0].text_content().strip(), 'Original')
            rendered_html = report_html.decode()
            self.assertIn('position: fixed', rendered_html)
            self.assertIn('opacity: 0.10', rendered_html)
            self.assertIn('rotate(-40deg)', rendered_html)
            pages = tree.xpath(
                "//div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-report-page ')]"
            )
            self.assertEqual(len(pages), 1)
            report_content = pages[0].xpath(
                "./div[contains(concat(' ', normalize-space(@class), ' '), ' mobikey-report-content ')]"
            )
            self.assertEqual(len(report_content), 1)
            self.assertIn(
                'mobikey-report-content-watermarked',
                report_content[0].classes,
            )

    def test_enabled_watermark_requires_text(self):
        with self.assertRaises(ValidationError):
            self.document_template.write({
                'watermark_enabled': True,
                'watermark_text': '   ',
            })

    def test_native_report_is_retained_without_selection(self):
        self.document_template.write({
            'watermark_enabled': True,
            'watermark_text': 'Original',
        })
        order = self._create_order(mobikey_document_template_id=False)

        html, report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale.action_report_saleorder',
            order.ids,
        )

        self.assertEqual(report_type, 'html')
        self.assertNotIn(b'mobikey-watermark', html)
        self.assertNotIn(b'Description and Product Characteristics', html)
        self.assertIn(b'Quotation', html)

        proforma_html, proforma_report_type = (
            self.env['ir.actions.report']._render_qweb_html(
                'sale.action_report_pro_forma_invoice',
                order.ids,
            )
        )
        self.assertEqual(proforma_report_type, 'html')
        self.assertNotIn(b'mobikey-watermark', proforma_html)
        self.assertNotIn(
            b'Description and Product Characteristics',
            proforma_html,
        )

    def test_representative_report_outputs_render(self):
        """Exercise the PDF entrypoint, including Odoo's test-mode HTML fallback."""
        second_product = self.product_template.copy({
            'name': 'Second PDF Product',
            'model': 'SECOND PDF MODEL',
        }).product_variant_id
        third_product = self.product_template.copy({
            'name': 'Third PDF Product',
            'model': 'THIRD PDF MODEL',
        }).product_variant_id
        order = self._create_order()
        order.write({'order_line': [
            Command.create({
                'product_id': product.id,
                'name': product.display_name,
                'product_uom_qty': 1.0,
                'product_uom_id': product.uom_id.id,
                'price_unit': product.list_price,
            })
            for product in (second_product, third_product)
        ]})

        expected_markers = {
            'sale.action_report_saleorder': (
                b'Description and Product Characteristics',
                b'SECOND PDF MODEL',
            ),
            'sale.action_report_pro_forma_invoice': (
                b'Proforma Invoice',
                b'THIRD PDF MODEL',
            ),
        }
        for report_name, markers in expected_markers.items():
            payload, output_type = self.env['ir.actions.report']._render_qweb_pdf(
                report_name,
                order.ids,
            )
            self.assertIn(output_type, ('pdf', 'html'))
            if output_type == 'pdf':
                self.assertTrue(payload.startswith(b'%PDF'))
            else:
                self.assertTrue(payload.strip())
                for marker in markers:
                    self.assertIn(marker, payload)

        native_order = self._create_order(mobikey_document_template_id=False)
        native_payload, native_output_type = (
            self.env['ir.actions.report']._render_qweb_pdf(
                'sale.action_report_saleorder',
                native_order.ids,
            )
        )
        self.assertIn(native_output_type, ('pdf', 'html'))
        if native_output_type == 'pdf':
            self.assertTrue(native_payload.startswith(b'%PDF'))
        else:
            self.assertTrue(native_payload.strip())
            self.assertIn(b'Quotation', native_payload)
            self.assertNotIn(
                b'Description and Product Characteristics',
                native_payload,
            )
