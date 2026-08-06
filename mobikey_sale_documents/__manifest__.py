{
    'name': 'Mobikey Sale Documents',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Configurable branded quotation and proforma invoice documents',
    'description': """
Mobikey Sale Documents
======================

Adds administrator-managed document templates for Odoo quotations and
proforma invoices while retaining the native quotation-template and
send/print workflows.
    """,
    'author': 'Mobikey',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'sale_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rules.xml',
        'views/document_template_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'report/sale_document_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
