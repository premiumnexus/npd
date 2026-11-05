from django.utils import timezone

def record_transition(food,actor,action,from_stage,from_review,activity):
    from .models import GateTransition
    event=GateTransition.objects.create(food=food,actor=actor,activity=activity,action=action,from_stage=from_stage,to_stage=food.stage,from_review=from_review,to_review=food.review_status,completed=food.completed,occurred_at=activity.created)
    if food.stage=='launch' and from_stage!='launch' and not food.launched_at:
        food.launched_at=activity.created
        food.save(update_fields=['launched_at'])
    return event

def duration(start,end):
    if start is None or end is None: return ''
    minutes=max(0,int((end-start).total_seconds()//60))
    days,remainder=divmod(minutes,1440)
    hours,minutes=divmod(remainder,60)
    parts=[]
    if days: parts.append('%s өдөр'%days)
    if hours: parts.append('%s цаг'%hours)
    if minutes: parts.append('%s минут'%minutes)
    return ' '.join(parts) or '1 минутаас бага'

def gate_timing(food,now=None):
    from .models import STAGES,GateAccess
    now=now or timezone.now()
    events=list(food.gate_transitions.select_related('actor').all())
    rows={key:{'key':key,'label':label,'visits':[]} for key,label in STAGES}
    open_visit=None
    previous=None
    for event in events:
        if event.to_stage not in rows: continue
        if open_visit is None:
            # A non-creation first event only proves the new gate's start when
            # it actually changes stages; never invent an earlier entry time.
            start=event.occurred_at if not event.from_stage or event.from_stage!=event.to_stage else None
            open_visit={'entered_at':start,'exited_at':None,'stage':event.to_stage}
            rows[event.to_stage]['visits'].append(open_visit)
        elif open_visit['stage'] != event.to_stage:
            continuous=open_visit['stage']==event.from_stage
            if continuous: open_visit['exited_at']=event.occurred_at
            start=event.occurred_at if event.from_stage!=event.to_stage else None
            open_visit={'entered_at':start,'exited_at':None,'stage':event.to_stage}
            rows[event.to_stage]['visits'].append(open_visit)
        if event.completed:
            open_visit['exited_at']=event.occurred_at
            open_visit=None
        event.previous_elapsed=duration(previous.occurred_at,event.occurred_at) if previous else ''
        previous=event
    last=events[-1] if events else None
    state_matches=bool(last and last.to_stage==food.stage and last.completed==food.completed)
    for key,row in rows.items():
        latest=row['visits'][-1] if row['visits'] else {}
        row.update(latest)
        row['is_current']=key==food.stage and not food.completed
        row['visit_count']=len(row['visits'])
        start=latest.get('entered_at')
        end=latest.get('exited_at')
        if row['is_current'] and state_matches: end=now
        row['elapsed']=duration(start,end)
        row['running']=row['is_current'] and state_matches and bool(start)
        keys=list(rows)
        row['upcoming']=not row['visits'] and food.stage in keys and keys.index(key)>keys.index(food.stage)
    current=rows.get(food.stage,{})
    step_started=last.occurred_at if state_matches and last.to_review==food.review_status and not food.completed else None
    permission={'draft':'can_submit','qa':'can_qa_accept','manager':'can_manager_decide','director':'can_director_decide'}.get(food.review_status)
    responsible=list(GateAccess.objects.filter(stage=food.stage,**{permission:True}).values_list('group__name',flat=True)) if permission and not food.completed else []
    return {'gates':list(rows.values()),'events':list(reversed(events)),'current':current,'step_started':step_started,'step_elapsed':duration(step_started,now),'responsible':responsible}
