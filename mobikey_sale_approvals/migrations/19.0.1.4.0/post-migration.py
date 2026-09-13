from odoo import Command, SUPERUSER_ID, api


def migrate(cr, version):
    """Give configured and pending assignees the minimum approval-review access."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    approver_group = env.ref('mobikey_sale_approvals.group_approver')
    companies = env['res.company'].with_context(active_test=False).search([])
    companies._ensure_assigned_approver_access()

    pending = env['mobikey.sale.approval'].sudo().search([('status', '=', 'pending')])
    users = pending.mapped('assigned_user_ids').filtered(
        lambda user: user.active and not user.share
    )
    users.write({'group_ids': [Command.link(approver_group.id)]})
