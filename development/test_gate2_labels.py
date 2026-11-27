import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate2 import initial_brief, save_brief, save_slot_file
from .gate2_typed import Gate2Form
from .models import Food, Gate2Nutrition
from .test_gate2_mass_trial import COMPLETE
from .test_gate0_pricing import FormNestingParser


class Gate2LabelTests(TestCase):
    def setUp(self):
        media=tempfile.TemporaryDirectory();self.addCleanup(media.cleanup)
        override=self.settings(MEDIA_ROOT=media.name);override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('gate2-label-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Label example',stage='gate2',owner=self.user)
        self.url='/food/%s/'%self.food.pk
        for slot in ('G2-F2','G2-F3','G2-F5','G2-F6','G2-F7','G2-F8'):
            self.upload(slot)

    def upload(self,slot):
        save_slot_file(self.food,self.user,slot,SimpleUploadedFile(slot+'.pdf',b'label document'))

    def test_layout_and_unique_inline_files(self):
        html=self.client.get(self.url).content.decode()
        section=html.split('<fieldset class="gate0-identity gate2-labels"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Шошго ба савлагаа</legend>',section)
        self.assertIn('<small><em>Шошго, савлагаа бэлэн үү?</em></small>',section)
        positions=[section.index('class="field-number">4.%s</span>'%n) for n in range(1,6)]
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(section.count('class="required-star"'),5)
        self.assertIn('name="nutrition_info-0-energy_kcal"',section)
        self.assertIn('name="nutrition_info-__prefix__-salt_g"',section)
        bottom=html.split('<section class="gate0-file-slots"',1)[1]
        for slot in ('G2-F7','G2-F8'):
            self.assertEqual(html.count('id="file-%s"'%slot),1)
            self.assertIn('id="file-%s"'%slot,section)
            self.assertNotIn('id="file-%s"'%slot,bottom)
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)

    def test_required_values_block_submission_and_approval(self):
        self.assertTrue(Gate2Form(COMPLETE,food=self.food,submission=True).is_valid())
        for key in ('label_allergens','label_checked','nutrition_info'):
            data={**COMPLETE,key:[] if key=='nutrition_info' else ''}
            self.assertTrue(Gate2Form(data,food=self.food).is_valid())
            form=Gate2Form(data,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
            self.food.review_status='draft';self.food.save();save_brief(self.food,data)
            self.client.post(self.url,{'action':'submit'})
            self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
            self.food.review_status='manager';self.food.save()
            self.client.post(self.url,{'action':'approve'})
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate2')
        for slot,number in [('G2-F7','4.4'),('G2-F8','4.5')]:
            self.food.gate2_files.filter(slot_code=slot).delete()
            save_brief(self.food,COMPLETE)
            form=Gate2Form(COMPLETE,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(number,str(form.non_field_errors()))
            self.food.review_status='draft';self.food.save()
            self.client.post(self.url,{'action':'submit'})
            self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
            self.food.review_status='manager';self.food.save()
            self.client.post(self.url,{'action':'approve'})
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate2')
            self.upload(slot)
        self.food.review_status='draft';self.food.save()
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'qa')

    def test_rows_save_edit_remove_and_validate(self):
        data={'action':'gate2_save','nutrition_info-TOTAL_FORMS':'2'}
        for index in range(2):
            for key,value in COMPLETE['nutrition_info'][0].items():
                data['nutrition_info-%s-%s'%(index,key)]=value
        data['nutrition_info-1-salt_g']='0'
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        rows=list(Gate2Nutrition.objects.filter(gate_id=self.food.pk))
        self.assertEqual(len(rows),2);self.assertEqual(rows[1].salt_g,Decimal('0'))
        self.assertEqual(len(initial_brief(self.food)['nutrition_info']),2)
        data['nutrition_info-0-DELETE']='on';data['nutrition_info-1-energy_kcal']='210.25'
        self.client.post(self.url,data)
        row=Gate2Nutrition.objects.get(gate_id=self.food.pk)
        self.assertEqual(row.position,0);self.assertEqual(row.energy_kcal,Decimal('210.25'))
        partial={**COMPLETE,'nutrition_info':[{'energy_kcal':'0'}]}
        self.assertTrue(Gate2Form(partial,food=self.food).is_valid())
        form=Gate2Form(partial,food=self.food,submission=True)
        self.assertFalse(form.is_valid());self.assertIn('nutrition_info',form.errors)
        invalid={**COMPLETE,'nutrition_info':[{**COMPLETE['nutrition_info'][0],'salt_g':'-1'}]}
        form=Gate2Form(invalid,food=self.food)
        self.assertFalse(form.is_valid());self.assertIn('nutrition_info',form.errors)
