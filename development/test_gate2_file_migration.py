"""Exercise the Gate 2 document-table migration and its reverse operation."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Gate2FileMigrationTests(TransactionTestCase):
    migrate_from = [('development', '0037_gate1_files')]
    migrate_to = [('development', '0038_gate2_files')]
    history_fields = (
        'pk', 'food_id', 'actor_id', 'text', 'attachment', 'attachment_name',
        'attachment_stage', 'attachment_slot', 'created',
    )
    file_fields = (
        'pk', 'development_id', 'slot_code', 'file', 'original_filename',
        'uploader_id', 'uploaded_at', 'activity_id',
    )

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(self.restore_latest_schema)
        executor.migrate(self.migrate_from)
        self.old_apps = executor.loader.project_state(self.migrate_from).apps
        User = self.old_apps.get_model('auth', 'User')
        Food = self.old_apps.get_model('development', 'Food')
        Gate1 = self.old_apps.get_model('development', 'Gate1')
        self.owner = User.objects.create(username='gate2-file-migration-owner')
        self.development = Food.objects.create(pk=701, name='Gate 2 documents', owner_id=self.owner.pk)
        self.other_development = Food.objects.create(pk=808, name='Another process', owner_id=self.owner.pk)
        self.when = datetime(2026, 10, 20, 3, 4, 5, 123000, tzinfo=dt_timezone.utc)
        self.sources = {}
        for number in range(1, 12):
            stage = '' if number == 2 else 'gate1' if number == 3 else 'gate2'
            record = self.activity(
                self.development.pk, 'G2-F%s' % number, stage,
                'Slot %s.pdf' % number, self.when + timedelta(minutes=number),
                actor_id=None if number == 9 else self.owner.pk, pk=100 + number,
            )
            self.sources[record.pk] = self.source_values(record)
        revised = self.activity(self.development.pk, 'G2-F1', 'gate2', 'Revised.pdf', self.when + timedelta(days=1), pk=125)
        self.sources[revised.pk] = self.source_values(revised)
        other = self.activity(self.other_development.pk, 'G2-F1', 'gate2', 'Other process.pdf', self.when, pk=151)
        self.sources[other.pk] = self.source_values(other)

        self.activity(self.development.pk, 'G0-F2', 'gate0', 'Gate0-retained.pdf', self.when, pk=201)
        self.activity(self.development.pk, 'G1-F3', 'gate1', 'Gate1-retained.pdf', self.when, pk=202)
        marketing = self.activity(self.development.pk, 'G1-F10', 'gate1', 'Marketing-retained.pdf', self.when, pk=203)
        self.activity(self.development.pk, 'G2-F12', 'gate2', 'ISF-manual-retained.pdf', self.when, pk=204)
        self.activity(self.development.pk, 'G2-F13', 'gate2', 'Quality-standard-retained.pdf', self.when, pk=205)
        Gate1.objects.create(
            development_id=self.development.pk, marketing_brief='Keep the marketing idea',
            marketing_idea_file=marketing.attachment.name,
            marketing_idea_filename=marketing.attachment_name,
            marketing_idea_uploaded_by_id=marketing.actor_id,
            marketing_idea_uploaded_at=marketing.created,
        )
        Activity = self.old_apps.get_model('development', 'Activity')
        self.comment = Activity.objects.create(
            food_id=self.development.pk, actor_id=self.owner.pk,
            text='A plain Gate 2 comment', attachment_stage='gate2', attachment_slot='G2-F8',
        )
        for model_name, slot, path in [
            ('Gate0File', 'G0-F1', 'gate0/701/stored-gate0.pdf'),
            ('Gate1File', 'G1-F1', 'gate1/701/stored-gate1.pdf'),
        ]:
            log = Activity.objects.create(
                food_id=self.development.pk, actor_id=self.owner.pk,
                text='An existing normalized file log: ' + model_name,
            )
            self.old_apps.get_model('development', model_name).objects.create(
                development_id=self.development.pk, slot_code=slot,
                file=path, original_filename=model_name + '.pdf', uploader_id=self.owner.pk,
                uploaded_at=self.when, activity_id=log.pk,
            )
        self.file_tables_before = {
            name: list(self.old_apps.get_model('development', name).objects.order_by('pk').values(*self.file_fields))
            for name in ['Gate0File', 'Gate1File']
        }
        self.before = self.history(self.old_apps)
        self.unrelated_before = [row for row in self.before if row['pk'] not in self.sources]
        self.marketing_before = self.marketing_pointer(self.old_apps)

    def restore_latest_schema(self):
        MigrationExecutor(connection).migrate(self.latest_targets)

    def tearDown(self):
        try:
            self.restore_latest_schema()
        finally:
            super().tearDown()

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def activity(self, development_id, slot, stage, filename, when, actor_id='owner', pk=None):
        Activity = self.old_apps.get_model('development', 'Activity')
        values = {
            'food_id': development_id,
            'actor_id': self.owner.pk if actor_id == 'owner' else actor_id,
            'text': 'Keep document log: ' + filename,
            'attachment': 'activities/%s/%s' % (development_id, filename),
            'attachment_name': filename, 'attachment_stage': stage, 'attachment_slot': slot,
        }
        if pk is not None:
            values['pk'] = pk
        record = Activity.objects.create(**values)
        Activity.objects.filter(pk=record.pk).update(created=when)
        record.refresh_from_db()
        return record

    def source_values(self, activity):
        return {
            'development_id': activity.food_id, 'slot_code': activity.attachment_slot,
            'file': activity.attachment.name, 'original_filename': activity.attachment_name,
            'uploader_id': activity.actor_id, 'uploaded_at': activity.created,
            'text': activity.text,
        }

    def history(self, apps):
        return list(apps.get_model('development', 'Activity').objects.order_by('pk').values(*self.history_fields))

    def marketing_pointer(self, apps):
        return apps.get_model('development', 'Gate1').objects.values(
            'development_id', 'marketing_brief', 'marketing_idea_file', 'marketing_idea_filename',
            'marketing_idea_uploaded_by_id', 'marketing_idea_uploaded_at',
        ).get(development_id=self.development.pk)

    def assert_unrelated_unchanged(self, apps):
        history = [row for row in self.history(apps) if row['pk'] in {row['pk'] for row in self.unrelated_before}]
        self.assertEqual(history, self.unrelated_before)
        self.assertEqual(self.marketing_pointer(apps), self.marketing_before)
        for name, expected in self.file_tables_before.items():
            actual = list(apps.get_model('development', name).objects.order_by('pk').values(*self.file_fields))
            self.assertEqual(actual, expected)

    def assert_moved_sources(self, apps):
        Gate2File = apps.get_model('development', 'Gate2File')
        Activity = apps.get_model('development', 'Activity')
        for activity_id, expected in self.sources.items():
            uploaded = Gate2File.objects.get(activity_id=activity_id)
            self.assertEqual(uploaded.pk, activity_id)
            self.assertEqual(uploaded.development_id, expected['development_id'])
            self.assertEqual(uploaded.slot_code, expected['slot_code'])
            self.assertEqual(uploaded.file.name, expected['file'])
            self.assertEqual(uploaded.original_filename, expected['original_filename'])
            self.assertEqual(uploaded.uploader_id, expected['uploader_id'])
            self.assertEqual(uploaded.uploaded_at, expected['uploaded_at'])
            log = Activity.objects.get(pk=activity_id)
            self.assertEqual(log.food_id, expected['development_id'])
            self.assertEqual(log.actor_id, expected['uploader_id'])
            self.assertEqual(log.created, expected['uploaded_at'])
            self.assertEqual(log.text, expected['text'])
            self.assertFalse(log.attachment)
            self.assertEqual(log.attachment_name, '')
            self.assertEqual(log.attachment_stage, '')
            self.assertEqual(log.attachment_slot, '')

    def test_all_eleven_slots_move_by_slot_code_and_leave_other_documents_unchanged(self):
        with patch('django.core.files.storage.Storage.save', side_effect=AssertionError('Files must not be copied')), \
             patch('django.core.files.storage.Storage.open', side_effect=AssertionError('Files must not be opened')), \
             patch('django.core.files.storage.Storage.delete', side_effect=AssertionError('Files must not be deleted')):
            apps = self.migrate(self.migrate_to)
        Gate2File = apps.get_model('development', 'Gate2File')
        self.assertEqual(Gate2File._meta.db_table, 'development_gate2_files')
        self.assertEqual(Gate2File.objects.count(), len(self.sources))
        self.assertEqual(set(Gate2File.objects.values_list('slot_code', flat=True)), {'G2-F%s' % number for number in range(1, 12)})
        self.assert_moved_sources(apps)
        self.assert_unrelated_unchanged(apps)
        self.assertEqual(set(apps.get_model('development', 'Food').objects.values_list('pk', flat=True)), {701, 808})

    def test_reverse_and_reapply_restore_metadata_and_handle_standalone_files(self):
        apps = self.migrate(self.migrate_to)
        Gate2File = apps.get_model('development', 'Gate2File')
        standalone_path = 'activities/808/standalone-gate2.pdf'
        standalone_time = self.when + timedelta(days=2)
        Gate2File.objects.create(
            development_id=self.other_development.pk, slot_code='G2-F11', file=standalone_path,
            original_filename='Standalone.pdf', uploader_id=None,
            uploaded_at=standalone_time, activity_id=None,
        )
        with patch('django.core.files.storage.Storage.save', side_effect=AssertionError('Files must not be copied')), \
             patch('django.core.files.storage.Storage.delete', side_effect=AssertionError('Files must not be deleted')):
            restored = self.migrate(self.migrate_from)
        Activity = restored.get_model('development', 'Activity')
        for activity_id, expected in self.sources.items():
            log = Activity.objects.get(pk=activity_id)
            self.assertEqual(log.food_id, expected['development_id'])
            self.assertEqual(log.actor_id, expected['uploader_id'])
            self.assertEqual(log.attachment.name, expected['file'])
            self.assertEqual(log.attachment_name, expected['original_filename'])
            self.assertEqual(log.attachment_stage, 'gate2')
            self.assertEqual(log.attachment_slot, expected['slot_code'])
            self.assertEqual(log.text, expected['text'])
            self.assertEqual(log.created, expected['uploaded_at'])
        standalone = Activity.objects.get(attachment=standalone_path)
        self.assertEqual(standalone.food_id, self.other_development.pk)
        self.assertIsNone(standalone.actor_id)
        self.assertEqual(standalone.attachment_name, 'Standalone.pdf')
        self.assertEqual(standalone.attachment_slot, 'G2-F11')
        self.assertEqual(standalone.created, standalone_time)
        self.assert_unrelated_unchanged(restored)

        reapplied = self.migrate(self.migrate_to)
        self.assert_moved_sources(reapplied)
        Gate2File = reapplied.get_model('development', 'Gate2File')
        self.assertEqual(Gate2File.objects.count(), len(self.sources) + 1)
        standalone_file = Gate2File.objects.get(file=standalone_path)
        self.assertEqual(standalone_file.activity_id, standalone.pk)
        self.assertEqual(standalone_file.development_id, self.other_development.pk)
        self.assertEqual(standalone_file.uploaded_at, standalone_time)
        self.assert_unrelated_unchanged(reapplied)

    @skipUnless(connection.vendor == 'sqlite', 'Uses a deliberately invalid legacy foreign key fixture.')
    def test_missing_parent_is_preserved_in_history_and_not_given_a_new_process(self):
        orphan_id = 999991
        with connection.constraint_checks_disabled():
            orphan = self.activity(orphan_id, 'G2-F1', 'gate2', 'Orphan.pdf', self.when)
        orphan_before = self.old_apps.get_model('development', 'Activity').objects.values(*self.history_fields).get(pk=orphan.pk)

        def violations():
            with connection.cursor() as cursor:
                return set(cursor.execute('PRAGMA foreign_key_check').fetchall())

        baseline = violations()
        self.assertTrue(baseline)

        def reject_new_violations(table_names=None):
            if violations() - baseline:
                raise IntegrityError('Migration introduced a new foreign-key violation.')

        try:
            with patch.object(connection, 'check_constraints', side_effect=reject_new_violations):
                apps = self.migrate(self.migrate_to)
            self.assertEqual(violations(), baseline)
            self.assertFalse(apps.get_model('development', 'Food').objects.filter(pk=orphan_id).exists())
            self.assertFalse(apps.get_model('development', 'Gate2File').objects.filter(development_id=orphan_id).exists())
            orphan_after = apps.get_model('development', 'Activity').objects.values(*self.history_fields).get(pk=orphan.pk)
            self.assertEqual(orphan_after, orphan_before)
            self.assert_moved_sources(apps)
            self.assert_unrelated_unchanged(apps)
        finally:
            self.old_apps.get_model('development', 'Activity').objects.filter(pk=orphan.pk).delete()
