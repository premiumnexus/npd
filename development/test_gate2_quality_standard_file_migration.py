"""Verify the Gate 2 quality-standard backfill without changing upload history."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Gate2QualityStandardFileMigrationTests(TransactionTestCase):
    migrate_from = [('development', '0038_gate2_files')]
    migrate_to = [('development', '0039_gate2_quality_standard_file')]
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
        Gate2 = self.old_apps.get_model('development', 'Gate2')
        self.owner = User.objects.create(username='quality-standard-migration-owner')
        self.reviser = User.objects.create(username='quality-standard-migration-reviser')
        self.development = Food.objects.create(pk=701, name='Quality standard migration', owner_id=self.owner.pk)
        self.missing_gate = Food.objects.create(pk=702, name='Gate row to create', owner_id=self.owner.pk)
        self.unrelated = Food.objects.create(pk=703, name='Unrelated files', owner_id=self.owner.pk)
        Gate2.objects.create(development_id=self.development.pk, marketing_plan='Keep this idea', marketing_promotion='Campaign')
        Gate2.objects.create(development_id=self.unrelated.pk, marketing_plan='Untouched idea')
        self.when = datetime(2026, 10, 20, 3, 4, 5, 123000, tzinfo=dt_timezone.utc)

        # A larger PK is still older than the two newer files.
        self.oldest = self.activity(self.development.pk, 'old.pdf', self.when, pk=900)
        self.newer = self.activity(self.development.pk, 'new.pdf', self.when + timedelta(days=1), pk=31)
        self.latest = self.activity(self.development.pk, 'latest.pdf', self.when + timedelta(days=1), pk=32, actor_id=self.reviser.pk)
        self.no_actor = self.activity(self.missing_gate.pk, 'Чанарын стандарт.png', self.when, actor_id=None)
        self.activity(self.development.pk, 'other-slot.pdf', self.when + timedelta(days=6), slot='G2-F12')
        self.activity(self.development.pk, 'other-stage.pdf', self.when + timedelta(days=7), stage='gate1')
        self.activity(self.development.pk, '', self.when + timedelta(days=8), path='')
        self.activity(self.unrelated.pk, 'not-quality.pdf', self.when, slot='G2-F1')
        Activity = self.old_apps.get_model('development', 'Activity')
        Gate2File = self.old_apps.get_model('development', 'Gate2File')
        for number in range(1, 12):
            self.activity(self.unrelated.pk, 'Legacy slot %s.pdf' % number,
                          self.when + timedelta(days=9), slot='G2-F%s' % number)
            log = Activity.objects.create(
                food_id=self.development.pk, actor_id=self.owner.pk,
                text='Existing normalized Gate 2 file log %s' % number,
            )
            Gate2File.objects.create(
                development_id=self.development.pk, slot_code='G2-F%s' % number,
                file='gate2/701/normalized-slot-%s.pdf' % number,
                original_filename='Normalized slot %s.pdf' % number,
                uploader_id=self.owner.pk, uploaded_at=self.when, activity_id=log.pk,
            )
        self.files_before = list(Gate2File.objects.order_by('pk').values(*self.file_fields))
        self.before = self.history(self.old_apps)

    def restore_latest_schema(self):
        MigrationExecutor(connection).migrate(self.latest_targets)

    def tearDown(self):
        try:
            self.restore_latest_schema()
        finally:
            super().tearDown()

    def activity(self, development_id, filename, when, *, pk=None,
                 actor_id='owner', stage='gate2', slot='G2-F13', path=None):
        Activity = self.old_apps.get_model('development', 'Activity')
        actor_id = self.owner.pk if actor_id == 'owner' else actor_id
        values = {
            'food_id': development_id, 'actor_id': actor_id,
            'text': 'Keep upload history: ' + filename,
            'attachment': 'activities/%s/%s' % (development_id, filename) if path is None else path,
            'attachment_name': filename, 'attachment_stage': stage, 'attachment_slot': slot,
        }
        if pk is not None:
            values['pk'] = pk
        record = Activity.objects.create(**values)
        Activity.objects.filter(pk=record.pk).update(created=when)
        record.refresh_from_db()
        return record

    def history(self, apps):
        return list(apps.get_model('development', 'Activity').objects.order_by('pk').values(*self.history_fields))

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def assert_gate2_files_unchanged(self, apps):
        actual = list(apps.get_model('development', 'Gate2File').objects.order_by('pk').values(*self.file_fields))
        self.assertEqual(actual, self.files_before)

    def assert_current_quality_standard_files(self, apps):
        Gate2 = apps.get_model('development', 'Gate2')
        current = Gate2.objects.get(development_id=self.development.pk)
        self.assertEqual(current.pk, self.development.pk)
        self.assertEqual(current.quality_standard_file.name, self.latest.attachment.name)
        self.assertEqual(current.quality_standard_filename, 'latest.pdf')
        self.assertEqual(current.quality_standard_uploaded_by_id, self.reviser.pk)
        self.assertEqual(current.quality_standard_uploaded_at, self.latest.created)
        self.assertEqual(current.marketing_plan, 'Keep this idea')
        self.assertEqual(current.marketing_promotion, 'Campaign')
        created = Gate2.objects.get(development_id=self.missing_gate.pk)
        self.assertEqual(created.quality_standard_file.name, self.no_actor.attachment.name)
        self.assertEqual(created.quality_standard_filename, 'Чанарын стандарт.png')
        self.assertIsNone(created.quality_standard_uploaded_by_id)
        self.assertEqual(created.quality_standard_uploaded_at, self.no_actor.created)
        untouched = Gate2.objects.get(development_id=self.unrelated.pk)
        self.assertFalse(untouched.quality_standard_file)
        self.assertIsNone(untouched.quality_standard_filename)
        self.assertIsNone(untouched.quality_standard_uploaded_by_id)
        self.assertIsNone(untouched.quality_standard_uploaded_at)
        self.assertEqual(untouched.marketing_plan, 'Untouched idea')
        self.assert_gate2_files_unchanged(apps)

    def test_latest_timestamp_then_pk_wins_without_rewriting_history_or_physical_files(self):
        Gate2 = self.old_apps.get_model('development', 'Gate2')
        self.assertFalse(Gate2.objects.filter(development_id=self.missing_gate.pk).exists())
        # The migration copies stored path strings; file storage must never be invoked.
        with patch('django.core.files.storage.Storage.save', side_effect=AssertionError('Files must not be copied')), \
             patch('django.core.files.storage.Storage.open', side_effect=AssertionError('Files must not be opened')), \
             patch('django.core.files.storage.Storage.delete', side_effect=AssertionError('Files must not be deleted')):
            apps = self.migrate(self.migrate_to)
        self.assert_current_quality_standard_files(apps)
        self.assertEqual(self.history(apps), self.before)
        self.assertEqual(set(apps.get_model('development', 'Food').objects.values_list('pk', flat=True)), {701, 702, 703})

    def test_rollback_and_reapply_preserve_every_upload_version(self):
        apps = self.migrate(self.migrate_to)
        self.assert_current_quality_standard_files(apps)
        self.assertEqual(self.history(apps), self.before)
        restored = self.migrate(self.migrate_from)
        self.assertEqual(self.history(restored), self.before)
        self.assert_gate2_files_unchanged(restored)
        Gate2 = restored.get_model('development', 'Gate2')
        self.assertNotIn('quality_standard_file', {field.name for field in Gate2._meta.fields})
        self.assertEqual(Gate2.objects.get(development_id=self.development.pk).marketing_plan, 'Keep this idea')
        reapplied = self.migrate(self.migrate_to)
        self.assert_current_quality_standard_files(reapplied)
        self.assertEqual(self.history(reapplied), self.before)

    @skipUnless(connection.vendor == 'sqlite', 'Uses a deliberately invalid legacy foreign key fixture.')
    def test_missing_process_is_skipped_without_inventing_a_process_or_changing_history(self):
        orphan_id = 999991
        missing_user_id = 999992
        Food = self.old_apps.get_model('development', 'Food')
        valid_process = Food.objects.create(pk=704, name='Missing legacy uploader', owner_id=self.owner.pk)
        with connection.constraint_checks_disabled():
            orphan = self.activity(orphan_id, 'orphan.pdf', self.when + timedelta(days=10))
            missing_actor = self.activity(valid_process.pk, 'missing-uploader.pdf', self.when,
                                          actor_id=missing_user_id)
        before = self.history(self.old_apps)

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
            self.assertFalse(apps.get_model('development', 'Gate2').objects.filter(development_id=orphan_id).exists())
            normalized = apps.get_model('development', 'Gate2').objects.get(development_id=valid_process.pk)
            self.assertEqual(normalized.quality_standard_file.name, missing_actor.attachment.name)
            self.assertIsNone(normalized.quality_standard_uploaded_by_id)
            self.assert_current_quality_standard_files(apps)
            self.assertEqual(self.history(apps), before)
        finally:
            # Remove the intentionally invalid fixture before normal schema cleanup.
            self.old_apps.get_model('development', 'Activity').objects.filter(pk__in=[orphan.pk, missing_actor.pk]).delete()
