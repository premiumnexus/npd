from django.contrib.auth.models import User
from django.test import TestCase

from .gate0 import Gate0Form,save_brief
from .models import Food
from .tests import valid_gate0


class Gate0SupplyTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('supply-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Supply example',owner=self.user)

    def test_section_title_subtitle_order_numbering_and_three_required_stars(self):
        for url in ['/food/new/','/food/%s/'%self.food.pk]:
            with self.subTest(url=url):
                response=self.client.get(url)
                html=response.content.decode()
                group=html.split('<fieldset class="gate0-identity gate0-supply"',1)[1].split('</fieldset>',1)[0]
                self.assertIn('<legend>Үйлдвэрлэл ба нийлүүлэлт</legend>',group)
                self.assertIn('<small><em>Хийж, нийлүүлж чадах уу?</em></small>',group)
                self.assertEqual(group.count('class="required-star"'),3)
                self.assertLess(html.index('<legend>Борлуулалтын зорилт</legend>'),html.index('<legend>Үйлдвэрлэл ба нийлүүлэлт</legend>'))
                form=response.context['form'] if url=='/food/new/' else response.context['gate0form']
                positions=[]
                for index,key in enumerate(Gate0Form.supply_keys,1):
                    self.assertEqual(form.fields[key].gate_number,f'5.{index}')
                    self.assertEqual(form.fields[key].gate_required,index<=3)
                    self.assertEqual(html.count('id="id_%s"'%key),1)
                    positions.append(group.index('for="id_%s"'%key))
                self.assertEqual(positions,sorted(positions))
                self.assertEqual(form.fields['first_capacity_check'].label,'Нийлүүлэгчийн хүчин чадлын анхны үнэлгээ')
                self.assertEqual(form.fields['capacity_units_day'].label,'Нийлүүлэгчийн хүчин чадал (ширхэг/өдөр)')

    def test_required_supply_fields_allow_no_and_block_missing_values_on_submit_and_approval(self):
        complete={key:value for key,value in valid_gate0().items() if key in Gate0Form.required_keys}
        complete.update(new_supplier='no',raw_materials_supply_risk='no')
        form=Gate0Form(complete,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertTrue(Gate0Form({**complete,'new_supplier':'yes','raw_materials_supply_risk':'yes'},submission=True).is_valid())
        url='/food/%s/'%self.food.pk
        for key in Gate0Form.supply_keys[:3]:
            with self.subTest(field=key):
                incomplete={**complete,key:''}
                self.assertTrue(Gate0Form(incomplete).is_valid())
                validation=Gate0Form(incomplete,submission=True)
                self.assertFalse(validation.is_valid())
                self.assertIn(key,validation.errors)
                self.food.review_status='draft';self.food.save()
                save_brief(self.food,incomplete)
                self.client.post(url,{'action':'submit'})
                self.food.refresh_from_db()
                self.assertEqual(self.food.review_status,'draft')
                self.food.review_status='manager';self.food.save()
                self.client.post(url,{'action':'approve'})
                self.food.refresh_from_db()
                self.assertEqual(self.food.stage,'gate0')
                self.assertEqual(self.food.review_status,'manager')
        self.food.review_status='draft';self.food.save()
        save_brief(self.food,form.cleaned_data)
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status,'manager')
