from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import LaunchCheckpoint
from .test_launch_day7 import COMPLETE,LaunchDay7Tests


class LaunchDay14Tests(LaunchDay7Tests):
    # Reuse setup only; the Day 14 checks below cover this section independently.
    def save(self,**data):
        return self.client.post(self.url,{**COMPLETE,'action':'checkpoint_save','day':14,**data})

    def test_layout_numbering_and_unique_fields(self):
        html=self.client.get(self.url).content.decode()
        section=html.split('Day 14 – 14 дэх өдрийн шалгалт',1)[1].split('</section>',1)[0]
        positions=[section.index('class="field-number">2.%s</span>'%n) for n in range(1,12)]
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(section.count('class="required-star"'),5)
        form=self.client.get(self.url).context['checkpoint_cards'][1]['form']
        self.assertEqual(len(form.fields),11)
        for key in form.fields:
            self.assertEqual(section.count('name="%s"'%key),0 if key=='achievement_percent' else 1)
        self.assertNotIn('class="field-number">1.',section)

    def test_required_inputs_and_new_values_persist(self):
        for key in COMPLETE:
            response=self.save(**{key:''})
            self.assertEqual(response.status_code,200)
            self.assertIn(key,response.context['checkpoint_cards'][1]['form'].errors)
        self.assertFalse(self.food.launch_checkpoints.exists())
        LaunchCheckpoint.objects.create(development=self.food,day=7,sample_weight_g=100,actual_writeoff_percent=1,promotion_period='no')
        self.assertEqual(self.save(actual_apsd='8',actual_writeoff_percent='6',promotion_period='yes',report=SimpleUploadedFile('day14.pdf',b'quality')).status_code,302)
        record=self.food.launch_checkpoints.get(day=14)
        self.assertEqual(record.sample_weight_g,Decimal('150.125'))
        self.assertEqual(record.actual_writeoff_percent,6)
        self.assertEqual(record.complaints_count,0);self.assertEqual(record.promotion_period,'yes')
        day7=self.food.launch_checkpoints.get(day=7)
        self.assertEqual(day7.sample_weight_g,100);self.assertEqual(day7.actual_writeoff_percent,1)
        form=self.client.get(self.url).context['checkpoint_cards'][1]['form']
        self.assertEqual(form.writeoff_status,'Red')
        self.assertEqual(form.achievement['percent'],80)
        self.assertEqual(self.food.activities.get(attachment_slot='L14F10').attachment_name,'day14.pdf')

    def test_reason_required_only_for_failed_sample(self):
        self.assertEqual(self.save(sample_result='conditional').status_code,302)
        response=self.save(sample_result='outside',action_plan=' ')
        self.assertEqual(response.status_code,200)
        self.assertIn('action_plan',response.context['checkpoint_cards'][1]['form'].errors)
        self.assertEqual(self.save(sample_result='outside',action_plan='Replace batch').status_code,302)
        self.assertEqual(self.food.launch_checkpoints.get(day=14).action_plan,'Replace batch')

    def test_roles_save_their_fields_without_overwriting_other_teams(self):
        self.user.is_superuser=False;self.user.save()
        self.user.groups.add(Group.objects.get(name='Food Science'))
        self.assertEqual(self.save(actual_writeoff_percent='99',complaints_count='999').status_code,302)
        record=self.food.launch_checkpoints.get(day=14)
        self.assertIsNone(record.complaints_count);self.assertIsNone(record.actual_writeoff_percent)
        self.user.groups.clear();self.user.groups.add(Group.objects.get(name='QA'))
        self.assertEqual(self.client.post(self.url,{'action':'checkpoint_save','day':14,'complaints_count':'3','sample_weight_g':'999'}).status_code,302)
        record.refresh_from_db();self.assertEqual(record.complaints_count,3);self.assertEqual(record.sample_weight_g,Decimal('150.125'))
        self.user.groups.clear();self.user.groups.add(Group.objects.get(name='FF Planning'))
        self.assertEqual(self.client.post(self.url,{'action':'checkpoint_save','day':14,'actual_writeoff_percent':'4','promotion_period':'no'}).status_code,302)
        record.refresh_from_db();self.assertEqual(record.actual_writeoff_percent,4);self.assertEqual(record.complaints_count,3)

    def test_missing_required_values_block_advancement_without_time_lock(self):
        LaunchCheckpoint.objects.create(development=self.food,day=7,**COMPLETE)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'launch')
        self.assertEqual(self.save().status_code,302)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate3')

    def test_numeric_validation_and_target_status(self):
        for key,value in [('sample_weight_g','-1'),('actual_writeoff_percent','101'),('complaints_count','-1'),('promotion_period','unknown')]:
            response=self.save(**{key:value})
            self.assertEqual(response.status_code,200)
            self.assertIn(key,response.context['checkpoint_cards'][1]['form'].errors)
