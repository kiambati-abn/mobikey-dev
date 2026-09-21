from odoo import Command


def migrate(cr, version):
    from odoo.api import Environment

    env = Environment(cr, 1, {})

    # Start company-specific product policies from any positive legacy target.
    products = env['product.template'].with_context(active_test=False).search([
        ('target_margin', '>', 0),
    ])
    companies = env['res.company'].with_context(active_test=False).search([])
    for company in companies:
        for product in products:
            configured = product.with_company(company)
            if not configured.mobikey_minimum_margin:
                configured.mobikey_minimum_margin = product.target_margin

    # Existing approvals retain their decisions while gaining a readable order.
    orders = env['sale.order'].search([('approval_ids', '!=', False)])
    for order in orders:
        revisions = set(order.approval_ids.mapped('revision'))
        for revision in revisions:
            approvals = order.approval_ids.filtered(lambda item: item.revision == revision)
            discount = approvals.filtered(lambda item: item.category == 'discount')[:1]
            margin = approvals.filtered(lambda item: item.category == 'margin')[:1]
            hq_margin = approvals.filtered(lambda item: item.category == 'margin_hq')[:1]
            for approval in approvals:
                values = {'sequence': 1, 'dependency_ids': [Command.clear()]}
                if approval == margin:
                    values['sequence'] = 2 if discount else 1
                    if discount:
                        values['dependency_ids'] = [Command.set(discount.ids)]
                elif approval == hq_margin:
                    values['sequence'] = (2 if discount else 1) + 1
                    if margin:
                        values['dependency_ids'] = [Command.set(margin.ids)]
                approval.sudo().write(values)
