from django.db import migrations

STAGES=[('gate0','Gate 0 · Санаа ба танилцуулга'),('gate1','Gate 1 · Концепц ба жор'),('gate2','Gate 2 · Үйлдвэрлэл, нэвтрүүлэлтийн бэлэн байдал'),('launch','Launch GO · 7 / 14 дэх өдрийн хяналт'),('gate3','Gate 3 · 45 дахь өдрийн дүгнэлт')]
REVIEWS=[('draft','Бэлтгэж байна'),('qa','QA зөвшөөрөл хүлээж байна'),('manager','Fresh Food Manager хүлээж байна'),('director','Merchandising Director хүлээж байна')]
ACTIONS=[('Хяналтад илгээв','submit'),('QA зөвшөөрөл өгсөн','qa_accept'),('Захирлын шийдвэрт шилжүүлэв','escalate'),('Менежер зөвшөөрсөн','approve'),('Эцсийн шийдвэр: батлав','approve'),('Засварт буцаав','return')]

def backfill(apps,schema_editor):
    Activity=apps.get_model('development','Activity')
    Event=apps.get_model('development','GateTransition')
    previous={}
    for activity in Activity.objects.select_related('food').order_by('created','pk').iterator():
        if Event.objects.filter(activity_id=activity.pk).exists(): continue
        text=activity.text
        data=None
        if text in ['Хөгжүүлэлтийн танилцуулга үүсгэв','Created development brief']:
            data={'action':'created','from_stage':'','to_stage':'gate0','from_review':'','to_review':'draft','completed':False}
        elif text.startswith('Sample development created.'):
            data={'action':'created','from_stage':'','to_stage':activity.food.stage,'from_review':'','to_review':'draft','completed':False}
        elif ' → ' in text:
            left,_,right=text.partition(' → ')
            old=next((key for key,label in STAGES if left.endswith(label)),None)
            target=next(((key,label) for key,label in STAGES if right.startswith(label)),None)
            action=next((action for prefix,action in ACTIONS if text.startswith(prefix)),None)
            if old and target and action:
                suffix=right[len(target[1]):].lstrip(' ·')
                completed=suffix.startswith('Дууссан')
                review='draft' if completed else next((key for key,label in REVIEWS if suffix.startswith(label)),'')
                prior=previous.get(activity.food_id)
                data={'action':action,'from_stage':old,'to_stage':target[0],'from_review':prior.to_review if prior and prior.to_stage==old else '', 'to_review':review,'completed':completed}
        if data:
            previous[activity.food_id]=Event.objects.create(food_id=activity.food_id,actor_id=activity.actor_id,activity_id=activity.pk,occurred_at=activity.created,**data)

class Migration(migrations.Migration):
    dependencies=[('development','0020_gatetransition')]
    operations=[migrations.RunPython(backfill,migrations.RunPython.noop)]
