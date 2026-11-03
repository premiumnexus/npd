from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Food

def costing(food):
    return {'id':food.pk,'name':food.name,'stage':food.stage,'currency':'MNT','batch_units':food.batch_units,'yield_percent':str(food.yield_percent),'effective_units':str(food.effective_units),'ingredient_batch_cost':str(food.ingredient_cost),'packaging_per_unit':str(food.packaging),'labor_per_unit':str(food.labor),'overhead_per_unit':str(food.overhead),'unit_cost':str(round(food.unit_cost,2)),'selling_price':str(food.selling_price),'gross_margin_percent':str(round(food.margin,2))}

class FoodList(APIView):
    def get(self,request):
        return Response([costing(food) for food in Food.objects.prefetch_related('lines').order_by('-updated')])

class FoodCost(APIView):
    def get(self,request,pk):
        return Response(costing(get_object_or_404(Food.objects.prefetch_related('lines'),pk=pk)))
