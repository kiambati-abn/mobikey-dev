from odoo import SUPERUSER_ID, api
from odoo.addons.mobikey_sale_approvals.hooks import retire_legacy_acl


def migrate(cr, version):
    retire_legacy_acl(api.Environment(cr, SUPERUSER_ID, {}))
