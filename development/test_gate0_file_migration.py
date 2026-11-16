"""Exercise the real Gate 0 attachment migration in both directions."""
from datetime import datetime, timezone as dt_timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Gate0FileMigrationTests(TransactionTestCase):
    migrate_from = [('development', '0034_relational_gate_records')]
    migrate_to = [('development', '0035_gate0_files')]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(self.restore_latest_schema)
        executor.migrate(self.migrate_from)
        self.old_apps = executor.loader.project_state(self.migrate_from).apps
        User = self.old_apps.get_model('auth', 'User')
        Food = self.old_apps.get_model('development', 'Food')
        Activity = self.old_apps.get_model('development', 'Activity')
        self.owner = User.objects.create(username='gate0-file-migration-owner')
        self.development = Food.objects.create(pk=501, name='Gate 0 upload migration', owner_id=self.owner.pk)
        self.other_development = Food.objects.create(pk=808, name='Second development', owner_id=self.owner.pk)
        self.when = datetime(2026, 10, 20, 3, 4, 5, 123000, tzinfo=dt_timezone.utc)
        self.sources = {}

        def upload(development, slot, stage, filename, path, actor_id):
            activity = Activity.objects.create(
                food_id=development.pk, actor_id=actor_id,
                text='Keep this upload log: ' + filename,
                attachment=path, attachment_name=filename,
                attachment_stage=stage, attachment_slot=slot,
            )
            Activity.objects.filter(pk=activity.pk).update(created=self.when)
            self.sources[activity.pk] = {
                'development_id': development.pk, 'slot_code': slot,
                'path': path, 'filename': filename, 'uploader_id': actor_id,
                'text': activity.text,
            }
            return activity

        upload(self.development, 'G0-F1', 'gate0', 'Evidence.pdf',
               'activities/501/evidence-original.pdf', self.owner.pk)
        # Older uploads can be identified by their slot even without stage metadata.
        upload(self.development, 'G0-F2', '', 'Үнэ.xlsx',
               'activities/501/price-original.xlsx', self.owner.pk)
        upload(self.other_development, 'G0-F4', 'gate0', 'Anonymous report.png',
               'activities/808/report-original.png', None)
        self.gate1 = Activity.objects.create(
            food_id=self.development.pk, actor_id=self.owner.pk, text='Gate 1 upload',
            attachment='activities/501/gate1-retained.pdf', attachment_name='Recipe.pdf',
            attachment_stage='gate1', attachment_slot='G1-F1',
        )
        Activity.objects.filter(pk=self.gate1.pk).update(created=self.when)
        self.comment = Activity.objects.create(
            food_id=self.development.pk, actor_id=self.owner.pk,
            text='A comment without an attachment', attachment_stage='gate0',
        )

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

    def assert_other_records_unchanged(self, apps):
        Activity = apps.get_model('development', 'Activity')
        gate1 = Activity.objects.get(pk=self.gate1.pk)
        self.assertEqual(gate1.attachment.name, 'activities/501/gate1-retained.pdf')
        self.assertEqual(gate1.attachment_name, 'Recipe.pdf')
        self.assertEqual(gate1.attachment_stage, 'gate1')
        self.assertEqual(gate1.attachment_slot, 'G1-F1')
        self.assertEqual(gate1.created, self.when)
        comment = Activity.objects.get(pk=self.comment.pk)
        self.assertFalse(comment.attachment)
        self.assertEqual(comment.text, 'A comment without an attachment')

    def test_gate0_uploads_move_to_file_rows_and_keep_the_existing_activity_logs(self):
        apps = self.migrate(self.migrate_to)
        Gate0File = apps.get_model('development', 'Gate0File')
        Activity = apps.get_model('development', 'Activity')
        Food = apps.get_model('development', 'Food')
        self.assertEqual(Gate0File._meta.db_table, 'development_gate0_files')
        self.assertEqual(Gate0File.objects.count(), len(self.sources))
        self.assertEqual(set(Food.objects.values_list('pk', flat=True)), {501, 808})

        for activity_id, expected in self.sources.items():
            with self.subTest(activity_id=activity_id):
                upload = Gate0File.objects.get(activity_id=activity_id)
                self.assertEqual(upload.development_id, expected['development_id'])
                self.assertEqual(upload.slot_code, expected['slot_code'])
                self.assertEqual(upload.file.name, expected['path'])
                self.assertEqual(upload.original_filename, expected['filename'])
                self.assertEqual(upload.uploader_id, expected['uploader_id'])
                self.assertEqual(upload.uploaded_at, self.when)
                log = Activity.objects.get(pk=activity_id)
                self.assertEqual(log.food_id, expected['development_id'])
                self.assertEqual(log.actor_id, expected['uploader_id'])
                self.assertEqual(log.text, expected['text'])
                self.assertEqual(log.created, self.when)
                self.assertFalse(log.attachment)
                self.assertEqual(log.attachment_name, '')
                self.assertEqual(log.attachment_stage, '')
                self.assertEqual(log.attachment_slot, '')
        self.assert_other_records_unchanged(apps)

    def test_reverse_restores_paths_metadata_and_logs_then_forward_remains_lossless(self):
        apps = self.migrate(self.migrate_to)
        Gate0File = apps.get_model('development', 'Gate0File')
        # A file can survive deletion of its optional activity link.
        extra_path = 'activities/808/new-standalone-file.pdf'
        Gate0File.objects.create(
            development_id=self.other_development.pk, slot_code='G0-F3',
            file=extra_path, original_filename='Standalone.pdf',
            uploader_id=self.owner.pk, uploaded_at=self.when, activity_id=None,
        )
        restored_apps = self.migrate(self.migrate_from)
        Activity = restored_apps.get_model('development', 'Activity')
        for activity_id, expected in self.sources.items():
            restored = Activity.objects.get(pk=activity_id)
            self.assertEqual(restored.food_id, expected['development_id'])
            self.assertEqual(restored.actor_id, expected['uploader_id'])
            self.assertEqual(restored.attachment.name, expected['path'])
            self.assertEqual(restored.attachment_name, expected['filename'])
            self.assertEqual(restored.attachment_slot, expected['slot_code'])
            self.assertEqual(restored.attachment_stage, 'gate0')
            self.assertEqual(restored.created, self.when)
            self.assertEqual(restored.text, expected['text'])
        standalone = Activity.objects.get(attachment=extra_path)
        self.assertEqual(standalone.food_id, self.other_development.pk)
        self.assertEqual(standalone.actor_id, self.owner.pk)
        self.assertEqual(standalone.attachment_name, 'Standalone.pdf')
        self.assertEqual(standalone.attachment_slot, 'G0-F3')
        self.assertEqual(standalone.created, self.when)
        self.assert_other_records_unchanged(restored_apps)

        new_apps = self.migrate(self.migrate_to)
        Gate0File = new_apps.get_model('development', 'Gate0File')
        self.assertEqual(Gate0File.objects.count(), len(self.sources) + 1)
        self.assertEqual(set(Gate0File.objects.values_list('file', flat=True)),
                         {item['path'] for item in self.sources.values()} | {extra_path})
        self.assertEqual(Gate0File.objects.get(file=extra_path).activity_id, standalone.pk)
        self.assert_other_records_unchanged(new_apps)
