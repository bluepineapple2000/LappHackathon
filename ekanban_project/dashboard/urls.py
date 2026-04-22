from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('warenkorb/', views.warenkorb, name='warenkorb'),
    path('sensors/', views.sensors, name='sensors'),
    path('warnsystem/', views.warnsystem, name='warnsystem'),
]
