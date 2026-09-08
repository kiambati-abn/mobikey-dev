from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.addons.sale.controllers.portal import CustomerPortal, PaymentPortal


class ApprovalPortal(CustomerPortal):
    def _document_check_access(self, model_name, document_id, access_token=None):
        record = super()._document_check_access(model_name, document_id, access_token)
        if model_name == 'sale.order':
            try:
                record._check_commercial_approval(issue=True)
            except UserError as error:
                raise AccessError('This quotation is awaiting internal review.') from error
        return record

    @http.route()
    def portal_quote_accept(self, order_id, access_token=None, name=None, signature=None):
        # Native access validation precedes the model's signature-write guard.
        return super().portal_quote_accept(order_id, access_token, name, signature)


class ApprovalPaymentPortal(PaymentPortal):
    def _document_check_access(self, model_name, document_id, access_token=None):
        record = super()._document_check_access(model_name, document_id, access_token)
        if model_name == 'sale.order':
            record._check_commercial_approval()
        return record
