import tempfile
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase

from .gate2 import save_brief,initial_brief,save_slot_file
from .gate2_typed import Gate2Form
from .models import Food,Gate2
from .test_gate2_mass_trial import COMPLETE
from .test_gate0_pricing import FormNestingParser


class Gate2SafetyTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name);override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('gate2-lab-editor');self.client.force_login(self.user)
        self.food=Food.objects.create(name='Laboratory example',stage='gate2',owner=self.user)
        self.url='/food/%s/'%self.food.pk
        for slot in ('G2-F2','G2-F5','G2-F7','G2-F8'): self.upload(slot)

    def upload(self,slot):
        return save_slot_file(self.food,self.user,slot,SimpleUploadedFile(slot+'.pdf',b'safety document'))

    def test_layout_numbering_required_stars_and_unique_inline_files(self):
        html=self.client.get(self.url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate2-safety"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Хүнсний аюулгүй байдал ба хадгалах хугацаа</legend>',group)
        self.assertIn('<small><em>Лаборатори баталсан уу?</em></small>',group)
        self.assertEqual(group.count('class="required-star"'),4)
        positions=[group.index('class="field-number">3.%s</span>'%n) for n in range(1,7)]
        self.assertEqual(positions,sorted(positions))
        self.assertIn('Батлагдсан хадгалах хугацаа (цаг)',group)
        self.assertNotIn('name="approved_shelf_life_days"',html)
        bottom=html.split('<section class="gate0-file-slots"',1)[1]
        for slot in ('G2-F3','G2-F4','G2-F6'):
            self.assertEqual(html.count('id="file-%s"'%slot),1)
            self.assertIn('id="file-%s"'%slot,group)
            self.assertNotIn('id="file-%s"'%slot,bottom)
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)

    def test_required_inputs_and_files_block_submission_and_approval(self):
        for slot in ('G2-F3','G2-F6'): self.upload(slot)
        self.assertTrue(Gate2Form(COMPLETE,food=self.food,submission=True).is_valid())
        for key in ('lab_results_approved_shelf_life','approved_shelf_life_hours'):
            incomplete={**COMPLETE,key:''}
            self.assertTrue(Gate2Form(incomplete,food=self.food).is_valid())
            form=Gate2Form(incomplete,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
            self.food.review_status='draft';self.food.save();save_brief(self.food,incomplete)
            self.client.post(self.url,{'action':'submit'})
            self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
            self.food.review_status='manager';self.food.save()
            self.client.post(self.url,{'action':'approve'})
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate2')
        for slot,number in [('G2-F3','3.4'),('G2-F6','3.6')]:
            self.food.gate2_files.filter(slot_code=slot).delete()
            self.food.review_status='draft';self.food.save();save_brief(self.food,COMPLETE)
            form=Gate2Form(COMPLETE,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(number,str(form.non_field_errors()))
            self.client.post(self.url,{'action':'submit'})
            self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
            self.food.review_status='manager';self.food.save()
            self.client.post(self.url,{'action':'approve'})
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate2')
            self.upload(slot)
        self.food.review_status='draft';self.food.save();save_brief(self.food,COMPLETE)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'qa')

    def test_hours_storage_and_legacy_day_conversion(self):
        save_brief(self.food,{'approved_shelf_life_days':2})
        self.assertEqual(initial_brief(self.food)['approved_shelf_life_hours'],48)
        other=Food.objects.create(name='Hours already set',stage='gate2',owner=self.user)
        save_brief(other,{'approved_shelf_life_days':3,'approved_shelf_life_hours':36})
        migration=import_module('development.migrations.0012_approved_shelf_life_hours')
        migration.copy_approved_hours(apps,SimpleNamespace(connection=connection))
        self.assertEqual(Gate2.objects.get(development=self.food).approved_shelf_life_hours,48)
        self.assertEqual(Gate2.objects.get(development=other).approved_shelf_life_hours,36)
        response=self.client.post(self.url,{'action':'gate2_save','approved_shelf_life_hours':'36'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Gate2.objects.get(development=self.food).approved_shelf_life_hours,36)
        for value in ('0','-1','1.5'):
            form=Gate2Form({'approved_shelf_life_hours':value},food=self.food)
            self.assertFalse(form.is_valid());self.assertIn('approved_shelf_life_hours',form.errors)

    def test_relocated_file_histories_remain_downloadable_in_review(self):
        for slot in ('G2-F3','G2-F4','G2-F6'):
            self.upload(slot);self.upload(slot)
        self.food.review_status='manager';self.food.save()
        html=self.client.get(self.url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate2-safety"',1)[1].split('</fieldset>',1)[0]
        self.assertNotIn('name="slot_file"',group)
        for item in self.food.gate2_files.filter(slot_code__in=('G2-F3','G2-F4','G2-F6')):
            self.assertIn(item.download_url,group)
            response=self.client.get(item.download_url)
            self.assertEqual(b''.join(response.streaming_content),b'safety document')
