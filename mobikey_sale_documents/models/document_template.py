import re

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')

COLOR_SCHEME_DEFAULTS = {
    'mobikey': {
        'primary_color': '#323C48',
        'accent_color': '#D32D49',
        'body_text_color': '#222222',
        'muted_text_color': '#666666',
        'light_background_color': '#F0F1F3',
    },
    'blue_green': {
        'primary_color': '#305496',
        'accent_color': '#A9D08E',
        'body_text_color': '#222222',
        'muted_text_color': '#666666',
        'light_background_color': '#E5F1DD',
    },
}


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
    color_scheme = fields.Selection(
        selection=[
            ('mobikey', 'Mobikey Brand'),
            ('blue_green', 'Blue and Green'),
            ('custom', 'Custom'),
        ],
        required=True,
        default='mobikey',
        help='Select a maintained palette, or Custom to manage every color manually.',
    )
    primary_color = fields.Char(required=True, default='#323C48')
    accent_color = fields.Char(required=True, default='#D32D49')
    body_text_color = fields.Char(
        string='Body Text Color',
        default='#222222',
        help='Optional. Uses #222222 when left empty.',
    )
    muted_text_color = fields.Char(
        string='Muted Text Color',
        default='#666666',
        help='Optional. Uses #666666 when left empty.',
    )
    light_background_color = fields.Char(
        string='Light Background Color',
        default='#F0F1F3',
        help='Optional. A pale tint is generated automatically when left empty.',
    )
    palette_preview = fields.Html(
        string='Palette Preview',
        compute='_compute_palette_preview',
        sanitize=False,
    )
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

    @api.onchange('color_scheme')
    def _onchange_color_scheme(self):
        for template in self:
            defaults = COLOR_SCHEME_DEFAULTS.get(template.color_scheme)
            if defaults:
                template.update(defaults)

    def action_restore_color_scheme_defaults(self):
        for template in self:
            defaults = COLOR_SCHEME_DEFAULTS.get(template.color_scheme)
            if defaults:
                template.write(defaults)
        return True

    @staticmethod
    def _safe_color(value, fallback):
        return value.upper() if value and HEX_COLOR_RE.fullmatch(value) else fallback

    @staticmethod
    def _mix_with_white(color, color_weight):
        components = [
            int(color.lstrip('#')[index:index + 2], 16)
            for index in (0, 2, 4)
        ]
        tinted = [
            round(component * color_weight + 255 * (1 - color_weight))
            for component in components
        ]
        return '#%02X%02X%02X' % tuple(tinted)

    @staticmethod
    def _relative_luminance(color):
        components = [
            int(color.lstrip('#')[index:index + 2], 16) / 255.0
            for index in (0, 2, 4)
        ]
        linear = [
            component / 12.92
            if component <= 0.04045
            else ((component + 0.055) / 1.055) ** 2.4
            for component in components
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    @classmethod
    def _contrast_ratio(cls, first_color, second_color):
        first = cls._relative_luminance(first_color)
        second = cls._relative_luminance(second_color)
        lighter, darker = max(first, second), min(first, second)
        return (lighter + 0.05) / (darker + 0.05)

    @classmethod
    def _get_contrast_text(cls, background_color):
        black_ratio = cls._contrast_ratio(background_color, '#000000')
        white_ratio = cls._contrast_ratio(background_color, '#FFFFFF')
        return '#000000' if black_ratio >= white_ratio else '#FFFFFF'

    def _get_mobikey_accent_tint(self):
        """Return an override or blend the accent for calm large-area fills."""
        self.ensure_one()
        if self.light_background_color and HEX_COLOR_RE.fullmatch(
            self.light_background_color
        ):
            return self.light_background_color.upper()
        accent = self._safe_color(self.accent_color, '#D32D49')
        return self._mix_with_white(accent, 0.30)

    def _get_mobikey_accent_stripe(self):
        """Return an extra-light accent tint for alternating specification rows."""
        self.ensure_one()
        accent = self._safe_color(self.accent_color, '#D32D49')
        return self._mix_with_white(accent, 0.15)

    def _get_mobikey_palette(self):
        self.ensure_one()
        primary = self._safe_color(self.primary_color, '#323C48')
        accent = self._safe_color(self.accent_color, '#D32D49')
        light_background = self._get_mobikey_accent_tint()
        light_foreground = primary
        if self._contrast_ratio(light_background, light_foreground) < 4.5:
            light_foreground = self._get_contrast_text(light_background)
        return {
            'primary': primary,
            'accent': accent,
            'body': self._safe_color(self.body_text_color, '#222222'),
            'muted': self._safe_color(self.muted_text_color, '#666666'),
            'light_background': light_background,
            'stripe': self._get_mobikey_accent_stripe(),
            'separator': '#DADBDF',
            'primary_foreground': self._get_contrast_text(primary),
            'accent_foreground': self._get_contrast_text(accent),
            'light_foreground': light_foreground,
        }

    @api.depends(
        'primary_color',
        'accent_color',
        'body_text_color',
        'muted_text_color',
        'light_background_color',
    )
    def _compute_palette_preview(self):
        for template in self:
            palette = template._get_mobikey_palette()
            swatches = [
                ('Primary', palette['primary'], palette['primary_foreground']),
                ('Accent', palette['accent'], palette['accent_foreground']),
                ('Light panel', palette['light_background'], palette['light_foreground']),
                ('Stripe', palette['stripe'], palette['body']),
                ('Body', '#FFFFFF', palette['body']),
                ('Muted', '#FFFFFF', palette['muted']),
            ]
            template.palette_preview = Markup('').join(
                Markup(
                    '<span style="display:inline-block;min-width:92px;margin:0 6px 6px 0;'
                    'padding:8px 10px;border:1px solid #DADBDF;border-radius:4px;'
                    'background:%s;color:%s;font-weight:600">%s</span>'
                ) % (background, foreground, label)
                for label, background, foreground in swatches
            )

    @api.constrains(
        'primary_color',
        'accent_color',
        'body_text_color',
        'muted_text_color',
        'light_background_color',
    )
    def _check_colors(self):
        for template in self:
            invalid = [
                value
                for field_name, value in (
                    ('primary_color', template.primary_color),
                    ('accent_color', template.accent_color),
                    ('body_text_color', template.body_text_color),
                    ('muted_text_color', template.muted_text_color),
                    ('light_background_color', template.light_background_color),
                )
                if (
                    field_name in ('primary_color', 'accent_color') and not value
                ) or (value and not HEX_COLOR_RE.fullmatch(value))
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
