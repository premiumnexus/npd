from django.db import migrations

def backfill(apps,schema_editor):
    Food=apps.get_model('development','Food')
    Event=apps.get_model('development','GateTransition')
    for food in Food.objects.all().iterator():
        launch=Event.objects.filter(food_id=food.pk,to_stage='launch').exclude(from_stage='launch').order_by('occurred_at','pk').first()
        opened=Event.objects.filter(food_id=food.pk,to_stage='gate3').exclude(from_stage='gate3').order_by('occurred_at','pk').first()
        changes={}
        if launch and not food.launched_at: changes['launched_at']=launch.occurred_at
        if opened and not food.gate3_opened_at: changes['gate3_opened_at']=opened.occurred_at
        if changes: Food.objects.filter(pk=food.pk).update(**changes)

class Migration(migrations.Migration):
    dependencies=[('development','0022_food_gate3_opened_at_food_launched_at_and_more')]
    operations=[migrations.RunPython(backfill,migrations.RunPython.noop)]
