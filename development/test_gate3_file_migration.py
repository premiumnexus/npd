"""Exercise the actual forward and reverse Gate 3 upload migration."""
from datetime import datetime, timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Gate3FileMigrationTests(TransactionTestCase):
    previous=[('development','0040_launch_checkpoint_development')]
    target=[('development','0041_gate3_files')]

    def migrate(self,target):
        executor=MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def setUp(self):
        super().setUp()
        self.latest=MigrationExecutor(connection).loader.graph.leaf_nodes()
        self.addCleanup(self.migrate,self.latest)

    def tearDown(self):
        self.migrate(self.latest)
        super().tearDown()

    def test_forward_reverse_and_reapply_preserve_metadata_and_every_version(self):
        apps=self.migrate(self.previous)
        User=apps.get_model('auth','User')
        Food=apps.get_model('development','Food')
        Activity=apps.get_model('development','Activity')
        user=User.objects.create(username='gate3-migration')
        development=Food.objects.create(name='Gate 3 migration',owner_id=user.pk)
        when=datetime(2026,11,1,5,6,7,tzinfo=timezone.utc)
        sources=[]
        for slot in ('G3-F1','G3-F1','G3-F2','G3-F3'):
            record=Activity.objects.create(food_id=development.pk,actor_id=user.pk,
                text='Keep audit',attachment='activities/%s/%s.txt'%(development.pk,len(sources)),
                attachment_name=slot+'.txt',attachment_stage='gate3',attachment_slot=slot)
            Activity.objects.filter(pk=record.pk).update(created=when)
            record.refresh_from_db()
            sources.append(record)
        other=Activity.objects.create(food_id=development.pk,text='Other gate',
            attachment='activities/quality.pdf',attachment_stage='gate2',attachment_slot='G2-F13')
        before=list(Activity.objects.order_by('pk').values())
        apps=self.migrate(self.target)
        Gate3File=apps.get_model('development','Gate3File')
        Activity=apps.get_model('development','Activity')
        self.assertEqual(Gate3File.objects.count(),4)
        for source in sources:
            record=Gate3File.objects.get(activity_id=source.pk)
            self.assertEqual((record.pk,record.development_id,record.slot_code),
                (source.pk,development.pk,source.attachment_slot))
            self.assertEqual(str(record.file),str(source.attachment))
            self.assertEqual(record.original_filename,source.attachment_name)
            self.assertEqual(record.uploaded_at,when)
            self.assertEqual(record.uploader_id,user.pk)
            audit=Activity.objects.get(pk=source.pk)
            self.assertFalse(audit.attachment)
            self.assertEqual(audit.text,'Keep audit')
            self.assertEqual(audit.created,when)
        self.assertEqual(Activity.objects.get(pk=other.pk).attachment_slot,'G2-F13')
        apps=self.migrate(self.previous)
        self.assertEqual(list(apps.get_model('development','Activity').objects.order_by('pk').values()),before)
        apps=self.migrate(self.target)
        self.assertEqual(apps.get_model('development','Gate3File').objects.count(),4)
