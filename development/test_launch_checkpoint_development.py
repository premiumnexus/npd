"""Launch checkpoints keep each development's Day 7 and Day 14 records together."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .gate2 import save_brief as save_gate2
from .gate3 import Gate3Form
from .gate_storage import ensure_gate_rows
from .models import Food, LaunchCheckpoint


class LaunchCheckpointDevelopmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('launch-development-editor')
        self.user.groups.add(*Group.objects.filter(name__in=['Food Science', 'FF Planning', 'QA']))
        self.development = self.make_development('First launch process')
        self.client.force_login(self.user)

    def make_development(self, name):
        development = Food.objects.create(
            name=name, category='FF', stage='launch', owner=self.user,
            launched_at=timezone.now(),
        )
        ensure_gate_rows(development)
        save_gate2(development, {'day45_target_confirmed': 'changed', 'day45_units_store_day': '10'})
        return development

    def save_checkpoint(self, day, development=None, **values):
        development = development or self.development
        payload = {
            'action': 'checkpoint_save', 'day': day,
            'checked_date': '2026-11-01' if day == 7 else '2026-11-08',
            'sample_result': 'within', 'actual_apsd': '8', 'sample_weight_g':'150', 'complaints_count':'0',
        }
        payload.update(values)
        response = self.client.post(reverse('detail', args=[development.pk]), payload)
        self.assertEqual(response.status_code, 302)
        return LaunchCheckpoint.objects.get(development_id=development.pk, day=day)

    def test_day7_and_day14_save_read_and_update_the_same_development_rows(self):
        day7 = self.save_checkpoint(7)
        day14 = self.save_checkpoint(
            14, sample_result='conditional', actual_apsd='9.5', complaints_count='3',
            action_plan='Recheck batch; Food Science; tomorrow',
        )
        self.assertEqual(day7.development, self.development)
        self.assertEqual(day14.development_id, self.development.pk)
        self.assertEqual(self.development.launch_checkpoints.count(), 2)
        updated = self.save_checkpoint(
            7, sample_result='outside', actual_apsd='12', checked_date='2026-11-02',
            action_plan='Correct cooling; Food Science; today',
        )
        self.assertEqual(updated.pk, day7.pk)
        self.assertEqual(LaunchCheckpoint.objects.filter(development=self.development).count(), 2)
        self.assertEqual(updated.checked_date, date(2026, 11, 2))
        self.assertEqual(updated.sales_snapshot, Decimal('12'))
        self.assertEqual(updated.sample_result, 'outside')
        day14.refresh_from_db()
        self.assertEqual(day14.checked_date, date(2026, 11, 8))
        self.assertEqual(day14.sales_snapshot, Decimal('9.5'))
        self.assertEqual(day14.complaints_count, 3)
        page = self.client.get(reverse('detail', args=[self.development.pk]))
        forms = {card['day']: card['form'] for card in page.context['checkpoint_cards']}
        self.assertEqual(forms[7].initial['sample_result'], 'outside')
        self.assertEqual(forms[7].initial['actual_apsd'], Decimal('12'))
        self.assertEqual(forms[14].initial['sample_result'], 'conditional')
        self.assertEqual(forms[14].initial['complaints_count'], 3)
        with connection.cursor() as cursor:
            cursor.execute('SELECT development_id, day FROM development_launchcheckpoint')
            self.assertEqual(set(cursor.fetchall()), {(self.development.pk, 7), (self.development.pk, 14)})

    def test_different_processes_stay_isolated_and_gate3_reads_the_reverse_relation(self):
        other = self.make_development('Second launch process')
        self.save_checkpoint(7)
        self.save_checkpoint(14, sample_result='outside', action_plan='Investigate first process')
        self.save_checkpoint(7, development=other, sample_result='outside', action_plan='Investigate second process')
        self.save_checkpoint(14, development=other, actual_apsd='15', complaints_count='2')
        for development, expected in [(self.development, ('yes', 'no')), (other, ('no', 'yes'))]:
            form = Gate3Form(food=development)
            self.assertEqual(form.initial['shelf_samples_day7_day14'], expected[0])
            self.assertEqual(form.initial['day14_sample_within_tolerance'], expected[1])
            self.assertEqual(development.launch_checkpoints.count(), 2)
        first_ids = set(self.development.launch_checkpoints.values_list('pk', flat=True))
        other_ids = set(other.launch_checkpoints.values_list('pk', flat=True))
        self.assertFalse(first_ids & other_ids)
        self.assertEqual(LaunchCheckpoint.objects.count(), 4)
        page = self.client.get(reverse('detail', args=[self.development.pk]))
        self.assertEqual(page.context['checkpoint_cards'][1]['form'].initial['sample_result'], 'outside')
        self.assertEqual(page.context['checkpoint_cards'][1]['form'].initial['complaints_count'],0)
        other_page = self.client.get(reverse('detail', args=[other.pk]))
        self.assertEqual(other_page.context['checkpoint_cards'][1]['form'].initial['sample_result'], 'within')
        self.assertEqual(other_page.context['checkpoint_cards'][1]['form'].initial['complaints_count'], 2)

    def test_database_enforces_one_checkpoint_for_each_development_and_day(self):
        first = LaunchCheckpoint.objects.create(development=self.development, day=7)
        LaunchCheckpoint.objects.create(development_id=self.development.pk, day=14)
        other = self.make_development('Independent uniqueness process')
        LaunchCheckpoint.objects.create(development=other, day=7)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LaunchCheckpoint.objects.create(development_id=self.development.pk, day=7)
        self.assertEqual(LaunchCheckpoint.objects.count(), 3)
        self.assertEqual(self.development.launch_checkpoints.get(day=7).pk, first.pk)
        self.assertEqual(LaunchCheckpoint._meta.get_field('development').column, 'development_id')
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, LaunchCheckpoint._meta.db_table)
        self.assertTrue(any(
            item['unique'] and set(item['columns']) == {'development_id', 'day'}
            for item in constraints.values()
        ))
