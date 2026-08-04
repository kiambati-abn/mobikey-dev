{
    'name': 'Mobikey CRM',
    'version': '19.0.1.2.0',
    'category': 'Sales/CRM',
    'summary': 'Vehicle sales CRM pipeline for Mobikey (KE / UG / TZ)',
    'description': """
Mobikey CRM — Vehicle Sales Pipeline
=====================================

Custom CRM module for Mobikey operations across Kenya, Uganda, and Tanzania.

**Scope (v1.1.0)**

* Pipeline smart fields on leads and opportunities (Section 4.2)
* Extended lead form with vehicle, buying-intent, and qualification fields (Section 8.1)
* Automated field mapping on lead → opportunity conversion (Section 9.1)
* Conversion validation / blockers (Section 9.2)
* Pre-populated UTM source values for lead entry channels
* Controlled stage progression — state-machine pipeline (Section 10.0)
* Stage identification by ``mobikey_stage_type`` field (immune to stage renames)
* Auto-advance to Negotiation when quotation is sent by email

**Architecture notes**

* All custom fields live on ``crm.lead`` (shared between leads and opportunities).
* Stages are identified by ``mobikey_stage_type`` on ``crm.stage``, not by name.
  This means renaming a stage never breaks automation.
* Stage movement is guarded in ``write()``; only explicit action buttons
  or ``mobikey_bypass_stage_guard=True`` context can change the stage.
* Backward movement is only possible via the "Reset to Draft" button, which
  also cancels all open quotations linked to the opportunity.
    """,
    'author': 'Bista Solutions',
    'website': 'https://www.bistasolutions.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'sale_crm',
        'product','mail',
    ],
    'data': [
        'data/utm_source_data.xml',
        'data/margin_email_template.xml',
        'data/discount_email_template.xml',
        'data/financing_email_template.xml',
        'data/trade_in_email_template.xml',

        'security/groups.xml',
        'security/ir.model.access.csv',

        'views/crm_lead_views.xml',
        'views/crm_stage_views.xml',
        'views/product_product_view.xml',
        'views/res_config_settings.xml',
        'views/product_template_view.xml',
        'views/sale_order_view.xml',
        'views/mobikey_config_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
