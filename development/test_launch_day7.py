import tempfile
from decimal import Decimal

from django.contrib.auth.models import Group,User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate2 import save_brief as save_gate2
from .launch import CheckpointForm,writeoff_status
from .models import Food,LaunchCheckpoint,LaunchDecision


COMPLETE={'checked_date':'2026-11-27','sample_weight_g':'150.125','sample_result':'within','complaints_count':'0'}


class LaunchDay7Tests(TestCase):
    def setUp(self):
        media=tempfile.TemporaryDirectory();self.addCleanup(media.cleanup)
        override=self.settings(MEDIA_ROOT=media.name);override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('day7-editor');self.client.force_login(self.user)
        self.food=Food.objects.create(name='Day 7 example',stage='launch',owner=self.user)
        LaunchDecision.objects.create(development=self.food,decision='continue')
        save_gate2(self.food,{'day45_units_store_day':'10','day45_writeoff_percent':'5'})
        self.url='/food/%s/'%self.food.pk

    def save(self,**data):
        return self.client.post(self.url,{**COMPLETE,'action':'checkpoint_save','day':7,**data})

    def test_layout_numbering_and_unique_fields(self):
        html=self.client.get(self.url).content.decode()
        section=html.split('Day 7 – 7 дахь өдрийн шалгалт',1)[1].split('</section>',1)[0]
        self.assertIn('<small><em>Төлөвлөгөөний дагуу эхэлж байна уу?</em></small>',section)
        positions=[section.index('class="field-number">1.%s</span>'%n) for n in range(1,12)]
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(section.count('class="required-star"'),5) # Four fixed stars and the hidden conditional star.
        form=CheckpointForm(day=7,food=self.food,user=self.user)
        self.assertEqual(len(form.fields),11)
        for key in form.fields: self.assertEqual(section.count('name="%s"'%key),0 if key=='achievement_percent' else 1)
        self.assertEqual(list(form.fields['sample_result'].choices)[1:],[('within','Тэнцсэн'),('conditional','Засвартай'),('outside','Тэнцээгүй')])

    def test_required_inputs_and_new_values_persist(self):
        for key in COMPLETE:
            response=self.save(**{key:''})
            self.assertEqual(response.status_code,200)
            self.assertIn(key,response.context['checkpoint_cards'][0]['form'].errors)
            self.assertFalse(self.food.launch_checkpoints.exists())
        response=self.save(actual_apsd='12',actual_writeoff_percent='4.5',promotion_period='yes',report=SimpleUploadedFile('day7.pdf',b'quality'))
        self.assertEqual(response.status_code,302)
        record=self.food.launch_checkpoints.get(day=7)
        self.assertEqual(record.sample_weight_g,Decimal('150.125'))
        self.assertEqual(record.actual_writeoff_percent,Decimal('4.5'))
        self.assertEqual(record.complaints_count,0);self.assertEqual(record.promotion_period,'yes')
        form=self.client.get(self.url).context['checkpoint_cards'][0]['form']
        self.assertEqual(form.achievement['percent'],Decimal('120.00'))
        self.assertEqual(form.writeoff_status,'Green')
        self.assertEqual(form.initial['sample_weight_g'],Decimal('150.125'))
        self.assertEqual(self.food.activities.get(attachment_slot='L7F8').attachment_name,'day7.pdf')

    def test_reason_required_only_for_failed_sample(self):
        self.assertEqual(self.save(sample_result='conditional').status_code,302)
        self.assertEqual(self.save(sample_result='conditional',action_plan='Review packaging').status_code,302)
        self.assertEqual(self.food.launch_checkpoints.get(day=7).action_plan,'Review packaging')
        response=self.save(sample_result='outside',action_plan=' ')
        self.assertEqual(response.status_code,200)
        self.assertIn('action_plan',response.context['checkpoint_cards'][0]['form'].errors)
        self.assertEqual(self.save(sample_result='outside',action_plan='Replace batch').status_code,302)
        self.assertEqual(self.food.launch_checkpoints.get(day=7).action_plan,'Replace batch')

    def test_roles_save_their_fields_without_overwriting_other_teams(self):
        self.user.is_superuser=False;self.user.save()
        self.user.groups.add(Group.objects.get(name='Food Science'))
        self.assertEqual(self.save(actual_writeoff_percent='99',complaints_count='999').status_code,302)
        record=self.food.launch_checkpoints.get(day=7)
        self.assertIsNone(record.complaints_count);self.assertIsNone(record.actual_writeoff_percent)
        self.user.groups.clear();self.user.groups.add(Group.objects.get(name='QA'))
        self.assertEqual(self.client.post(self.url,{'action':'checkpoint_save','day':7,'complaints_count':'2','sample_weight_g':'999'}).status_code,302)
        record.refresh_from_db();self.assertEqual(record.complaints_count,2);self.assertEqual(record.sample_weight_g,Decimal('150.125'))
        self.user.groups.clear();self.user.groups.add(Group.objects.get(name='FF Planning'))
        self.assertEqual(self.client.post(self.url,{'action':'checkpoint_save','day':7,'actual_writeoff_percent':'6','promotion_period':'no','actual_apsd':'8'}).status_code,302)
        record.refresh_from_db();self.assertEqual(record.complaints_count,2);self.assertEqual(record.actual_writeoff_percent,6)
        self.assertEqual(record.sample_result,'within')

    def test_missing_required_values_block_advancement_without_time_lock(self):
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'launch')
        self.assertEqual(self.save().status_code,302)
        LaunchCheckpoint.objects.create(development=self.food,day=14,**{**COMPLETE,'sample_weight_g':150})
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate3')

    def test_numeric_validation_and_target_status(self):
        for key,value in [('sample_weight_g','-1'),('actual_writeoff_percent','101'),('actual_writeoff_percent','-1'),('complaints_count','-1'),('promotion_period','unknown')]:
            response=self.save(**{key:value})
            self.assertEqual(response.status_code,200)
            self.assertIn(key,response.context['checkpoint_cards'][0]['form'].errors)
        self.assertEqual(writeoff_status('5','5'),'Green')
        self.assertEqual(writeoff_status('5.01','5'),'Red')
        self.assertEqual(writeoff_status('0','0'),'Green')
        self.assertEqual(writeoff_status('1',None),'Pending')
        self.assertEqual(writeoff_status(None,'5'),'Pending')
