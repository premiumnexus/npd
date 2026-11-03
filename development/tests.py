from datetime import date
from decimal import Decimal
from unittest.mock import patch
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.contrib.auth.models import User,Group
from .models import Food,Supplier,Ingredient,RecipeLine

class DevelopmentTests(TestCase):
    def test_attachments_available_at_every_stage_to_all_signed_in_users(self):
        from .models import STAGES, Activity
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                for stage,_ in STAGES:
                    self.food.stage=stage
                    self.food.save()
                    response=self.client.post('/food/%s/' % self.food.pk,{
                        'action':'attachment',
                        'attachment':SimpleUploadedFile('report.custom',b'file contents',content_type='application/octet-stream'),
                    })
                    self.assertEqual(response.status_code,302)
                    activity=Activity.objects.latest('pk')
                    self.assertEqual(activity.attachment_stage,stage)
                    self.assertEqual(activity.attachment_name,'report.custom')
                reader=User.objects.create_user('reader')
                self.client.force_login(reader)
                response=self.client.get('/food/%s/' % self.food.pk)
                self.assertContains(response,'report.custom')
                self.assertContains(response,'attachment-file')
                response=self.client.get('/attachments/%s/' % activity.pk)
                self.assertEqual(response.status_code,200)
                self.assertIn('attachment;',response['Content-Disposition'])
                self.assertEqual(b''.join(response.streaming_content),b'file contents')
                response.close()
                self.client.logout()
                self.assertEqual(self.client.get('/attachments/%s/' % activity.pk).status_code,302)

    def test_missing_attachment_does_not_create_log(self):
        self.client.post('/food/%s/' % self.food.pk,{'action':'attachment'})
        self.assertEqual(self.food.activities.count(),0)

    def test_stage_overview_counts_all_stages_and_preserves_search(self):
        Food.objects.create(name='Test launch',owner=self.user,due=date.today(),stage='approved')
        Food.objects.create(name='Other recipe',owner=self.user,due=date.today(),stage='recipe')
        response=self.client.get('/?stage=approved&q=Test')
        summary={item['key']:item['count'] for item in response.context['stage_summary']}
        self.assertEqual(summary,{'concept':1,'recipe':0,'sourcing':0,'quality':0,'costing':0,'approved':1})
        self.assertEqual(len(response.context['foods']),1)
        self.assertContains(response,'Үе шат тус бүрийн хөгжүүлэлт')
        self.assertContains(response,'?stage=recipe&amp;q=Test')
        response=self.client.get('/')
        summary={item['key']:item['count'] for item in response.context['stage_summary']}
        self.assertEqual(summary['recipe'],1)

    @patch('development.views.timezone.localdate',return_value=date(2026,12,15))
    def test_sla_due_includes_today_and_overdue_but_excludes_approved(self,localdate):
        self.food.due=date(2026,12,15)
        self.food.save()
        for name,due,stage in [('Overdue',date(2026,12,14),'quality'),('Future',date(2026,12,16),'recipe'),('Finished',date(2026,12,14),'approved')]:
            Food.objects.create(name=name,owner=self.user,due=due,stage=stage)
        response=self.client.get('/?q=does-not-exist')
        self.assertEqual(response.context['sla_due'],2)
        self.assertContains(response,'Хугацаа тулсан ажил')

    @patch('development.views.timezone.localdate',return_value=date(2026,12,15))
    def test_launch_statistics_use_calendar_dates_and_ignore_search(self,localdate):
        for index,(production,launch) in enumerate([
            (date(2026,12,1),date(2026,1,1)),
            (date(2026,12,31),date(2026,12,15)),
            (date(2027,1,1),date(2025,12,31)),
            (date(2026,11,30),date(2026,12,16)),
        ]):
            Food.objects.create(name='Launch %s' % index,owner=self.user,due=date(2026,12,1),production_date=production,market_launch_date=launch)
        response=self.client.get('/?q=does-not-exist')
        self.assertEqual(response.context['production_this_month'],2)
        self.assertEqual(response.context['market_launches_this_year'],2)
        self.assertContains(response,'Энэ сард үйлдвэрлэх')
        self.assertContains(response,'Энэ онд зах зээлд гарсан')
        self.assertEqual(len(response.context['foods']),0)

    def test_launch_dates_editable_after_approval_without_unlocking_recipe(self):
        self.food.stage='approved'; self.food.save()
        response=self.client.post('/food/%s/' % self.food.pk,{'action':'launch_dates','production_date':'2026-01-01','market_launch_date':'2026-01-02'})
        self.assertEqual(response.status_code,302)
        self.food.refresh_from_db()
        self.assertEqual(self.food.market_launch_date,date(2026,1,2))
        self.assertEqual(self.food.stage,'approved')
        self.assertEqual(self.food.activities.count(),1)

    def test_launch_dates_require_owner_or_product_role(self):
        stranger=User.objects.create_user('stranger')
        self.client.force_login(stranger)
        self.assertEqual(self.client.post('/food/%s/' % self.food.pk,{'action':'launch_dates','production_date':'2026-01-01'}).status_code,403)

    def test_future_actual_launch_rejected(self):
        self.client.post('/food/%s/' % self.food.pk,{'action':'launch_dates','market_launch_date':'2099-01-01'})
        self.food.refresh_from_db()
        self.assertIsNone(self.food.market_launch_date)

    def setUp(self):
        self.user=User.objects.create_user('developer',password='test-password')
        self.food=Food.objects.create(name='Test bowl',owner=self.user,due=date.today(),batch_units=100,yield_percent=80,packaging=100,labor=50,overhead=25,selling_price=1000)
        supplier=Supplier.objects.create(name='Supplier')
        self.ingredient=Ingredient.objects.create(name='Rice',supplier=supplier,unit='kg',price=2000)
        RecipeLine.objects.create(food=self.food,ingredient=self.ingredient,quantity=10,unit_price=2000)
        self.client.force_login(self.user)
    def test_yield_and_cost(self):
        self.assertEqual(self.food.effective_units,80)
        self.assertEqual(self.food.unit_cost,Decimal(425))
        self.assertEqual(self.food.margin,Decimal('57.5'))
    def test_price_snapshot(self):
        self.ingredient.price=9999
        self.ingredient.save()
        self.assertEqual(self.food.unit_cost,425)
    def test_role_gate_and_handoff(self):
        url='/food/%s/' % self.food.pk
        self.assertEqual(self.client.post(url,{'action':'advance'}).status_code,403)
        self.user.groups.add(Group.objects.create(name='Product'))
        self.assertEqual(self.client.post(url,{'action':'advance'}).status_code,302)
        self.food.refresh_from_db()
        self.assertEqual(self.food.stage,'recipe')
        self.assertEqual(self.food.activities.count(),1)
    def test_approved_record_locked(self):
        self.food.stage='approved'; self.food.save()
        response=self.client.post('/food/%s/' % self.food.pk,{'action':'remove','line':self.food.lines.first().pk})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.food.lines.count(),1)
    def test_pages_api_and_export(self):
        for url in ['/','/food/%s/' % self.food.pk,'/ingredients/','/suppliers/','/food/new/','/api/foods/','/api/foods/%s/cost/' % self.food.pk,'/food/%s/?export=csv' % self.food.pk]:
            expected=403 if url=='/food/new/' else 200
            self.assertEqual(self.client.get(url).status_code,expected,url)
    def test_anonymous_denied(self):
        self.client.logout()
        self.assertEqual(self.client.get('/').status_code,302)
        self.assertEqual(self.client.get('/api/foods/').status_code,403)
    def test_invalid_quantity(self):
        response=self.client.post('/food/%s/' % self.food.pk,{'action':'add','ingredient':self.ingredient.pk,'quantity':'-1'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['lineform'].errors.as_data()['quantity'][0].code,'min_value')
        self.assertEqual(self.food.lines.count(),1)
    def test_final_cost_approval_requires_margin(self):
        self.food.stage='costing'; self.food.selling_price=100; self.food.save()
        self.user.groups.add(Group.objects.create(name='Finance'))
        self.client.post('/food/%s/' % self.food.pk,{'action':'advance'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.stage,'costing')
