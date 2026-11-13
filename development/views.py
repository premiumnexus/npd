import csv
import json
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Food, Supplier, Ingredient, RecipeLine, Activity, STAGES
from .workflow import context as gate_context, transition, GateAccessQuery, CATEGORY, PURCHASING
from .forms import SupplierForm, IngredientForm, Gate1LineForm, Gate1PackagingForm
from .gate0 import Gate0Form, initial_brief, save_brief, FILE_SLOTS, file_slots, save_slot_file
from .gate1 import Gate1Form, initial_brief as initial_gate1, save_brief as save_gate1, FILE_SLOTS as GATE1_FILE_SLOTS, file_slots as gate1_file_slots, save_slot_file as save_gate1_file
from .gate2 import Gate2Form, initial_brief as initial_gate2, save_brief as save_gate2, FILE_SLOTS as GATE2_FILE_SLOTS, file_slots as gate2_file_slots, save_slot_file as save_gate2_file, available_file_slots as available_gate2_file_slots
from .gate3 import Gate3Form, initial_brief as initial_gate3, save_brief as save_gate3, FILE_SLOTS as GATE3_FILE_SLOTS, file_slots as gate3_file_slots, save_slot_file as save_gate3_file
from .gate3_typed import ROOT_CAUSES,LESSON_TAGS
from .timing import record_transition,gate_timing
from .role_progress import role_progress
from .launch import schedule as launch_schedule,checkpoint_cards,can_edit_checkpoint,checkpoint_slots,CheckpointForm,open_gate3_if_due,open_due_reviews

def allowed(user, role):
    return user.is_superuser or user.groups.filter(name=role).exists()

@login_required
def lessons(request):
    from .models import Gate3Brief
    records=[]
    for brief in Gate3Brief.objects.select_related('food').order_by('-food__updated'):
        data=json.loads(brief.data)
        lesson=(data.get('lesson_card') or '').strip()
        stop=(data.get('lesson_stop') or '').strip()
        change=(data.get('lesson_change') or '').strip()
        if lesson or stop or change:
            cause=data.get('root_cause','')
            records.append({'food':brief.food,'lesson':lesson,'stop':stop,'change':change,'root_cause':dict(ROOT_CAUSES).get(cause,cause),'evidence':data.get('root_cause_evidence',''),'tags':[dict(LESSON_TAGS).get(tag,tag) for tag in data.get('lesson_tags',[])]})
    return render(request,'lessons.html',{'lessons':records})

@login_required
def recipes(request):
    foods=Food.objects.filter(stage__in=['launch','gate3']).prefetch_related('lines__ingredient__supplier').order_by('name','pk')
    query=request.GET.get('q','').strip()
    if query: foods=foods.filter(Q(name__icontains=query)|Q(category__icontains=query))
    return render(request,'recipes.html',{'foods':foods,'query':query})

@login_required
def dashboard(request):
    open_due_reviews()
    today = timezone.localdate()
    month_start = today.replace(day=1)
    next_month = month_start.replace(year=today.year+1,month=1) if today.month == 12 else month_start.replace(month=today.month+1)
    foods = Food.objects.select_related('owner').prefetch_related('lines__ingredient').order_by('-updated')
    query = request.GET.get('q','')
    if query: foods = foods.filter(Q(name__icontains=query)|Q(category__icontains=query))
    counts = dict(foods.order_by().values('stage').annotate(count=Count('pk')).values_list('stage','count'))
    stage_summary = [{'key':key,'label':label,'count':counts.get(key,0)} for key,label in STAGES]
    stage = request.GET.get('stage','')
    if stage: foods = foods.filter(stage=stage)
    return render(request,'dashboard.html',{'foods':foods,'stages':STAGES,'total':Food.objects.count(),'review':Food.objects.exclude(review_status='draft').count(),'ready':Food.objects.filter(stage='launch').count(),'suppliers_count':Supplier.objects.count(),'production_this_month':Food.objects.filter(production_date__gte=month_start,production_date__lt=next_month).count(),'market_launches_this_year':Food.objects.filter(market_launch_date__gte=today.replace(month=1,day=1),market_launch_date__lte=today).count(),'sla_due':Food.objects.filter(due__lte=today).filter(completed=False).count(),'stage_summary':stage_summary,'stats_today':today})

@login_required
@require_http_methods(['GET','POST'])
def create_food(request):
    if not (request.user.is_superuser or GateAccessQuery(request.user,'gate0','can_submit')): return HttpResponseForbidden('Бүтээгдэхүүний багийн эрх шаардлагатай')
    form = Gate0Form(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            food = Food.objects.create(name='Нэргүй бүтээгдэхүүн',owner=request.user)
            save_brief(food,form.cleaned_data)
            for key,_ in FILE_SLOTS:
                uploaded=request.FILES.get(key)
                if uploaded and uploaded.size: save_slot_file(food,request.user,key,uploaded)
            activity=Activity.objects.create(food=food,actor=request.user,text='Хөгжүүлэлтийн танилцуулга үүсгэв')
            record_transition(food,request.user,'created','','',activity)
            if form.launch_warning: messages.warning(request,'Нэвтрүүлэх огноо 30 хоногийн дотор байна. Энэ нь зөвхөн анхааруулга юм.')
        return redirect('detail',pk=food.pk)
    return render(request,'form.html',{'form':form,'gate0':True,'gate0slots':file_slots(),'title':'Gate 0 · Санаа ба танилцуулга','subtitle':'Бүтээгдэхүүний анхны мэдээллийг оруулна уу.'})

@login_required
@require_http_methods(['GET','POST'])
def detail(request,pk):
    with transaction.atomic():
        food = get_object_or_404(Food.objects.select_for_update(),pk=pk)
        open_gate3_if_due(food)
        view_stage=request.GET.get('gate',food.stage)
        if view_stage not in dict(STAGES): raise Http404
        viewing_current=view_stage == food.stage
        if request.method == 'POST' and not viewing_current:
            return HttpResponseForbidden('Өөр үе шатны мэдээллийг зөвхөн харах боломжтой.')
        rights = gate_context(request.user,food)
        if not viewing_current:
            rights={key:False for key in rights}
        editable = rights['editable']
        ingredient_form = Gate1LineForm(stage=view_stage)
        packaging_form = Gate1PackagingForm(instance=food)
        gate0form = Gate0Form(initial=initial_brief(food),food=food)
        gate1form = Gate1Form(initial=initial_gate1(food),food=food)
        gate2form = Gate2Form(initial=initial_gate2(food),food=food)
        gate3form = Gate3Form(initial=initial_gate3(food),food=food)
        for field in gate3form.fields.values(): field.disabled = field.disabled or not editable
        for field in gate2form.fields.values(): field.disabled = field.disabled or not editable
        for field in gate1form.fields.values(): field.disabled = field.disabled or not editable
        for field in gate0form.fields.values(): field.disabled = field.disabled or not editable
        def render_page(checkpoint_error=None):
            cards=checkpoint_cards(request.user,food)
            if not viewing_current:
                for card in cards:
                    card['editable']=False
                    for field in card['form'].fields.values(): field.disabled=True
            if checkpoint_error:
                for card in cards:
                    if card['day']==checkpoint_error['day']:
                        card['form']=checkpoint_error['form']
                        for upload in card['upload_fields']:
                            upload['field']=card['form'][upload['field'].name]
            return render(request,'detail.html',{'food':food,'timing':gate_timing(food),'role_progress':role_progress(food),'view_stage':view_stage,'view_stage_label':dict(STAGES)[view_stage],'viewing_current':viewing_current,'gate0form':gate0form,'gate1form':gate1form,'gate2form':gate2form,'gate3form':gate3form,'checkpoint_cards':cards,'launch_schedule':launch_schedule(food),'gate3slots':gate3_file_slots(food),'gate2slots':gate2_file_slots(food),'gate1slots':gate1_file_slots(food),'gate0slots':file_slots(food),'stages':STAGES,'ingredient_form':ingredient_form,'packaging_form':packaging_form,'ingredient_unit_cost':food.unit_cost,**rights})
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'slot_upload':
                if food.stage not in ['gate0','gate1','gate2','gate3'] or not editable: return HttpResponseForbidden('Энэ үе шатыг засах эрх шаардлагатай.')
                slots,save_file = {'gate0':(FILE_SLOTS,save_slot_file),'gate1':(GATE1_FILE_SLOTS,save_gate1_file),'gate2':(GATE2_FILE_SLOTS,save_gate2_file),'gate3':(GATE3_FILE_SLOTS,save_gate3_file)}[food.stage]
                if food.stage=='gate2': slots=available_gate2_file_slots(food)
                key=request.POST.get('slot','')
                if key not in dict(slots): return HttpResponseForbidden('Файлын талбар тохирохгүй байна.')
                uploaded=request.FILES.get('slot_file')
                if uploaded and uploaded.size:
                    save_file(food,request.user,key,uploaded)
                else:
                    messages.error(request,'Хавсаргах файлаа сонгоно уу.')
            elif action in ['launch_dates','add','remove','save','gate1_cost_save','launch_checkpoint_save']:
                return HttpResponseForbidden('This legacy form is no longer part of the gate process.')
            elif action == 'comment':
                comment = request.POST.get('comment','').strip()
                if comment: Activity.objects.create(food=food,actor=request.user,text=comment[:2000])
            elif action in ['submit','qa_accept','approve','return','escalate']:
                error = transition(request.user,food,action,request.POST.get('note','').strip()[:1000])
                if error: messages.error(request,error)
            elif action == 'checkpoint_save':
                try: day=int(request.POST.get('day',''))
                except (ValueError,TypeError): return HttpResponseForbidden('Хяналтын өдөр тохирохгүй байна.')
                if not can_edit_checkpoint(request.user,food,day): return HttpResponseForbidden('Хугацаа болоогүй эсвэл энэ хяналтыг засах эрхгүй байна.')
                form=CheckpointForm(request.POST,request.FILES,day=day)
                if not form.is_valid():
                    checkpoint_error={'day':day,'form':form}
                    return render_page(checkpoint_error)
                for slot,key,label in checkpoint_slots(day):
                    uploaded=form.cleaned_data.get(key)
                    if uploaded:
                        Activity.objects.create(food=food,actor=request.user,
                            text='Launch GO / Day %s / %s' % (day,label),
                            attachment=uploaded,attachment_name=uploaded.name[:255],
                            attachment_stage='launch',attachment_slot=slot)
            elif not editable: return HttpResponseForbidden('Хөгжүүлэлт түгжигдсэн эсвэл өөр баг хариуцаж байна')
            elif action in ['gate1_packaging_save','gate2_packaging_save']:
                if food.stage not in ['gate1','gate2'] or action != food.stage+'_packaging_save':
                    return HttpResponseForbidden('Савлагааны зардлыг зөвхөн тухайн Gate 1 эсвэл Gate 2-д засварлана.')
                packaging_form=Gate1PackagingForm(request.POST,instance=food)
                if not packaging_form.is_valid(): return render_page()
                packaging_form.save()
                food.recipe_version=(food.recipe_version or 0)+1
                food.save(update_fields=['recipe_version','updated'])
                Activity.objects.create(food=food,actor=request.user,text=food.get_stage_display().split(' · ')[0]+' / Packaging cost updated')
            elif action in ['gate1_line_add','gate1_line_update','gate1_line_remove','gate2_line_add','gate2_line_update','gate2_line_remove']:
                if food.stage not in ['gate1','gate2'] or not action.startswith(food.stage+'_line_'):
                    return HttpResponseForbidden('Тооцооллыг зөвхөн тухайн Gate 1 эсвэл Gate 2-д засварлана.')
                stage_label=food.get_stage_display().split(' · ')[0]
                if action.endswith('_line_remove'):
                    line=get_object_or_404(RecipeLine,pk=request.POST.get('line'),food=food)
                    description=stage_label+' · Орц хасав: '+line.ingredient.name
                    line.delete()
                else:
                    line=get_object_or_404(RecipeLine,pk=request.POST.get('line'),food=food) if action.endswith('_line_update') else None
                    ingredient_form=Gate1LineForm(request.POST,instance=line,stage=food.stage)
                    if not ingredient_form.is_valid(): return render_page()
                    line=ingredient_form.save(commit=False)
                    line.food=food
                    line.save()
                    description=stage_label+' · Орцын тооцоо хадгалав: %s · %s %s × ₮%s' % (line.ingredient.name,line.quantity,line.ingredient.unit,line.unit_price)
                food.recipe_version=(food.recipe_version or 0)+1
                food.save(update_fields=['updated','recipe_version'])
                Activity.objects.create(food=food,actor=request.user,text=description)
            elif action == 'gate3_save':
                if food.stage != 'gate3': return HttpResponseForbidden('Зөвхөн Gate 3-д засварлана.')
                gate3form = Gate3Form(request.POST,initial=initial_gate3(food),food=food)
                if gate3form.is_valid():
                    save_gate3(food,gate3form.cleaned_data)
                    Activity.objects.create(food=food,actor=request.user,text='Gate 3 мэдээллийг шинэчлэв')
                    if gate3form.delay_reason_recommended:
                        messages.warning(request,'Нэвтрүүлэлт 7-оос олон хоногоор хоцорсон байна. Шалтгаан оруулахыг зөвлөж байна. Энэ нь хадгалахыг хориглохгүй.')
                else: return render_page()
            elif action == 'gate2_save':
                if food.stage != 'gate2': return HttpResponseForbidden('Зөвхөн Gate 2-д засварлана.')
                gate2form = Gate2Form(request.POST,initial=initial_gate2(food),food=food)
                if gate2form.is_valid():
                    save_gate2(food,gate2form.cleaned_data)
                    Activity.objects.create(food=food,actor=request.user,text='Gate 2 мэдээллийг шинэчлэв')
                else: return render_page()
            elif action == 'gate1_save':
                if food.stage != 'gate1': return HttpResponseForbidden('Зөвхөн Gate 1-д засварлана.')
                gate1form = Gate1Form(request.POST,initial=initial_gate1(food),food=food)
                if gate1form.is_valid():
                    save_gate1(food,gate1form.cleaned_data)
                    Activity.objects.create(food=food,actor=request.user,text='Gate 1 мэдээллийг шинэчлэв')
                else: return render_page()
            elif action == 'gate0_save':
                if food.stage != 'gate0': return HttpResponseForbidden('Зөвхөн Gate 0-д засварлана.')
                gate0form = Gate0Form(request.POST,initial=initial_brief(food),food=food)
                if gate0form.is_valid():
                    save_brief(food,gate0form.cleaned_data)
                    Activity.objects.create(food=food,actor=request.user,text='Gate 0 танилцуулгын мэдээллийг шинэчлэв')
                    if gate0form.launch_warning: messages.warning(request,'Нэвтрүүлэх огноо 30 хоногийн дотор байна. Энэ нь зөвхөн анхааруулга юм.')
                else: return render_page()
            return redirect('detail',pk=pk)
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="food-%s-costing.csv"' % food.pk
        writer = csv.writer(response)
        writer.writerow(['Орц','Нийлүүлэгч','Хэмжих нэгж','Багцад орох хэмжээ','Хадгалсан нэгжийн үнэ (₮)','Багцын өртөг (₮)'])
        for line in food.lines.select_related('ingredient__supplier'):
            name = line.ingredient.name
            supplier = line.ingredient.supplier.name
            writer.writerow(["'"+name if name.startswith(('=','+','-','@')) else name,"'"+supplier if supplier.startswith(('=','+','-','@')) else supplier,line.ingredient.unit,line.quantity,line.unit_price,line.cost])
        writer.writerow(['Unit ingredient cost (MNT)',food.unit_cost])
        return response
    return render_page()

@login_required
@require_http_methods(['GET','POST'])
def catalog(request,kind):
    supplier = kind == 'suppliers'
    formclass,model = (SupplierForm,Supplier) if supplier else (IngredientForm,Ingredient)
    form = formclass(request.POST or None)
    if request.method == 'POST':
        if not allowed(request.user,PURCHASING): return HttpResponseForbidden('Худалдан авалтын багийн эрх шаардлагатай')
        if form.is_valid():
            form.save()
            return redirect(kind)
    return render(request,'catalog.html',{'kind':kind,'catalog_title':'Нийлүүлэгчид' if supplier else 'Орц','add_title':'Нийлүүлэгч нэмэх' if supplier else 'Орц нэмэх','records':model.objects.all(),'form':form,'can_edit':allowed(request.user,PURCHASING)})

@login_required
@require_http_methods(['GET'])
def download_attachment(request,pk):
    activity = get_object_or_404(Activity,pk=pk)
    if not activity.attachment: raise Http404
    try:
        opened = activity.attachment.open('rb')
    except FileNotFoundError:
        raise Http404
    response = FileResponse(opened,as_attachment=True,filename=activity.attachment_name or 'attachment',content_type='application/octet-stream')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
