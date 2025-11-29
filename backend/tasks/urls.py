# tasks/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('add/', views.add_task, name='add_task'),
   path('add-bulk/', views.add_bulk_tasks, name='add_bulk_tasks'),
    path('analyze/', views.analyze_tasks, name='analyze_tasks'),
    path('clear/', views.clear_all_tasks, name='clear_all_tasks'),
    path('suggest/', views.suggest_tasks, name='suggest_tasks'),
    path('health/', views.health_check, name='health_check'),
    path('<str:task_id>/done/', views.mark_done, name='mark_done'),
]