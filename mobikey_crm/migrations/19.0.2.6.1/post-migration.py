from odoo import SUPERUSER_ID, api
from odoo.addons.mobikey_crm.models.branch import migrate_legacy_branches


def migrate(cr, version):
    migrate_legacy_branches(api.Environment(cr, SUPERUSER_ID, {}))
