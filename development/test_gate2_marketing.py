import tempfile
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase

from .gate2 import initial_brief,save_brief,save_slot_file
from .gate2_typed import Gate2Form
from .gate3_typed import Gate3Form
from .models import Food,Gate2,Gate2MarketingChannel
from .test_gate0_pricing import FormNestingParser
from .test_gate2_mass_trial import COMPLETE


PROMOTION={**COMPLETE,'marketing_has_promotion':'yes','marketing_promotion':'discount',
           'marketing_budget':'100000.50','marketing_start_date':'2027-05-01','marketing_end_date':'2027-05-15'}


class Gate2MarketingTests(TestCase):
    def setUp(self):
        media=tempfile.TemporaryDirectory();self.addCleanup(media.cleanup)
        override=self.settings(MEDIA_ROOT=media.name);override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('gate2-marketing-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Launch marketing example',stage='gate2',owner=self.user)
        self.url='/food/%s/'%self.food.pk
        for slot in ('G2-F2','G2-F3','G2-F5','G2-F6','G2-F7','G2-F8'):
            save_slot_file(self.food,self.user,slot,SimpleUploadedFile(slot+'.pdf',b'required file'))

    def section(self):
        html=self.client.get(self.url).content.decode()
        return html,html.split('<fieldset class="gate0-identity gate2-marketing"',1)[1].split('</fieldset>',1)[0]

    def test_layout_numbering_stars_choices_and_unique_file(self):
        html,section=self.section()
        self.assertIn('<legend>Нэвтрүүлэлтийн маркетинг</legend>',section)
        self.assertIn('<small><em>Хэрхэн танилцуулах вэ?</em></small>',section)
        positions=[section.index('class="field-number">6.%s</span>'%n) for n in range(1,8)]
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(section.count('data-promotion-required'),4)
        self.assertEqual(section.count('aria-label="Заавал бөглөх" hidden'),4)
        for key in Gate2Form.marketing_keys:
            if key!='marketing_channels': self.assertEqual(html.count('name="%s"'%key),1)
        self.assertEqual(section.count('name="marketing_channels"'),4)
        for label in ('дэлгүүрийн POP','сошиал','CU апп','бусад','хөнгөлөлт','1+1','багц','амталгаа'):
            self.assertIn(label,section)
        self.assertEqual(html.count('id="file-G2-F9"'),1)
        self.assertIn('id="file-G2-F9"',section)
        self.assertNotIn('id="file-G2-F9"',html.split('<section class="gate0-file-slots"',1)[1])
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)
        save_brief(self.food,PROMOTION)
        _,section=self.section()
        self.assertNotIn('aria-label="Заавал бөглөх" hidden',section)

    def test_conditional_requirements_block_submit_and_approve(self):
        self.assertTrue(Gate2Form(COMPLETE,food=self.food,submission=True).is_valid())
        self.assertTrue(Gate2Form(PROMOTION,food=self.food,submission=True).is_valid())
        for key in ('marketing_has_promotion',)+Gate2Form.promotion_required:
            data={**PROMOTION,key:''}
            self.assertTrue(Gate2Form(data,food=self.food).is_valid())
            form=Gate2Form(data,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
            self.food.review_status='draft';self.food.save();save_brief(self.food,data)
            self.client.post(self.url,{'action':'submit'})
            self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft',key)
            self.food.review_status='manager';self.food.save()
            self.client.post(self.url,{'action':'approve'})
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate2',key)
        self.food.review_status='draft';self.food.save();save_brief(self.food,PROMOTION)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'qa')

    def test_channels_persist_edit_clear_and_support_handover(self):
        data={'action':'gate2_save','marketing_has_promotion':'no','marketing_channels':['pop','cu_app']}
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        self.assertEqual(initial_brief(self.food)['marketing_channels'],['pop','cu_app'])
        self.assertEqual(list(Gate2MarketingChannel.objects.filter(gate_id=self.food.pk).values_list('position','value')),[(0,'pop'),(1,'cu_app')])
        self.assertEqual(Gate3Form(food=self.food).initial['handover_marketing_plan'],'yes')
        self.assertEqual(self.client.post(self.url,{**data,'marketing_channels':['social']}).status_code,302)
        self.assertEqual(initial_brief(self.food)['marketing_channels'],['social'])
        self.assertEqual(self.client.post(self.url,{'action':'gate2_save','marketing_has_promotion':'no'}).status_code,302)
        self.assertEqual(initial_brief(self.food)['marketing_channels'],[])
        self.assertEqual(Gate3Form(food=self.food).initial['handover_marketing_plan'],'no')

    def test_invalid_choices_budget_and_date_order(self):
        for key,value in [('marketing_has_promotion','maybe'),('marketing_promotion','unknown'),('marketing_budget','-1'),('marketing_channels',['unknown']),('marketing_end_date','2027-04-01')]:
            form=Gate2Form({**PROMOTION,key:value},food=self.food)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
        form=Gate2Form({**PROMOTION,'marketing_budget':'0'},food=self.food,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        for code in ('discount','bogo','bundle','tasting','other'):
            self.assertTrue(Gate2Form({**PROMOTION,'marketing_promotion':code},food=self.food,submission=True).is_valid())

    def test_historical_marketing_choices_and_notes_remain_available(self):
        save_brief(self.food,{'marketing_plan':'дэлгүүрийн POP · CU апп · Notes','marketing_promotion':'амталгаа'})
        migration=import_module('development.migrations.0015_gate2_launch_marketing')
        for _ in range(2): migration.copy_marketing_choices(apps,SimpleNamespace(connection=connection))
        self.assertEqual(initial_brief(self.food)['marketing_channels'],['pop','cu_app'])
        record=Gate2.objects.get(development=self.food)
        self.assertEqual(record.marketing_promotion,'tasting')
        self.assertEqual(record.marketing_has_promotion,'yes')
        self.assertEqual(self.client.post(self.url,{'action':'gate2_save','marketing_has_promotion':'no'}).status_code,302)
        _,section=self.section()
        self.assertIn('дэлгүүрийн POP · CU апп · Notes',section)

    def test_inline_file_history_is_available_during_review(self):
        for version in range(2):
            save_slot_file(self.food,self.user,'G2-F9',SimpleUploadedFile('marketing-%s.pdf'%version,b'marketing plan'))
        self.food.review_status='manager';self.food.save()
        _,section=self.section()
        self.assertNotIn('name="slot_file"',section)
        for item in self.food.gate2_files.filter(slot_code='G2-F9'):
            self.assertIn(item.download_url,section)
            response=self.client.get(item.download_url)
            self.assertEqual(b''.join(response.streaming_content),b'marketing plan')
            response.close()
