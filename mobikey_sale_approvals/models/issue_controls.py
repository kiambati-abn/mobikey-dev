from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def write(self, vals):
        if vals.get('signature') or vals.get('signed_on'):
            self._check_commercial_approval()
        return super().write(vals)

    def message_post(self, **kwargs):
        if kwargs.get('subtype_xmlid') == 'mail.mt_comment' or kwargs.get('message_type') == 'comment':
            self._check_commercial_approval(issue=True)
        return super().message_post(**kwargs)


class MailCompose(models.TransientModel):
    _inherit = 'mail.compose.message'

    def _action_send_mail(self, *args, **kwargs):
        for wizard in self:
            if wizard.model == 'sale.order':
                self.env['sale.order'].browse(wizard._evaluate_res_ids())._check_commercial_approval(issue=True)
        return super()._action_send_mail(*args, **kwargs)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_processing_values(self):
        self.sale_order_ids._check_commercial_approval()
        return super()._get_processing_values()


class Report(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_html(self, report_ref, res_ids, data=None):
        if self._get_report(report_ref).model == 'sale.order' and res_ids:
            self.env['sale.order'].browse(res_ids)._check_commercial_approval(issue=True)
        return super()._render_qweb_html(report_ref, res_ids, data=data)

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        if self._get_report(report_ref).model == 'sale.order' and res_ids:
            self.env['sale.order'].browse(res_ids)._check_commercial_approval(issue=True)
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
