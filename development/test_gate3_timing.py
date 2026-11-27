from django.contrib.auth.models import User
from django.test import TestCase

from .gate0 import save_brief as save_gate0
from .gate2 import save_brief as save_gate2
from .gate3 import initial_brief
from .gate3_typed import Gate3Form
from .models import Food
from .test_gate0_pricing import FormNestingParser


class Gate3TimingTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gate3-timing-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Timing example',stage='gate3',owner=self.user)
        self.url='/food/%s/'%self.food.pk

    def test_section_order_numbering_and_no_duplicate_fields(self):
        html=self.client.get(self.url).content.decode()
        section=html.split('<fieldset class="gate0-identity gate3-timing"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Хугацаа</legend>',section)
        self.assertIn('<small><em>Төлөвлөсөн хугацаандаа гарсан уу?</em></small>',section)
        positions=[section.index('class="field-number">1.%s</span>'%number) for number in range(1,5)]
        self.assertEqual(positions,sorted(positions))
        for key in Gate3Form.timing_keys:
            self.assertEqual(html.count('name="%s"'%key),1)
            self.assertIn('name="%s"'%key,section)
        self.assertIn('Gate 0 1.6-аас',section)
        self.assertIn('Gate 2 5.1-ээс',section)
        self.assertIn('Gate 2 5.4-өөс',section)
        self.assertLess(html.index('<legend>Хугацаа</legend>'),html.index('name="sales_vs_target"'))
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)

    def test_values_copy_sources_and_posted_overrides_are_ignored(self):
        save_gate0(self.food,{'planned_launch_date':'2026-11-01'})
        save_gate2(self.food,{'launch_date':'2026-11-10','launch_date_change_reason':'Supplier delay'})
        form=Gate3Form(food=self.food)
        self.assertEqual([form.initial[key] for key in form.timing_keys],['2026-11-01','2026-11-10',9,'Supplier delay'])
        self.assertTrue(all(form.fields[key].disabled for key in form.timing_keys))
        response=self.client.post(self.url,{'action':'gate3_save','planned_vs_actual_launch_date':'2099-01-01','actual_launch_date':'2099-01-02','launch_days_late':'999','launch_delay_reason':'Override'})
        self.assertEqual(response.status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual([saved[key] for key in form.timing_keys],['2026-11-01','2026-11-10',9,'Supplier delay'])
        save_gate2(self.food,{'launch_date':'2026-10-31','launch_date_change_reason':'Earlier delivery'})
        saved=initial_brief(self.food)
        self.assertEqual(saved['launch_days_late'],0)
        self.assertEqual(saved['launch_delay_reason'],'Earlier delivery')
