"""Gate 3 file records retain their process identity, versions and downloads."""
from datetime import timedelta
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Activity, Food, Gate3File


class Gate3FileTests(TestCase):
    def test_uploads_use_dedicated_rows_and_preserve_authenticated_version_downloads(self):
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            user=User.objects.create_user('gate3-file-editor')
            user.groups.add(Group.objects.get(name='Category Manager (MD)'))
            development=Food.objects.create(name='Gate 3 files',owner=user,stage='gate3',
                launched_at=timezone.now()-timedelta(days=60))
            self.client.force_login(user)
            url=reverse('detail',args=[development.pk])
            for number in (1,2,3):
                slot='G3-F%s'%number
                for version in (1,2):
                    body=('%s version %s'%(slot,version)).encode('ascii')
                    response=self.client.post(url,{'action':'slot_upload','slot':slot,
                        'slot_file':SimpleUploadedFile('%s-v%s.txt'%(slot,version),body)})
                    self.assertEqual(response.status_code,302)
            records=list(development.gate3_files.select_related('activity'))
            self.assertEqual(len(records),6)
            self.assertEqual(len({item.file.name for item in records}),6)
            self.assertFalse(development.activities.exclude(attachment='').exists())
            page=self.client.get(url)
            self.assertTrue(all(len(slot['files'])==2 for slot in page.context['gate3slots']))
            for record in records:
                self.assertEqual(record.development_id,development.pk)
                self.assertEqual(record.uploader_id,user.pk)
                self.assertEqual(record.uploaded_at,record.activity.created)
                self.assertEqual(record.activity.food_id,development.pk)
                self.assertContains(page,record.download_url)
                record.full_clean()
                expected=record.original_filename.replace('.txt','').replace('-v',' version ').encode('ascii')
                for download_url in (record.download_url,reverse('download_attachment',args=[record.activity_id])):
                    response=self.client.get(download_url)
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(b''.join(response.streaming_content),expected)
                    response.close()
            user.groups.clear()
            self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G3-F1',
                'slot_file':SimpleUploadedFile('blocked.txt',b'blocked')}).status_code,403)
            self.client.logout()
            for download_url in (records[0].download_url,reverse('download_attachment',args=[records[0].activity_id])):
                self.assertEqual(self.client.get(download_url).status_code,302)

    def test_standalone_file_and_deleted_audit_link_remain_downloadable(self):
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            user=User.objects.create_user('gate3-file-reader')
            development=Food.objects.create(name='Standalone Gate 3 file',owner=user)
            activity=Activity.objects.create(food=development,text='Report uploaded')
            record=Gate3File.objects.create(development=development,slot_code='G3-F3',
                file=SimpleUploadedFile('report.txt',b'report'),original_filename='report.txt',activity=activity)
            activity.delete()
            record.refresh_from_db()
            self.assertIsNone(record.activity_id)
            self.client.force_login(user)
            response=self.client.get(record.download_url)
            self.assertEqual(b''.join(response.streaming_content),b'report')
            response.close()
            record.file.storage.delete(record.file.name)
            self.assertEqual(self.client.get(record.download_url).status_code,404)
