import tempfile
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from .gate0 import save_brief as save_gate0
from .gate2 import initial_brief, save_brief, save_slot_file
from .gate2_typed import Gate2Form
from .models import Food, Gate2, Gate2File
from .test_gate0_pricing import FormNestingParser
from .test_gate2_mass_trial import COMPLETE


class Gate2ReadinessTests(TestCase):
    def setUp(self):
        media=tempfile.TemporaryDirectory();self.addCleanup(media.cleanup)
        override=self.settings(MEDIA_ROOT=media.name);override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('gate2-readiness-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Launch readiness example',stage='gate2',owner=self.user)
        self.url='/food/%s/'%self.food.pk
        for slot in ('G2-F2','G2-F3','G2-F5','G2-F6','G2-F7','G2-F8'):
            save_slot_file(self.food,self.user,slot,SimpleUploadedFile(slot+'.pdf',b'required file'))

    def test_section_order_required_stars_and_no_duplicates(self):
        html=self.client.get(self.url).content.decode()
        section=html.split('<fieldset class="gate0-identity gate2-readiness"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Нэвтрүүлэлтийн бэлэн байдал</legend>',section)
        self.assertIn('<small><em>Дэлгүүрт гаргахад бэлэн үү?</em></small>',section)
        positions=[section.index('class="field-number">5.%s</span>'%n) for n in range(1,12)]
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(section.count('class="required-star"'),8)
        form=Gate2Form(food=self.food)
        for index,key in enumerate(form.readiness_keys,1):
            self.assertEqual(form.fields[key].gate_number,'5.%s'%index)
            self.assertIn('name="%s"'%key,section)
            self.assertEqual(html.count('name="%s"'%key),1)
        self.assertNotIn('name="delivery_slot"',html)
        self.assertNotIn('id="file-G2-F10"',html)
        self.assertNotIn('delivery_slot',form.fields)
        self.assertNotIn('data-option-field="cold_chain_temperature"',section)
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)

    def test_each_required_value_blocks_submission_and_approval(self):
        self.assertTrue(Gate2Form(COMPLETE,food=self.food,submission=True).is_valid())
        for key in Gate2Form.readiness_required:
            data={**COMPLETE,key:''}
            self.assertTrue(Gate2Form(data,food=self.food).is_valid())
            form=Gate2Form(data,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
            self.food.review_status='draft';self.food.save();save_brief(self.food,data)
            self.client.post(self.url,{'action':'submit'})
            self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft',key)
            self.food.review_status='manager';self.food.save()
            self.client.post(self.url,{'action':'approve'})
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate2',key)
        self.food.review_status='draft';self.food.save();save_brief(self.food,COMPLETE)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'qa')

    def test_temperature_choices_persistence_and_historical_mapping(self):
        form=Gate2Form(food=self.food)
        self.assertEqual(list(form.fields['cold_chain_temperature'].choices),[
            ('','---------'),('chilled','0–5 °C'),('frozen','−18 °C'),('ambient','өрөөний')])
        for condition in ('chilled','frozen','ambient'):
            data={'cold_chain_temperature':condition,'barcode_system_registration':'00123456789'}
            self.assertTrue(Gate2Form(data,food=self.food).is_valid())
            self.assertEqual(self.client.post(self.url,{**data,'action':'gate2_save'}).status_code,302)
            self.assertEqual(initial_brief(self.food)['cold_chain_temperature'],condition)
            self.assertEqual(initial_brief(self.food)['barcode_system_registration'],'00123456789')
        self.assertFalse(Gate2Form({'cold_chain_temperature':'-20'},food=self.food).is_valid())
        migration=import_module('development.migrations.0014_gate2_launch_readiness')
        for value,expected in [('-18.00','frozen'),('5.00','chilled'),('0','chilled'),('ambient','ambient'),('8.00','8.00')]:
            Gate2.objects.filter(development=self.food).update(cold_chain_temperature=value)
            migration.map_storage_conditions(apps,SimpleNamespace(connection=connection))
            self.assertEqual(Gate2.objects.get(development=self.food).cold_chain_temperature,expected)

    def test_dates_remain_derived_and_removed_file_upload_is_rejected(self):
        save_gate0(self.food,{'planned_launch_date':'2028-02-28'})
        data={'action':'gate2_save','launch_date':'2028-03-01','original_launch_date':'2099-01-01','launch_delay_days':'999','launch_date_change_reason':'Updated date'}
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(saved['original_launch_date'],'2028-02-28')
        self.assertEqual(saved['launch_delay_days'],2)
        self.assertEqual(saved['launch_date_change_reason'],'Updated date')
        self.assertEqual(self.client.post(self.url,{'action':'slot_upload','slot':'G2-F10','slot_file':SimpleUploadedFile('allocation.pdf',b'new')}).status_code,403)
        legacy=Gate2File.objects.create(development=self.food,slot_code='G2-F10',file=SimpleUploadedFile('old-allocation.pdf',b'historical'),original_filename='old-allocation.pdf')
        response=self.client.get(reverse('download_gate2_file',args=[legacy.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(b''.join(response.streaming_content),b'historical')
        response.close()
