from django.contrib import admin
from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'importance', 'urgency', 'effort', 'deadline', 'is_done', 'priority_score', 'created_at']
    list_filter = ['is_done', 'importance', 'urgency', 'created_at']
    search_fields = ['title', 'description']
    ordering = ['-priority_score', '-created_at']
    readonly_fields = ['priority_score', 'score_breakdown', 'created_at', 'updated_at', 'completed_at']
