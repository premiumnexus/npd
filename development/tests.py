from datetime import date
from decimal import Decimal
from unittest.mock import patch
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.contrib.auth.models import User,Group
from .models import Food,Supplier,Ingredient,RecipeLine

def valid_gate0():
    from .models import Gate0Option
    Gate0Option.objects.get_or_create(kind='subcategory',code='test-subtype',category='FF',defaults={'label':'Test subtype'})
    Gate0Option.objects.get_or_create(kind='segment',code='test-segment',defaults={'label':'Test segment'})
    return {
        'product_type':'new','product_name':'Test bowl','category':'FF','subcategory':'test-subtype',
        'product_role':'core','customer_segment':'test-segment','daypart':'lunch',
        'customer_need_evidence':'POS evidence','evidence_level':'B',
        'target_shelf_price':'5000','cu_margin':'30.0','vendor_rebate':'0','producer':'central_foods','vendor_margin':'20',
        'analog_skus_sales_target':[{'sku':'SKU1','units_per_store_day':'10'},{'sku':'SKU2','units_per_store_day':'12'}],
        'target_units_store_day':'15','store_scope':'all','store_count':'20',
        'raw_materials_supply_risk':'no','new_supplier':'no','seasonal_price_swing':'yes','moq':'100',
        'first_food_safety_risk':['milk'],'high_risk_inputs':['rice'],
        'first_capacity_check':'available','capacity_units_day':'500','day45_success_criteria':'15',
        'day45_writeoff_percent':'5','day45_margin_percent':'30','planned_launch_date':'2027-05-01',
    }

class DevelopmentTests(TestCase):
    def test_role_progress_follows_gate_reviews_and_configured_groups(self):
        from .role_progress import role_progress
        from .models import GateAccess
        self.food.stage='gate0';self.food.review_status='draft'
        rows=role_progress(self.food)
        self.assertIn('Category Manager (MD)',rows[0]['roles'])
        self.assertEqual([row['key'] for row in rows],['draft','manager','director'])
        self.assertEqual(rows[0]['state'],'current')
        self.assertTrue(rows[2]['conditional'])
        self.food.stage='gate2';self.food.review_status='qa'
        rows=role_progress(self.food)
        self.assertEqual([row['key'] for row in rows],['draft','qa','manager','director'])
        self.assertEqual([row['state'] for row in rows],['done','current','upcoming','upcoming'])
        self.assertIn('QA',rows[1]['roles'])
        self.food.review_status='director'
        self.assertEqual(role_progress(self.food)[-1]['state'],'current')
        self.food.completed=True
        self.assertTrue(all(row['state']=='done' for row in role_progress(self.food)))
        self.food.completed=False;self.food.review_status='draft'
        custom=Group.objects.create(name='Custom Gate 2 submitter')
        GateAccess.objects.filter(stage='gate2').update(can_submit=False)
        GateAccess.objects.create(stage='gate2',group=custom,can_submit=True)
        self.assertEqual(role_progress(self.food)[0]['roles'],[custom.name])

    def test_role_progress_launch_and_position_above_gate_navigation(self):
        from .role_progress import role_progress
        from django.utils import timezone
        from datetime import timedelta
        self.food.stage='launch';self.food.launched_at=timezone.now()-timedelta(days=8);self.food.save()
        rows=role_progress(self.food)
        self.assertFalse(rows[0]['locked']);self.assertTrue(rows[1]['locked'])
        self.assertIn('Food Science',rows[0]['roles'])
        self.assertIn('QA',rows[1]['roles'])
        self.food.launched_at=timezone.now()-timedelta(days=15)
        self.assertEqual(role_progress(self.food)[1]['state'],'current')
        response=self.client.get('/food/%s/?gate=gate0'%self.food.pk)
        self.assertEqual(response.status_code,200)
        html=response.content.decode()
        self.assertLess(html.index('steps role-progress'),html.index('aria-label="Gate navigation"'))
        self.assertIn('Food Science',response.context['role_progress'][0]['roles'])

    def test_gate2_real_vendor_price_example_and_saved_calculations(self):
        from .gate0 import save_brief
        from .gate2 import Gate2Form,initial_brief
        from decimal import ROUND_HALF_UP
        save_brief(self.food,{'target_shelf_price':9000,'cu_margin':30,'vendor_rebate':2,'vendor_margin':15})
        self.food.lines.all().delete()
        self.food.stage='gate2';self.food.packaging=350;self.food.save()
        for grams,yield_factor,price in [(200,'1',4000),(120,'.7',16000),(60,'.85',5000),(30,'1',8000)]:
            RecipeLine.objects.create(food=self.food,ingredient=self.ingredient,quantity=Decimal(grams)/1000,yield_factor=Decimal(yield_factor),unit_price=price)
        payload={'vendor_invoice_price':'5800','typed_cogs':'1','final_cogs_invoice_price':'1','front_margin_percent':'99','margin_gap_points':'99','implied_vendor_margin_percent':'99'}
        form=Gate2Form(payload,food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        for key,expected in [('front_margin_percent','29.1'),('margin_gap_points','0.9'),('implied_vendor_margin_percent','21.1')]:
            self.assertEqual(form.cleaned_data[key].quantize(Decimal('.1'),rounding=ROUND_HALF_UP),Decimal(expected))
            self.assertEqual(form.initial[key],expected)
            self.assertTrue(form.fields[key].disabled)
        self.assertEqual(form.cleaned_data['final_cogs_invoice_price'],self.food.unit_cost)
        self.assertNotIn('typed_cogs',form.fields)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        response=self.client.post('/food/%s/'%self.food.pk,dict(payload,action='gate2_save'))
        self.assertEqual(response.status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(Decimal(saved['front_margin_percent']),form.cleaned_data['front_margin_percent'])
        self.assertEqual(Decimal(saved['final_cogs_invoice_price']),self.food.unit_cost)

    def test_gate2_real_vendor_price_missing_zero_and_margin_floor(self):
        from .gate0 import save_brief
        from .gate2 import Gate2Form
        save_brief(self.food,{'target_shelf_price':1100,'cu_margin':30,'vendor_rebate':0,'vendor_margin':15})
        for invoice in ['600','700']:
            form=Gate2Form({'vendor_invoice_price':invoice},food=self.food)
            self.assertTrue(form.is_valid(),form.errors)
            self.assertEqual(form.cleaned_data['margin_gap_points'],0)
        form=Gate2Form({'vendor_invoice_price':'0'},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['front_margin_percent'],100)
        self.assertIsNone(form.cleaned_data['implied_vendor_margin_percent'])
        form=Gate2Form({},food=self.food)
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data['front_margin_percent'])
        self.assertIsNone(form.cleaned_data['margin_gap_points'])
        form=Gate2Form({'vendor_invoice_price':'-1'},food=self.food)
        self.assertFalse(form.is_valid())
        save_brief(self.food,{})
        form=Gate2Form({'vendor_invoice_price':'5800'},food=self.food)
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data['front_margin_percent'])
        self.assertIsNone(form.cleaned_data['implied_vendor_margin_percent'])

    def test_gate1_official_recipe_example_and_red_approval_route(self):
        from .models import Gate0
        from .gate1_typed import cost_comparison
        from .workflow import transition
        import json
        from decimal import ROUND_HALF_UP
        self.food.lines.all().delete()
        self.food.stage='gate1';self.food.packaging=350;self.food.save()
        Gate0.objects.create(development=self.food,cogs_limit=Decimal(9000)/Decimal('1.1')*Decimal('.7')*Decimal('.98')*Decimal('.85'))
        for grams,yield_factor,price,expected in [(200,'1',4000,800),(120,'.7',16000,2743),(60,'.85',5000,353),(30,'1',8000,240)]:
            line=RecipeLine.objects.create(food=self.food,ingredient=self.ingredient,quantity=Decimal(grams)/1000,yield_factor=Decimal(yield_factor),unit_price=price)
            self.assertEqual(line.cost.quantize(Decimal(1),rounding=ROUND_HALF_UP),expected)
        self.assertEqual(self.food.unit_cost.quantize(Decimal(1),rounding=ROUND_HALF_UP),4486)
        comparison=cost_comparison(self.food,'99999')
        self.assertEqual(comparison['cogs_status'],'Green')
        self.assertEqual(comparison['cogs_gap_percent'].quantize(Decimal('.1')),Decimal('-6.0'))
        self.assertEqual(comparison['send_to_director'],'No')
        self.food.packaging=1200;self.food.review_status='manager';self.food.save()
        self.assertEqual(cost_comparison(self.food,None)['cogs_status'],'Red')
        self.user.groups.add(Group.objects.get(name='Fresh Food Manager'))
        self.assertIsNone(transition(self.user,self.food,'approve',''))
        self.food.refresh_from_db()
        self.assertEqual(self.food.stage,'gate1');self.assertEqual(self.food.review_status,'director')

    def test_gate1_grams_yield_packaging_validation_and_boundaries(self):
        from .forms import Gate1LineForm
        from .gate1_typed import cost_comparison
        from .models import Gate0
        import json
        for value in ['0','.009','1.01','-1']:
            form=Gate1LineForm({'ingredient':self.ingredient.pk,'net_grams':'120','yield_factor':value})
            self.assertFalse(form.is_valid(),value)
        form=Gate1LineForm({'ingredient':self.ingredient.pk,'net_grams':'120','yield_factor':'.7','unit_price':'16000'})
        self.assertTrue(form.is_valid(),form.errors)
        line=form.save(commit=False);line.food=self.food;line.save()
        self.assertEqual(line.quantity,Decimal('.12'))
        self.assertEqual(line.cost,Decimal('.12')/Decimal('.7')*16000)
        self.food.lines.all().delete()
        Gate0.objects.create(development=self.food,cogs_limit=1000)
        for amount,status in [('1000','Green'),('1000.01','Amber'),('1050','Amber'),('1050.01','Red')]:
            self.assertEqual(cost_comparison(self.food,amount)['cogs_status'],status)
        self.food.stage='gate1';self.food.save()
        url='/food/%s/'%self.food.pk
        self.assertEqual(self.client.post(url,{'action':'gate1_packaging_save','packaging':'350'}).status_code,403)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.assertEqual(self.client.post(url,{'action':'gate1_packaging_save','packaging':'350'}).status_code,302)
        self.food.refresh_from_db();self.assertEqual(self.food.packaging,350)
        self.assertEqual(self.client.post(url,{'action':'gate1_packaging_save','packaging':'-1'}).status_code,200)

    def test_gate0_target_costing_example_precision_and_tampering(self):
        from .gate0 import Gate0Form,save_brief,initial_brief
        from decimal import ROUND_HALF_UP
        data={'target_shelf_price':'9000','cu_margin':'30','vendor_rebate':'2','vendor_margin':'15',
              'price_excl_vat':'1','max_invoice_price':'1','cogs_limit':'1','cu_total_margin':'1','vat_percent':'99'}
        form=Gate0Form(data)
        self.assertTrue(form.is_valid(),form.errors)
        expected={'price_excl_vat':'8182','max_invoice_price':'5727','cogs_limit':'4771','cu_total_margin':'31.4'}
        for key,value in expected.items():
            places=Decimal('0.1') if key=='cu_total_margin' else Decimal('1')
            self.assertEqual(form.cleaned_data[key].quantize(places,rounding=ROUND_HALF_UP),Decimal(value))
            self.assertTrue(form.fields[key].disabled)
        save_brief(self.food,form.cleaned_data)
        saved=initial_brief(self.food)
        self.assertEqual(Decimal(saved['vat_percent']),Decimal('10'))
        exact=Decimal('9000')/Decimal('1.1')*Decimal('.7')*Decimal('.98')*Decimal('.85')
        self.assertEqual(Decimal(saved['cogs_limit']),exact)
        self.assertEqual(Gate0Form(initial=saved).initial['cogs_limit'],'4771')

    def test_gate0_target_costing_optional_zero_and_admin_vat(self):
        from .gate0 import Gate0Form
        from .models import TargetCostingSettings
        form=Gate0Form({})
        self.assertTrue(form.is_valid(),form.errors)
        self.assertIsNone(form.cleaned_data['cogs_limit'])
        TargetCostingSettings.objects.all().update(vat_percent=20)
        form=Gate0Form({'target_shelf_price':'1200','cu_margin':'0','vendor_rebate':'0','vendor_margin':'0'})
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['cogs_limit'],Decimal('1000'))
        self.assertEqual(form.cleaned_data['cu_total_margin'],0)
        partial=Gate0Form({'cu_margin':'30','vendor_rebate':'2'})
        self.assertTrue(partial.is_valid(),partial.errors)
        self.assertEqual(partial.cleaned_data['cu_total_margin'],Decimal('31.4'))
        self.assertIsNone(partial.cleaned_data['price_excl_vat'])

    def test_launch_file_uploads_keep_history_downloads_and_time_locks(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import Activity
        self.food.stage='launch';self.food.launched_at=timezone.now()-timedelta(days=8);self.food.save()
        self.user.groups.add(Group.objects.get(name='Food Science'))
        url='/food/%s/'%self.food.pk
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            def upload(day=7,content=b'first report'):
                return self.client.post(url,{'action':'checkpoint_save','day':day,
                    'report':SimpleUploadedFile('quality.pdf',content,content_type='application/pdf')})
            self.assertEqual(upload(14).status_code,403)
            self.assertFalse(Activity.objects.filter(food=self.food,attachment_stage='launch').exists())
            self.assertEqual(upload().status_code,302)
            self.assertEqual(upload(content=b'revised report').status_code,302)
            files=Activity.objects.filter(food=self.food,attachment_slot='L7F8')
            self.assertEqual(files.count(),2)
            response=self.client.get(url)
            self.assertContains(response,'enctype="multipart/form-data"')
            self.assertContains(response,'type="file"',count=1)
            self.assertEqual(len(response.context['checkpoint_cards'][0]['upload_fields'][0]['files']),2)
            item=files.first()
            from django.urls import reverse
            download=self.client.get(reverse('download_attachment',args=[item.pk]))
            self.assertEqual(download.status_code,200)
            self.assertEqual(b''.join(download.streaming_content),b'revised report')
            download.close()
            self.food.launched_at=timezone.now()-timedelta(days=14);self.food.save()
            self.assertEqual(upload(14).status_code,302)
            self.assertTrue(Activity.objects.filter(food=self.food,attachment_slot='L14F10').exists())
            self.assertFalse(Activity.objects.filter(food=self.food,attachment_slot='L14F1').exists())

    def test_day7_role_fields_target_apsd_and_achievement_thresholds(self):
        from datetime import timedelta
        from django.utils import timezone
        from .gate0 import save_brief as save_gate0
        from .gate2 import save_brief as save_gate2
        save_gate0(self.food,{'day45_success_criteria':'12'})
        save_gate2(self.food,{'day45_target_confirmed':'changed','day45_units_store_day':'10'})
        self.food.stage='launch'; self.food.launched_at=timezone.now()-timedelta(days=8); self.food.save()
        url='/food/%s/' % self.food.pk
        self.user.groups.add(Group.objects.get(name='Food Science'))
        page=self.client.get(url)
        self.assertContains(page,'Day 7 – 7 дахь өдрийн шалгалт')
        self.assertContains(page,'type="file"',count=1)
        self.assertNotContains(page,'name="sample_weight"')
        form=page.context['checkpoint_cards'][0]['form']
        self.assertNotIn('complaints_count',form.fields)
        self.assertIn('complaints_count',page.context['checkpoint_cards'][1]['form'].fields)
        self.assertFalse(form.fields['checked_date'].disabled)
        self.assertFalse(form.fields['sample_result'].disabled)
        self.assertTrue(form.fields['actual_apsd'].disabled)
        self.assertTrue(form.fields['target_apsd'].disabled)
        self.assertEqual(form.initial['target_apsd'],'10')
        checked=timezone.localdate().isoformat()
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7,'checked_date':checked,'sample_result':'within','actual_apsd':'999'}).status_code,302)
        record=self.food.launch_checkpoints.get(day=7)
        self.assertEqual(record.checked_date.isoformat(),checked)
        self.assertIsNone(record.sales_snapshot)
        self.user.groups.clear(); self.user.groups.add(Group.objects.get(name='FF Planning'))
        for actual,percent,status in [('10','100.00','Green'),('9.99','99.90','Amber'),('8','80.00','Amber'),('7.99','79.90','Red'),('0','0.00','Red')]:
            response=self.client.post(url,{'action':'checkpoint_save','day':7,'actual_apsd':actual,'sample_result':'outside','checked_date':'2099-01-01','target_apsd':'1','achievement_percent':'999'})
            self.assertEqual(response.status_code,302)
            record.refresh_from_db()
            self.assertEqual(record.sample_result,'within')
            self.assertEqual(record.checked_date.isoformat(),checked)
            self.assertEqual(record.sales_snapshot,Decimal(actual))
            form=self.client.get(url).context['checkpoint_cards'][0]['form']
            self.assertEqual(form.achievement,{'percent':Decimal(percent),'status':status})
            self.assertEqual(form.initial['target_apsd'],'10')
        save_gate2(self.food,{'day45_target_confirmed':'changed','day45_units_store_day':'0'})
        self.assertIsNone(self.client.get(url).context['checkpoint_cards'][0]['form'].achievement['percent'])
        save_gate2(self.food,{'day45_target_confirmed':'same'})
        self.assertEqual(self.client.get(url).context['checkpoint_cards'][0]['form'].initial['target_apsd'],'12')
        from .models import GateAccess
        self.user.groups.add(Group.objects.get(name='Food Science'))
        GateAccess.objects.filter(stage='launch',group__name='Food Science').update(can_edit=False)
        form=self.client.get(url).context['checkpoint_cards'][0]['form']
        self.assertTrue(form.fields['checked_date'].disabled)
        self.assertFalse(form.fields['actual_apsd'].disabled)
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7,'actual_apsd':'8','sample_result':'outside','checked_date':'2099-01-01'}).status_code,302)
        record.refresh_from_db()
        self.assertEqual(record.sample_result,'within')
        self.assertEqual(record.checked_date.isoformat(),checked)

    def test_day7_action_required_only_for_conditional_or_outside_results(self):
        from datetime import timedelta
        from django.utils import timezone
        self.food.stage='launch'; self.food.launched_at=timezone.now()-timedelta(days=8); self.food.save()
        self.user.groups.add(Group.objects.get(name='Food Science'))
        url='/food/%s/' % self.food.pk
        with tempfile.TemporaryDirectory() as media,self.settings(MEDIA_ROOT=media):
            for result in ['conditional','outside']:
                response=self.client.post(url,{'action':'checkpoint_save','day':7,'sample_result':result,'action_plan':'  ','report':SimpleUploadedFile('invalid.pdf',b'not saved')})
                self.assertEqual(response.status_code,200)
                form=response.context['checkpoint_cards'][0]['form']
                self.assertIn('action_plan',form.errors)
                self.assertTrue(form.action_required)
                self.assertFalse(self.food.launch_checkpoints.exists())
                self.assertFalse(self.food.activities.filter(attachment_stage='launch').exists())
            payload={'action':'checkpoint_save','day':7,'sample_result':'conditional','action_plan':'Adjust cooling; Food Science; tomorrow','report':SimpleUploadedFile('report.pdf',b'quality report')}
            self.assertEqual(self.client.post(url,payload).status_code,302)
            record=self.food.launch_checkpoints.get(day=7)
            self.assertEqual(record.sample_result,'conditional')
            self.assertEqual(record.within_tolerance,'no')
            self.assertEqual(record.action_plan,'Adjust cooling; Food Science; tomorrow')
            self.assertEqual(self.food.activities.filter(attachment_slot='L7F8').count(),1)
            self.assertTrue(self.client.get(url).context['checkpoint_cards'][0]['form'].action_required)
            self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7,'sample_result':'within','action_plan':'irrelevant'}).status_code,302)
            record.refresh_from_db()
            self.assertEqual(record.action_plan,'')
            self.assertFalse(self.client.get(url).context['checkpoint_cards'][0]['form'].action_required)

    def test_day7_supplied_dates_results_and_apsd_are_validated(self):
        from datetime import timedelta
        from django.utils import timezone
        self.food.stage='launch'; self.food.launched_at=timezone.now()-timedelta(days=8); self.food.save()
        self.user.is_superuser=True; self.user.save()
        url='/food/%s/' % self.food.pk
        for key,value in [('checked_date','not-a-date'),('sample_result','unknown'),('actual_apsd','-1'),('actual_apsd','1.001')]:
            response=self.client.post(url,{'action':'checkpoint_save','day':7,key:value})
            self.assertEqual(response.status_code,200)
            self.assertIn(key,response.context['checkpoint_cards'][0]['form'].errors)
        self.assertFalse(self.food.launch_checkpoints.exists())
        self.food.review_status='manager'; self.food.save()
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7,'actual_apsd':'10'}).status_code,403)

    def test_day14_roles_complaints_and_apsd_do_not_overwrite_day7(self):
        from datetime import timedelta
        from django.utils import timezone
        from .gate2 import save_brief
        from .models import GateAccess
        save_brief(self.food,{'day45_target_confirmed':'changed','day45_units_store_day':'10'})
        self.food.stage='launch'; self.food.launched_at=timezone.now()-timedelta(days=15); self.food.save()
        self.user.groups.add(Group.objects.get(name='Food Science'))
        url='/food/%s/' % self.food.pk
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7,'sample_result':'within','checked_date':'2026-11-01'}).status_code,302)
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':14,'sample_result':'within','checked_date':'2026-11-08','complaints_count':'999','actual_apsd':'999'}).status_code,302)
        day14=self.food.launch_checkpoints.get(day=14)
        self.assertIsNone(day14.complaints_count)
        self.assertIsNone(day14.sales_snapshot)
        self.user.groups.clear(); self.user.groups.add(Group.objects.get(name='QA'))
        form=self.client.get(url).context['checkpoint_cards'][1]['form']
        self.assertFalse(form.fields['complaints_count'].disabled)
        self.assertTrue(form.fields['checked_date'].disabled)
        self.assertTrue(form.fields['sample_result'].disabled)
        self.assertTrue(form.fields['actual_apsd'].disabled)
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':14,'complaints_count':'0'}).status_code,302)
        day14.refresh_from_db()
        self.assertEqual(day14.complaints_count,0)
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':14,'complaints_count':'3','sample_result':'outside','actual_apsd':'999','checked_date':'2099-01-01'}).status_code,302)
        day14.refresh_from_db()
        self.assertEqual(day14.complaints_count,3)
        self.assertEqual(day14.sample_result,'within')
        self.assertEqual(day14.checked_date.isoformat(),'2026-11-08')
        self.assertIsNone(day14.sales_snapshot)
        for invalid in ['-1','1.5','2147483648']:
            response=self.client.post(url,{'action':'checkpoint_save','day':14,'complaints_count':invalid})
            self.assertEqual(response.status_code,200)
            self.assertIn('complaints_count',response.context['checkpoint_cards'][1]['form'].errors)
        self.user.groups.clear(); self.user.groups.add(Group.objects.get(name='FF Planning'))
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':14,'actual_apsd':'8','complaints_count':'999','sample_result':'outside'}).status_code,302)
        day14.refresh_from_db()
        self.assertEqual(day14.complaints_count,3)
        self.assertEqual(day14.sales_snapshot,Decimal('8'))
        self.assertEqual(day14.sample_result,'within')
        form=self.client.get(url).context['checkpoint_cards'][1]['form']
        self.assertEqual(form.initial['target_apsd'],'10')
        self.assertEqual(form.achievement,{'percent':Decimal('80.00'),'status':'Amber'})
        day7=self.food.launch_checkpoints.get(day=7)
        self.assertEqual(day7.checked_date.isoformat(),'2026-11-01')
        self.assertIsNone(day7.sales_snapshot)
        self.assertIsNone(day7.complaints_count)
        self.user.groups.add(Group.objects.get(name='QA'))
        GateAccess.objects.filter(group__name='QA',stage='launch').update(can_edit=False)
        self.assertTrue(self.client.get(url).context['checkpoint_cards'][1]['form'].fields['complaints_count'].disabled)

    def test_day14_conditional_actions_and_report_history_are_independent(self):
        from datetime import timedelta
        from django.utils import timezone
        self.food.stage='launch'; self.food.launched_at=timezone.now()-timedelta(days=15); self.food.save()
        self.user.groups.add(Group.objects.get(name='Food Science'))
        url='/food/%s/' % self.food.pk
        with tempfile.TemporaryDirectory() as media,self.settings(MEDIA_ROOT=media):
            self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7,'sample_result':'within','report':SimpleUploadedFile('day7.pdf',b'day7')}).status_code,302)
            for result in ['conditional','outside']:
                response=self.client.post(url,{'action':'checkpoint_save','day':14,'sample_result':result,'report':SimpleUploadedFile('blocked.pdf',b'blocked')})
                self.assertEqual(response.status_code,200)
                cards=response.context['checkpoint_cards']
                self.assertIn('action_plan',cards[1]['form'].errors)
                self.assertFalse(cards[0]['form'].errors)
                self.assertFalse(self.food.launch_checkpoints.filter(day=14).exists())
            for name,body in [('day14.pdf',b'first'),('day14-revised.pdf',b'revised')]:
                response=self.client.post(url,{'action':'checkpoint_save','day':14,'sample_result':'conditional','action_plan':'Recheck; Food Science; tomorrow','report':SimpleUploadedFile(name,body)})
                self.assertEqual(response.status_code,302)
            page=self.client.get(url)
            self.assertContains(page,'Day 14 – 14 дэх өдрийн шалгалт')
            self.assertContains(page,'14 дэх өдрийн чанарын шалгалтын тайлан, зураг')
            self.assertContains(page,'type="file"',count=2)
            self.assertEqual(len(page.context['checkpoint_cards'][0]['upload_fields'][0]['files']),1)
            self.assertEqual(len(page.context['checkpoint_cards'][1]['upload_fields'][0]['files']),2)
            activity=self.food.activities.get(attachment_name='day14-revised.pdf')
            self.assertEqual(activity.attachment_slot,'L14F10')
            activity.full_clean()
            download=self.client.get('/attachments/%s/' % activity.pk)
            self.assertEqual(b''.join(download.streaming_content),b'revised')
            download.close()
            self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':14,'sample_result':'within','action_plan':'irrelevant'}).status_code,302)
            self.assertEqual(self.food.launch_checkpoints.get(day=14).action_plan,'')
            self.user.groups.clear()
            page=self.client.get(url)
            self.assertNotContains(page,'type="file"')
            self.assertContains(page,'day14-revised.pdf')
            self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':14,'complaints_count':'1'}).status_code,403)

    def test_day45_after_late_launch_reentry_keeps_chronological_timing(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import GateTransition
        from .launch import open_gate3_if_due
        now=timezone.now()
        self.food.stage='launch';self.food.launched_at=now-timedelta(days=60);self.food.save()
        reentry=now-timedelta(days=2)
        GateTransition.objects.create(food=self.food,action='approve',from_stage='gate2',to_stage='launch',to_review='draft',occurred_at=reentry)
        self.assertTrue(open_gate3_if_due(self.food,now))
        self.assertEqual(self.food.gate3_opened_at,reentry)
        self.assertEqual(self.food.gate_transitions.get(action='auto_open').occurred_at,reentry)

    def test_day7_and_day14_unlock_at_exact_elapsed_time(self):
        from datetime import datetime,timedelta,timezone as dt_timezone
        start=datetime(2026,11,1,8,30,tzinfo=dt_timezone.utc)
        self.food.stage='launch';self.food.launched_at=start;self.food.save()
        self.user.groups.add(Group.objects.get(name='Food Science'))
        url='/food/%s/'%self.food.pk
        payload={'action':'checkpoint_save','day':'7','checked_date':'2026-11-08','sample_result':'within'}
        with patch('django.utils.timezone.now',return_value=start+timedelta(days=7)-timedelta(seconds=1)):
            self.client.force_login(self.user)
            self.assertEqual(self.client.post(url,payload).status_code,403)
            self.assertFalse(self.client.get(url).context['checkpoint_cards'][0]['editable'])
        with patch('django.utils.timezone.now',return_value=start+timedelta(days=7)):
            self.client.force_login(self.user)
            self.assertEqual(self.client.post(url,payload).status_code,302)
            cards=self.client.get(url).context['checkpoint_cards']
            self.assertTrue(cards[0]['editable'])
            self.assertEqual(len(cards),2)
            self.assertFalse(cards[1]['editable'])
            self.assertEqual(self.client.post(url,{**payload,'day':'14'}).status_code,403)
        with patch('django.utils.timezone.now',return_value=start+timedelta(days=14)-timedelta(seconds=1)):
            self.client.force_login(self.user)
            self.assertEqual(self.client.post(url,{**payload,'day':'14','complaints_count':'2','complaints_details':'Packaging concerns'}).status_code,403)
        with patch('django.utils.timezone.now',return_value=start+timedelta(days=14)):
            self.client.force_login(self.user)
            self.assertEqual(self.client.post(url,{**payload,'day':'14','checked_date':'2026-11-15'}).status_code,302)
            self.assertTrue(self.client.get(url).context['checkpoint_cards'][1]['editable'])
        self.assertEqual(self.food.launch_checkpoints.get(day=7).sample_result,'within')
        self.assertEqual(self.food.launch_checkpoints.get(day=14).sample_result,'within')
        from .launch import CheckpointForm
        with self.assertRaises(ValueError): CheckpointForm(day=21)

    def test_launch_checkpoint_role_ownership_and_superuser_time_lock(self):
        from datetime import timedelta
        from django.utils import timezone
        self.food.stage='launch';self.food.launched_at=timezone.now()-timedelta(days=15);self.food.save()
        url='/food/%s/'%self.food.pk
        for role in ['Food Science','FF Planning','QA','Category Manager (MD)']:
            self.user.groups.clear();self.user.groups.add(Group.objects.get(name=role))
            for day in [7,14]:
                expected=302 if role in ['Food Science','FF Planning']+(['QA'] if day==14 else []) else 403
                self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':day,'sample_result':'within'}).status_code,expected,(role,day))
        self.food.launched_at=timezone.now();self.food.save()
        self.user.is_superuser=True;self.user.save()
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':'7'}).status_code,403)
        self.assertEqual(self.client.post(url,{'action':'submit'}).status_code,302)
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'launch')

    def test_gate3_opens_automatically_at_day45_without_duplicate_events(self):
        from datetime import datetime,timedelta,timezone as dt_timezone
        start=datetime(2026,11,1,8,30,tzinfo=dt_timezone.utc)
        self.food.stage='launch';self.food.launched_at=start;self.food.save()
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        url='/food/%s/'%self.food.pk
        with patch('django.utils.timezone.now',return_value=start+timedelta(days=45)-timedelta(seconds=1)):
            self.client.force_login(self.user)
            response=self.client.get(url+'?gate=gate3')
            self.assertFalse(response.context['editable'])
            self.assertEqual(self.client.post(url+'?gate=gate3',{'action':'gate3_save','sales_vs_target':'10'}).status_code,403)
        with patch('django.utils.timezone.now',return_value=start+timedelta(days=45)):
            self.client.force_login(self.user)
            response=self.client.get(url)
            self.food.refresh_from_db()
            self.assertEqual(self.food.stage,'gate3')
            self.assertTrue(response.context['editable'])
            self.assertEqual(self.food.gate3_opened_at,start+timedelta(days=45))
            self.assertEqual(self.client.post(url,{'action':'gate3_save','sales_vs_target':'10'}).status_code,302)
            self.client.get(url)
        event=self.food.gate_transitions.get(action='auto_open')
        self.assertIsNone(event.actor)
        self.assertEqual(event.occurred_at,start+timedelta(days=45))

    def test_early_gate3_even_if_manually_selected_is_locked_and_unknown_launch_not_invented(self):
        from datetime import timedelta
        from django.utils import timezone
        self.user.is_superuser=True;self.user.save()
        self.food.stage='gate3';self.food.launched_at=timezone.now()-timedelta(days=10);self.food.save()
        url='/food/%s/'%self.food.pk
        self.assertFalse(self.client.get(url).context['editable'])
        self.assertEqual(self.client.post(url,{'action':'gate3_save','sales_vs_target':'10'}).status_code,403)
        self.food.stage='launch';self.food.launched_at=None;self.food.save()
        response=self.client.get(url)
        self.assertFalse(response.context['launch_schedule']['day7_open'])
        self.assertIsNone(response.context['launch_schedule']['day7_at'])
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7}).status_code,403)

    def test_launch_anchor_is_not_reset_by_returns_or_reentry(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import Activity
        from .timing import record_transition
        start=timezone.now()-timedelta(days=20)
        self.food.stage='launch';self.food.launched_at=start;self.food.save()
        activity=Activity.objects.create(food=self.food,actor=self.user,text='Re-enter launch')
        record_transition(self.food,self.user,'approve','gate2','director',activity)
        self.food.refresh_from_db()
        self.assertEqual(self.food.launched_at,start)

    def test_gate_timestamps_and_review_clocks_follow_handoffs_not_edits(self):
        from datetime import datetime,timedelta,timezone as dt_timezone
        from .timing import gate_timing
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        start=datetime(2026,11,5,0,0,tzinfo=dt_timezone.utc)
        with patch('django.utils.timezone.now',return_value=start):
            response=self.client.post('/food/new/',valid_gate0())
        food=Food.objects.get(pk=int(response.url.rstrip('/').split('/')[-1]))
        url='/food/%s/'%food.pk
        with patch('django.utils.timezone.now',return_value=start+timedelta(hours=2)):
            self.client.post(url,{'action':'submit'})
        food.refresh_from_db()
        timing=gate_timing(food,now=start+timedelta(hours=3))
        self.assertEqual(timing['current']['entered_at'],start)
        self.assertEqual(timing['current']['elapsed'],'3 цаг')
        self.assertEqual(timing['step_elapsed'],'1 цаг')
        self.user.groups.add(Group.objects.get(name='Fresh Food Manager'))
        with patch('django.utils.timezone.now',return_value=start+timedelta(hours=4)):
            self.client.post(url,{'action':'approve'})
        food.refresh_from_db()
        timing=gate_timing(food,now=start+timedelta(hours=5))
        self.assertEqual(timing['gates'][0]['elapsed'],'4 цаг')
        self.assertEqual(timing['current']['entered_at'],start+timedelta(hours=4))
        self.assertEqual(timing['current']['elapsed'],'1 цаг')
        self.assertEqual(timing['events'][0].previous_elapsed,'2 цаг')
        count=food.gate_transitions.count()
        self.client.post(url,{'action':'comment','comment':'A note must not reset the clock'})
        self.assertEqual(food.gate_transitions.count(),count)

    def test_gate_timing_unknown_history_is_not_invented_and_reads_are_public_to_team(self):
        from .timing import gate_timing
        timing=gate_timing(self.food)
        self.assertIsNone(timing['current'].get('entered_at'))
        self.assertEqual(timing['current']['elapsed'],'')
        self.assertEqual(self.client.get('/food/%s/?gate=gate3'%self.food.pk).status_code,200)
        self.assertEqual(self.food.gate_transitions.count(),0)
        self.client.post('/food/%s/'%self.food.pk,{'action':'submit'})
        self.assertEqual(self.food.gate_transitions.count(),0)

    def test_gate_timing_returns_keep_visits_and_completion_stops_clock(self):
        from datetime import datetime,timedelta,timezone as dt_timezone
        from .models import GateTransition
        from .timing import gate_timing
        start=datetime(2026,11,1,tzinfo=dt_timezone.utc)
        for hours,old,new,action,completed in [(0,'','gate1','created',False),(2,'gate1','gate2','approve',False),(3,'gate2','gate1','return',False),(5,'gate1','gate2','approve',False),(7,'gate2','gate3','approve',False),(9,'gate3','gate3','approve',True)]:
            GateTransition.objects.create(food=self.food,from_stage=old,to_stage=new,action=action,to_review='draft',completed=completed,occurred_at=start+timedelta(hours=hours))
        self.food.stage='gate3';self.food.completed=True;self.food.save()
        timing=gate_timing(self.food,now=start+timedelta(days=10))
        self.assertEqual(timing['gates'][1]['visit_count'],2)
        self.assertEqual(timing['gates'][1]['elapsed'],'2 цаг')
        self.assertEqual(timing['current']['elapsed'],'2 цаг')
        self.assertFalse(timing['current']['running'])
        self.assertIsNone(timing['step_started'])

    def test_gate3_derived_launch_sales_margin_and_writeoff_comparisons(self):
        from .gate0 import save_brief as save_gate0
        from .gate2 import save_brief as save_gate2
        from .gate3 import Gate3Form
        save_gate0(self.food,{'planned_launch_date':'2027-04-01','target_units_store_day':'10','day45_margin_percent':'30','day45_writeoff_percent':'5'})
        save_gate2(self.food,{'launch_date':'2027-04-10'})
        form=Gate3Form({'sales_vs_target':'12','margin_after_writeoff':'25','writeoff_percent_of_cost':'7','launch_days_late':'999'},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['launch_days_late'],9)
        self.assertTrue(form.delay_reason_recommended)
        self.assertEqual(form.cleaned_data['sales_difference'],2)
        self.assertEqual(form.cleaned_data['sales_attainment_percent'],120)
        self.assertEqual(form.cleaned_data['margin_difference'],-5)
        self.assertEqual(form.cleaned_data['writeoff_difference'],2)

    def test_gate3_inputs_optional_and_entered_types_validated(self):
        from .gate3 import Gate3Form
        form=Gate3Form({},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertTrue(all(not field.required for field in form.fields.values()))
        for key,value in [('sales_vs_target','-1'),('writeoff_percent_of_cost','101'),('availability','101'),('complaints','1.5'),('complaints_closed','maybe'),('root_cause','made-up')]:
            form=Gate3Form({key:value},food=self.food)
            self.assertFalse(form.is_valid(),(key,value))
            self.assertIn(key,form.errors)
        self.assertTrue(Gate3Form({'margin_after_writeoff':'-10','customer_feedback':'4.5','complaints':'0','root_cause':'none'},food=self.food).is_valid())

    def test_launch_checkpoints_feed_readonly_gate3_sample_fields(self):
        from .gate3 import Gate3Form
        from django.utils import timezone
        from datetime import timedelta
        self.food.stage='launch'; self.food.launched_at=timezone.now()-timedelta(days=15); self.food.save()
        url='/food/%s/'%self.food.pk
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':'7','within_tolerance':'yes'}).status_code,403)
        self.user.groups.add(Group.objects.get(name='Food Science'))
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7,'sample_result':'within'}).status_code,302)
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':14,'sample_result':'outside','action_plan':'Replace sample; Food Science; tomorrow'}).status_code,302)
        form=Gate3Form({'shelf_samples_day7_day14':'no','day14_sample_within_tolerance':'yes'},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['shelf_samples_day7_day14'],'yes')
        self.assertEqual(form.cleaned_data['day14_sample_within_tolerance'],'no')
        self.food.stage='gate3'; self.food.save()
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        self.assertEqual(self.client.post(url,{'action':'checkpoint_save','day':7}).status_code,403)

    def test_gate3_handover_checklist_recomputed_from_sources(self):
        from .gate2 import save_brief as save_gate2
        from .gate3 import Gate3Form
        self.food.lines.all().delete()
        form=Gate3Form({'handover_pack_complete':'yes'},food=self.food)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['handover_pack_complete'],'no')
        save_gate2(self.food,{'typed_cogs':'1500','final_technology_transfer_document':'Signed version 1','label_checked':'yes','marketing_plan':'Launch channels'})
        form=Gate3Form({'handover_pack_complete':'no'},food=self.food)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['handover_pack_complete'],'yes')

    def test_lessons_page_displays_stop_change_tags_and_root_cause_labels(self):
        from .gate3 import save_brief
        save_brief(self.food,{'lesson_stop':'Stop over-ordering','lesson_change':'Change store allocation','lesson_tags':['vendor','issue'],'root_cause':'availability','root_cause_evidence':'Out of stock days'})
        response=self.client.get('/lessons/')
        self.assertContains(response,'Stop over-ordering')
        self.assertContains(response,'Change store allocation')
        self.assertContains(response,'Out of stock days')

    def test_gate2_types_optional_and_validate_entered_values(self):
        from .gate2 import Gate2Form
        form=Gate2Form({},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertTrue(all(not field.required for field in form.fields.values()))
        for key,value in [('trial_yield_percent','101'),('trial_taste_score','6'),('mass_trial_result','-1'),('allocation','2.5'),('lab_results_approved_shelf_life','unknown'),('label_checked','maybe'),('launch_date','not-a-date')]:
            form=Gate2Form({key:value},food=self.food)
            self.assertFalse(form.is_valid(),(key,value))
            self.assertIn(key,form.errors)
        form=Gate2Form({'cold_chain_temperature':'-18','barcode_system_registration':'00123456789','label_checked':'yes'},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['barcode_system_registration'],'00123456789')

    def test_gate2_derived_cost_version_and_launch_delay_are_readonly(self):
        from .gate2 import Gate2Form
        from .gate0 import save_brief
        from .gate1 import save_brief as save_gate1
        save_brief(self.food,{'planned_launch_date':'2027-04-01'})
        self.food.recipe_version=4; self.food.save()
        save_gate1(self.food,{'typed_cogs':'1500'})
        form=Gate2Form({'launch_date':'2027-04-11','original_launch_date':'2099-01-01','final_recipe_version':'999','launch_delay_days':'999'},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['final_recipe_version'],4)
        self.assertEqual(form.cleaned_data['launch_delay_days'],10)
        self.assertEqual(form.cleaned_data['original_launch_date'],'2027-04-01')
        self.assertEqual(form.cleaned_data['final_cogs_invoice_price'],20100)
        self.assertIsNone(form.cleaned_data['front_margin_percent'])
        form=Gate2Form({'typed_cogs':'1700','launch_date':'2027-03-30'},food=self.food)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['final_cogs_invoice_price'],20100)
        self.assertEqual(form.cleaned_data['launch_delay_days'],-2)

    def test_gate2_launch_dates_autofill_and_delay_persist_across_leap_day(self):
        from .gate0 import save_brief as save_gate0
        from .gate2 import save_brief as save_gate2,initial_brief
        save_gate0(self.food,{'planned_launch_date':'2028-02-28'})
        self.food.stage='gate2'; self.food.save()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        save_gate2(self.food,{'original_launch_date':'2030-01-01','launch_delay_days':999,'launch_date':'2028-03-01'})
        url='/food/%s/' % self.food.pk
        form=self.client.get(url).context['gate2form']
        self.assertEqual(form.initial['original_launch_date'],'2028-02-28')
        self.assertEqual(form.initial['launch_delay_days'],2)
        self.assertTrue(form.fields['original_launch_date'].disabled)
        self.assertTrue(form.fields['launch_delay_days'].disabled)
        for actual,expected in [('2028-02-27',-1),('2028-02-28',0),('2028-03-01',2),('','')]:
            response=self.client.post(url,{'action':'gate2_save','launch_date':actual,'original_launch_date':'2099-01-01','launch_delay_days':'999'})
            self.assertEqual(response.status_code,302)
            saved=initial_brief(self.food)
            self.assertEqual(saved['original_launch_date'],'2028-02-28')
            self.assertEqual(saved['launch_delay_days'],expected)
        save_gate0(self.food,{})
        self.assertEqual(self.client.post(url,{'action':'gate2_save','launch_date':'2028-03-01'}).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(saved['original_launch_date'],'')
        self.assertEqual(saved['launch_delay_days'],'')

    def test_gate2_same_day45_targets_copied_from_gate0_or_changed_optionally(self):
        from .gate0 import save_brief
        from .gate2 import Gate2Form
        save_brief(self.food,{'day45_success_criteria':'15','day45_writeoff_percent':'3','day45_margin_percent':'30'})
        initial=Gate2Form(food=self.food)
        self.assertEqual(initial.initial['day45_target_confirmed'],'same')
        self.assertEqual([initial.initial[key] for key in ['day45_units_store_day','day45_writeoff_percent','day45_margin_percent']],['15','3','30'])
        self.assertTrue(initial.fields['day45_change_reason'].frontend_hidden)
        form=Gate2Form({'day45_target_confirmed':'same','day45_units_store_day':'999'},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['day45_units_store_day'],15)
        self.assertEqual(form.cleaned_data['day45_writeoff_percent'],3)
        form=Gate2Form({'day45_target_confirmed':'changed','day45_units_store_day':'20'},food=self.food)
        self.assertTrue(form.is_valid())  # Reasons remain optional per user request.
        self.assertEqual(form.cleaned_data['day45_units_store_day'],20)
        legacy=Gate2Form(initial={'day45_units_store_day':'20','day45_writeoff_percent':'3','day45_margin_percent':'30'},food=self.food)
        self.assertEqual(legacy.initial['day45_target_confirmed'],'changed')
        self.assertEqual(legacy.initial['day45_units_store_day'],'20')

    def test_gate2_day45_changed_targets_and_reason_survive_save_and_return_to_gate0(self):
        from .gate0 import save_brief as save_gate0
        from .gate2 import initial_brief
        save_gate0(self.food,{'day45_success_criteria':'15','day45_writeoff_percent':'3','day45_margin_percent':'30'})
        self.food.stage='gate2'; self.food.save()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        url='/food/%s/' % self.food.pk
        page=self.client.get(url)
        self.assertContains(page,'Gate 0-ийн зорилт хэвээр / Өөрчилсөн')
        self.assertNotContains(page,'45 хоногийн зорилтын сонголт')
        mode=page.context['gate2form'].fields['day45_target_confirmed']
        self.assertEqual(list(mode.choices),[('same','Gate 0-ийн зорилт хэвээр'),('changed','Өөрчилсөн')])
        changed={'action':'gate2_save','day45_target_confirmed':'changed','day45_units_store_day':'20','day45_writeoff_percent':'4','day45_margin_percent':'28','day45_change_reason':'Updated sales plan'}
        self.assertEqual(self.client.post(url,changed).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(saved['day45_change_reason'],'Updated sales plan')
        page=self.client.get(url)
        form=page.context['gate2form']
        self.assertEqual(form.initial['day45_units_store_day'],'20')
        self.assertFalse(form.fields['day45_change_reason'].frontend_hidden)
        self.assertFalse(form.fields['day45_units_store_day'].disabled)
        invalid=self.client.post(url,{**changed,'allocation':'2.5'})
        self.assertEqual(invalid.status_code,200)
        self.assertFalse(invalid.context['gate2form'].fields['day45_change_reason'].frontend_hidden)
        self.assertEqual(self.client.post(url,{**changed,'day45_target_confirmed':'same','day45_units_store_day':'999'}).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(saved['day45_target_confirmed'],'same')
        self.assertEqual([Decimal(saved[key]) for key in ['day45_units_store_day','day45_writeoff_percent','day45_margin_percent']],[15,3,30])
        self.assertEqual(saved['day45_change_reason'],'')
        self.assertTrue(self.client.get(url).context['gate2form'].fields['day45_change_reason'].frontend_hidden)

    def test_gate2_quality_ranges_and_marketing_dates_consistent_when_entered(self):
        from .gate2 import Gate2Form
        form=Gate2Form({'quality_tolerance_baseline':'150','quality_weight_min':'140','quality_weight_max':'160','marketing_start_date':'2027-04-01','marketing_end_date':'2027-04-10'},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        form=Gate2Form({'quality_weight_min':'160','quality_weight_max':'140','marketing_start_date':'2027-04-10','marketing_end_date':'2027-04-01'},food=self.food)
        self.assertFalse(form.is_valid())
        self.assertIn('quality_weight_max',form.errors)
        self.assertIn('marketing_end_date',form.errors)

    def test_gate1_types_allow_blanks_but_validate_supplied_scores_counts_dates(self):
        from .gate1 import Gate1Form
        empty=Gate1Form({},food=self.food)
        self.assertTrue(empty.is_valid(),empty.errors)
        self.assertTrue(all(not field.required for field in empty.fields.values()))
        for key,value in [('tasting_score','0'),('tasting_score','5.1'),('taster_count','4'),('consumer_liking','10'),('consumer_test','1.5'),('consumer_would_buy_percent','101'),('shelf_life_result_due','not-a-date'),('material_certificate','maybe')]:
            form=Gate1Form({key:value},food=self.food)
            self.assertFalse(form.is_valid(),(key,value))
            self.assertIn(key,form.errors)
        form=Gate1Form({'tasting_score':'5','taster_count':'5','consumer_liking':'9','consumer_would_buy_percent':'100','shelf_life_result_due':'2027-01-15'},food=self.food)
        self.assertTrue(form.is_valid(),form.errors)

    def test_gate1_cogs_uses_editor_or_manual_and_configured_status_thresholds(self):
        from .gate1 import Gate1Form
        from .models import Gate0,COGSComparisonPolicy
        import json
        Gate0.objects.create(development=self.food,cogs_limit=20000)
        form=Gate1Form({},food=self.food)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['estimated_cogs_vs_limit'],20100)
        self.assertEqual(form.cleaned_data['cogs_status'],'Amber')
        COGSComparisonPolicy.objects.create(amber_band_percent=10)
        self.food.lines.all().delete()
        for amount,status in [('20000','Green'),('21000','Amber'),('23000','Red')]:
            form=Gate1Form({'typed_cogs':amount,'cogs_status':'Green','estimated_cogs_vs_limit':'1'},food=self.food)
            self.assertTrue(form.is_valid(),form.errors)
            self.assertEqual(form.cleaned_data['cogs_status'],status)
            self.assertEqual(form.cleaned_data['estimated_cogs_vs_limit'],Decimal(amount))
        form=Gate1Form({'typed_cogs':'23000'},food=self.food)
        self.assertTrue(form.is_valid())  # Reasons/actions remain optional.

    def test_gate1_recipe_version_from_editor_and_manual_fallback(self):
        from .gate1 import Gate1Form
        self.food.stage='gate1'; self.food.save()
        form=Gate1Form({'recipe_version_internal_tasting':'3'},food=self.food)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['recipe_version_internal_tasting'],3)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.client.post('/food/%s/'%self.food.pk,{'action':'gate1_line_add','ingredient':self.ingredient.pk,'quantity':'0.1'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.recipe_version,1)
        form=Gate1Form({'recipe_version_internal_tasting':'999'},food=self.food)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['recipe_version_internal_tasting'],1)
        self.assertTrue(form.fields['recipe_version_internal_tasting'].disabled)

    def test_gate1_material_repeat_rows_and_packaging_enum(self):
        from .gate1 import Gate1Form
        from .models import PackagingType
        PackagingType.objects.create(code='test-pack',name='Test pack')
        data={'raw_material_spec_price_moq_second_source':[{'material':'Chicken','spec_written':'yes','price_kg':'14500','moq':'10','second_source':'no'}],'packaging_label_concept':'test-pack','pack_size':'150g','material_certificate':'yes'}
        form=Gate1Form(data,food=self.food)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['raw_material_spec_price_moq_second_source'][0]['price_kg'],Decimal(14500))
        data['packaging_label_concept']='unknown-pack'
        self.assertFalse(Gate1Form(data,food=self.food).is_valid())

    def test_gate1_fridge_checks_dates_and_qa_values_roundtrip(self):
        from .gate1 import Gate1Form,save_brief,initial_brief
        payload={'fridge_0_texture':'Firm','fridge_0_result':'pass','fridge_72_taste':'Good','fridge_check_72h':'pass','fridge_check_date':'2027-02-02','qa_requirements_issued':'yes','process_flow_ccp_issued':'no','shelf_life_result_due':'2027-02-03'}
        form=Gate1Form(payload,food=self.food)
        self.assertEqual([key for key,field in form.fields.items() if field.gate_number=='1.6'],['fridge_check_72h','fridge_check_date'])
        self.assertTrue(form.is_valid(),form.errors)
        save_brief(self.food,form.cleaned_data)
        saved=initial_brief(self.food)
        self.assertEqual(saved['fridge_check_72h'],'pass')
        self.assertEqual(saved['fridge_check_date'],'2027-02-02')
        self.assertEqual(saved['shelf_life_result_due'],'2027-02-03')
        self.assertTrue(Gate1Form(saved,food=self.food).is_valid())
        self.assertFalse(Gate1Form({'fridge_check_date':'2027-02-30'},food=self.food).is_valid())

    def test_gate0_partial_drafts_allowed_but_identity_required_for_submission(self):
        from .gate0 import Gate0Form,initial_brief
        for data in [{},{'product_type':'improvement'},{'store_scope':'cluster'},{'evidence_level':'C'},{'competitor_benchmark':[{'product':'Only a name'}]}]:
            form=Gate0Form(data)
            self.assertTrue(form.is_valid(),form.errors)
            self.assertTrue(all(not field.required for field in form.fields.values()))
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        response=self.client.post('/food/new/',{})
        self.assertEqual(response.status_code,302)
        food=Food.objects.get(pk=int(response.url.rstrip('/').split('/')[-1]))
        self.assertEqual(initial_brief(food)['product_type'],'')
        self.client.post('/food/%s/'%food.pk,{'action':'submit'})
        food.refresh_from_db()
        self.assertEqual(food.review_status,'draft')
        self.assertIsNone(food.gate0_submitted_at)

    def test_gate0_each_identity_field_required_but_launch_date_optional(self):
        from .gate0 import Gate0Form,save_brief
        data={key:value for key,value in valid_gate0().items() if key in Gate0Form.required_keys}
        self.assertTrue(Gate0Form(data,submission=True).is_valid())
        self.assertTrue(Gate0Form({**data,'product_type':'improvement'},submission=True).is_valid())
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        for key in Gate0Form.required_keys:
            with self.subTest(field=key):
                incomplete={**data,key:''}
                form=Gate0Form(incomplete,submission=True)
                self.assertFalse(form.is_valid())
                self.assertIn(key,form.errors)
                save_brief(self.food,incomplete)
                self.client.post('/food/%s/'%self.food.pk,{'action':'submit'})
                self.food.refresh_from_db()
                self.assertEqual(self.food.review_status,'draft')
                self.assertIsNone(self.food.gate0_submitted_at)
        save_brief(self.food,data)
        self.client.post('/food/%s/'%self.food.pk,{'action':'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status,'manager')

    def test_gate0_identity_group_order_numbering_and_required_stars(self):
        from .gate0 import Gate0Form
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        response=self.client.get('/food/new/')
        html=response.content.decode()
        group=html.split('<fieldset class="gate0-identity"',1)[1].split('</fieldset>',1)[0]
        self.assertEqual(group.count('class="required-star"'),5)
        form=response.context['form']
        positions=[group.index('id="id_%s"'%key) for key in Gate0Form.identity_keys]
        self.assertEqual(positions,sorted(positions))
        for index,key in enumerate(Gate0Form.identity_keys,1):
            self.assertEqual(form.fields[key].gate_number,f'1.{index}')
        self.assertNotIn('id="id_existing_sku"',group)

    def test_gate0_approval_cannot_advance_incomplete_legacy_brief(self):
        self.food.review_status='manager';self.food.save()
        self.user.groups.add(Group.objects.get(name='Fresh Food Manager'))
        self.client.post('/food/%s/'%self.food.pk,{'action':'approve'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.stage,'gate0')
        self.assertEqual(self.food.review_status,'manager')

    def test_gate0_customer_section_order_numbers_and_required_stars(self):
        from .gate0 import Gate0Form
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        for url in ['/food/new/','/food/%s/'%self.food.pk]:
            with self.subTest(url=url):
                response=self.client.get(url)
                html=response.content.decode()
                group=html.split('<fieldset class="gate0-identity gate0-customer"',1)[1].split('</fieldset>',1)[0]
                self.assertIn('<legend>Хэрэглэгч ба нотолгоо</legend>',group)
                self.assertIn('<small><em>Хэнд, хэзээ, яагаад?</em></small>',group)
                self.assertEqual(group.count('class="required-star"'),2)
                form=response.context['form'] if url=='/food/new/' else response.context['gate0form']
                positions=[]
                for index,key in enumerate(Gate0Form.customer_keys,1):
                    self.assertEqual(form.fields[key].gate_number,f'2.{index}')
                    self.assertEqual(form.fields[key].gate_required,key in ('customer_segment','daypart'))
                    positions.append(group.index('for="id_%s"'%key))
                self.assertEqual(positions,sorted(positions))
                self.assertLess(html.index('<legend>Бүтээгдэхүүн</legend>'),html.index('<legend>Хэрэглэгч ба нотолгоо</legend>'))
                self.assertIn('name="evidence-0-file"',group)
                self.assertNotIn('name="competitor_benchmark-0-product"',group)

    def test_gate0_customer_requirements_block_submit_and_legacy_approval(self):
        from .gate0 import Gate0Form,save_brief
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'),Group.objects.get(name='Fresh Food Manager'))
        complete={key:value for key,value in valid_gate0().items() if key in Gate0Form.required_keys}
        self.assertTrue(Gate0Form(complete,submission=True).is_valid())
        for key in ('customer_segment','daypart'):
            for blank in ('',[]):
                if key=='customer_segment' and blank==[]: continue
                with self.subTest(field=key,blank=blank):
                    incomplete={**complete,key:blank}
                    self.assertTrue(Gate0Form(incomplete).is_valid())
                    validation=Gate0Form(incomplete,submission=True)
                    self.assertFalse(validation.is_valid())
                    self.assertIn(key,validation.errors)
                    self.food.review_status='draft';self.food.save()
                    save_brief(self.food,incomplete)
                    self.client.post('/food/%s/'%self.food.pk,{'action':'submit'})
                    self.food.refresh_from_db()
                    self.assertEqual(self.food.review_status,'draft')
                    self.food.review_status='manager';self.food.save()
                    self.client.post('/food/%s/'%self.food.pk,{'action':'approve'})
                    self.food.refresh_from_db()
                    self.assertEqual(self.food.stage,'gate0')
                    self.assertEqual(self.food.review_status,'manager')

    def test_gate0_returned_legacy_brief_can_fill_missing_route(self):
        from django.utils import timezone
        from .gate0 import Gate0Form,initial_brief,save_brief
        self.food.gate0_submitted_at=timezone.now();self.food.save()
        data=valid_gate0()
        form=Gate0Form(data,initial=initial_brief(self.food),food=self.food,submission=True)
        self.assertFalse(form.fields['product_type'].disabled)
        self.assertTrue(form.is_valid(),form.errors)
        save_brief(self.food,form.cleaned_data)
        locked=Gate0Form(initial=initial_brief(self.food),food=self.food)
        self.assertTrue(locked.fields['product_type'].disabled)

    def test_gate0_numeric_bounds_and_whole_tugrik_price(self):
        from .gate0 import Gate0Form
        data=valid_gate0()
        self.assertTrue(Gate0Form(data,submission=True).is_valid())
        for key,value in [('target_shelf_price','0'),('target_shelf_price','1.5'),('cu_margin','60.1'),('cu_margin','30.12'),('vendor_rebate','30.01'),('vendor_margin','60.01'),('store_count','0')]:
            form=Gate0Form({**data,key:value},submission=True)
            self.assertFalse(form.is_valid(),(key,value))
            self.assertIn(key,form.errors)
        for key,value in [('cu_margin','60.0'),('vendor_rebate','0'),('vendor_margin','60')]:
            self.assertTrue(Gate0Form({**data,key:value},submission=True).is_valid(),(key,value))

    def test_gate0_improvement_details_optional_but_enum_values_validated(self):
        from .gate0 import Gate0Form
        data=valid_gate0()
        data['product_type']='improvement'
        form=Gate0Form(data,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        data.update(existing_sku='EXISTING-SKU',improvement_reasons=['R01'],improvement_reason='Change flavour because of customer feedback')
        self.assertTrue(Gate0Form(data,submission=True).is_valid())
        data['improvement_reasons']=['invented-code']
        self.assertFalse(Gate0Form(data,submission=True).is_valid())

    def test_gate0_repeat_rows_and_submission_counts(self):
        from .gate0 import Gate0Form
        data=valid_gate0()
        for count in [0,1,2,3,4]:
            form=Gate0Form({**data,'analog_skus_sales_target':[{'sku':'SKU%s'%n,'units_per_store_day':'10'} for n in range(count)]},submission=True)
            self.assertEqual(form.is_valid(),count<=3)
            if count>3: self.assertIn('analog_skus_sales_target',form.errors)
        form=Gate0Form({**data,'competitor_benchmark':[{'product':'Rival','price':'5000','weight_g':'150'}],'cannibalisation':[{'sku':'SKU3','sales_taken_percent':'20.0'}]},submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        form=Gate0Form({**data,'cannibalisation':[{'sku':'SKU3','sales_taken_percent':'101'}]},submission=True)
        self.assertFalse(form.is_valid())
        self.assertIn('cannibalisation',form.errors)

    def test_gate0_html_repeat_row_roundtrip(self):
        from .gate0 import Gate0Form
        data={'product_type':'new','competitor_benchmark-TOTAL_FORMS':'2','competitor_benchmark-0-product':'Rival A','competitor_benchmark-0-price':'5000','competitor_benchmark-0-weight_g':'150','competitor_benchmark-1-product':'Rival B','competitor_benchmark-1-DELETE':'1'}
        form=Gate0Form(data)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(len(form.cleaned_data['competitor_benchmark']),1)
        self.assertEqual(form.cleaned_data['competitor_benchmark'][0]['product'],'Rival A')

    def test_gate0_first_submission_locks_route_even_after_return(self):
        from .gate0 import save_brief,initial_brief
        save_brief(self.food,valid_gate0())
        url='/food/%s/'%self.food.pk
        self.act_as('Category Manager (MD)','submit')
        self.assertIsNotNone(self.food.gate0_submitted_at)
        self.act_as('Fresh Food Manager','return','Correct the brief')
        self.user.groups.clear(); self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        response=self.client.get(url)
        self.assertTrue(response.context['gate0form'].fields['product_type'].disabled)
        self.assertTrue(response.context['gate0form'].fields['cogs_limit'].disabled)
        self.client.post(url,{'action':'gate0_save','product_type':'improvement','product_name':'Updated name'})
        self.assertEqual(initial_brief(self.food)['product_type'],'new')

    def test_gate0_configuration_dependency_and_nonblocking_date_warning(self):
        from .gate0 import Gate0Form
        from django.utils import timezone
        from datetime import timedelta
        data=valid_gate0()
        data['planned_launch_date']=timezone.localdate()+timedelta(days=10)
        form=Gate0Form(data,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertTrue(form.launch_warning)
        data['category']='ISF'
        form=Gate0Form(data,submission=True)
        self.assertFalse(form.is_valid())
        self.assertIn('subcategory',form.errors)

    def test_gate0_preserves_legacy_free_text_during_conversion(self):
        from .models import Gate0
        from .gate0 import Gate0Form,initial_brief,save_brief
        import json
        from .gate_storage import save_gate
        save_gate(0,self.food,{'product_name':'Old name','cu_margin':'TBD','competitor_benchmark':'Old competitor notes'})
        form=Gate0Form(initial=initial_brief(self.food),food=self.food)
        self.assertTrue(form.legacy_values)
        save_brief(self.food,valid_gate0())
        data=initial_brief(self.food)
        self.assertEqual(data['_legacy_free_text']['competitor_benchmark'],'Old competitor notes')
        self.assertEqual(Decimal(data['cu_margin']),Decimal('30.0'))

    def test_recipes_lists_launched_products_and_expands_ingredients(self):
        self.food.stage='launch'; self.food.save()
        Food.objects.create(name='Completed product',owner=self.user,stage='gate3',completed=True)
        Food.objects.create(name='Unlaunched product',owner=self.user,stage='gate2')
        response=self.client.get('/recipes/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Test bowl')
        self.assertContains(response,'Completed product')
        self.assertNotContains(response,'Unlaunched product')
        self.assertContains(response,'Rice')
        self.assertContains(response,'<details',count=2)
        self.assertContains(response,'?gate=gate1')
        self.assertNotContains(response,'name="quantity"')
        self.assertEqual(len(self.client.get('/recipes/?q=Completed').context['foods']),1)

    def test_recipe_library_requires_login_and_has_empty_state(self):
        self.assertEqual(len(self.client.get('/recipes/').context['foods']),0)
        self.client.logout()
        self.assertEqual(self.client.get('/recipes/').status_code,302)

    def test_every_signed_in_user_can_browse_gates_without_changing_workflow(self):
        from .models import STAGES
        from .gate1 import save_brief
        save_brief(self.food,{'consumer_test':'Saved consumer results'})
        for key,_ in STAGES:
            response=self.client.get('/food/%s/?gate=%s' % (self.food.pk,key))
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.context['view_stage'],key)
            self.assertContains(response,'?gate=gate3')
            if key != 'gate0': self.assertFalse(response.context['editable'])
        response=self.client.get('/food/%s/?gate=gate1' % self.food.pk)
        self.assertContains(response,'Saved consumer results')
        self.assertTrue(response.context['gate1form'].fields['consumer_test'].disabled)
        self.food.refresh_from_db()
        self.assertEqual(self.food.stage,'gate0')
        self.assertEqual(self.food.activities.count(),0)

    def test_other_gate_view_is_readonly_even_for_superuser(self):
        self.user.is_superuser=True; self.user.save()
        url='/food/%s/?gate=gate1' % self.food.pk
        self.assertFalse(self.client.get(url).context['editable'])
        self.assertEqual(self.client.post(url,{'action':'gate0_save','product_name':'Changed'}).status_code,403)
        self.assertEqual(self.client.get('/food/%s/?gate=invalid' % self.food.pk).status_code,404)
        self.assertTrue(self.client.get('/food/%s/' % self.food.pk).context['editable'])

    def test_gate1_per_product_ingredient_cost(self):
        self.food.stage='gate1'; self.food.save()
        self.food.lines.all().delete()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        url='/food/%s/' % self.food.pk
        self.client.post(url,{'action':'gate1_line_add','ingredient':self.ingredient.pk,'quantity':'0.1','unit_price':'14500'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.unit_cost,Decimal('1550'))
        line=self.food.lines.get()
        self.client.post(url,{'action':'gate1_line_update','line':line.pk,'ingredient':self.ingredient.pk,'quantity':'0.2','unit_price':'14500'})
        self.assertEqual(self.food.unit_cost,Decimal('3000'))
        self.client.post(url,{'action':'gate1_line_add','ingredient':self.ingredient.pk,'quantity':'0.05'})
        self.assertEqual(self.food.unit_cost,Decimal('3100'))
        self.food.batch_units=999; self.food.yield_percent=1; self.food.packaging=999; self.food.labor=999; self.food.overhead=999; self.food.save()
        self.assertEqual(self.food.unit_cost,Decimal('3999'))
        response=self.client.get('/api/foods/%s/cost/' % self.food.pk)
        self.assertEqual(response.json()['unit_cost'],'3999.00')
        self.assertNotIn('batch_units',response.json())

    def test_gate2_cogs_status_matches_gate0_limit_and_is_derived(self):
        import json
        from .gate2 import Gate2Form,initial_brief
        from .models import Gate0,COGSComparisonPolicy
        self.food.stage='gate2'; self.food.packaging=0; self.food.save()
        line=self.food.lines.get()
        line.quantity=Decimal('.1'); line.save()
        brief=Gate0.objects.create(development=self.food,cogs_limit=1000)
        url='/food/%s/' % self.food.pk
        for price,status,label in [('10000','Green','Ногоон'),('10000.10','Amber','Шар'),('10500','Amber','Шар'),('10500.10','Red','Улаан')]:
            with self.subTest(status=status,price=price):
                line.unit_price=Decimal(price); line.save()
                page=self.client.get(url)
                self.assertEqual(page.context['gate2form'].initial['cogs_status'],status)
                self.assertEqual(page.context['gate2form'].initial['cogs_limit'],Decimal('1000'))
                self.assertContains(page,'data-cogs-status="%s"' % status)
                self.assertContains(page,'value="%s"' % label)
                self.assertContains(page,'COGS төлөв:')
        COGSComparisonPolicy.objects.create(amber_band_percent=10)
        line.unit_price=Decimal('11000'); line.save()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.assertEqual(self.client.post(url,{'action':'gate2_save','cogs_status':'Green','cogs_limit':'1','cogs_gap_percent':'0'}).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(saved['cogs_status'],'Amber')
        self.assertEqual(Decimal(saved['cogs_limit']),Decimal('1000'))
        self.assertEqual(Decimal(saved['cogs_gap_percent']),Decimal('10'))
        for gate in ['gate1','gate2']:
            self.assertContains(self.client.get(url+'?gate='+gate),'value="Шар"')
        brief.cogs_limit=None; brief.save(update_fields=['cogs_limit'])
        self.assertEqual(Gate2Form(food=self.food).initial['cogs_status'],'Хүлээгдэж байна')
        self.assertContains(self.client.get(url),'data-cogs-status="Pending"')

    def test_gate2_recipe_edits_update_cost_version_and_activity(self):
        from .gate2 import initial_brief
        self.food.stage='gate2'; self.food.recipe_version=3; self.food.save()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        url='/food/%s/' % self.food.pk
        page=self.client.get(url)
        self.assertContains(page,'2.2 · Жорын COGS')
        self.assertContains(page,'value="gate2_line_add"')
        self.assertContains(page,'data-option-stage="gate2"')
        self.assertNotContains(page,'value="gate1_line_add"')
        line=self.food.lines.get()
        response=self.client.post(url,{'action':'gate2_line_update','line':line.pk,'ingredient':self.ingredient.pk,'net_grams':'120','yield_factor':'.75','unit_price':'3000'})
        self.assertEqual(response.status_code,302)
        self.food.refresh_from_db()
        self.assertEqual(self.food.unit_cost,Decimal('580'))
        self.assertEqual(self.food.recipe_version,4)
        response=self.client.post(url,{'action':'gate2_line_add','ingredient':self.ingredient.pk,'net_grams':'80','yield_factor':'1','unit_price':'2000'})
        self.assertEqual(response.status_code,302)
        added=self.food.lines.exclude(pk=line.pk).get()
        self.food.refresh_from_db()
        self.assertEqual(self.food.unit_cost,Decimal('740'))
        self.assertEqual(self.food.recipe_version,5)
        self.assertEqual(self.client.post(url,{'action':'gate2_packaging_save','packaging':'250'}).status_code,302)
        self.food.refresh_from_db()
        self.assertEqual(self.food.unit_cost,Decimal('890'))
        self.assertEqual(self.food.recipe_version,6)
        self.assertEqual(self.client.post(url,{'action':'gate2_line_remove','line':added.pk}).status_code,302)
        self.food.refresh_from_db()
        self.assertEqual(self.food.unit_cost,Decimal('730'))
        self.assertEqual(self.food.recipe_version,7)
        page=self.client.get(url)
        self.assertEqual(page.context['gate2form'].initial['final_cogs_invoice_price'],'730')
        self.assertEqual(page.context['gate2form'].initial['final_recipe_version'],7)
        self.assertEqual(self.food.activities.filter(text__startswith='Gate 2').count(),4)
        self.assertEqual(self.client.post(url,{'action':'gate2_save','final_cogs_invoice_price':'1','final_recipe_version':'999'}).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(Decimal(saved['final_cogs_invoice_price']),Decimal('730'))
        self.assertEqual(saved['final_recipe_version'],7)
        self.assertEqual(self.client.get('/api/foods/%s/cost/' % self.food.pk).json()['unit_cost'],'730.00')

    def test_gate2_recipe_edits_respect_permissions_validation_and_record_scope(self):
        self.food.stage='gate2'; self.food.recipe_version=3; self.food.save()
        url='/food/%s/' % self.food.pk
        line=self.food.lines.get()
        payloads=[{'action':'gate2_line_add','ingredient':self.ingredient.pk,'net_grams':'100'},
                  {'action':'gate2_line_update','line':line.pk,'ingredient':self.ingredient.pk,'net_grams':'100'},
                  {'action':'gate2_line_remove','line':line.pk},
                  {'action':'gate2_packaging_save','packaging':'250'}]
        for payload in payloads:
            self.assertEqual(self.client.post(url,payload).status_code,403)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        for changed in [{'net_grams':'-1'},{'yield_factor':'0'},{'unit_price':'-1'}]:
            response=self.client.post(url,{**payloads[0],**changed})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['ingredient_form'].errors)
            self.assertContains(response,'value="gate2_line_add"')
        self.assertTrue(self.client.post(url,{'action':'gate2_packaging_save','packaging':'-1'}).context['packaging_form'].errors)
        other=Food.objects.create(name='Other recipe',owner=self.user,stage='gate2')
        other_line=RecipeLine.objects.create(food=other,ingredient=self.ingredient,quantity=1,unit_price=2000)
        for payload in payloads[1:3]:
            self.assertEqual(self.client.post(url,{**payload,'line':other_line.pk}).status_code,404)
        for payload in payloads:
            self.assertEqual(self.client.post(url+'?gate=gate1',payload).status_code,403)
        for status in ['qa','manager','director']:
            self.food.review_status=status; self.food.save()
            for payload in payloads:
                self.assertEqual(self.client.post(url,payload).status_code,403)
            self.assertNotContains(self.client.get(url),'data-recipe-add')
        self.food.refresh_from_db()
        self.assertEqual(self.food.recipe_version,3)
        self.assertEqual(self.food.unit_cost,Decimal('20100'))
        self.assertEqual(self.food.lines.count(),1)
        other_line.refresh_from_db()
        self.assertEqual(other_line.quantity,1)
        self.assertFalse(self.food.activities.exists())
        self.food.review_status='draft'; self.food.save()
        for stage in ['gate0','gate1','launch','gate3']:
            self.food.stage=stage; self.food.save()
            for payload in payloads:
                self.assertEqual(self.client.post(url,payload).status_code,403)

    def test_gate1_calculator_validation_and_permissions(self):
        self.food.stage='gate1'; self.food.save()
        url='/food/%s/' % self.food.pk
        payload={'action':'gate1_line_add','ingredient':self.ingredient.pk,'quantity':'-1','unit_price':'14500'}
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        response=self.client.post(url,payload)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context['ingredient_form'].errors)
        self.assertEqual(self.food.lines.count(),1)
        for name in ['batch_units','yield_percent','labor','overhead']:
            self.assertNotContains(response,'name="%s"' % name)
        self.assertEqual(self.client.post(url,{'action':'gate1_cost_save'}).status_code,403)
        self.food.review_status='manager'; self.food.save()
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.food.stage='gate2'; self.food.review_status='draft'; self.food.save()
        self.assertEqual(self.client.post(url,payload).status_code,403)

    def test_gate3_file_slots_history_permissions_and_completion(self):
        from .models import Gate3File
        from django.utils import timezone
        from datetime import timedelta
        self.food.launched_at=timezone.now()-timedelta(days=60)
        self.food.save(update_fields=['launched_at'])
        from .gate3 import FILE_SLOTS
        self.food.stage='gate3'; self.food.save()
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        url='/food/%s/' % self.food.pk
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                for key,_ in FILE_SLOTS:
                    response=self.client.post(url,{'action':'slot_upload','slot':key,'slot_file':SimpleUploadedFile('review.csv',b'review')})
                    self.assertEqual(response.status_code,302)
                    self.assertEqual(Gate3File.objects.filter(development=self.food,slot_code=key).count(),1)
                self.client.post(url,{'action':'slot_upload','slot':'G3-F1','slot_file':SimpleUploadedFile('revised.xlsx',b'revised')})
                response=self.client.get(url)
                self.assertEqual(len(response.context['gate3slots']),3)
                self.assertEqual(len(response.context['gate3slots'][0]['files']),2)
                self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G2-F1'}).status_code,403)
                for status,completed in [('manager',False),('draft',True)]:
                    self.food.review_status=status; self.food.completed=completed; self.food.save()
                    self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G3-F1'}).status_code,403)
                self.user.groups.clear()
                response=self.client.get(url)
                self.assertContains(response,'revised.xlsx')
                self.assertNotContains(response,'name="slot_file"')
                uploaded=self.food.gate3_files.get(original_filename='revised.xlsx')
                response=self.client.get('/attachments/%s/' % uploaded.activity_id)
                self.assertEqual(response.status_code,200)
                self.assertEqual(b''.join(response.streaming_content),b'revised')
                response.close()

    def test_gate3_fields_save_and_lock_after_submission_and_completion(self):
        from django.utils import timezone
        from datetime import timedelta
        self.food.launched_at=timezone.now()-timedelta(days=60)
        self.food.save(update_fields=['launched_at'])
        from .gate3 import initial_brief
        self.food.stage='gate3'; self.food.save()
        url='/food/%s/' % self.food.pk
        payload={'action':'gate3_save','sales_vs_target':'15','root_cause':'quality','lesson_card':'Keep good packaging','complaints':'2'}
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        response=self.client.get(url)
        self.assertContains(response,'id_handover_pack_complete')
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(initial_brief(self.food)['sales_vs_target'],'15')
        self.assertEqual(initial_brief(self.food)['root_cause'],'quality')
        self.assertEqual(self.food.activities.count(),1)
        self.client.post(url,{'action':'submit'})
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.assertTrue(self.client.get(url).context['gate3form'].fields['sales_vs_target'].disabled)
        self.food.completed=True; self.food.review_status='draft'; self.food.save()
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.food.completed=False; self.food.stage='gate2'; self.food.save()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.assertNotContains(self.client.get(url),'id_handover_pack_complete')

    def test_gate2_file_slots_and_review_lock(self):
        from django.urls import reverse
        from .gate2 import available_file_slots
        from .models import Gate2File
        self.food.stage='gate2'; self.food.save()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        url='/food/%s/' % self.food.pk
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                for key,_ in available_file_slots(self.food):
                    response=self.client.post(url,{'action':'slot_upload','slot':key,'slot_file':SimpleUploadedFile('report.pdf',b'report')})
                    self.assertEqual(response.status_code,302)
                    if key in ['G2-F12','G2-F13']:
                        self.assertEqual(self.food.activities.filter(attachment_slot=key,attachment_stage='gate2').count(),1)
                    else:
                        self.assertEqual(Gate2File.objects.filter(development=self.food,slot_code=key).count(),1)
                self.client.post(url,{'action':'slot_upload','slot':'G2-F11','slot_file':SimpleUploadedFile('final.xlsx',b'final costing')})
                response=self.client.get(url)
                self.assertEqual(len(response.context['gate2slots']),12)
                costing=next(slot for slot in response.context['gate2slots'] if slot['key']=='G2-F11')
                self.assertEqual(len(costing['files']),2)
                self.assertContains(response,'final.xlsx')
                self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G1-F1'}).status_code,403)
                self.client.post(url,{'action':'submit'})
                self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G2-F1'}).status_code,403)
                self.user.groups.clear()
                response=self.client.get(url)
                self.assertContains(response,'report.pdf')
                self.assertNotContains(response,'name="slot_file"')
                uploaded=Gate2File.objects.get(development=self.food,original_filename='final.xlsx')
                response=self.client.get(reverse('download_gate2_file',args=[uploaded.pk]))
                self.assertEqual(response.status_code,200)
                self.assertEqual(b''.join(response.streaming_content),b'final costing')
                response.close()

    def test_gate2_quality_standard_replaces_text_and_is_available_in_launch(self):
        from datetime import timedelta
        from django.utils import timezone
        self.food.stage='gate2'; self.food.save()
        url='/food/%s/' % self.food.pk
        payload={'action':'slot_upload','slot':'G2-F13'}
        with tempfile.TemporaryDirectory() as media,self.settings(MEDIA_ROOT=media):
            self.assertEqual(self.client.post(url,{**payload,'slot_file':SimpleUploadedFile('blocked.pdf',b'blocked')}).status_code,403)
            self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
            page=self.client.get(url)
            self.assertContains(page,'<span class="field-number">2.10</span> Чанарын стандарт',html=True)
            self.assertContains(page,'id="file-G2-F13"',count=1)
            for key in ['quality_texture_target','quality_texture_range','quality_taste_target','quality_taste_range']:
                self.assertNotIn(key,page.context['gate2form'].fields)
                self.assertNotContains(page,'name="%s"' % key)
            html=page.content.decode()
            self.assertLess(html.index('id="id_quality_weight_max"'),html.index('id="file-G2-F13"'))
            self.assertLess(html.index('id="file-G2-F13"'),html.index('id="id_day45_target_confirmed"'))
            for name,body in [('standard.pdf',b'first'),('standard-v2.pdf',b'revised')]:
                self.assertEqual(self.client.post(url,{**payload,'slot_file':SimpleUploadedFile(name,body)}).status_code,302)
            activity=self.food.activities.get(attachment_name='standard-v2.pdf')
            activity.full_clean()
            self.food.review_status='qa'; self.food.save()
            self.assertEqual(self.client.post(url,{**payload,'slot_file':SimpleUploadedFile('locked.pdf',b'locked')}).status_code,403)
            self.assertNotContains(self.client.get(url),'id="file-G2-F13"')
            self.food.stage='launch'; self.food.review_status='draft'; self.food.launched_at=timezone.now()-timedelta(days=15); self.food.save()
            self.user.groups.add(Group.objects.get(name='Food Science'))
            page=self.client.get(url)
            self.assertTrue(all(len(card['quality_standards'])==2 for card in page.context['checkpoint_cards']))
            self.assertContains(page,'standard-v2.pdf')
            self.assertNotContains(page,'Бүтцийн зорилт / хүрээ')
            self.assertNotContains(page,'Амтын зорилт / хүрээ')
            self.assertContains(page,'type="file"',count=2)
            download=self.client.get('/attachments/%s/' % activity.pk)
            self.assertEqual(b''.join(download.streaming_content),b'revised')
            download.close()

    def test_gate2_isf_manual_visibility_upload_history_and_permissions(self):
        from .gate0 import save_brief as save_gate0
        save_gate0(self.food,{'category':'FF'})
        self.food.stage='gate2'; self.food.save()
        url='/food/%s/' % self.food.pk
        page=self.client.get(url)
        self.assertNotContains(page,'for="file-G2-F12"')
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                save_gate0(self.food,{'category':'ISF'})
                # Gate 0's saved category is authoritative, even if the summary differs.
                self.food.category='FF'; self.food.save()
                payload={'action':'slot_upload','slot':'G2-F12'}
                self.assertEqual(self.client.post(url,{**payload,'slot_file':SimpleUploadedFile('blocked.pdf',b'blocked')}).status_code,403)
                self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
                page=self.client.get(url)
                self.assertContains(page,'<span class="field-number">2.12</span> ISF Manual',html=True)
                self.assertContains(page,'id="file-G2-F12"',count=1)
                html=page.content.decode()
                self.assertLess(html.index('id="id_launch_date_change_reason"'),html.index('id="file-G2-F12"'))
                self.assertLess(html.index('id="file-G2-F12"'),html.index('value="gate2_save"'))
                self.assertLess(html.index('id="file-G2-F12"'),html.index('class="gate0-file-slots"'))
                for name,body in [('manual.pdf',b'first'),('manual-revised.pdf',b'revised')]:
                    self.assertEqual(self.client.post(url,{**payload,'slot_file':SimpleUploadedFile(name,body)}).status_code,302)
                activity=self.food.activities.get(attachment_name='manual-revised.pdf')
                activity.full_clean()
                self.assertEqual(activity.attachment_stage,'gate2')
                page=self.client.get(url)
                manual=next(slot for slot in page.context['gate2slots'] if slot['key']=='G2-F12')
                self.assertEqual(len(manual['files']),2)
                self.food.review_status='qa'; self.food.save()
                self.assertEqual(self.client.post(url,{**payload,'slot_file':SimpleUploadedFile('locked.pdf',b'locked')}).status_code,403)
                page=self.client.get(url)
                self.assertContains(page,'manual-revised.pdf')
                self.assertNotContains(page,'id="file-G2-F12"')
                download=self.client.get('/attachments/%s/' % activity.pk)
                self.assertEqual(b''.join(download.streaming_content),b'revised')
                download.close()
                self.food.review_status='draft'; self.food.save()
                save_gate0(self.food,{'category':'FF'})
                self.assertNotContains(self.client.get(url),'for="file-G2-F12"')
                self.assertEqual(self.client.post(url,{**payload,'category':'ISF','slot_file':SimpleUploadedFile('wrong-category.pdf',b'wrong')}).status_code,403)
                self.assertEqual(self.food.activities.filter(attachment_slot='G2-F12').count(),2)

    def test_gate2_fields_save_and_lock_for_ordered_review(self):
        from .gate2 import initial_brief
        self.food.stage='gate2'; self.food.save()
        url='/food/%s/' % self.food.pk
        payload={'action':'gate2_save','mass_trial_result':'10.5','typed_cogs':'1200','launch_date':'2027-05-15','lab_results_approved_shelf_life':'pass'}
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        response=self.client.get(url)
        self.assertContains(response,'id_day45_target_confirmed')
        self.assertContains(response,'id_launch_date')
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(initial_brief(self.food)['launch_date'],'2027-05-15')
        self.assertEqual(Decimal(initial_brief(self.food)['final_cogs_invoice_price']),Decimal('20100'))
        self.assertEqual(self.food.activities.count(),1)
        self.client.post(url,{'action':'submit'})
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.assertTrue(self.client.get(url).context['gate2form'].fields['lab_results_approved_shelf_life'].disabled)
        self.food.stage='gate1'; self.food.review_status='draft'; self.food.save()
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.assertNotContains(self.client.get(url),'id_day45_target_confirmed')

    def test_gate1_file_slots_upload_history_and_access(self):
        from django.urls import reverse
        from .gate1 import FILE_SLOTS
        from .models import Gate1File
        self.food.stage='gate1'; self.food.save()
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        url='/food/%s/' % self.food.pk
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                for key,_ in FILE_SLOTS:
                    response=self.client.post(url,{'action':'slot_upload','slot':key,'slot_file':SimpleUploadedFile('evidence.xlsx',b'evidence')})
                    self.assertEqual(response.status_code,302)
                    if key=='G1-F10':
                        self.assertEqual(self.food.activities.filter(attachment_slot=key,attachment_stage='gate1').count(),1)
                    else:
                        self.assertEqual(Gate1File.objects.filter(development=self.food,slot_code=key).count(),1)
                self.client.post(url,{'action':'slot_upload','slot':'G1-F9','slot_file':SimpleUploadedFile('revised.xlsx',b'new version')})
                response=self.client.get(url)
                self.assertEqual(len(response.context['gate1slots']),10)
                slots={slot['key']:slot for slot in response.context['gate1slots']}
                self.assertEqual(len(slots['G1-F9']['files']),2)
                self.assertEqual(len(slots['G1-F10']['files']),1)
                self.assertContains(response,'<span class="field-number">1.10</span> Нэвтрүүлэлтийн маркетингийн санааны файл',html=True)
                self.assertContains(response,'id="file-G1-F10"',count=1)
                html=response.content.decode()
                self.assertLess(html.index('id="id_marketing_brief"'),html.index('id="file-G1-F10"'))
                self.assertLess(html.index('id="file-G1-F10"'),html.index('value="gate1_save"'))
                self.assertLess(html.index('id="file-G1-F10"'),html.index('class="gate0-file-slots"'))
                self.food.activities.get(attachment_slot='G1-F10').full_clean()
                self.assertContains(response,'revised.xlsx')
                self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G0-F1','slot_file':SimpleUploadedFile('wrong.pdf',b'wrong gate')}).status_code,403)
                self.food.review_status='qa'; self.food.save()
                self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G1-F1'}).status_code,403)
                self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G1-F10','slot_file':SimpleUploadedFile('locked.pdf',b'locked')}).status_code,403)
                self.user.groups.clear()
                response=self.client.get(url)
                self.assertContains(response,'evidence.xlsx')
                self.assertNotContains(response,'name="slot_file"')
                uploaded=Gate1File.objects.filter(development=self.food,slot_code='G1-F9').first()
                download=self.client.get(reverse('download_gate1_file',args=[uploaded.pk]))
                self.assertEqual(download.status_code,200)
                self.assertEqual(b''.join(download.streaming_content),b'new version')
                download.close()

    def test_gate1_fields_save_and_follow_gate_edit_rights(self):
        from .gate1 import initial_brief
        self.food.stage='gate1'; self.food.save()
        url='/food/%s/' % self.food.pk
        payload={'action':'gate1_save','recipe_version_internal_tasting':'2','consumer_test':'50','typed_cogs':'1200','marketing_brief':'Launch idea'}
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
        response=self.client.get(url)
        self.assertContains(response,'id_marketing_brief')
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(Decimal(initial_brief(self.food)['estimated_cogs_vs_limit']),Decimal('20100'))
        self.assertEqual(initial_brief(self.food)['consumer_test'],50)
        self.assertEqual(self.food.activities.count(),1)
        self.food.review_status='manager'; self.food.save()
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.assertTrue(self.client.get(url).context['gate1form'].fields['consumer_test'].disabled)
        self.food.stage='gate0'; self.food.review_status='draft'; self.food.save()
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.assertNotContains(self.client.get(url),'id_marketing_brief')

    def test_gate0_file_slots_upload_and_read_history(self):
        from .gate0 import FILE_SLOTS
        from .models import Gate0File
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                for key,_ in FILE_SLOTS:
                    for version in range(2):
                        response=self.client.post('/food/%s/' % self.food.pk,{'action':'slot_upload','slot':key,'slot_file':SimpleUploadedFile('evidence-%s.bin' % version,b'evidence')})
                        self.assertEqual(response.status_code,302)
                    self.assertEqual(Gate0File.objects.filter(development=self.food,slot_code=key).count(),2)
                self.user.groups.clear()
                response=self.client.get('/food/%s/' % self.food.pk)
                self.assertEqual(len(response.context['gate0slots']),len(FILE_SLOTS))
                self.assertContains(response,'evidence-1.bin')
                self.assertNotContains(response,'name="slot_file"')
                for slot in response.context['gate0slots']:
                    self.assertEqual(len(slot['files']),2)
                self.assertEqual(self.client.post('/food/%s/' % self.food.pk,{'action':'slot_upload','slot':'G0-F1'}).status_code,403)

    def test_gate0_file_slots_on_creation(self):
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        self.assertContains(self.client.get('/food/new/'),'name="analog_skus_sales_target-0-file"')
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                response=self.client.post('/food/new/',{'product_type':'new','product_name':'Brief with file','evidence-TOTAL_FORMS':'1','evidence-0-file':SimpleUploadedFile('evidence.pdf',b'evidence')})
                self.assertEqual(response.status_code,302)
                food=Food.objects.get(name='Brief with file')
                self.assertEqual(food.gate0_files.get(slot_code='G0-F1').original_filename,'evidence.pdf')

    def test_gate0_typed_draft_fields_save_and_ignore_cogs_input(self):
        from .gate0 import initial_brief
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        response=self.client.get('/food/%s/' % self.food.pk)
        self.assertContains(response,'id_product_name')
        self.assertContains(response,'id_store_scope')
        self.assertNotContains(response,'name="batch_units"')
        self.assertNotContains(response,'name="selling_price"')
        payload={'product_type':'new','product_name':'Typed draft','vendor_rebate':'5','action':'gate0_save','cogs_limit':'9999'}
        self.assertEqual(self.client.post('/food/%s/' % self.food.pk,payload).status_code,302)
        self.food.refresh_from_db()
        self.assertEqual(initial_brief(self.food)['vendor_rebate'],'5')
        self.assertIsNone(initial_brief(self.food)['cogs_limit'])
        self.assertEqual(self.food.name,'Typed draft')
        self.assertEqual(self.food.lines.count(),1)

    def test_gate0_creation_accepts_partial_typed_draft(self):
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        response=self.client.post('/food/new/',{'product_type':'new','product_name':'New brief','cu_margin':'30'})
        self.assertEqual(response.status_code,302)
        food=Food.objects.get(name='New brief')
        self.assertEqual(food.stage,'gate0')
        self.assertIsNone(food.due)
        from .gate0 import initial_brief
        self.assertEqual(initial_brief(food)['cu_margin'],'30')

    def test_gate0_brief_locked_during_review_and_for_readers(self):
        self.assertEqual(self.client.post('/food/%s/' % self.food.pk,{'action':'gate0_save','product_name':'Unauthorized'}).status_code,403)
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        self.food.review_status='manager'; self.food.save()
        self.assertEqual(self.client.post('/food/%s/' % self.food.pk,{'action':'gate0_save','product_name':'Unauthorized'}).status_code,403)
        self.food.refresh_from_db()
        self.assertEqual(self.food.name,'Test bowl')

    def test_official_party_matrix_and_creation_rights(self):
        from django.utils import timezone
        from datetime import timedelta
        self.food.launched_at=timezone.now()-timedelta(days=60)
        self.food.save(update_fields=['launched_at'])
        from .workflow import PARTIES, EDITORS, SUBMITTERS, context
        from .models import STAGES, GateAccess
        self.assertEqual(GateAccess.objects.count(),50)
        for party in PARTIES:
            self.user.groups.clear()
            self.user.groups.add(Group.objects.get(name=party))
            for gate,_ in STAGES:
                self.food.stage=gate
                rights=context(self.user,self.food)
                self.assertEqual(rights['editable'],party in EDITORS[gate],(party,gate))
                self.assertEqual(rights['can_submit'],party==SUBMITTERS[gate],(party,gate))
            response=self.client.get('/food/new/')
            self.assertEqual(response.status_code,200 if party=='Category Manager (MD)' else 403)

    def act_as(self,role,action,note=''):
        self.user.groups.clear()
        self.user.groups.add(Group.objects.get(name=role))
        response=self.client.post('/food/%s/' % self.food.pk,{'action':action,'note':note})
        self.food.refresh_from_db()
        return response

    def test_gate2_approval_order_and_launch_gate3_completion(self):
        self.food.stage='gate2'; self.food.save()
        self.act_as('NPD / Product Developer','submit')
        self.assertEqual(self.food.review_status,'qa')
        self.act_as('Merchandising Director','approve')
        self.assertEqual(self.food.review_status,'qa')
        self.act_as('Fresh Food Manager','approve')
        self.assertEqual(self.food.review_status,'qa')
        self.act_as('QA','qa_accept')
        self.assertEqual(self.food.review_status,'manager')
        self.act_as('Fresh Food Manager','approve')
        self.assertEqual(self.food.review_status,'director')
        self.act_as('Merchandising Director','approve')
        self.assertEqual(self.food.stage,'launch')
        self.assertIsNotNone(self.food.launched_at)
        self.act_as('FF Planning','submit')
        self.assertEqual(self.food.stage,'launch')
        from django.utils import timezone
        from datetime import timedelta
        self.food.launched_at=timezone.now()-timedelta(days=45)
        self.food.save(update_fields=['launched_at'])
        self.act_as('FF Planning','submit')
        self.assertEqual(self.food.stage,'gate3')
        self.act_as('Category Manager (MD)','submit')
        self.act_as('Fresh Food Manager','approve')
        self.assertFalse(self.food.completed)
        self.act_as('Merchandising Director','approve')
        self.assertTrue(self.food.completed)

    def test_owner_has_no_permission_bypass_and_rights_editable_in_admin(self):
        from .models import GateAccess
        response=self.client.post('/food/%s/' % self.food.pk,{'action':'remove','line':self.food.lines.first().pk})
        self.assertEqual(response.status_code,403)
        self.user.groups.add(Group.objects.get(name='Marketing'))
        self.assertTrue(self.client.get('/food/%s/' % self.food.pk).context['editable'])
        GateAccess.objects.filter(group__name='Marketing',stage='gate0').update(can_edit=False)
        self.assertFalse(self.client.get('/food/%s/' % self.food.pk).context['editable'])

    def test_return_clears_review_and_escalation_requires_note(self):
        self.food.review_status='manager'; self.food.save()
        self.act_as('Fresh Food Manager','escalate')
        self.assertEqual(self.food.review_status,'manager')
        self.act_as('Fresh Food Manager','escalate','Escalate decision')
        self.assertEqual(self.food.review_status,'director')
        self.act_as('Merchandising Director','return','Revise brief')
        self.assertEqual(self.food.stage,'gate0')
        self.assertEqual(self.food.review_status,'draft')

    def test_general_uploader_removed_and_old_upload_rejected(self):
        response=self.client.get('/food/%s/' % self.food.pk)
        self.assertNotContains(response,'attachment-file')
        self.client.post('/food/%s/' % self.food.pk,{'action':'attachment','attachment':SimpleUploadedFile('old.pdf',b'old')})
        self.assertEqual(self.food.activities.count(),0)

    def test_stage_overview_counts_all_stages_and_preserves_search(self):
        Food.objects.create(name='Test launch',owner=self.user,due=date.today(),stage='gate3')
        Food.objects.create(name='Other recipe',owner=self.user,due=date.today(),stage='gate1')
        response=self.client.get('/?stage=gate3&q=Test')
        summary={item['key']:item['count'] for item in response.context['stage_summary']}
        self.assertEqual(summary,{'gate0':1,'gate1':0,'gate2':0,'launch':0,'gate3':1})
        self.assertEqual(len(response.context['foods']),1)
        self.assertContains(response,'Үе шат тус бүрийн хөгжүүлэлт')
        self.assertContains(response,'?stage=gate1&amp;q=Test')
        response=self.client.get('/')
        summary={item['key']:item['count'] for item in response.context['stage_summary']}
        self.assertEqual(summary['gate1'],1)

    @patch('development.views.timezone.localdate',return_value=date(2026,12,15))
    def test_sla_due_includes_today_and_overdue_but_excludes_approved(self,localdate):
        self.food.due=date(2026,12,15)
        self.food.save()
        for name,due,stage in [('Overdue',date(2026,12,14),'gate2'),('Future',date(2026,12,16),'gate1'),('Finished',date(2026,12,14),'gate3')]:
            Food.objects.create(name=name,owner=self.user,due=due,stage=stage,completed=(name=='Finished'))
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

    def test_legacy_sections_and_write_actions_retired(self):
        from .models import STAGES
        self.user.is_superuser=True; self.user.save()
        for gate,_ in STAGES:
            self.food.stage=gate; self.food.save()
            response=self.client.get('/food/%s/' % self.food.pk)
            for name in (['batch_units','selling_price','production_date'] if gate in ['gate1','gate2'] else ['batch_units','selling_price','production_date','ingredient']):
                self.assertNotContains(response,'name="%s"' % name)
            for action in ['launch_dates','add','remove','save']:
                self.assertEqual(self.client.post('/food/%s/' % self.food.pk,{'action':action}).status_code,403)

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
        self.assertEqual(self.food.unit_cost,Decimal(20100))
        self.assertEqual(self.food.margin,Decimal('-1910'))
    def test_price_snapshot(self):
        self.ingredient.price=9999
        self.ingredient.save()
        self.assertEqual(self.food.unit_cost,20100)
    def test_role_gate_and_handoff(self):
        url='/food/%s/' % self.food.pk
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status,'draft')
        self.user.groups.add(Group.objects.get(name='Category Manager (MD)'))
        from .gate0 import save_brief
        save_brief(self.food,valid_gate0())
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status,'manager')
        self.assertEqual(self.food.stage,'gate0')
        self.user.groups.add(Group.objects.get(name='Fresh Food Manager'))
        self.client.post(url,{'action':'approve'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.stage,'gate1')

    def test_approved_record_locked(self):
        self.food.completed=True; self.food.stage='gate3'; self.food.save()
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
    def test_gate_submissions_no_longer_require_ingredients_or_calculated_margin(self):
        self.food.lines.all().delete()
        self.food.selling_price=0
        for gate in ['gate1','gate2']:
            self.food.stage=gate; self.food.review_status='draft'; self.food.save()
            self.user.groups.clear()
            self.user.groups.add(Group.objects.get(name='NPD / Product Developer'))
            self.client.post('/food/%s/' % self.food.pk,{'action':'submit'})
            self.food.refresh_from_db()
            self.assertEqual(self.food.review_status,'manager' if gate=='gate1' else 'qa')
