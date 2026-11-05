from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from development import views
from development.api import FoodList, FoodCost
urlpatterns_api = [path('api/foods/',FoodList.as_view()),path('api/foods/<int:pk>/cost/',FoodCost.as_view())]
urlpatterns = [path('admin/',admin.site.urls),path('login/',auth.LoginView.as_view()),path('logout/',auth.LogoutView.as_view()),path('',views.dashboard,name='dashboard'),path('food/new/',views.create_food,name='create_food'),path('food/<int:pk>/',views.detail,name='detail'),path('suppliers/',views.catalog,{'kind':'suppliers'},name='suppliers'),path('ingredients/',views.catalog,{'kind':'ingredients'},name='ingredients')]
urlpatterns += urlpatterns_api
urlpatterns += [path('lessons/',views.lessons,name='lessons')]
urlpatterns += [path('recipes/',views.recipes,name='recipes')]
urlpatterns += [path('attachments/<int:pk>/',views.download_attachment,name='download_attachment')]
