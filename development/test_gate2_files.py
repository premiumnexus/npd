"""Gate 2's first eleven file slots use development-linked file records."""
from datetime import timedelta
from pathlib import PurePosixPath
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .gate0 import save_brief as save_gate0
from .gate2 import file_slots
from .gate_storage import ensure_gate_rows
from .models import Activity, Food, Gate2File


class Gate2FileStorageTests(TestCase):
    supporting_slots = ['G2-F%s' % number for number in range(1, 12)]

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = self.settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = User.objects.create_user('gate2-file-editor')
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.development = Food.objects.create(name='Gate 2 supporting files', stage='gate2', category='FF', owner=self.user)
        ensure_gate_rows(self.development)
        save_gate0(self.development, {'product_name': self.development.name, 'category': 'FF'})
        self.url = reverse('detail', args=[self.development.pk])
        self.client.force_login(self.user)

    def upload(self, slot='G2-F1', name='evidence.pdf', body=b'original supporting document', url=None):
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

    def test_all_eleven_slots_store_files_in_the_dedicated_gate2_table(self):
        for slot in self.supporting_slots:
            body = slot.encode('ascii')
            self.assertEqual(self.upload(slot=slot, name=slot + '.pdf', body=body).status_code, 302)
            record = Gate2File.objects.get(development_id=self.development.pk, slot_code=slot)
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
        self.assertEqual(Gate2File._meta.db_table, 'development_gate2_files')
        self.assertEqual(self.development.gate2_files.count(), 11)
        self.assertFalse(self.development.activities.exclude(attachment='').exists())
        with connection.cursor() as cursor:
            cursor.execute('SELECT development_id, slot_code FROM development_gate2_files')
            self.assertEqual(set(cursor.fetchall()), {(self.development.pk, slot) for slot in self.supporting_slots})

    def test_each_supporting_slot_keeps_versions_for_authenticated_readers(self):
        expected = {}
        for slot in self.supporting_slots:
            for version in (1, 2):
                body = ('%s version %s' % (slot, version)).encode('ascii')
                self.assertEqual(self.upload(slot=slot, name='same-name.pdf', body=body).status_code, 302)
                record = Gate2File.objects.get(slot_code=slot, activity=self.development.activities.latest('pk'))
                expected[record.pk] = body
        self.assertEqual(self.development.gate2_files.count(), 22)
        self.assertEqual(len(set(self.development.gate2_files.values_list('file', flat=True))), 22)
        self.user.groups.clear()
        page = self.client.get(self.url)
        self.assertNotContains(page, 'name="slot_file"')
        self.assertEqual(len(page.context['gate2slots']), 12)
        for slot in page.context['gate2slots']:
            if slot['key'] == 'G2-F13':
                self.assertFalse(slot['files'])
                continue
            self.assertEqual(len(slot['files']), 2)
            for record in slot['files']:
                url = reverse('download_gate2_file', args=[record.pk])
                self.assertContains(page, url)
                self.assertNotContains(page, record.file.url)
                self.assertEqual(self.download(url), expected[record.pk])

    def test_isf_manual_and_quality_standard_remain_activity_files_and_available_in_launch(self):
        self.assertNotIn('G2-F12', {slot['key'] for slot in file_slots(self.development)})
        self.assertNotContains(self.client.get(self.url), 'id="file-G2-F12"')
        self.assertEqual(self.upload(slot='G2-F12').status_code, 403)
        save_gate0(self.development, {'category': 'ISF'})
        # The saved Gate 0 category governs the manual, even if the summary differs.
        self.development.category = 'FF'
        self.development.save()
        expected = {}
        for slot in ('G2-F12', 'G2-F13'):
            for version in (1, 2):
                name = '%s-version%s.pdf' % (slot, version)
                body = name.encode('ascii')
                self.assertEqual(self.upload(slot=slot, name=name, body=body).status_code, 302)
                activity = self.development.activities.get(attachment_name=name)
                self.assertEqual(activity.attachment_stage, 'gate2')
                self.assertEqual(activity.attachment_slot, slot)
                activity.full_clean()
                expected[activity.pk] = body
        self.assertFalse(Gate2File.objects.exists())
        self.assertEqual(self.upload(slot='G2-F1').status_code, 302)
        self.assertEqual(self.development.gate2_files.count(), 1)
        page = self.client.get(self.url)
        slots = {slot['key']: slot for slot in page.context['gate2slots']}
        self.assertEqual(len(slots), 13)
        self.assertContains(page, 'id="file-G2-F12"', count=1)
        self.assertContains(page, 'id="file-G2-F13"', count=1)
        for key in ('G2-F12', 'G2-F13'):
            self.assertEqual(len(slots[key]['files']), 2)
            self.assertTrue(all(isinstance(item, Activity) for item in slots[key]['files']))
            for activity in slots[key]['files']:
                self.assertEqual(self.download(reverse('download_attachment', args=[activity.pk])), expected[activity.pk])
        save_gate0(self.development, {'category': 'FF'})
        self.assertNotIn('G2-F12', {slot['key'] for slot in file_slots(self.development)})
        self.assertEqual(self.upload(slot='G2-F12').status_code, 403)
        self.development.stage = 'launch'
        self.development.launched_at = timezone.now() - timedelta(days=15)
        self.development.save()
        self.user.groups.add(Group.objects.get(name='Food Science'))
        page = self.client.get(self.url)
        self.assertEqual(len(page.context['checkpoint_cards']), 2)
        for card in page.context['checkpoint_cards']:
            standards = card['quality_standards']
            self.assertEqual(len(standards), 2)
            self.assertEqual({item.attachment_slot for item in standards}, {'G2-F13'})
            for activity in standards:
                self.assertContains(page, activity.attachment_name)
                self.assertEqual(self.download(reverse('download_attachment', args=[activity.pk])), expected[activity.pk])

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
        self.development.stage = 'gate1'
        self.development.save()
        self.assertEqual(self.upload().status_code, 403)
        self.development.stage = 'gate2'
        self.development.completed = True
        self.development.save()
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.upload().status_code, 403)
        self.assertFalse(Gate2File.objects.exists())
        self.assertFalse(self.development.activities.exists())

    def test_gate3_handover_flags_follow_this_process_uploaded_files(self):
        from .gate3 import Gate3Form
        required = [
            ('G2-F11', 'handover_final_cogs'),
            ('G2-F5', 'handover_technology_document'),
            ('G2-F7', 'handover_label'),
            ('G2-F9', 'handover_marketing_plan'),
        ]

        def assert_handover(food, completed):
            form = Gate3Form(food=food)
            for slot, field in required:
                self.assertEqual(form.initial[field], 'yes' if slot in completed else 'no')
            self.assertEqual(form.initial['handover_pack_complete'], 'yes' if len(completed) == len(required) else 'no')

        # Neither typed Gate 2 values nor a recipe can satisfy these checks.
        self.assertFalse(self.development.lines.exists())
        assert_handover(self.development, set())
        other = Food.objects.create(name='Another development', stage='gate2', category='FF', owner=self.user)
        ensure_gate_rows(other)
        other_url = reverse('detail', args=[other.pk])
        for slot, _ in required:
            self.assertEqual(self.upload(slot=slot, name=slot + '.pdf', url=other_url).status_code, 302)
        assert_handover(other, {slot for slot, _ in required})
        assert_handover(self.development, set())
        self.assertEqual(self.upload(slot='G2-F1').status_code, 302)
        assert_handover(self.development, set())
        completed = set()
        for slot, _ in required:
            self.assertEqual(self.upload(slot=slot, name=slot + '.pdf').status_code, 302)
            completed.add(slot)
            assert_handover(self.development, completed)
        self.assertFalse(self.development.activities.exclude(attachment='').exists())
        self.assertFalse(other.activities.exclude(attachment='').exists())

    def test_invalid_slots_and_empty_files_do_not_create_records(self):
        for slot in ('', 'unknown', 'G0-F1', 'G1-F1', 'G2-F12', 'G2-F14'):
            self.assertEqual(self.upload(slot=slot).status_code, 403)
        self.assertEqual(self.upload(body=b'').status_code, 302)
        self.assertEqual(self.client.post(self.url, {'action': 'slot_upload', 'slot': 'G2-F1'}).status_code, 302)
        self.assertFalse(Gate2File.objects.exists())
        self.assertFalse(self.development.activities.exists())

    def test_dedicated_and_legacy_downloads_keep_authentication_and_exact_file_bytes(self):
        earlier = Activity.objects.create(food=self.development, actor=self.user, text='Earlier comment')
        self.assertEqual(self.upload(name='private-report.pdf', body=b'private bytes').status_code, 302)
        record = Gate2File.objects.get(development_id=self.development.pk)
        self.assertNotEqual(record.pk, record.activity_id)
        dedicated = reverse('download_gate2_file', args=[record.pk])
        legacy = reverse('download_attachment', args=[record.activity_id])
        self.client.logout()
        for url in (dedicated, legacy):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.url)
        self.client.force_login(User.objects.create_user('gate2-file-reader'))
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
        standalone = Gate2File.objects.create(
            development=self.development, slot_code='G2-F2',
            file=SimpleUploadedFile('standalone.pdf', b'standalone bytes'),
            original_filename='standalone.pdf', uploader=None, activity=None,
        )
        self.assertEqual(self.download(reverse('download_gate2_file', args=[standalone.pk])), b'standalone bytes')
        self.assertEqual(self.upload(slot='G2-F1', body=b'linked bytes').status_code, 302)
        record = Gate2File.objects.get(slot_code='G2-F1')
        audit_id = record.activity_id
        Activity.objects.get(pk=audit_id).delete()
        record.refresh_from_db()
        self.assertIsNone(record.activity_id)
        self.assertEqual(record.uploader_id, self.user.pk)
        self.assertEqual(self.download(reverse('download_gate2_file', args=[record.pk])), b'linked bytes')
        self.assertEqual(self.client.get(reverse('download_attachment', args=[audit_id])).status_code, 404)
        page = self.client.get(self.url)
        self.assertContains(page, 'standalone.pdf')
        self.assertContains(page, reverse('download_gate2_file', args=[standalone.pk]))
        self.assertContains(page, reverse('download_gate2_file', args=[record.pk]))

    def test_missing_file_records_and_physical_files_return_404(self):
        self.assertEqual(self.client.get(reverse('download_gate2_file', args=[999999])).status_code, 404)
        self.assertEqual(self.upload().status_code, 302)
        record = Gate2File.objects.get(development_id=self.development.pk)
        record.file.storage.delete(record.file.name)
        self.assertEqual(self.client.get(reverse('download_gate2_file', args=[record.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('download_attachment', args=[record.activity_id]), follow=True).status_code, 404)
        self.assertTrue(Gate2File.objects.filter(pk=record.pk).exists())
        self.assertTrue(Activity.objects.filter(pk=record.activity_id).exists())
