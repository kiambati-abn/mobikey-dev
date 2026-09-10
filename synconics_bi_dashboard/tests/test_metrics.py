from types import SimpleNamespace
from unittest.mock import patch
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestMetricCorrectness(TransactionCase):
    def config(self, **changes):
        values = dict(model='res.partner', measurement_field_id=False, data_type='count', domain=[],
            company=self.env.company.id, date_filter_field=False, date_filter_option=False,
            sort_order=False, sort_field=False, limit_record=1, is_apply_multiplier=False,
            chart_multiplier_ids=False, show_unit=False, unit_type=False,
            name='Test total', background_color=False, is_kpi_border=False, kpi_border_type=False,
            kpi_border_color=False, kpi_border_width=False, font_color=False, font_size=12,
            font_weight=False, text_align=False, layout_type=False, tile_layout_type=False,
            icon_option=False, default_icon=False, icon=False)
        values.update(changes)
        return SimpleNamespace(**values)

    @mute_logger('odoo.addons.synconics_bi_dashboard.models.dashboard_chart')
    def test_invalid_domain_does_not_broaden_population(self):
        with self.assertRaises(ValidationError):
            self.env['dashboard.chart'].evaluate_odoo_domain('this is not a domain')

    def test_total_ignores_ranking_limit(self):
        records = self.env['res.partner'].create([{'name': 'Metric A'}, {'name': 'Metric B'}, {'name': 'Metric C'}])
        data = self.env['dashboard.chart'].get_tile_data(self.config(domain=[('id', 'in', records.ids)]))
        self.assertEqual(data['calculated_count'], 3)

    def test_monetary_measure_requires_currency(self):
        partner = self.env['res.partner'].create({'name': 'Unspecified currency'})
        field = self.env['ir.model.fields']._get('res.partner', 'color')
        with self.assertRaises(ValidationError):
            self.env['dashboard.chart'].get_tile_data(self.config(domain=[('id', '=', partner.id)],
                measurement_field_id=field, data_type='sum', show_unit=True, unit_type='monetary'))

    def test_comparison_is_growth_and_zero_baseline_is_explicit(self):
        chart = self.env['dashboard.chart']
        conf = self.config(previous_period_comparision=True, previous_period_duration=1,
                           previous_period_type='percentage', kpi_model=False, kpi_enable_target=False)
        for current, previous, expected in [(250, 200, '25.0%'), (0, 0, '0%'), (100, 0, 'N/A (no baseline)')]:
            with patch.object(type(chart), 'get_tile_data', side_effect=[
                    {'calculated_count': current}, {'calculated_count': previous}]):
                self.assertEqual(chart.get_kpi_data(conf)['previous_data']['standard'], expected)
