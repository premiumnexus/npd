from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Food

def costing(food):
    return {'id':food.pk,'name':food.name,'stage':food.stage,'currency':'MNT','calculation_basis':'ingredient_quantity_per_product','unit_cost':str(round(food.unit_cost,2))}

class FoodList(APIView):
    def get(self,request):
        return Response([costing(food) for food in Food.objects.prefetch_related('lines').order_by('-updated')])

class FoodCost(APIView):
    def get(self,request,pk):
        return Response(costing(get_object_or_404(Food.objects.prefetch_related('lines'),pk=pk)))
