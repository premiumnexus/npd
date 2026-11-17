"""Fresh installation and retained defaults for the consolidated migration."""
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Group
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from .models import Food, Gate0Option, GateAccess, Ingredient, Supplier, TargetCostingSettings
from .workflow import PARTIES


class BaselineDefaultsTests(TestCase):
    def test_fresh_install_seeds_configuration_without_demo_records(self):
        self.assertEqual(set(Group.objects.values_list('name', flat=True)), set(PARTIES))
        self.assertEqual(GateAccess.objects.count(), 50)
        self.assertTrue(GateAccess.objects.get(group__name='QA', stage='gate2').can_qa_accept)
        self.assertTrue(GateAccess.objects.get(group__name='NPD / Product Developer', stage='gate1').can_submit)
        self.assertFalse(GateAccess.objects.get(group__name='QA', stage='gate0').can_submit)
        self.assertEqual(TargetCostingSettings.objects.get(pk=1).vat_percent, Decimal('10.00'))
        self.assertEqual(Gate0Option.objects.filter(kind='product_role').count(), 5)
        self.assertEqual(Gate0Option.objects.filter(kind='improvement_reason').count(), 11)
        self.assertEqual(Gate0Option.objects.filter(kind='allergen').count(), 9)
        self.assertEqual(Gate0Option.objects.filter(kind='high_risk').count(), 5)
        for model in (Food, Supplier, Ingredient):
            self.assertEqual(model.objects.count(), 0)

    def test_defaults_can_be_reapplied_without_overwriting_admin_changes(self):
        access = GateAccess.objects.get(group__name='QA', stage='gate2')
        access.can_qa_accept = False
        access.save()
        option = Gate0Option.objects.get(kind='product_role', code='core', category='')
        option.label = 'Our core products'
        option.save()
        TargetCostingSettings.objects.filter(pk=1).update(vat_percent=Decimal('12.50'))
        migration = import_module('development.migrations.0001_baseline')
        editor = SimpleNamespace(connection=connection)
        for seed in (migration.seed_workflow_defaults, migration.seed_gate0_defaults, migration.seed_costing_defaults):
            seed(apps, editor)
            seed(apps, editor)
        access.refresh_from_db()
        option.refresh_from_db()
        self.assertFalse(access.can_qa_accept)
        self.assertEqual(option.label, 'Our core products')
        self.assertEqual(TargetCostingSettings.objects.get(pk=1).vat_percent, Decimal('12.50'))
        self.assertEqual(GateAccess.objects.count(), 50)
        self.assertEqual(Gate0Option.objects.count(), 30)


class BaselineSchemaTests(TransactionTestCase):
    def test_unapply_and_recreate_the_complete_schema(self):
        target = [('development', '0001_baseline')]
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(target))
        MigrationExecutor(connection).migrate([('development', None)])
        self.assertNotIn('development_food', connection.introspection.table_names())
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        historical = executor.loader.project_state(target).apps
        for model in historical.get_app_config('development').get_models():
            self.assertIn(model._meta.db_table, connection.introspection.table_names())
        self.assertEqual(historical.get_model('development', 'GateAccess').objects.count(), 50)
        self.assertEqual(historical.get_model('development', 'Gate0Option').objects.count(), 30)
        self.assertEqual(historical.get_model('development', 'TargetCostingSettings').objects.get(pk=1).vat_percent, Decimal('10.00'))
        self.assertEqual(historical.get_model('development', 'Food').objects.count(), 0)
