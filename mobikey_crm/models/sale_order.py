"""Mobikey CRM — sale.order extension.

Hooks into the quotation email-send flow to automatically advance the linked
opportunity to the Negotiation stage when a quotation is sent to the customer.

Requires: sale_crm (provides sale.order.opportunity_id)
"""

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'


    vehicle_condition = fields.Selection(
        selection=[
            ('new', 'New'),
            ('used', 'Used'),
            ('either', 'Either'),
        ],
        string='Vehicle Condition',
    )
    customer_type = fields.Many2one(
        'mobikey.customer.type',
        string="Customer Type",
        tracking=True,
    )

    deal_type = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('financing', 'Financing'),
            ('lease', 'Lease'),
            ('fleet', 'Fleet'),
        ], string="Deal Type")

    margin_warning = fields.Boolean(
        string="Margin Warning",
        compute="_compute_margin_warning",
        store=False,  # display only
        readonly=True,
    )

    margin_warning_msg = fields.Text(
        string="Margin Warning Details",
        compute="_compute_margin_warning",
        store=False,
        readonly=True,
    )


    @api.depends(
        'order_line.price_unit',
        'order_line.product_id',
        'order_line.product_id.standard_price',
        'order_line.product_id.target_margin',
        'opportunity_id',
        'opportunity_id.reconditioning_cost',
    )
    def _compute_margin_warning(self):
        for order in self:
            lead = order.opportunity_id
            recond_cost = lead.reconditioning_cost if lead else 0.0

            bad_lines = []
            for line in order.order_line:
                if not line.product_id:
                    continue
                target_margin = line.product_id.target_margin or 0.0

                min_price = (line.product_id.standard_price + recond_cost) / (1.0 - target_margin)
                if line.price_unit < min_price:
                    bad_lines.append(
                        f"• {line.product_id.display_name}: "
                        f"quoted price {line.price_unit:.2f} < minimum price {min_price:.2f}"
                    )

            order.margin_warning = bool(bad_lines)
            order.margin_warning_msg = "\n".join(bad_lines) if bad_lines else False



    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)  # this is always a recordset
        # if 'opportunity_id' in vals_list[0]:
        #     lead_rec = self.env['crm.lead'].browse([vals_list[0]['opportunity_id']])
        #     if 'amount_total' in vals_list[0] and lead_rec:
        #         lead_rec.expected_revenue = vals_list[0]['amount_total']
        #     elif lead_rec and 'amount_total' not in vals_list[0]:
        #         lead_rec.expected_revenue = self.amount_total
        for record in records:  # loop safely
            if record.opportunity_id and record.order_line:
                for line in record.order_line:
                    if line.product_id:
                        product_rec = self.env['crm.product.lines'].search([
                            ('product_id', '=', line.product_id.id),
                            ('lead_id', '=', record.opportunity_id.id)
                        ], limit=1)
                        if product_rec:
                            product_rec.sale_order_line_id = line.id
        return records


    def write(self, vals):
        """When a quotation transitions to 'sent', advance the linked
        opportunity from Quotation → Negotiation automatically.

        This fires whenever ``state`` becomes ``'sent'``, which happens
        both from the "Send by Email" wizard and from the "Send & Sign"
        flow.  The stage change uses the bypass context so it does not
        trip the stage-guard in crm.lead.write().
        """
        result = super().write(vals)
        # if 'amount_total' in vals and self.opportunity_id:
        #     self.opportunity_id.expected_revenue = self.amount_total

        if vals.get('state') == 'sent':
            for order in self:
                opportunity = order.opportunity_id
                if not opportunity:
                    continue
                if opportunity.stage_id.mobikey_stage_type != 'quotation':
                    # Only advance if currently in Quotation stage
                    continue

                negotiation_stage = self.env['crm.stage'].search(
                    [('mobikey_stage_type', '=', 'negotiation')],
                    limit=1,
                )
                if not negotiation_stage:
                    _logger.warning(
                        "Mobikey CRM: No stage with mobikey_stage_type='negotiation' found. "
                        "Cannot auto-advance opportunity %s to Negotiation.",
                        opportunity.id,
                    )
                    continue

                _logger.info(
                    "Mobikey CRM: Quotation %s sent — advancing opportunity %s "
                    "from '%s' to '%s'.",
                    order.name,
                    opportunity.name,
                    opportunity.stage_id.name,
                    negotiation_stage.name,
                )
                opportunity.with_context(
                    mobikey_bypass_stage_guard=True
                ).write({'stage_id': negotiation_stage.id})

        return result

