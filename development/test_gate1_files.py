"""Gate 1's nine supporting-file slots use their own development-linked table."""
from pathlib import PurePosixPath
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .gate1 import file_slots
from .gate_storage import ensure_gate_rows
from .models import Activity, Food, Gate1, Gate1File


class Gate1FileStorageTests(TestCase):
    supporting_slots = ['G1-F%s' % number for number in range(1, 10)]

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = self.settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = User.objects.create_user('gate1-file-editor')
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.development = Food.objects.create(name='Gate 1 supporting files', stage='gate1', category='FF', owner=self.user)
        ensure_gate_rows(self.development)
        self.url = reverse('detail', args=[self.development.pk])
        self.client.force_login(self.user)

    def upload(self, slot='G1-F1', name='evidence.pdf', body=b'original supporting document', url=None):
        return self.client.post(url or self.url, {
            'action': 'slot_upload', 'slot': slot,
            'slot_file': SimpleUploadedFile(name, body, content_type='application/pdf'),
        })

    def audit_has_no_file_metadata(self, record):
        self.assertIsNotNone(record.activity_id)
        activity = Activity.objects.get(pk=record.activity_id)
        self.assertEqual(activity.food_id, record.development_id)
        self.assertEqual(activity.actor_id, record.uploader_id)
        self.assertFalse(activity.attachment)
        self.assertEqual(activity.attachment_name, '')
        self.assertEqual(activity.attachment_stage, '')
        self.assertEqual(activity.attachment_slot, '')

    def download(self, url, **kwargs):
        response = self.client.get(url, **kwargs)
        self.assertEqual(response.status_code, 200)
        body = b''.join(response.streaming_content)
        response.close()
        return body

    def marketing_pointer(self):
        gate = Gate1.objects.get(development_id=self.development.pk)
        return (gate.marketing_idea_file.name, gate.marketing_idea_filename,
                gate.marketing_idea_uploaded_by_id, gate.marketing_idea_uploaded_at)

    def test_all_nine_slots_store_files_in_the_dedicated_gate1_table(self):
        for slot in self.supporting_slots:
            body = slot.encode('ascii')
            self.assertEqual(self.upload(slot=slot, name=slot + '.pdf', body=body).status_code, 302)
            record = Gate1File.objects.get(development_id=self.development.pk, slot_code=slot)
            self.assertEqual(record.original_filename, slot + '.pdf')
            self.assertEqual(record.uploader_id, self.user.pk)
            self.assertIsNotNone(record.uploaded_at)
            self.assertTrue(record.file.name.startswith('activities/%s/' % self.development.pk))
            self.assertEqual(PurePosixPath(record.file.name).suffix, '.pdf')
            self.assertEqual(record.uploaded_at, record.activity.created)
            record.full_clean()
            self.audit_has_no_file_metadata(record)
            with record.file.open('rb') as uploaded:
                self.assertEqual(uploaded.read(), body)
        self.assertEqual(Gate1File._meta.db_table, 'development_gate1_files')
        self.assertEqual(self.development.gate1_files.count(), 9)
        self.assertFalse(self.development.activities.exclude(attachment='').exists())
        self.assertFalse(Gate1.objects.get(pk=self.development.pk).marketing_idea_file)
        with connection_cursor() as cursor:
            cursor.execute('SELECT development_id, slot_code FROM development_gate1_files')
            self.assertEqual(set(cursor.fetchall()), {(self.development.pk, slot) for slot in self.supporting_slots})

    def test_each_supporting_slot_keeps_versions_for_authenticated_readers(self):
        expected = {}
        for slot in self.supporting_slots:
            for version in (1, 2):
                body = ('%s version %s' % (slot, version)).encode('ascii')
                self.assertEqual(self.upload(slot=slot, name='same-name.pdf', body=body).status_code, 302)
                record = Gate1File.objects.get(slot_code=slot, activity=self.development.activities.latest('pk'))
                expected[record.pk] = body
        self.assertEqual(self.development.gate1_files.count(), 18)
        self.assertEqual(len(set(self.development.gate1_files.values_list('file', flat=True))), 18)
        self.user.groups.clear()
        page = self.client.get(self.url)
        self.assertNotContains(page, 'name="slot_file"')
        self.assertEqual(len(page.context['gate1slots']), 10)
        for slot in page.context['gate1slots']:
            if slot['key'] == 'G1-F10':
                self.assertFalse(slot['files'])
                continue
            self.assertEqual(len(slot['files']), 2)
            for record in slot['files']:
                url = reverse('download_gate1_file', args=[record.pk])
                self.assertContains(page, url)
                self.assertNotContains(page, record.file.url)
                self.assertEqual(self.download(url), expected[record.pk])

    def test_supporting_uploads_do_not_replace_the_direct_marketing_pointer(self):
        self.assertEqual(self.upload(slot='G1-F10', name='marketing-v1.pdf', body=b'marketing first').status_code, 302)
        first = self.development.activities.get(attachment_slot='G1-F10')
        original_pointer = self.marketing_pointer()
        self.assertEqual(original_pointer[0], first.attachment.name)
        for slot in self.supporting_slots:
            self.assertEqual(self.upload(slot=slot, name=slot + '.pdf').status_code, 302)
            self.assertEqual(self.marketing_pointer(), original_pointer)
        self.assertEqual(self.upload(slot='G1-F10', name='marketing-v2.pdf', body=b'marketing revised').status_code, 302)
        latest = self.development.activities.get(attachment_name='marketing-v2.pdf')
        self.assertEqual(self.marketing_pointer(), (latest.attachment.name, latest.attachment_name, self.user.pk, latest.created))
        self.assertEqual(self.development.gate1_files.count(), 9)
        self.assertFalse(Gate1File.objects.filter(slot_code='G1-F10').exists())
        self.assertEqual(self.development.activities.filter(attachment_slot='G1-F10').count(), 2)
        self.assertEqual(self.download(reverse('download_attachment', args=[first.pk])), b'marketing first')
        self.assertEqual(self.download(reverse('download_attachment', args=[latest.pk])), b'marketing revised')
        slots = {slot['key']: slot for slot in file_slots(self.development)}
        self.assertEqual({item.pk for item in slots['G1-F10']['files']}, {first.pk, latest.pk})

    def test_upload_permissions_review_locks_and_gate_scope_are_preserved(self):
        self.user.groups.clear()
        self.assertEqual(self.upload().status_code, 403)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        for status in ('qa', 'manager', 'director'):
            self.development.review_status = status
            self.development.save()
            self.assertEqual(self.upload().status_code, 403)
        self.development.review_status = 'draft'
        self.development.save()
        self.assertEqual(self.upload(url=self.url + '?gate=gate0').status_code, 403)
        self.development.stage = 'gate2'
        self.development.save()
        self.assertEqual(self.upload().status_code, 403)
        self.development.stage = 'gate1'
        self.development.completed = True
        self.development.save()
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.upload().status_code, 403)
        self.assertFalse(Gate1File.objects.exists())
        self.assertFalse(self.development.activities.exists())

    def test_invalid_slots_and_empty_files_do_not_create_records(self):
        for slot in ('', 'unknown', 'G0-F1', 'G2-F1'):
            self.assertEqual(self.upload(slot=slot).status_code, 403)
        self.assertEqual(self.upload(body=b'').status_code, 302)
        self.assertEqual(self.client.post(self.url, {'action': 'slot_upload', 'slot': 'G1-F1'}).status_code, 302)
        self.assertFalse(Gate1File.objects.exists())
        self.assertFalse(self.development.activities.exists())

    def test_dedicated_and_legacy_downloads_keep_authentication_and_exact_file_bytes(self):
        earlier = Activity.objects.create(food=self.development, actor=self.user, text='Earlier comment')
        self.assertEqual(self.upload(name='private-report.pdf', body=b'private bytes').status_code, 302)
        record = Gate1File.objects.get(development_id=self.development.pk)
        self.assertNotEqual(record.pk, record.activity_id)
        dedicated = reverse('download_gate1_file', args=[record.pk])
        legacy = reverse('download_attachment', args=[record.activity_id])
        self.client.logout()
        for url in (dedicated, legacy):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.url)
        self.client.force_login(User.objects.create_user('gate1-file-reader'))
        self.assertEqual(self.client.get(reverse('download_attachment', args=[earlier.pk])).status_code, 404)
        response = self.client.get(dedicated)
        self.assertEqual(response.status_code, 200)
        self.assertIn('private-report.pdf', response['Content-Disposition'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(b''.join(response.streaming_content), b'private bytes')
        response.close()
        self.assertEqual(self.download(legacy, follow=True), b'private bytes')
        for url in (dedicated, legacy):
            self.assertEqual(self.client.post(url).status_code, 405)

    def test_standalone_files_and_deleted_audit_links_remain_downloadable(self):
        standalone = Gate1File.objects.create(
            development=self.development, slot_code='G1-F2',
            file=SimpleUploadedFile('standalone.pdf', b'standalone bytes'),
            original_filename='standalone.pdf', uploader=None, activity=None,
        )
        self.assertEqual(self.download(reverse('download_gate1_file', args=[standalone.pk])), b'standalone bytes')
        self.assertEqual(self.upload(slot='G1-F1', body=b'linked bytes').status_code, 302)
        record = Gate1File.objects.get(slot_code='G1-F1')
        audit_id = record.activity_id
        Activity.objects.get(pk=audit_id).delete()
        record.refresh_from_db()
        self.assertIsNone(record.activity_id)
        self.assertEqual(record.uploader_id, self.user.pk)
        self.assertEqual(self.download(reverse('download_gate1_file', args=[record.pk])), b'linked bytes')
        self.assertEqual(self.client.get(reverse('download_attachment', args=[audit_id])).status_code, 404)
        page = self.client.get(self.url)
        self.assertContains(page, 'standalone.pdf')
        self.assertContains(page, reverse('download_gate1_file', args=[standalone.pk]))
        self.assertContains(page, reverse('download_gate1_file', args=[record.pk]))

    def test_missing_file_records_and_physical_files_return_404(self):
        self.assertEqual(self.client.get(reverse('download_gate1_file', args=[999999])).status_code, 404)
        self.assertEqual(self.upload().status_code, 302)
        record = Gate1File.objects.get(development_id=self.development.pk)
        record.file.storage.delete(record.file.name)
        self.assertEqual(self.client.get(reverse('download_gate1_file', args=[record.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('download_attachment', args=[record.activity_id]), follow=True).status_code, 404)
        self.assertTrue(Gate1File.objects.filter(pk=record.pk).exists())
        self.assertTrue(Activity.objects.filter(pk=record.activity_id).exists())


def connection_cursor():
    from django.db import connection
    return connection.cursor()
