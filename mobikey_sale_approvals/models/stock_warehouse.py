from odoo import api, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    @api.model_create_multi
    def create(self, vals_list):
        # During `module force-demo`, the demo company is created after Stock is
        # installed, so Stock has already auto-created this warehouse by the
        # time stock_demo.xml assigns its external ID.
        if self.env.su and self.env.context.get('install_demo') and len(vals_list) == 1:
            vals = vals_list[0]
            company = self.env['res.company'].browse(
                vals.get('company_id') or self.env.company.id
            )
            name = vals.get('name') or company.name
            if name:
                warehouse = self.with_context(active_test=False).search([
                    ('name', '=', name),
                    ('company_id', '=', company.id),
                ], limit=1)
                if warehouse:
                    return warehouse
        return super().create(vals_list)
