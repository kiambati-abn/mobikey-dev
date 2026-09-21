def migrate(cr, version):
    from odoo.api import Environment

    env = Environment(cr, 1, {})
    english = env.ref('mobikey_crm.preferred_language_english')
    swahili = env.ref('mobikey_crm.preferred_language_swahili')

    cr.execute("""
        UPDATE crm_lead
           SET preferred_language_id = CASE
               WHEN preferred_language = 'sw' THEN %s
               ELSE %s
           END
         WHERE preferred_language_id IS NULL
    """, [swahili.id, english.id])
    cr.execute("""
        UPDATE crm_lead AS lead
           SET walkin_company_id = location.company_id
          FROM stock_location AS location
         WHERE lead.walkin_company_id IS NULL
           AND lead.walkin_location = location.id
           AND location.company_id IS NOT NULL
    """)
