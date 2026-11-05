from django.db import migrations

def seed(apps,schema_editor):
    Option=apps.get_model('development','Gate0Option')
    defaults={
        'product_role':[('core','Core'),('hero','Hero'),('traffic_driver','Traffic driver'),('premium_test','Premium test'),('lto','LTO')],
        'improvement_reason':[('R%02d' % n,'R%02d' % n) for n in range(1,12)],
        'allergen':[
            ('gluten','Цавуулаг агуулсан үр тариа'),('crustaceans','Хавч хэлбэртэн'),
            ('egg','Өндөг'),('fish','Загас'),('peanut','Газрын самар'),('soy','Шар буурцаг'),
            ('milk','Сүү (лактоз орно)'),('tree_nuts','Модны самар'),('sulphite','Сульфит ≥ 10 мг/кг'),
        ],
        'high_risk':[('raw_meat','Түүхий мах'),('raw_vegetables','Түүхий ногоо'),('egg','Өндөг'),('dairy','Сүүн бүтээгдэхүүн'),('rice','Будаа')],
    }
    for kind,items in defaults.items():
        for order,(code,label) in enumerate(items):
            Option.objects.get_or_create(kind=kind,code=code,category='',defaults={'label':label,'order':order})

class Migration(migrations.Migration):
    dependencies=[('development','0015_gate0option_food_gate0_submitted_at_and_more')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
