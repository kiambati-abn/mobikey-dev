{
    'name': 'Mobikey Sales Approvals',
    'version': '19.0.1.3.1',
    'author': 'Mobikey',
    'license': 'LGPL-3',
    'depends': ['mobikey_crm', 'sale_margin', 'stock_account'],
    'data': ['security/security.xml', 'security/ir.model.access.csv',
             'views/views.xml', 'data/cron.xml'],
    'auto_install': True,
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
