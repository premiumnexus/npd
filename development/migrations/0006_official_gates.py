from django.db import migrations

MAPPING = {'concept':'gate0','recipe':'gate1','sourcing':'gate2','quality':'gate2','costing':'gate2','approved':'launch'}

def migrate_gates(apps,schema_editor):
    Food=apps.get_model('development','Food')
    Activity=apps.get_model('development','Activity')
    for old,new in MAPPING.items():
        Food.objects.filter(stage=old).update(stage=new)
        Activity.objects.filter(attachment_stage=old).update(attachment_stage=new)
    Group=apps.get_model('auth','Group')
    Access=apps.get_model('development','GateAccess')
    parties=['Category Manager (MD)','NPD / Product Developer','Food Science','Purchasing / Supply Chain','Producer','QA','Marketing','FF Planning','Fresh Food Manager','Merchandising Director']
    editors={'gate0':[0,2,3,4,5,6,7],'gate1':[1,2,3,4,5,6],'gate2':[0,1,2,3,4,5,6,7],'launch':[2,5,7],'gate3':[0,1,2,5,6,7]}
    submitters={'gate0':0,'gate1':1,'gate2':1,'launch':7,'gate3':0}
    for index,name in enumerate(parties):
        group,_=Group.objects.get_or_create(name=name)
        for stage,indices in editors.items():
            Access.objects.get_or_create(group=group,stage=stage,defaults={'can_edit':index in indices,'can_submit':index==submitters[stage],'can_qa_accept':index==5 and stage=='gate2','can_manager_decide':index==8 and stage!='launch','can_director_decide':index==9 and stage!='launch'})

class Migration(migrations.Migration):
    dependencies=[('development','0005_food_completed_food_review_status_and_more')]
    operations=[migrations.RunPython(migrate_gates,migrations.RunPython.noop)]
