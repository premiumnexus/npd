"""Official parties and editable per-gate access defaults."""
CATEGORY = 'Category Manager (MD)'
NPD = 'NPD / Product Developer'
SCIENCE = 'Food Science'
PURCHASING = 'Purchasing / Supply Chain'
PRODUCER = 'Producer'
QA = 'QA'
MARKETING = 'Marketing'
PLANNING = 'FF Planning'
MANAGER = 'Fresh Food Manager'
DIRECTOR = 'Merchandising Director'
PARTIES = [CATEGORY,NPD,SCIENCE,PURCHASING,PRODUCER,QA,MARKETING,PLANNING,MANAGER,DIRECTOR]
EDITORS = {
    'gate0':[CATEGORY,SCIENCE,PURCHASING,PRODUCER,QA,MARKETING,PLANNING],
    'gate1':[NPD,SCIENCE,PURCHASING,PRODUCER,QA,MARKETING],
    'gate2':[CATEGORY,NPD,SCIENCE,PURCHASING,PRODUCER,QA,MARKETING,PLANNING],
    'launch':[SCIENCE,QA,PLANNING],
    'gate3':[CATEGORY,NPD,SCIENCE,QA,MARKETING,PLANNING],
}
SUBMITTERS = {'gate0':CATEGORY,'gate1':NPD,'gate2':NPD,'launch':PLANNING,'gate3':CATEGORY}

def access(user,food,permission):
    if food.completed: return False
    if user.is_superuser: return True
    return GateAccessQuery(user,food.stage,permission)

def GateAccessQuery(user,stage,permission):
    from .models import GateAccess
    return GateAccess.objects.filter(group__user=user,stage=stage,**{permission:True}).exists()

def context(user,food):
    draft = food.review_status == 'draft'
    rights={
        'editable':draft and access(user,food,'can_edit'),
        'can_manage_launch':draft and access(user,food,'can_edit'),
        'can_submit':draft and access(user,food,'can_submit'),
        'can_qa':food.review_status == 'qa' and access(user,food,'can_qa_accept'),
        'can_decide':food.review_status in ['manager','director'] and access(user,food,'can_'+food.review_status+'_decide'),
        'can_return':not food.completed and ((draft and access(user,food,'can_submit')) or (food.review_status == 'qa' and access(user,food,'can_qa_accept')) or (food.review_status in ['manager','director'] and access(user,food,'can_'+food.review_status+'_decide'))),
        'can_escalate':food.stage in ['gate0','gate1'] and food.review_status == 'manager' and access(user,food,'can_manager_decide'),
    }
    return rights

def transition(user,food,action,note):
    """Called with the food row locked in a transaction by the view."""
    from .models import STAGES, Activity
    rights = context(user,food)
    previous_stage=food.stage
    previous_review=food.review_status
    previous = food.get_stage_display()
    if action == 'submit':
        if not rights['can_submit']: return 'Илгээх эрхгүй эсвэл хяналтад орсон байна.'
        if food.stage == 'gate0':
            from .gate0 import Gate0Form,initial_brief
            from django.utils import timezone
            saved=initial_brief(food)
            validation=Gate0Form(saved,initial=saved,food=food,submission=True)
            if not validation.is_valid():
                return 'Оруулсан мэдээллийн төрлийг шалгана уу: '+ '; '.join('%s: %s' % (validation.fields[key].label if key in validation.fields else key,', '.join(errors)) for key,errors in validation.errors.items())
            if not food.gate0_submitted_at: food.gate0_submitted_at=timezone.now()
        elif food.stage == 'gate1':
            from .gate1 import Gate1Form,initial_brief
            saved=initial_brief(food)
            validation=Gate1Form(saved,initial=saved,food=food,submission=True)
            if not validation.is_valid():
                return 'Оруулсан мэдээллийг шалгана уу: '+ '; '.join('%s: %s' % (validation.fields[key].label if key in validation.fields else 'Жор ба өртөг',', '.join(errors)) for key,errors in validation.errors.items())
        elif food.stage == 'gate2':
            from .gate2 import Gate2Form,initial_brief
            saved=initial_brief(food)
            validation=Gate2Form(saved,initial=saved,food=food,submission=True)
            if not validation.is_valid():
                return 'Оруулсан мэдээллийг шалгана уу: '+ '; '.join('%s: %s' % (validation.fields[key].label if key in validation.fields else 'Gate 2',', '.join(errors)) for key,errors in validation.errors.items())
        elif food.stage == 'gate3':
            from .gate3 import Gate3Form,initial_brief
            saved=initial_brief(food)
            validation=Gate3Form(saved,initial=saved,food=food)
            if not validation.is_valid():
                return 'Оруулсан мэдээллийн төрлийг шалгана уу: '+ '; '.join('%s: %s' % (validation.fields[key].label if key in validation.fields else key,', '.join(errors)) for key,errors in validation.errors.items())
        if food.stage == 'launch':
            food.stage = 'gate3'
        elif food.stage == 'gate2':
            food.review_status = 'qa'
        elif food.stage == 'gate3':
            food.review_status = 'manager'
        else:
            food.review_status = 'manager'
        description = 'Хяналтад илгээв'
    elif action == 'qa_accept':
        if not rights['can_qa']: return 'QA зөвшөөрөл өгөх эрхгүй эсвэл дараалал тохирохгүй байна.'
        food.review_status = 'manager'
        description = 'QA зөвшөөрөл өгсөн'
    elif action == 'escalate':
        if not rights['can_escalate']: return 'Шатлан шийдвэрлүүлэх эрхгүй.'
        if not note: return 'Шатлан шийдвэрлүүлэх шалтгаанаа оруулна уу.'
        food.review_status = 'director'
        description = 'Захирлын шийдвэрт шилжүүлэв'
    elif action == 'approve':
        if not rights['can_decide']: return 'Шийдвэр гаргах эрхгүй эсвэл хяналтын дараалал тохирохгүй байна.'
        if food.stage == 'gate1':
            from .gate1 import Gate1Form,initial_brief
            saved=initial_brief(food)
            validation=Gate1Form(saved,initial=saved,food=food,submission=True)
            if not validation.is_valid(): return '; '.join(str(error) for errors in validation.errors.values() for error in errors)
        if food.stage == 'gate0':
            from .gate0 import Gate0Form,initial_brief
            saved=initial_brief(food)
            validation=Gate0Form(saved,initial=saved,food=food,submission=True)
            if not validation.is_valid():
                return 'Оруулсан мэдээллийн төрлийг шалгана уу: '+ '; '.join('%s: %s' % (validation.fields[key].label if key in validation.fields else key,', '.join(errors)) for key,errors in validation.errors.items())
        if food.stage == 'gate2':
            from .gate2 import Gate2Form,initial_brief
            saved=initial_brief(food)
            validation=Gate2Form(saved,initial=saved,food=food,submission=True)
            if not validation.is_valid():
                return 'Оруулсан мэдээллийг шалгана уу: '+ '; '.join('%s: %s' % (validation.fields[key].label if key in validation.fields else 'Gate 2',', '.join(errors)) for key,errors in validation.errors.items())
        from .gate1_typed import cost_comparison
        from .gate1 import initial_brief as gate1_data
        red_gate1=food.stage=='gate1' and cost_comparison(food,gate1_data(food).get('typed_cogs'))['cogs_status']=='Red'
        if food.review_status == 'manager' and (food.stage in ['gate2','gate3'] or red_gate1):
            food.review_status = 'director'
            description = 'Менежер зөвшөөрсөн, захирлын шийдвэр хүлээж байна'
        else:
            keys = [key for key,_ in STAGES]
            index = keys.index(food.stage)
            if food.stage == 'gate3': food.completed = True
            else: food.stage = keys[index+1]
            food.review_status = 'draft'
            description = 'Эцсийн шийдвэр: батлав'
    elif action == 'return':
        if not rights['can_return']: return 'Буцаах эрхгүй.'
        if not note: return 'Буцаах шалтгаанаа оруулна уу.'
        # Reviewers return to the same gate for corrections. Draft submitters
        # may send it to the previous gate; earlier decisions must be repeated.
        if food.review_status == 'draft':
            keys = [key for key,_ in STAGES]
            food.stage = keys[max(0,keys.index(food.stage)-1)]
        food.review_status = 'draft'
        description = 'Засварт буцаав'
    else:
        return 'Үйлдэл тохирохгүй байна.'
    food.save()
    activity=Activity.objects.create(food=food,actor=user,text='%s · %s → %s · %s%s' % (description,previous,food.get_stage_display(),'Дууссан' if food.completed else food.get_review_status_display(),(' · '+note) if note else ''))
    from .timing import record_transition
    record_transition(food,user,action,previous_stage,previous_review,activity)
