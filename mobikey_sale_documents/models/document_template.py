import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


class MobikeyDocumentBrand(models.Model):
    _name = 'mobikey.document.brand'
    _description = 'Document Manufacturer Brand'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    logo = fields.Image(
        required=True,
        max_width=1024,
        max_height=512,
        help='Manufacturer logo displayed on branded quotations and proforma invoices.',
    )

    _unique_name = models.Constraint(
        'unique(name)',
        'A manufacturer brand with this name already exists.',
    )


class MobikeyDocumentTemplate(models.Model):
    _name = 'mobikey.document.template'
    _description = 'Quotation and Proforma Document Template'
    _order = 'sequence, name, id'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company / Branch',
        default=lambda self: self.env.company,
        required=True,
        index=True,
        help='Company or branch whose legal details and bank accounts are used.',
    )
    company_partner_id = fields.Many2one(
        'res.partner',
        related='company_id.partner_id',
        string='Company Partner',
    )
    brand_source = fields.Selection(
        selection=[
            ('order', 'Brands from Products'),
            ('template', 'Brands Selected on Template'),
        ],
        string='Manufacturer Logos',
        required=True,
        default='template',
        help='Use brands configured on the products, or always use the brands selected here.',
    )
    brand_ids = fields.Many2many(
        'mobikey.document.brand',
        'mobikey_document_template_brand_rel',
        'template_id',
        'brand_id',
        string='Brands',
    )
    issuer_logo = fields.Image(
        string='Dealer Logo Override',
        max_width=1024,
        max_height=512,
        help='Optional. When empty, the logo of the sales order company or branch is used.',
    )
    issuer_logo_size = fields.Selection(
        selection=[
            ('compact', 'Compact'),
            ('standard', 'Standard'),
            ('large', 'Large'),
        ],
        string='Dealer Logo Size',
        required=True,
        default='standard',
        help='Controls the maximum printed size while preserving the logo aspect ratio.',
    )
    manufacturer_logo_size = fields.Selection(
        selection=[
            ('auto', 'Automatic'),
            ('compact', 'Compact'),
            ('standard', 'Standard'),
            ('large', 'Large'),
        ],
        string='Manufacturer Logo Size',
        required=True,
        default='auto',
        help='Automatic is recommended for quotations containing multiple brands.',
    )
    primary_color = fields.Char(required=True, default='#1A5A96')
    accent_color = fields.Char(required=True, default='#E9EEF4')
    bank_account_ids = fields.Many2many(
        'res.partner.bank',
        'mobikey_document_template_bank_rel',
        'template_id',
        'bank_account_id',
        string='Payment Bank Accounts',
        help='Accounts copied to the sales order when this document template is selected.',
    )
    terms_html = fields.Html(
        string='Terms and Conditions',
        translate=True,
        sanitize=True,
    )
    footer_note = fields.Html(
        translate=True,
        sanitize=True,
        help='Optional short note shown with the compact company details in the footer.',
    )
    signatory_1_id = fields.Many2one('res.users', string='First Signatory')
    signatory_1_title = fields.Char(translate=True)
    signatory_1_image = fields.Image(
        string='First Signature Image',
        max_width=1024,
        max_height=512,
    )
    signatory_2_id = fields.Many2one('res.users', string='Second Signatory')
    signatory_2_title = fields.Char(translate=True)
    signatory_2_image = fields.Image(
        string='Second Signature Image',
        max_width=1024,
        max_height=512,
    )
    show_customer_signature = fields.Boolean(default=True)

    _unique_name_company = models.Constraint(
        'unique(name, company_id)',
        'A document template with this name already exists for this company or branch.',
    )

    def _get_mobikey_logo_dimensions(self, brand_count):
        """Return bounded print dimensions in millimetres for reliable PDF output."""
        self.ensure_one()
        issuer_sizes = {
            'compact': (45, 13),
            'standard': (60, 17),
            'large': (75, 21),
        }
        manufacturer_sizes = {
            'compact': (30, 11),
            'standard': (45, 15),
            'large': (60, 19),
        }
        automatic_sizes = {
            0: (45, 15),
            1: (60, 19),
            2: (42, 15),
            3: (28, 12),
        }

        issuer_width, issuer_height = issuer_sizes[
            self.issuer_logo_size or 'standard'
        ]
        if self.manufacturer_logo_size == 'auto':
            brand_width, brand_height = automatic_sizes.get(brand_count, (20, 9))
        else:
            brand_width, brand_height = manufacturer_sizes[
                self.manufacturer_logo_size or 'standard'
            ]
            if brand_count == 2:
                brand_width = min(brand_width, 42)
                brand_height = min(brand_height, 17)
            elif brand_count == 3:
                brand_width = min(brand_width, 28)
                brand_height = min(brand_height, 13)
            elif brand_count > 3:
                brand_width = min(brand_width, 20)
                brand_height = min(brand_height, 9)

        return {
            'issuer_width': issuer_width,
            'issuer_height': issuer_height,
            'brand_width': brand_width,
            'brand_height': brand_height,
            'header_height': max(23, issuer_height + 2),
        }

    @api.constrains('primary_color', 'accent_color')
    def _check_colors(self):
        for template in self:
            invalid = [
                value
                for value in (template.primary_color, template.accent_color)
                if not value or not HEX_COLOR_RE.fullmatch(value)
            ]
            if invalid:
                raise ValidationError(_(
                    'Document colors must use the #RRGGBB format, for example #1A5A96.'
                ))

    @api.constrains('brand_source', 'brand_ids')
    def _check_template_brands(self):
        for template in self:
            if template.brand_source == 'template' and not template.brand_ids:
                raise ValidationError(_(
                    'Select at least one manufacturer brand, or use Brands from Products.'
                ))

    @api.constrains(
        'company_id',
        'bank_account_ids',
        'signatory_1_id',
        'signatory_2_id',
    )
    def _check_company_configuration(self):
        for template in self:
            invalid_accounts = template.bank_account_ids.filtered(
                lambda account: account.partner_id != template.company_id.partner_id
            )
            if invalid_accounts:
                raise ValidationError(_(
                    'Every payment bank account must belong to the selected company or branch.'
                ))
            invalid_signatories = (
                template.signatory_1_id | template.signatory_2_id
            ).filtered(lambda user: template.company_id not in user.company_ids)
            if invalid_signatories:
                raise ValidationError(_(
                    'Every signatory must have access to the selected company or branch.'
                ))
