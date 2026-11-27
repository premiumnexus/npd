import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate0 import save_brief as save_gate0
from .gate2 import initial_brief,save_brief,save_slot_file
from .gate2_typed import Gate2Form
from .models import Food
from .test_gate0_pricing import FormNestingParser
from .test_gate2_mass_trial import COMPLETE


class Gate2TargetsTests(TestCase):
    def setUp(self):
        media=tempfile.TemporaryDirectory();self.addCleanup(media.cleanup)
        override=self.settings(MEDIA_ROOT=media.name);override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('gate2-target-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='45-day targets',stage='gate2',owner=self.user)
        self.url='/food/%s/'%self.food.pk
        for slot in ('G2-F2','G2-F3','G2-F5','G2-F6','G2-F7','G2-F8'):
            save_slot_file(self.food,self.user,slot,SimpleUploadedFile(slot+'.pdf',b'required file'))

    def test_layout_numbering_stars_and_no_duplicates(self):
        html=self.client.get(self.url).content.decode()
        section=html.split('<fieldset class="gate0-identity gate2-targets"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>45 хоногийн зорилт</legend>',section)
        self.assertIn('<small><em>Амжилтыг юугаар хэмжих вэ?</em></small>',section)
        self.assertEqual(section.count('class="required-star"'),2)
        positions=[section.index('class="field-number">7.%s</span>'%n) for n in range(1,5)]
        self.assertEqual(positions,sorted(positions))
        form=Gate2Form(food=self.food)
        for index,key in enumerate(form.target_keys,1):
            self.assertEqual(form.fields[key].gate_number,'7.%s'%index)
            self.assertFalse(form.fields[key].disabled)
            self.assertIn('name="%s"'%key,section)
            self.assertEqual(html.count('name="%s"'%key),1)
        self.assertNotIn('name="day45_target_confirmed"',html)
        self.assertNotIn('day45_target_confirmed',form.fields)
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)

    def test_required_targets_block_submission_and_approval(self):
        for key in Gate2Form.target_keys[:2]:
            data={**COMPLETE,key:''}
            self.assertTrue(Gate2Form(data,food=self.food).is_valid())
            form=Gate2Form(data,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
            self.food.review_status='draft';self.food.save();save_brief(self.food,data)
            self.client.post(self.url,{'action':'submit'})
            self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
            self.food.review_status='manager';self.food.save()
            self.client.post(self.url,{'action':'approve'})
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate2')
        # Optional margin/reason remain blank; explicit zero still counts as filled.
        data={**COMPLETE,'day45_units_store_day':'0','day45_writeoff_percent':'0'}
        form=Gate2Form(data,food=self.food,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        self.food.review_status='draft';self.food.save();save_brief(self.food,data)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'qa')

    def test_defaults_saved_targets_and_reason_survive_gate0_changes(self):
        save_gate0(self.food,{'target_units_store_day':'15','day45_writeoff_percent':'3','day45_margin_percent':'30'})
        form=Gate2Form(food=self.food)
        self.assertEqual([form.initial[key] for key in form.target_keys[:3]],['15','3','30'])
        self.assertEqual(self.client.post(self.url,{'action':'gate2_save','day45_units_store_day':'20.5','day45_writeoff_percent':'4','day45_margin_percent':'-2','day45_change_reason':'Updated sales plan','day45_target_confirmed':'same'}).status_code,302)
        save_gate0(self.food,{'target_units_store_day':'99','day45_writeoff_percent':'9','day45_margin_percent':'35'})
        saved=initial_brief(self.food)
        form=Gate2Form(initial=saved,food=self.food)
        self.assertEqual([Decimal(form.initial[key]) for key in form.target_keys[:3]],[Decimal('20.5'),4,-2])
        self.assertEqual(form.initial['day45_change_reason'],'Updated sales plan')
        self.assertNotIn('day45_target_confirmed',form.fields)

    def test_invalid_values_are_rejected_in_drafts_and_submission(self):
        for key,value in [('day45_units_store_day','-1'),('day45_writeoff_percent','-1'),('day45_writeoff_percent','101'),('day45_units_store_day','abc')]:
            for submission in (False,True):
                form=Gate2Form({**COMPLETE,key:value},food=self.food,submission=submission)
                self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
