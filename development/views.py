import csv
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Food, Supplier, Ingredient, RecipeLine, Activity, STAGES
from .forms import FoodForm, SupplierForm, IngredientForm, LineForm, LaunchDatesForm

def allowed(user, role):
    return user.is_superuser or user.groups.filter(name=role).exists()

@login_required
def dashboard(request):
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
    return render(request,'dashboard.html',{'foods':foods,'stages':STAGES,'total':Food.objects.count(),'review':Food.objects.filter(stage__in=['quality','costing']).count(),'ready':Food.objects.filter(stage='approved').count(),'suppliers_count':Supplier.objects.count(),'production_this_month':Food.objects.filter(production_date__gte=month_start,production_date__lt=next_month).count(),'market_launches_this_year':Food.objects.filter(market_launch_date__gte=today.replace(month=1,day=1),market_launch_date__lte=today).count(),'sla_due':Food.objects.filter(due__lte=today).exclude(stage='approved').count(),'stage_summary':stage_summary,'stats_today':today})

@login_required
@require_http_methods(['GET','POST'])
def create_food(request):
    if not allowed(request.user,'Product'): return HttpResponseForbidden('Бүтээгдэхүүний багийн эрх шаардлагатай')
    form = FoodForm(request.POST or None, initial={'owner':request.user})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            food = form.save()
            Activity.objects.create(food=food,actor=request.user,text='Хөгжүүлэлтийн танилцуулга үүсгэв')
        return redirect('detail',pk=food.pk)
    return render(request,'form.html',{'form':form,'title':'Шинэ хоолны хөгжүүлэлт эхлүүлэх','subtitle':'Сайн бүтээгдэхүүн тодорхой төлөвлөгөөнөөс эхэлнэ.'})

@login_required
@require_http_methods(['GET','POST'])
def detail(request,pk):
    with transaction.atomic():
        food = get_object_or_404(Food.objects.select_for_update(),pk=pk)
        form = LineForm()
        costform = FoodForm(instance=food)
        launchform = LaunchDatesForm(instance=food)
        can_manage_launch = request.user == food.owner or allowed(request.user,'Product')
        editable = food.stage != 'approved' and (request.user == food.owner or allowed(request.user,food.role))
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'attachment':
                uploaded = request.FILES.get('attachment')
                if not uploaded or not uploaded.size:
                    messages.error(request,'Хавсаргах файлаа сонгоно уу. Хоосон файл оруулах боломжгүй.')
                else:
                    Activity.objects.create(food=food,actor=request.user,text='Файл хавсаргав',attachment=uploaded,attachment_name=uploaded.name[:255],attachment_stage=food.stage)
            elif action == 'launch_dates':
                if not can_manage_launch: return HttpResponseForbidden('Бүтээгдэхүүний багийн эсвэл хариуцагчийн эрх шаардлагатай')
                launchform = LaunchDatesForm(request.POST,instance=food)
                if launchform.is_valid():
                    launchform.save()
                    Activity.objects.create(food=food,actor=request.user,text='Updated production and market launch dates: %s / %s' % (food.production_date or 'Тохируулаагүй',food.market_launch_date or 'Зах зээлд гараагүй'))
                else:
                    messages.error(request, ' '.join(str(error) for errors in launchform.errors.values() for error in errors))
            elif action == 'comment':
                comment = request.POST.get('comment','').strip()
                if comment: Activity.objects.create(food=food,actor=request.user,text=comment[:2000])
            elif action in ['advance','return']:
                if not allowed(request.user,food.role): return HttpResponseForbidden('Энэ үе шатыг хариуцах эрх шаардлагатай: '+food.role)
                keys = [s[0] for s in STAGES]
                index = keys.index(food.stage)
                if food.stage == 'approved': return HttpResponseForbidden('Батлагдсан хөгжүүлэлтийг засах боломжгүй')
                if action == 'advance' and food.stage != 'concept' and not food.lines.exists():
                    messages.error(request,'Үргэлжлүүлэхийн өмнө дор хаяж нэг орц нэмнэ үү.')
                elif action == 'advance' and food.stage == 'costing' and food.selling_price <= food.unit_cost:
                    messages.error(request,'Эцэслэн батлахын өмнө борлуулах үнэ нэгжийн өртгөөс өндөр байх ёстой.')
                elif action == 'return' and not request.POST.get('note','').strip():
                    messages.error(request,'Буцаах шалтгаанаа оруулна уу.')
                else:
                    previous = food.get_stage_display()
                    food.stage = keys[min(index+1,len(keys)-1)] if action == 'advance' else keys[max(index-1,0)]
                    food.save()
                    Activity.objects.create(food=food,actor=request.user,text='%s → %s. %s' % (previous,food.get_stage_display(),request.POST.get('note','')[:1000]))
            elif not editable: return HttpResponseForbidden('Хөгжүүлэлт түгжигдсэн эсвэл өөр баг хариуцаж байна')
            elif action == 'add':
                form = LineForm(request.POST)
                if form.is_valid():
                    line = form.save(commit=False)
                    line.food = food
                    line.unit_price = line.ingredient.price
                    line.save()
                    Activity.objects.create(food=food,actor=request.user,text='Орц нэмэв: '+line.ingredient.name)
                else: return render(request,'detail.html',{'food':food,'lineform':form,'costform':costform,'stages':STAGES,'editable':editable,'can_advance':allowed(request.user,food.role)})
            elif action == 'remove':
                line = get_object_or_404(RecipeLine,pk=request.POST.get('line'),food=food)
                Activity.objects.create(food=food,actor=request.user,text='Орц хасав: '+line.ingredient.name)
                line.delete()
            elif action == 'save':
                costform = FoodForm(request.POST,instance=food)
                if costform.is_valid():
                    costform.save()
                    Activity.objects.create(food=food,actor=request.user,text='Хөгжүүлэлт ба өртгийн мэдээллийг шинэчлэв')
                else: return render(request,'detail.html',{'food':food,'lineform':form,'costform':costform,'stages':STAGES,'editable':editable,'can_advance':allowed(request.user,food.role)})
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
        for label,value in [('Бэлэн бүтээгдэхүүний тоо',food.effective_units),('Нэгжийн орцын өртөг',food.ingredient_cost/food.effective_units),('Нэгжийн савлагааны зардал',food.packaging),('Нэгжийн хөдөлмөрийн зардал',food.labor),('Нэгжийн нэмэгдэл зардал',food.overhead),('Нэгжийн нийт өртөг',food.unit_cost),('Борлуулах үнэ',food.selling_price),('Нийт ашгийн хувь (%)',food.margin)]: writer.writerow([label,value])
        return response
    return render(request,'detail.html',{'food':food,'lineform':form,'costform':costform,'launchform':launchform,'can_manage_launch':can_manage_launch,'stages':STAGES,'editable':editable,'can_advance':allowed(request.user,food.role) and food.stage != 'approved'})

@login_required
@require_http_methods(['GET','POST'])
def catalog(request,kind):
    supplier = kind == 'suppliers'
    formclass,model = (SupplierForm,Supplier) if supplier else (IngredientForm,Ingredient)
    form = formclass(request.POST or None)
    if request.method == 'POST':
        if not allowed(request.user,'Procurement'): return HttpResponseForbidden('Худалдан авалтын багийн эрх шаардлагатай')
        if form.is_valid():
            form.save()
            return redirect(kind)
    return render(request,'catalog.html',{'kind':kind,'catalog_title':'Нийлүүлэгчид' if supplier else 'Орц','add_title':'Нийлүүлэгч нэмэх' if supplier else 'Орц нэмэх','records':model.objects.all(),'form':form,'can_edit':allowed(request.user,'Procurement')})

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
