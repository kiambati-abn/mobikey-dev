def migrate(cr, version):
    """Preserve the old report's effective default when OBS gains a true toggle."""
    cr.execute("""
        UPDATE product_template
           SET mobikey_show_product_details = TRUE
    """)
    cr.execute("""
        UPDATE sale_order_line
           SET mobikey_show_product_details = TRUE
    """)
