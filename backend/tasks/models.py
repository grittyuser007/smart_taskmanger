from django.db import models
from django.db.models import JSONField


class Task(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    importance = models.IntegerField(default=5)
    urgency = models.IntegerField(default=5)
    effort = models.IntegerField(default=5)
    due_date = models.DateField(blank=True, null=True)
    dependencies = JSONField(default=list, blank=True)
    is_done = models.BooleanField(default=False)
    priority_score = models.FloatField(default=0.0)
    score_breakdown = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-priority_score', '-created_at']

    def __str__(self):
        return self.title
