"""Conservative cutover: preserve values, never infer legacy approval validity."""
import logging
from odoo import Command

_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    # Preserve the stored estimate before the new computed field is initialised.
    env.cr.execute('ALTER TABLE crm_lead ADD COLUMN IF NOT EXISTS initial_expected_revenue double precision')
    env.cr.execute('UPDATE crm_lead SET initial_expected_revenue = expected_revenue WHERE initial_expected_revenue IS NULL')


def post_init_hook(env):
    queued = env['mail.mail'].search([('model', '=', 'crm.lead'), ('state', '=', 'outgoing'),
        ('subject', 'in', ['Discount Approval Request', 'Margin Approval Request',
                         'Financing Approval Request', 'Trade In Approval Request', 'Trade-In Approval Request'])])
    if queued:
        queued.write({'state': 'cancel'})
        _logger.warning('Quarantined legacy approval queue IDs for recipient review: %s', queued.ids)
    # Existing commitments remain printable. This marker never exempts a draft/revision.
    env['sale.order'].search([('state', '=', 'sale')]).write({'legacy_confirmed_order': True})
    ambiguous = []
    for lead in env['crm.lead'].search([('type', '=', 'opportunity')]):
        orders = lead.order_ids.filtered(lambda order: order.state != 'cancel')
        confirmed = orders.filtered(lambda order: order.state == 'sale')
        primary = confirmed if len(confirmed) == 1 else orders if len(orders) == 1 else env['sale.order']
        if len(primary) != 1:
            if orders or lead.product_line_ids:
                ambiguous.append(lead.id)
            continue
        lead.primary_quotation_id = primary
        if primary.state != 'draft':
            continue
        values = {}
        mapping = {'payment_terms_type': 'payment_term_id', 'price_list': 'pricelist_id',
                   'delivery_location': 'warehouse_id', 'bank_id': 'bank_id',
                   'after_sales_user_id': 'after_sales_user_id'}
        for source, target in mapping.items():
            if lead[source] and not primary[target]:
                values[target] = lead[source].id
        if lead.trade_in and not primary.trade_in:
            values.update(trade_in=True, trade_in_valuation=lead.trade_in_valuation)
        if lead.insurance_required:
            values['insurance_required'] = True
        if not primary.order_line and lead.product_line_ids:
            values['order_line'] = [Command.create({'product_id': line.product_id.id,
                'product_uom_qty': line.quantity, 'price_unit': line.price_unit, 'discount': line.discount,
                'reconditioning_cost': lead.reconditioning_cost if index == 0 else 0,
                'vehicle_year': lead.year, 'vehicle_mileage': lead.mileage})
                for index, line in enumerate(lead.product_line_ids) if line.product_id]
        if values:
            primary.write(values)
    if ambiguous:
        _logger.warning('Mobikey cutover requires manual quotation selection for opportunity IDs: %s', ambiguous)
    # Retire the over-broad legacy ACL even if it survived a prior partial upgrade.
    acl = env.ref('mobikey_crm.access_sale_order_margin_warning', raise_if_not_found=False)
    if acl:
        acl.active = False
