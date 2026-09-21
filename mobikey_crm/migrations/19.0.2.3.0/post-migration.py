import logging

from odoo import Command, SUPERUSER_ID, api


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Retire Country Director without promoting legacy members to Country GM."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    legacy = env.ref('mobikey_crm.group_mobikey_country_director', raise_if_not_found=False)
    if not legacy:
        return

    sales_manager = env.ref('mobikey_crm.group_mobikey_sales_manager')
    legacy_users = legacy.user_ids
    if legacy_users:
        # Country Director previously implied Sales Manager. Preserve that effective
        # access, but require an explicit business decision before granting GM authority.
        legacy_users.write({'group_ids': [Command.link(sales_manager.id)]})
        _logger.warning(
            'Retired Country Director access and retained Sales Manager access for user IDs: %s',
            legacy_users.ids,
        )
    legacy.unlink()
