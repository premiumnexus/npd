"""The latest marketing upload belongs to Gate 1; Activities retain version history."""
from pathlib import Path
import tempfile
from unittest import skipUnless

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection
from django.test import TestCase
from django.urls import reverse

from .gate1 import file_slots, save_brief, save_slot_file
from .gate_storage import ensure_gate_rows
from .models import Activity, Food, Gate1


class Gate1MarketingFileTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = self.settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = User.objects.create_user('marketing-file-editor')
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.development = Food.objects.create(name='Marketing-file process', category='FF', stage='gate1', owner=self.user)
        ensure_gate_rows(self.development)
        self.url = reverse('detail', args=[self.development.pk])
        self.client.force_login(self.user)

    def upload(self, name='marketing.pdf', body=b'original marketing idea', slot='G1-F10', url=None):
        return self.client.post(url or self.url, {
            'action': 'slot_upload', 'slot': slot,
            'slot_file': SimpleUploadedFile(name, body, content_type='application/pdf'),
        })

    def pointer(self, development=None):
        record = Gate1.objects.get(development_id=(development or self.development).pk)
        return (record.marketing_idea_file.name, record.marketing_idea_filename,
                record.marketing_idea_uploaded_by_id, record.marketing_idea_uploaded_at)

    def stored_files(self):
        return {path.relative_to(self.media.name).as_posix() for path in Path(self.media.name).rglob('*') if path.is_file()}

    def download(self, activity):
        response = self.client.get(reverse('download_attachment', args=[activity.pk]))
        self.assertEqual(response.status_code, 200)
        content = b''.join(response.streaming_content)
        response.close()
        return content

    def test_marketing_upload_is_referenced_directly_by_the_gate1_row(self):
        self.assertEqual(self.upload().status_code, 302)
        activity = self.development.activities.get(attachment_slot='G1-F10')
        record = Gate1.objects.get(development_id=self.development.pk)
        self.assertEqual(record.pk, self.development.pk)
        self.assertEqual(record.marketing_idea_file.name, activity.attachment.name)
        self.assertEqual(record.marketing_idea_filename, 'marketing.pdf')
        self.assertEqual(record.marketing_idea_uploaded_by_id, self.user.pk)
        self.assertEqual(record.marketing_idea_uploaded_at, activity.created)
        self.assertEqual(activity.attachment_stage, 'gate1')
        self.assertEqual(self.stored_files(), {activity.attachment.name})
        with record.marketing_idea_file.open('rb') as uploaded:
            self.assertEqual(uploaded.read(), b'original marketing idea')
        self.assertEqual(self.download(activity), b'original marketing idea')
        with connection.cursor() as cursor:
            cursor.execute('SELECT marketing_idea_file, marketing_idea_filename FROM development_gate1 WHERE development_id = %s', [self.development.pk])
            self.assertEqual(cursor.fetchone(), (activity.attachment.name, 'marketing.pdf'))

    def test_new_versions_update_the_pointer_without_replacing_existing_files(self):
        self.assertEqual(self.upload(name='first.pdf', body=b'first version').status_code, 302)
        first = self.development.activities.get(attachment_slot='G1-F10')
        first_path = first.attachment.name
        other = User.objects.create_user('second-marketing-editor')
        other.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.client.force_login(other)
        self.assertEqual(self.upload(name='revised.pdf', body=b'revised version').status_code, 302)
        second = self.development.activities.get(attachment_name='revised.pdf')
        self.assertNotEqual(first_path, second.attachment.name)
        self.assertEqual(self.pointer(), (second.attachment.name, 'revised.pdf', other.pk, second.created))
        first.refresh_from_db()
        self.assertEqual(first.attachment.name, first_path)
        self.assertEqual(first.actor_id, self.user.pk)
        self.assertEqual(self.stored_files(), {first_path, second.attachment.name})
        self.assertEqual(self.download(first), b'first version')
        self.assertEqual(self.download(second), b'revised version')
        slots = {slot['key']: slot for slot in file_slots(self.development)}
        self.assertEqual({activity.pk for activity in slots['G1-F10']['files']}, {first.pk, second.pk})
        page = self.client.get(self.url)
        self.assertContains(page, 'first.pdf')
        self.assertContains(page, 'revised.pdf')

    def test_brief_saves_cannot_clear_or_forge_the_marketing_file_reference(self):
        self.assertEqual(self.upload().status_code, 302)
        expected = self.pointer()
        save_brief(self.development, {'marketing_name': 'New campaign', 'marketing_brief': 'New idea'})
        self.assertEqual(self.pointer(), expected)
        save_brief(self.development, {})
        self.assertEqual(self.pointer(), expected)
        response = self.client.post(self.url, {
            'action': 'gate1_save', 'marketing_name': 'Another campaign',
            'marketing_idea_file': '', 'marketing_idea_filename': 'forged.pdf',
            'marketing_idea_uploaded_by': '999999', 'marketing_idea_uploaded_at': '2099-01-01T00:00:00Z',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.pointer(), expected)
        self.assertEqual(Gate1.objects.get(development_id=self.development.pk).marketing_name, 'Another campaign')
        self.assertEqual(self.development.activities.filter(attachment_slot='G1-F10').count(), 1)
        self.assertEqual(self.stored_files(), {expected[0]})

    def test_other_file_slots_and_other_processes_do_not_change_this_pointer(self):
        self.assertEqual(self.upload().status_code, 302)
        expected = self.pointer()
        for slot in ('G1-F1', 'G1-F9'):
            self.assertEqual(self.upload(name=slot + '.pdf', body=slot.encode('ascii'), slot=slot).status_code, 302)
            self.assertEqual(self.pointer(), expected)
        other = Food.objects.create(name='Separate process', category='ISF', stage='gate1', owner=self.user)
        ensure_gate_rows(other)
        self.assertEqual(self.upload(name='other.pdf', body=b'other process', url=reverse('detail', args=[other.pk])).status_code, 302)
        self.assertEqual(self.pointer(), expected)
        self.assertEqual(self.pointer(other)[1], 'other.pdf')
        self.assertNotEqual(self.pointer(other)[0], expected[0])

    def test_permissions_and_review_locks_prevent_pointer_changes(self):
        self.assertEqual(self.upload().status_code, 302)
        expected = self.pointer()
        self.user.groups.clear()
        self.assertEqual(self.upload(name='blocked.pdf').status_code, 403)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        for status in ('manager', 'director', 'qa'):
            self.development.review_status = status
            self.development.save()
            self.assertEqual(self.upload(name='locked.pdf').status_code, 403)
        self.development.review_status = 'draft'
        self.development.save()
        self.assertEqual(self.upload(url=self.url + '?gate=gate0').status_code, 403)
        self.development.stage = 'gate2'
        self.development.save()
        self.assertEqual(self.upload(name='wrong-stage.pdf').status_code, 403)
        self.development.stage = 'gate1'
        self.development.completed = True
        self.development.save()
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.upload(name='completed.pdf').status_code, 403)
        self.assertEqual(self.pointer(), expected)
        self.assertEqual(self.development.activities.filter(attachment_slot='G1-F10').count(), 1)
        self.assertEqual(self.stored_files(), {expected[0]})

    @skipUnless(connection.vendor == 'sqlite', 'Uses a SQLite trigger to reject the pointer update.')
    def test_failed_pointer_update_rolls_back_the_upload_history_record(self):
        self.assertEqual(self.upload().status_code, 302)
        expected = self.pointer()
        existing_ids = set(self.development.activities.values_list('pk', flat=True))
        table = connection.ops.quote_name(Gate1._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TRIGGER reject_marketing_pointer BEFORE UPDATE ON %s WHEN NEW.marketing_idea_filename = 'reject.pdf' BEGIN SELECT RAISE(ABORT, 'forced pointer failure'); END" % table)
        try:
            with self.assertRaises(IntegrityError):
                save_slot_file(self.development, self.user, 'G1-F10', SimpleUploadedFile('reject.pdf', b'rejected'))
        finally:
            with connection.cursor() as cursor:
                cursor.execute('DROP TRIGGER reject_marketing_pointer')
        self.assertEqual(self.pointer(), expected)
        self.assertEqual(set(self.development.activities.values_list('pk', flat=True)), existing_ids)
        with Gate1.objects.get(development_id=self.development.pk).marketing_idea_file.open('rb') as old_file:
            self.assertEqual(old_file.read(), b'original marketing idea')
