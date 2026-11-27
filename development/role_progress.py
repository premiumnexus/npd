"""Display the current gate's responsibility sequence without granting access."""
from .workflow import CATEGORY,NPD,QA,MANAGER,DIRECTOR,SUBMITTERS,SCIENCE,PLANNING

def role_progress(food):
    from .models import GateAccess
    from .gate1 import initial_brief
    from .gate1_typed import cost_comparison
    if food.stage=='launch':
        recorded_days=set(food.launch_checkpoints.values_list('day',flat=True))
        rows=[]
        for day,roles,task in [
            (7,[SCIENCE,PLANNING,QA],'Дээж, борлуулалт, акт, гомдол'),
            (14,[SCIENCE,PLANNING,QA],'Хадгалах хугацааны дээж, борлуулалт, гомдол'),
            (45,[PLANNING],'Gate 3 руу шилжүүлэх'),
        ]:
            rows.append({'key':'day%s'%day,'roles':roles,'task':task,'conditional':False,
                'state':'done' if day in recorded_days else 'current'})
        return rows
    def groups(permission,fallback):
        return list(GateAccess.objects.filter(stage=food.stage,**{permission:True}).order_by('group__name').values_list('group__name',flat=True)) or fallback
    red=food.stage=='gate1' and cost_comparison(food,initial_brief(food).get('typed_cogs'))['cogs_status']=='Red'
    conditional=food.stage in ['gate0','gate1'] and not red
    rows=[{'key':'draft','roles':groups('can_submit',[SUBMITTERS.get(food.stage,CATEGORY)]),'task':'Мэдээлэл бэлтгэх, хяналтад илгээх','editors':groups('can_edit',[])}]
    if food.stage=='gate2': rows.append({'key':'qa','roles':groups('can_qa_accept',[QA]),'task':'QA хяналт, зөвшөөрөл'})
    rows.append({'key':'manager','roles':groups('can_manager_decide',[MANAGER]),'task':'Хянах, зөвшөөрөх'})
    rows.append({'key':'director','roles':groups('can_director_decide',[DIRECTOR]),
        'task':'Эцсийн шийдвэр' if not conditional else 'Шатлан шилжүүлсэн тохиолдолд шийдвэрлэх','conditional':conditional})
    keys=[row['key'] for row in rows]
    current=keys.index(food.review_status) if food.review_status in keys else 0
    events=list(food.gate_transitions.order_by('occurred_at','pk'))
    # Only timestamps belonging to the latest visit to this gate are relevant.
    visit=[]
    for event in events:
        if event.to_stage!=food.stage: visit=[];continue
        if event.from_stage!=food.stage: visit=[]
        visit.append(event)
    for index,row in enumerate(rows):
        row['state']='done' if food.completed or index<current else ('current' if index==current else 'upcoming')
        row['conditional']=row.get('conditional',False)
        matching=[event for event in visit if event.to_review==row['key']]
        last=matching[-1] if matching else None
        if row['state']=='current' and last and last.to_review==food.review_status:
            row['started_at']=last.occurred_at
    return rows
