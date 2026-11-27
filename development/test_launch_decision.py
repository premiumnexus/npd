import tempfile
from datetime import date
from datetime import timedelta

from django.contrib.auth.models import Group,User
from django.test import TestCase
from django.utils import timezone

from .models import Food,LaunchCheckpoint,LaunchDecision,LaunchAction
from .test_gate0_pricing import FormNestingParser


class LaunchDecisionTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('launch-decision-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Launch decision',stage='launch',owner=self.user)
        self.url='/food/%s/'%self.food.pk

    def test_section_numbering_and_required_star(self):
        html=self.client.get(self.url).content.decode()
        section=html.split('<fieldset class="gate0-identity launch-decision"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Шийдвэр</legend>',section)
        self.assertIn('<small><em>Яаж үргэлжлүүлэх вэ?</em></small>',section)
        self.assertIn('class="field-number">3.1</span>',section)
        self.assertIn('class="field-number">3.2</span>',section)
        self.assertEqual(section.count('class="required-star"'),1)
        self.assertEqual(html.count('name="decision"'),1)
        for label in ('Үргэлжлүүлэх','Засах','Зогсоох'): self.assertIn(label,section)
        self.assertIn('name="decision_actions-0-what"',section)
        self.assertIn('name="decision_actions-__prefix__-when"',section)
        self.assertIn('data-add-row',section)
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)
        self.assertLess(html.index('id_day14_checked_date'),html.index('<legend>Шийдвэр</legend>'))

    def test_required_decision_and_valid_choices(self):
        for value in ('','unknown'):
            response=self.client.post(self.url,{'action':'launch_decision_save','decision':value})
            self.assertEqual(response.status_code,200)
            self.assertIn('decision',response.context['launch_decision_form'].errors)
            self.assertFalse(LaunchDecision.objects.exists())
        for value in ('continue','fix','stop'):
            self.assertEqual(self.client.post(self.url,{'action':'launch_decision_save','decision':value}).status_code,302)
            self.assertEqual(LaunchDecision.objects.get(development=self.food).decision,value)
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'launch')

    def test_multiple_rows_save_edit_delete_and_validate(self):
        data={'action':'launch_decision_save','decision':'fix','decision_actions-TOTAL_FORMS':'2'}
        for index in range(2):
            data.update({'decision_actions-%s-what'%index:'Action %s'%index,
                         'decision_actions-%s-who'%index:'Owner %s'%index,
                         'decision_actions-%s-when'%index:'2026-12-01'})
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        self.assertEqual(LaunchAction.objects.count(),2)
        data['decision_actions-0-DELETE']='on';data['decision_actions-1-what']='Updated action'
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        row=LaunchAction.objects.get()
        self.assertEqual((row.position,row.what,row.who,row.when),(0,'Updated action','Owner 1',date(2026,12,1)))
        data['decision_actions-1-when']='invalid'
        response=self.client.post(self.url,data)
        self.assertEqual(response.status_code,200)
        self.assertIn('decision_actions',response.context['launch_decision_form'].errors)
        row.refresh_from_db();self.assertEqual(row.when,date(2026,12,1))
        data['decision_actions-1-when']=''
        self.assertEqual(self.client.post(self.url,data).status_code,200)

    def test_decision_required_before_advancing(self):
        for day in (7,14):
            LaunchCheckpoint.objects.create(development=self.food,day=day,checked_date='2026-11-27',sample_weight_g=150,sample_result='within',complaints_count=0)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'launch')
        self.client.post(self.url,{'action':'launch_decision_save','decision':'continue'})
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate3')

    def test_permissions_and_historical_section_are_read_only(self):
        payload={'action':'launch_decision_save','decision':'continue'}
        self.user.is_superuser=False;self.user.save()
        self.assertEqual(self.client.post(self.url,payload).status_code,403)
        self.user.groups.add(Group.objects.get(name='FF Planning'))
        self.assertEqual(self.client.post(self.url,payload).status_code,302)
        self.assertEqual(self.client.post(self.url+'?gate=gate2',payload).status_code,403)
        for stage,review,complete in [('launch','manager',False),('launch','draft',True),('gate3','draft',False)]:
            self.food.stage=stage;self.food.review_status=review;self.food.completed=complete;self.food.save()
            self.assertEqual(self.client.post(self.url,payload).status_code,403)
        html=self.client.get(self.url+'?gate=launch').content.decode()
        section=html.split('<fieldset class="gate0-identity launch-decision"',1)[1].split('</fieldset>',1)[0]
        self.assertNotIn('data-add-row',section)
        self.assertNotIn('value="launch_decision_save"',section)
        self.assertIn('disabled',section)

    def test_gate3_fields_editable_as_soon_as_launch_finishes(self):
        from .gate3 import initial_brief
        self.user.is_superuser=False;self.user.save()
        self.user.groups.add(Group.objects.get(name='FF Planning'))
        for launch_date in (None,timezone.now(),timezone.now()+timedelta(days=45)):
            with self.subTest(launch_date=launch_date):
                food=Food.objects.create(name='Immediate Gate 3',stage='launch',owner=self.user,launched_at=launch_date)
                for day in (7,14):
                    LaunchCheckpoint.objects.create(development=food,day=day,checked_date='2026-11-27',sample_weight_g=150,sample_result='within',complaints_count=0)
                LaunchDecision.objects.create(development=food,decision='continue')
                url='/food/%s/'%food.pk
                self.assertEqual(self.client.post(url,{'action':'submit'}).status_code,302)
                food.refresh_from_db();self.assertEqual((food.stage,food.review_status),('gate3','draft'))
                page=self.client.get(url)
                self.assertTrue(page.context['editable'])
                self.assertFalse(page.context['gate3form'].fields['sales_vs_target'].disabled)
                self.assertEqual(self.client.post(url,{'action':'gate3_save','sales_vs_target':'10'}).status_code,302)
                self.assertEqual(initial_brief(food)['sales_vs_target'],'10')
