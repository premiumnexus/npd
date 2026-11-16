"""Gate 0 uploads are separate file records linked to the permanent process ID."""
from pathlib import PurePosixPath
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .gate0 import FILE_SLOTS, file_slots
from .models import Activity, Food, Gate0, Gate0File, Gate1, Gate2, Gate3


class Gate0FileStorageTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = self.settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = User.objects.create_user('gate0-file-editor')
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        self.development = Food.objects.create(name='File example', category='FF', owner=self.user)
        self.url = reverse('detail', args=[self.development.pk])
        self.client.force_login(self.user)

    def upload(self, slot='G0-F1', name='evidence.pdf', body=b'original evidence', url=None):
        return self.client.post(url or self.url, {
            'action': 'slot_upload', 'slot': slot,
            'slot_file': SimpleUploadedFile(name, body, content_type='application/pdf'),
        })

    def assert_audit_has_no_file_metadata(self, record):
        self.assertIsNotNone(record.activity_id)
        activity = Activity.objects.get(pk=record.activity_id)
        self.assertEqual(activity.food_id, record.development_id)
        self.assertEqual(activity.actor_id, record.uploader_id)
        self.assertFalse(activity.attachment)
        self.assertEqual(activity.attachment_name, '')
        self.assertEqual(activity.attachment_stage, '')
        self.assertEqual(activity.attachment_slot, '')

    def read_download(self, url, **kwargs):
        response = self.client.get(url, **kwargs)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        body = b''.join(response.streaming_content)
        response.close()
        return body

    def test_upload_stores_metadata_in_dedicated_gate0_table(self):
        self.assertEqual(self.upload().status_code, 302)
        record = Gate0File.objects.get(development_id=self.development.pk)
        self.assertEqual(Gate0File._meta.db_table, 'development_gate0_files')
        self.assertEqual(record.slot_code, 'G0-F1')
        self.assertEqual(record.original_filename, 'evidence.pdf')
        self.assertEqual(record.uploader_id, self.user.pk)
        self.assertIsNotNone(record.uploaded_at)
        self.assertTrue(record.file.name.startswith('activities/%s/' % self.development.pk))
        self.assertEqual(PurePosixPath(record.file.name).suffix, '.pdf')
        self.assertTrue(record.file.storage.exists(record.file.name))
        with record.file.open('rb') as saved:
            self.assertEqual(saved.read(), b'original evidence')
        record.full_clean()
        self.assertEqual(list(self.development.gate0_files.values_list('pk', flat=True)), [record.pk])
        self.assert_audit_has_no_file_metadata(record)
        slots = {slot['key']: slot for slot in file_slots(self.development)}
        self.assertEqual([item.pk for item in slots['G0-F1']['files']], [record.pk])
        self.assertTrue(all(not slot['files'] for key, slot in slots.items() if key != 'G0-F1'))

    def test_creation_uploads_use_the_same_development_id_as_every_gate(self):
        response = self.client.post(reverse('create_food'), {
            'product_type': 'new', 'product_name': 'Development with four files', 'category': 'ISF',
            **{slot: SimpleUploadedFile('%s.pdf' % slot, slot.encode('ascii')) for slot, _ in FILE_SLOTS},
        })
        self.assertEqual(response.status_code, 302)
        development = Food.objects.get(name='Development with four files')
        self.assertEqual(response.url, reverse('detail', args=[development.pk]))
        records = list(Gate0File.objects.filter(development_id=development.pk))
        self.assertEqual({record.slot_code for record in records}, {slot for slot, _ in FILE_SLOTS})
        self.assertEqual(len(records), 4)
        self.assertFalse(Gate0File.objects.filter(development_id=self.development.pk).exists())
        for model in (Gate0, Gate1, Gate2, Gate3):
            self.assertEqual(model.objects.get(development_id=development.pk).pk, development.pk)
        for record in records:
            self.assertEqual(record.uploader_id, self.user.pk)
            self.assert_audit_has_no_file_metadata(record)
            self.assertEqual(self.read_download(reverse('download_gate0_file', args=[record.pk])), record.slot_code.encode('ascii'))

    def test_each_slot_keeps_its_upload_history_for_authenticated_readers(self):
        for slot, _ in FILE_SLOTS:
            for version in (1, 2):
                self.assertEqual(self.upload(slot=slot, name='same-name.pdf', body=('%s version %s' % (slot, version)).encode('ascii')).status_code, 302)
        self.assertEqual(Gate0File.objects.filter(development_id=self.development.pk).count(), 8)
        self.assertEqual(len(set(self.development.gate0_files.values_list('file', flat=True))), 8)
        self.assertFalse(self.development.activities.exclude(attachment='').exists())
        self.user.groups.clear()
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'name="slot_file"')
        self.assertEqual(len(page.context['gate0slots']), 4)
        for slot in page.context['gate0slots']:
            self.assertEqual(len(slot['files']), 2)
            for record in slot['files']:
                self.assertContains(page, reverse('download_gate0_file', args=[record.pk]))
                self.assertNotContains(page, record.file.url)
                body = self.read_download(reverse('download_gate0_file', args=[record.pk]))
                self.assertIn(body, [('%s version 1' % slot['key']).encode('ascii'), ('%s version 2' % slot['key']).encode('ascii')])

    def test_uploads_enforce_editor_rights_review_locks_and_current_gate(self):
        self.user.groups.clear()
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.post(reverse('create_food'), {
            'product_name': 'Unauthorized file',
            'G0-F1': SimpleUploadedFile('blocked.pdf', b'blocked'),
        }).status_code, 403)
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        for status in ('manager', 'qa', 'director'):
            self.development.review_status = status
            self.development.save()
            self.assertEqual(self.upload().status_code, 403)
        self.development.review_status = 'draft'
        self.development.save()
        self.assertEqual(self.upload(url=self.url + '?gate=gate1').status_code, 403)
        self.development.stage = 'gate1'
        self.development.save()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.assertEqual(self.upload().status_code, 403)
        self.development.stage = 'gate0'
        self.development.completed = True
        self.development.save()
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.upload().status_code, 403)
        self.assertFalse(Gate0File.objects.exists())
        self.assertFalse(self.development.activities.exists())

    def test_invalid_slots_and_empty_uploads_do_not_create_file_records(self):
        for slot in ('unknown', 'G1-F1', 'G2-F1'):
            self.assertEqual(self.upload(slot=slot).status_code, 403)
        self.assertEqual(self.upload(body=b'').status_code, 302)
        self.assertEqual(self.client.post(self.url, {'action': 'slot_upload', 'slot': 'G0-F1'}).status_code, 302)
        self.assertFalse(Gate0File.objects.exists())
        self.assertFalse(self.development.activities.exists())

    def test_dedicated_and_legacy_downloads_preserve_authentication_and_bytes(self):
        earlier = Activity.objects.create(food=self.development, actor=self.user, text='Earlier activity')
        self.assertEqual(self.upload(name='quality-report.pdf', body=b'private report').status_code, 302)
        record = Gate0File.objects.get(development_id=self.development.pk)
        self.assertNotEqual(record.pk, record.activity_id)
        dedicated = reverse('download_gate0_file', args=[record.pk])
        legacy = reverse('download_attachment', args=[record.activity_id])
        self.client.logout()
        for url in (dedicated, legacy):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.url)
        viewer = User.objects.create_user('gate0-file-reader')
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse('download_attachment', args=[earlier.pk])).status_code, 404)
        response = self.client.get(dedicated)
        self.assertEqual(response.status_code, 200)
        self.assertIn('quality-report.pdf', response['Content-Disposition'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(b''.join(response.streaming_content), b'private report')
        response.close()
        self.assertEqual(self.read_download(legacy, follow=True), b'private report')
        for url in (dedicated, legacy):
            self.assertEqual(self.client.post(url).status_code, 405)

    def test_missing_file_records_and_missing_physical_files_return_404(self):
        self.assertEqual(self.client.get(reverse('download_gate0_file', args=[999999])).status_code, 404)
        self.assertEqual(self.upload().status_code, 302)
        record = Gate0File.objects.get(development_id=self.development.pk)
        record.file.storage.delete(record.file.name)
        self.assertEqual(self.client.get(reverse('download_gate0_file', args=[record.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('download_attachment', args=[record.activity_id]), follow=True).status_code, 404)
        self.assertTrue(Gate0File.objects.filter(pk=record.pk).exists())
        self.assertTrue(Activity.objects.filter(pk=record.activity_id).exists())
