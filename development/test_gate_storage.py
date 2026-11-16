"""Persistence contracts for development IDs and relational gate records."""
from datetime import date
from decimal import Decimal
import json
from unittest import skipUnless

from django.contrib.auth.models import User
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, connection, models
from django.test import TestCase

from .models import (
    Food, Gate0, Gate1, Gate2, Gate3, GateDataArchive,
    Gate0AnalogSKU, Gate0Cannibalisation, Gate0Competitor, Gate0Daypart,
    Gate0ImprovementReason, Gate1Material, Gate3LessonTag,
)
from .gate0 import initial_brief as read_gate0, save_brief as save_gate0
from .gate1 import initial_brief as read_gate1, save_brief as save_gate1
from .gate2 import initial_brief as read_gate2, save_brief as save_gate2
from .gate3 import initial_brief as read_gate3, save_brief as save_gate3


class TypedGateStorageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('typed-gate-owner')
        self.development = Food.objects.create(name='Original development', owner=self.user)

    def test_starting_a_development_initializes_all_gates_with_one_id(self):
        self.user.is_superuser=True
        self.user.save()
        self.client.force_login(self.user)
        response=self.client.post('/food/new/',{'product_name':'One process across gates','category':'FF'})
        self.assertEqual(response.status_code,302)
        development=Food.objects.get(name='One process across gates')
        for gate in (Gate0,Gate1,Gate2,Gate3):
            self.assertEqual(gate.objects.get(development_id=development.pk).pk,development.pk)
        self.assertEqual(Gate0.objects.get(pk=development.pk).category,'FF')

    def test_archived_label_information_still_feeds_legacy_handover(self):
        from .gate3 import Gate3Form
        save_gate2(self.development, {'_schema_version':2,'label_check':'Previously recorded product label'})
        saved=read_gate2(self.development)
        self.assertEqual(saved['_legacy_free_text']['label_check'],'Previously recorded product label')
        form=Gate3Form({},food=self.development)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['handover_label'],'yes')

    def test_one_development_id_identifies_all_four_gate_rows(self):
        process_id = self.development.pk
        save_gate0(self.development, {'product_name': 'ISF development', 'category': 'ISF'})
        save_gate1(self.development, {'marketing_name': 'Launch campaign'})
        save_gate2(self.development, {'allocation': 25})
        save_gate3(self.development, {'lesson_card': 'Keep the smaller pack'})

        self.development.refresh_from_db()
        self.assertEqual(self.development.pk, process_id)
        for gate_model in (Gate0, Gate1, Gate2, Gate3):
            record = gate_model.objects.get(development_id=process_id)
            self.assertEqual(record.pk, process_id)
            self.assertEqual(record.development_id, process_id)

        other = Food.objects.create(name='Another process', owner=self.user)
        save_gate2(other, {'allocation': 10})
        self.assertEqual(Gate2.objects.get(development_id=process_id).allocation, 25)
        self.assertEqual(Gate2.objects.get(development_id=other.pk).allocation, 10)

    def test_gate_tables_have_typed_columns_instead_of_a_json_payload(self):
        for number, gate_model in enumerate((Gate0, Gate1, Gate2, Gate3)):
            self.assertEqual(gate_model._meta.db_table, 'development_gate%s' % number)
            link = gate_model._meta.get_field('development')
            self.assertTrue(link.primary_key)
            self.assertEqual(link.column, 'development_id')
            self.assertTrue(link.one_to_one)
            self.assertFalse(any(isinstance(field, models.JSONField) for field in gate_model._meta.fields))
            with self.assertRaises(FieldDoesNotExist):
                gate_model._meta.get_field('data')

        self.assertIsInstance(Gate0._meta.get_field('product_name'), models.CharField)
        self.assertIsInstance(Gate0._meta.get_field('category'), models.CharField)
        self.assertIsInstance(Gate0._meta.get_field('cu_margin'), models.DecimalField)
        self.assertIsInstance(Gate0._meta.get_field('planned_launch_date'), models.DateField)
        self.assertIsInstance(Gate2._meta.get_field('allocation'), models.IntegerField)
        self.assertIsInstance(Gate3._meta.get_field('complaints'), models.IntegerField)

    def test_gate0_values_can_be_queried_directly_and_keep_the_product_summary_in_sync(self):
        save_gate0(self.development, {
            'product_name': 'New rice bowl', 'category': 'ISF',
            'target_shelf_price': 5000, 'cu_margin': Decimal('30.5'),
            'vendor_rebate': Decimal('0'), 'vendor_margin': Decimal('20'),
            'planned_launch_date': date(2027, 4, 3),
        })
        record = Gate0.objects.get(
            product_name='New rice bowl', category='ISF', cu_margin__gt=30,
            planned_launch_date=date(2027, 4, 3),
        )
        self.assertEqual(record.development_id, self.development.pk)
        self.assertEqual(record.cu_margin, Decimal('30.5'))
        self.development.refresh_from_db()
        self.assertEqual(self.development.name, 'New rice bowl')
        self.assertEqual(self.development.category, 'ISF')
        with connection.cursor() as cursor:
            cursor.execute('SELECT development_id, product_name, category FROM development_gate0')
            self.assertIn((self.development.pk, 'New rice bowl', 'ISF'), cursor.fetchall())
        self.assertEqual(read_gate0(self.development)['planned_launch_date'], '2027-04-03')

    def test_dates_and_numeric_values_roundtrip_as_typed_gate_columns(self):
        save_gate1(self.development, {
            'consumer_test': 20, 'tasting_score': Decimal('4.25'),
            'typed_cogs': Decimal('1234.5'), 'fridge_check_date': '2027-04-02',
        })
        gate1 = Gate1.objects.get(development_id=self.development.pk)
        self.assertEqual(gate1.consumer_test, 20)
        self.assertEqual(gate1.tasting_score, Decimal('4.25'))
        self.assertEqual(gate1.fridge_check_date, date(2027, 4, 2))
        self.assertEqual(Decimal(str(read_gate1(self.development)['typed_cogs'])), Decimal('1234.5'))

        save_gate2(self.development, {
            'allocation': 20, 'first_order_units': 0,
            'unit_weight_mean': Decimal('150.125'), 'launch_date': '2027-04-03',
        })
        gate2 = Gate2.objects.get(development_id=self.development.pk)
        self.assertEqual(gate2.allocation, 20)
        self.assertEqual(gate2.first_order_units, 0)
        self.assertEqual(gate2.unit_weight_mean, Decimal('150.125'))
        self.assertEqual(gate2.launch_date, date(2027, 4, 3))
        self.assertEqual(read_gate2(self.development)['launch_date'], '2027-04-03')

        save_gate3(self.development, {'complaints': 0, 'sales_vs_target': Decimal('12.75')})
        gate3 = Gate3.objects.get(development_id=self.development.pk)
        self.assertEqual(gate3.complaints, 0)
        self.assertEqual(gate3.sales_vs_target, Decimal('12.75'))

    def test_missing_numeric_values_remain_distinct_from_zero(self):
        save_gate2(self.development, {'allocation': None, 'first_order_units': 0})
        record = Gate2.objects.get(development_id=self.development.pk)
        self.assertIsNone(record.allocation)
        self.assertEqual(record.first_order_units, 0)
        save_gate2(self.development, {'allocation': 0, 'first_order_units': None})
        record.refresh_from_db()
        self.assertEqual(record.allocation, 0)
        self.assertIsNone(record.first_order_units)
        self.assertEqual(Gate2.objects.filter(development_id=self.development.pk).count(), 1)

    def test_multi_select_values_are_ordered_relational_rows_and_can_be_replaced(self):
        save_gate0(self.development, {
            'product_name': 'Multi-select example', 'category': 'FF',
            'improvement_reasons': ['R08', 'R01'], 'daypart': ['lunch', 'morning'],
            'first_food_safety_risk': ['milk', 'egg'], 'high_risk_inputs': ['dairy'],
        })
        saved = read_gate0(self.development)
        self.assertEqual(saved['improvement_reasons'], ['R08', 'R01'])
        self.assertEqual(saved['daypart'], ['lunch', 'morning'])
        self.assertEqual(saved['first_food_safety_risk'], ['milk', 'egg'])
        self.assertEqual(saved['high_risk_inputs'], ['dairy'])
        self.assertEqual(list(Gate0Daypart.objects.filter(gate_id=self.development.pk).values_list('value', flat=True)), ['lunch', 'morning'])
        self.assertEqual(Gate0ImprovementReason.objects.filter(gate_id=self.development.pk).count(), 2)

        save_gate0(self.development, {'product_name': 'Multi-select example', 'category': 'FF', 'daypart': ['evening'], 'improvement_reasons': []})
        self.assertEqual(read_gate0(self.development)['daypart'], ['evening'])
        self.assertFalse(Gate0ImprovementReason.objects.filter(gate_id=self.development.pk).exists())
        self.assertEqual(Gate0Daypart.objects.filter(gate_id=self.development.pk).count(), 1)

        save_gate3(self.development, {'lesson_tags': ['ingredient', 'vendor']})
        self.assertEqual(read_gate3(self.development)['lesson_tags'], ['ingredient', 'vendor'])
        self.assertEqual(list(Gate3LessonTag.objects.filter(gate_id=self.development.pk).values_list('value', flat=True)), ['ingredient', 'vendor'])

    def test_unconvertible_legacy_values_are_archived_until_resolved(self):
        save_gate0(self.development, {
            'product_name': 'Legacy example', 'category': 'FF',
            'cu_margin': 'TBD', 'retired_note': 'Keep this old note',
        })
        record = Gate0.objects.get(development_id=self.development.pk)
        self.assertIsNone(record.cu_margin)
        self.assertEqual(read_gate0(self.development)['cu_margin'], 'TBD')
        snapshots = GateDataArchive.objects.filter(gate='gate0', development_id=self.development.pk)
        self.assertTrue(any(json.loads(item.raw_data).get('retired_note') == 'Keep this old note' for item in snapshots))
        save_gate0(self.development, {'product_name': 'Legacy example', 'category': 'FF', 'cu_margin': Decimal('30')})
        self.assertEqual(Decimal(str(read_gate0(self.development)['cu_margin'])), Decimal('30'))
        self.assertTrue(any(json.loads(item.raw_data).get('cu_margin') == 'TBD' for item in snapshots))

    def test_competitors_analogs_and_cannibalisation_are_typed_child_rows(self):
        save_gate0(self.development, {
            'product_name': 'Benchmark example', 'category': 'FF',
            'competitor_benchmark': [
                {'product': 'Competitor B', 'price': 4200, 'weight_g': Decimal('155.25')},
                {'product': 'Competitor A', 'price': None, 'weight_g': None},
            ],
            'analog_skus_sales_target': [{'sku': 'SKU-1', 'units_per_store_day': Decimal('12.5')}],
            'cannibalisation': [{'sku': 'SKU-2', 'sales_taken_percent': Decimal('2.5')}],
        })
        competitors = list(Gate0Competitor.objects.filter(gate_id=self.development.pk))
        self.assertEqual([row.product for row in competitors], ['Competitor B', 'Competitor A'])
        self.assertEqual(competitors[0].price, 4200)
        self.assertEqual(competitors[0].weight_g, Decimal('155.25'))
        self.assertIsNone(competitors[1].price)
        self.assertEqual(Gate0AnalogSKU.objects.get(gate_id=self.development.pk).units_per_store_day, Decimal('12.5'))
        self.assertEqual(Gate0Cannibalisation.objects.get(gate_id=self.development.pk).sales_taken_percent, Decimal('2.5'))
        saved = read_gate0(self.development)
        self.assertEqual([row['product'] for row in saved['competitor_benchmark']], ['Competitor B', 'Competitor A'])

        save_gate0(self.development, {'product_name': 'Benchmark example', 'category': 'FF', 'competitor_benchmark': []})
        self.assertFalse(Gate0Competitor.objects.filter(gate_id=self.development.pk).exists())

    def test_material_rows_are_linked_to_the_same_gate1_development_id(self):
        save_gate1(self.development, {'raw_material_spec_price_moq_second_source': [
            {'material': 'Rice', 'spec_written': 'yes', 'price_kg': Decimal('4500.25'), 'moq': Decimal('2.125'), 'second_source': 'no'},
            {'material': 'Sauce', 'spec_written': '', 'price_kg': None, 'moq': None, 'second_source': ''},
        ]})
        materials = list(Gate1Material.objects.filter(gate_id=self.development.pk))
        self.assertEqual([row.material for row in materials], ['Rice', 'Sauce'])
        self.assertEqual(materials[0].price_kg, Decimal('4500.25'))
        self.assertEqual(materials[0].moq, Decimal('2.125'))
        self.assertIsNone(materials[1].price_kg)
        self.assertEqual(read_gate1(self.development)['raw_material_spec_price_moq_second_source'][0]['material'], 'Rice')
        save_gate1(self.development, {'raw_material_spec_price_moq_second_source': []})
        self.assertFalse(Gate1Material.objects.filter(gate_id=self.development.pk).exists())

    @skipUnless(connection.vendor == 'sqlite', 'Uses a SQLite trigger to simulate a write failure.')
    def test_failed_child_replacement_rolls_back_gate_values_and_existing_children(self):
        save_gate0(self.development, {
            'product_name': 'Before failure', 'category': 'FF', 'daypart': ['morning'],
            'competitor_benchmark': [{'product': 'Existing competitor', 'price': 1000}],
        })
        table = connection.ops.quote_name(Gate0Competitor._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TRIGGER typed_gate_reject_competitor BEFORE INSERT ON %s WHEN NEW.product = 'Reject this row' BEGIN SELECT RAISE(ABORT, 'forced child write failure'); END" % table)
        try:
            with self.assertRaises(IntegrityError):
                save_gate0(self.development, {
                    'product_name': 'Should roll back', 'category': 'ISF', 'daypart': ['evening'],
                    'competitor_benchmark': [{'product': 'Reject this row', 'price': 2000}],
                })
        finally:
            with connection.cursor() as cursor:
                cursor.execute('DROP TRIGGER typed_gate_reject_competitor')
        record = Gate0.objects.get(development_id=self.development.pk)
        self.assertEqual(record.product_name, 'Before failure')
        self.assertEqual(record.category, 'FF')
        self.assertEqual(read_gate0(self.development)['daypart'], ['morning'])
        self.assertEqual(list(Gate0Competitor.objects.filter(gate_id=self.development.pk).values_list('product', flat=True)), ['Existing competitor'])
        self.development.refresh_from_db()
        self.assertEqual(self.development.name, 'Before failure')
