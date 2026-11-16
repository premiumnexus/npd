"""Exercise the actual legacy-to-relational gate migration with historical models."""
from datetime import date
from decimal import Decimal
import json

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RelationalGateMigrationTests(TransactionTestCase):
    migrate_from = [('development', '0033_gate2_quality_standard_slot')]
    migrate_to = [('development', '0034_relational_gate_records')]

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_latest_schema)
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.old_apps = executor.loader.project_state(self.migrate_from).apps

    def restore_latest_schema(self):
        executor=MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def tearDown(self):
        try:
            self.restore_latest_schema()
        finally:
            super().tearDown()

    def test_existing_json_becomes_typed_rows_without_changing_process_ids(self):
        User = self.old_apps.get_model('auth', 'User')
        Food = self.old_apps.get_model('development', 'Food')
        owner = User.objects.create(username='migration-owner')
        ContentType=self.old_apps.get_model('contenttypes','ContentType')
        Permission=self.old_apps.get_model('auth','Permission')
        Group=self.old_apps.get_model('auth','Group')
        old_type,_=ContentType.objects.get_or_create(app_label='development',model='gate0brief')
        permission,_=Permission.objects.get_or_create(content_type=old_type,codename='change_gate0brief',defaults={'name':'Can change gate 0 brief'})
        editors=Group.objects.create(name='Existing gate editors')
        editors.permissions.add(permission)
        owner.user_permissions.add(permission)
        valid = Food.objects.create(pk=707, name='Original title', category='FF', owner_id=owner.pk)
        invalid = Food.objects.create(pk=1103, name='Legacy inputs', category='FF', owner_id=owner.pk)
        untouched = Food.objects.create(pk=2003, name='No brief yet', category='ISF', owner_id=owner.pk)
        root_ids = {valid.pk, invalid.pk, untouched.pk}
        originals = {}

        def legacy(gate, source_pk, development_id, payload=None, raw=None):
            text = raw if raw is not None else json.dumps(payload, ensure_ascii=False, indent=2)
            self.old_apps.get_model('development', 'Gate%sBrief' % gate).objects.create(
                pk=source_pk, food_id=development_id, data=text,
            )
            originals[('gate%s' % gate, source_pk)] = (development_id, text)

        legacy(0, 31, valid.pk, {
            'product_name': 'Шинэ будаатай хоол', 'category': 'ISF',
            'target_shelf_price': 9000, 'cu_margin': '30.5', 'vendor_rebate': 0.1,
            'planned_launch_date': '2027-04-03',
            'improvement_reasons': ['R08', 'R01'], 'daypart': 'lunch',
            'first_food_safety_risk': ['milk', 'egg'], 'high_risk_inputs': ['dairy'],
            'competitor_benchmark': [
                {'product': 'Competitor B', 'price': 4500, 'weight_g': '155.25'},
                {'product': 'Competitor A', 'price': None, 'weight_g': None},
            ],
            'analog_skus_sales_target': [{'sku': 'SKU-A', 'units_per_store_day': '12.5'}],
            'cannibalisation': [{'sku': 'SKU-B', 'sales_taken_percent': '2.5'}],
        })
        legacy(1, 83, valid.pk, {
            'consumer_test': 50, 'tasting_score': '4.25', 'fridge_check_date': '2027-04-02',
            'raw_material_spec_price_moq_second_source': [
                {'material': 'Rice', 'spec_written': 'yes', 'price_kg': '4500.25', 'moq': '2.125', 'second_source': 'no'},
                {'material': 'Sauce', 'spec_written': '', 'price_kg': None, 'moq': None, 'second_source': ''},
            ],
        })
        legacy(2, 97, valid.pk, {
            'mass_trial_result': '10.125', 'unit_weight_mean': '150.875',
            'launch_date': '2027-04-04', 'day45_target_confirmed': 'changed',
            'day45_units_store_day': '15.5', 'day45_writeoff_percent': '3.25',
            'signed_npd': 'yes', 'quality_texture_target': 'Retired texture description',
        })
        legacy(3, 119, valid.pk, {
            'sales_vs_target': '17.5', 'complaints': 0, 'actual_launch_date': '2027-04-04',
            'lesson_card': 'Keep the packaging', 'lesson_tags': ['vendor', 'ingredient', 'vendor'],
        })
        legacy(0, 151, invalid.pk, {
            'product_name': 'Unconverted legacy input', 'category': 'FF',
            'cu_margin': 'TBD', 'store_count': 1.5, 'planned_launch_date': 'next winter',
            'competitor_benchmark': [{'product': 'Old competitor', 'price': 'unknown', 'weight_g': '12.25'}],
            'retired_note': 'Preserve this exact note',
        })
        legacy(1, 166, invalid.pk, raw='{not valid JSON')
        legacy(2, 177, invalid.pk, {'allocation': True, 'first_order_units': 0})
        orphan_id = 99991
        if connection.vendor == 'sqlite':
            with connection.constraint_checks_disabled():
                legacy(3, 299, orphan_id, {'lesson_card': 'An orphan must be archived, not assigned a new process'})

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        self.assertTrue(apps.get_model('auth','Group').objects.get(pk=editors.pk).permissions.filter(codename='change_gate0').exists())
        for child_action in ['add','change','delete','view']:
            self.assertTrue(apps.get_model('auth','Group').objects.get(pk=editors.pk).permissions.filter(codename=child_action+'_gate0competitor').exists())
        self.assertTrue(apps.get_model('auth','User').objects.get(pk=owner.pk).user_permissions.filter(codename='change_gate0').exists())
        Food = apps.get_model('development', 'Food')
        Archive = apps.get_model('development', 'GateDataArchive')

        self.assertEqual(set(Food.objects.values_list('pk', flat=True)), root_ids)
        for gate in range(4):
            model = apps.get_model('development', 'Gate%s' % gate)
            self.assertEqual(set(model.objects.values_list('pk', flat=True)), root_ids)
            self.assertEqual(model.objects.get(pk=valid.pk).development_id, valid.pk)
            self.assertFalse(model.objects.filter(pk=orphan_id).exists())
        for (gate, source_pk), (development_id, raw) in originals.items():
            archive = Archive.objects.get(gate=gate, source_pk=source_pk)
            self.assertEqual(archive.development_id, development_id)
            self.assertEqual(archive.raw_data, raw)

        gate0 = apps.get_model('development', 'Gate0').objects.get(pk=valid.pk)
        self.assertEqual(gate0.product_name, 'Шинэ будаатай хоол')
        self.assertEqual(gate0.category, 'ISF')
        self.assertEqual(gate0.target_shelf_price, 9000)
        self.assertEqual(gate0.cu_margin, Decimal('30.5'))
        self.assertEqual(gate0.vendor_rebate, Decimal('0.1'))
        self.assertEqual(gate0.planned_launch_date, date(2027, 4, 3))
        self.assertEqual(list(apps.get_model('development', 'Gate0ImprovementReason').objects.filter(gate_id=valid.pk).values_list('value', flat=True)), ['R08', 'R01'])
        self.assertEqual(list(apps.get_model('development', 'Gate0Daypart').objects.filter(gate_id=valid.pk).values_list('value', flat=True)), ['lunch'])
        self.assertEqual(list(apps.get_model('development', 'Gate0Allergen').objects.filter(gate_id=valid.pk).values_list('value', flat=True)), ['milk', 'egg'])
        self.assertEqual(list(apps.get_model('development', 'Gate0HighRiskInput').objects.filter(gate_id=valid.pk).values_list('value', flat=True)), ['dairy'])
        competitors = list(apps.get_model('development', 'Gate0Competitor').objects.filter(gate_id=valid.pk))
        self.assertEqual([row.position for row in competitors], [0, 1])
        self.assertEqual([row.product for row in competitors], ['Competitor B', 'Competitor A'])
        self.assertEqual(competitors[0].price, 4500)
        self.assertEqual(competitors[0].weight_g, Decimal('155.25'))
        self.assertIsNone(competitors[1].price)
        self.assertEqual(apps.get_model('development', 'Gate0AnalogSKU').objects.get(gate_id=valid.pk).units_per_store_day, Decimal('12.5'))
        self.assertEqual(apps.get_model('development', 'Gate0Cannibalisation').objects.get(gate_id=valid.pk).sales_taken_percent, Decimal('2.5'))

        gate1 = apps.get_model('development', 'Gate1').objects.get(pk=valid.pk)
        self.assertEqual(gate1.consumer_test, 50)
        self.assertEqual(gate1.tasting_score, Decimal('4.25'))
        self.assertEqual(gate1.fridge_check_date, date(2027, 4, 2))
        materials = list(apps.get_model('development', 'Gate1Material').objects.filter(gate_id=valid.pk))
        self.assertEqual([row.material for row in materials], ['Rice', 'Sauce'])
        self.assertEqual(materials[0].price_kg, Decimal('4500.25'))
        self.assertEqual(materials[0].moq, Decimal('2.125'))
        self.assertIsNone(materials[1].price_kg)
        gate2 = apps.get_model('development', 'Gate2').objects.get(pk=valid.pk)
        self.assertEqual(gate2.mass_trial_result, Decimal('10.125'))
        self.assertEqual(gate2.unit_weight_mean, Decimal('150.875'))
        self.assertEqual(gate2.launch_date, date(2027, 4, 4))
        self.assertEqual(gate2.day45_units_store_day, Decimal('15.5'))
        gate3 = apps.get_model('development', 'Gate3').objects.get(pk=valid.pk)
        self.assertEqual(gate3.complaints, 0)
        self.assertEqual(gate3.actual_launch_date, date(2027, 4, 4))
        self.assertEqual(list(apps.get_model('development', 'Gate3LessonTag').objects.filter(gate_id=valid.pk).values_list('value', flat=True)), ['vendor', 'ingredient', 'vendor'])

        invalid_gate = apps.get_model('development', 'Gate0').objects.get(pk=invalid.pk)
        self.assertIsNone(invalid_gate.cu_margin)
        self.assertIsNone(invalid_gate.store_count)
        self.assertIsNone(invalid_gate.planned_launch_date)
        self.assertIsNone(apps.get_model('development', 'Gate0Competitor').objects.get(gate_id=invalid.pk).price)
        self.assertIsNone(apps.get_model('development', 'Gate2').objects.get(pk=invalid.pk).allocation)
        invalid_issues = json.loads(Archive.objects.get(gate='gate0', source_pk=151).issues)
        self.assertIn({'field': 'cu_margin', 'reason': 'invalid_scalar'}, invalid_issues)
        self.assertIn({'field': 'store_count', 'reason': 'invalid_scalar'}, invalid_issues)
        self.assertIn({'field': 'retired_note', 'reason': 'retired_or_unknown'}, invalid_issues)
        self.assertIn({'reason': 'invalid_json'}, json.loads(Archive.objects.get(gate='gate1', source_pk=166).issues))
        retired = json.loads(Archive.objects.get(gate='gate2', source_pk=97).raw_data)
        self.assertEqual(retired['signed_npd'], 'yes')
        self.assertEqual(retired['quality_texture_target'], 'Retired texture description')
        if connection.vendor == 'sqlite':
            self.assertIn({'reason': 'missing_development'}, json.loads(Archive.objects.get(gate='gate3', source_pk=299).issues))
        self.assertEqual(apps.get_model('development', 'Gate0').objects.get(pk=untouched.pk).product_name, 'No brief yet')
        with connection.cursor() as cursor:
            columns = {column.name for column in connection.introspection.get_table_description(cursor, 'development_gate0')}
        self.assertTrue({'development_id', 'product_name', 'category'} <= columns)
        self.assertNotIn('data', columns)

    def test_forward_reverse_forward_preserves_invalid_sources_and_current_updates(self):
        User = self.old_apps.get_model('auth', 'User')
        Food = self.old_apps.get_model('development', 'Food')
        owner = User.objects.create(username='migration-roundtrip-owner')
        process = Food.objects.create(pk=391, name='Original process', category='FF', owner_id=owner.pk)
        original_payload = {
            'product_name': 'Original gate title', 'category': 'FF',
            'cu_margin': 'TBD', 'vendor_rebate': '1.25',
            'planned_launch_date': '2027-04-03',
            'competitor_benchmark': 'Legacy competitor description, not structured rows',
            'daypart': ['lunch'], 'retired_note': 'Keep the old note verbatim',
        }
        original_raw = json.dumps(original_payload, ensure_ascii=False, indent=3)
        self.old_apps.get_model('development', 'Gate0Brief').objects.create(
            pk=41, food_id=process.pk, data=original_raw,
        )
        self.old_apps.get_model('development', 'Gate1Brief').objects.create(
            pk=71, food_id=process.pk,
            data=json.dumps({'marketing_name': 'Original campaign', 'raw_material_spec_price_moq_second_source': [
                {'material': 'Rice', 'spec_written': 'yes', 'price_kg': '4500.25', 'moq': '2.125', 'second_source': 'no'},
            ]}),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        typed_apps = executor.loader.project_state(self.migrate_to).apps
        Gate0 = typed_apps.get_model('development', 'Gate0')
        Gate1 = typed_apps.get_model('development', 'Gate1')
        Daypart = typed_apps.get_model('development', 'Gate0Daypart')
        Material = typed_apps.get_model('development', 'Gate1Material')
        Archive = typed_apps.get_model('development', 'GateDataArchive')
        initial_archive = Archive.objects.get(gate='gate0', source_pk=41)
        self.assertEqual(initial_archive.raw_data, original_raw)
        self.assertIsNone(initial_archive.reviewed_at)
        self.assertIsNone(Gate0.objects.get(pk=process.pk).cu_margin)

        # Update valid current fields while leaving the unresolved legacy inputs alone.
        Gate0.objects.filter(pk=process.pk).update(
            product_name='Current gate title', vendor_rebate=None,
            planned_launch_date=date(2028, 2, 29),
        )
        Gate1.objects.filter(pk=process.pk).update(marketing_name='Current campaign')
        Daypart.objects.filter(gate_id=process.pk).delete()
        Daypart.objects.bulk_create([
            Daypart(gate_id=process.pk, position=0, value='morning'),
            Daypart(gate_id=process.pk, position=1, value='evening'),
        ])
        material = Material.objects.get(gate_id=process.pk)
        material.price_kg = Decimal('4600.75')
        material.save(update_fields=['price_kg'])

        # A development started after the migration also needs a coherent rollback.
        NewFood = typed_apps.get_model('development', 'Food')
        newer = NewFood.objects.create(pk=1109, name='New process', category='ISF', owner_id=owner.pk)
        for number in range(4):
            values = {'product_name': 'New process', 'category': 'ISF'} if number == 0 else {}
            typed_apps.get_model('development', 'Gate%s' % number).objects.create(development_id=newer.pk, **values)
        root_ids = {process.pk, newer.pk}

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        rolled_apps = executor.loader.project_state(self.migrate_from).apps
        rolled = rolled_apps.get_model('development', 'Gate0Brief').objects.get(food_id=process.pk)
        restored = json.loads(rolled.data)
        self.assertEqual(rolled.pk, 41)
        self.assertEqual(restored['product_name'], 'Current gate title')
        self.assertIsNone(restored['vendor_rebate'])
        self.assertEqual(restored['planned_launch_date'], '2028-02-29')
        self.assertEqual(restored['cu_margin'], 'TBD')
        self.assertEqual(restored['competitor_benchmark'], original_payload['competitor_benchmark'])
        self.assertEqual(restored['retired_note'], original_payload['retired_note'])
        self.assertEqual(restored['daypart'], ['morning', 'evening'])
        self.assertIn(original_raw, restored['_relational_source_archives'])
        rolled_gate1 = json.loads(rolled_apps.get_model('development', 'Gate1Brief').objects.get(food_id=process.pk).data)
        self.assertEqual(rolled_gate1['marketing_name'], 'Current campaign')
        self.assertEqual(Decimal(rolled_gate1['raw_material_spec_price_moq_second_source'][0]['price_kg']), Decimal('4600.75'))
        self.assertEqual(set(rolled_apps.get_model('development', 'Food').objects.values_list('pk', flat=True)), root_ids)
        for number in range(4):
            self.assertEqual(set(rolled_apps.get_model('development', 'Gate%sBrief' % number).objects.values_list('food_id', flat=True)), root_ids)
        rolled_raw = rolled.data

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        final_apps = executor.loader.project_state(self.migrate_to).apps
        for number in range(4):
            self.assertEqual(set(final_apps.get_model('development', 'Gate%s' % number).objects.values_list('pk', flat=True)), root_ids)
        final_gate0 = final_apps.get_model('development', 'Gate0').objects.get(pk=process.pk)
        self.assertEqual(final_gate0.product_name, 'Current gate title')
        self.assertEqual(final_gate0.planned_launch_date, date(2028, 2, 29))
        self.assertIsNone(final_gate0.cu_margin)
        self.assertIsNone(final_gate0.vendor_rebate)
        self.assertFalse(final_apps.get_model('development', 'Gate0Competitor').objects.filter(gate_id=process.pk).exists())
        self.assertEqual(list(final_apps.get_model('development', 'Gate0Daypart').objects.filter(gate_id=process.pk).values_list('value', flat=True)), ['morning', 'evening'])
        self.assertEqual(final_apps.get_model('development', 'Gate1Material').objects.get(gate_id=process.pk).price_kg, Decimal('4600.75'))
        final_archive = final_apps.get_model('development', 'GateDataArchive').objects.get(gate='gate0', source_pk=41)
        self.assertEqual(final_archive.raw_data, rolled_raw)
        self.assertIn(original_raw, json.loads(final_archive.raw_data)['_relational_source_archives'])
        self.assertEqual(set(final_apps.get_model('development', 'Food').objects.values_list('pk', flat=True)), root_ids)
