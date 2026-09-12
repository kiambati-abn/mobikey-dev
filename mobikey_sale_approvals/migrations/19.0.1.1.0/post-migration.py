from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields


BACKFILL_MARKER = 'Mobikey approval history synchronized'


def _category_label(approval):
    return dict(approval._fields['category'].selection).get(approval.category, approval.category)


def _status_label(approval):
    return dict(approval._fields['status'].selection).get(approval.status, approval.status)


def migrate(cr, version):
    """Preserve active legacy policies and make existing approval history visible."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Message = env['mail.message'].sudo()
    for order in env['sale.order'].sudo().search([('approval_ids', '!=', False)]):
        approvals = order.approval_ids.sorted(lambda approval: (approval.revision, approval.id))
        if order.approval_submitted and not order.approval_policy_snapshot:
            order.with_context(tracking_disable=True).write({
                'approval_policy_snapshot': {
                    'version': 'legacy_product_v1',
                    'discount_sm_limit': 2.0,
                    'discount_gm_limit': 5.0,
                    'financing_required': bool(order.payment_term_id.financing_required),
                },
            })

        if not Message.search_count([
            ('model', '=', 'sale.order'), ('res_id', '=', order.id),
            ('body', 'ilike', BACKFILL_MARKER),
        ]):
            items = Markup().join(
                Markup('<li>Revision %s — %s: %s%s</li>') % (
                    approval.revision,
                    _category_label(approval),
                    _status_label(approval),
                    Markup(' — %s') % approval.decided_by.name
                    if approval.decided_by else Markup(),
                )
                for approval in approvals
            )
            order.message_post(
                body=Markup('<p><strong>%s</strong></p><ul>%s</ul>') % (BACKFILL_MARKER, items),
                subtype_xmlid='mail.mt_note',
                notify_skip_followers=True,
            )

        for approval in approvals:
            if not Message.search_count([
                ('model', '=', 'mobikey.sale.approval'), ('res_id', '=', approval.id),
                ('body', 'ilike', BACKFILL_MARKER),
            ]):
                approval.message_post(
                    body=Markup(
                        '<p><strong>%s</strong></p>'
                        '<p>Revision %s — %s: %s.</p>'
                    ) % (
                        BACKFILL_MARKER,
                        approval.revision,
                        _category_label(approval),
                        _status_label(approval),
                    ),
                    subtype_xmlid='mail.mt_note',
                    notify_skip_followers=True,
                )

            if approval.status == 'pending' and approval.notified_at:
                existing_users = approval.activity_ids.mapped('user_id')
                for user in approval.assigned_user_ids - existing_users:
                    approval.with_context(mail_activity_quick_update=True).activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=user.id,
                        summary=f'Review quotation {order.name}',
                        date_deadline=approval.deadline or fields.Date.today(),
                        note='Review the assigned decision in Sales approvals.',
                    )
