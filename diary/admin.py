from django.contrib import admin
from .models import *

@admin.register(DiaryEntry)
class DiaryEntryAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'created_at', 'language', 'word_count', 'is_processed']
    list_filter = ['language', 'is_processed', 'created_at']
    search_fields = ['user__username', 'text']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

@admin.register(VoiceToText)
class VoiceToTextAdmin(admin.ModelAdmin):
    list_display = ['entry', 'original_duration', 'processing_time']
    readonly_fields = ['processing_time']

@admin.register(KeyPoint)
class KeyPointAdmin(admin.ModelAdmin):
    list_display = ['entry', 'type', 'text', 'confidence']
    list_filter = ['type', 'confidence']
    search_fields = ['text']

@admin.register(PsychoAnalysis)
class PsychoAnalysisAdmin(admin.ModelAdmin):
    list_display = ['entry', 'mood_score', 'processing_time', 'insights_extracted']
    list_filter = ['mood_score']
    readonly_fields = ['processing_time', 'insights_extracted']

@admin.register(UserInsight)
class UserInsightAdmin(admin.ModelAdmin):
    list_display = ['user', 'text', 'category', 'weight', 'last_mentioned']
    list_filter = ['category', 'weight']
    search_fields = ['user__username', 'text']
    readonly_fields = ['first_mentioned']

@admin.register(TherapyProgress)
class TherapyProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'date', 'avg_mood', 'insights_count', 'tasks_completed']
    list_filter = ['date']
    date_hierarchy = 'date'
    readonly_fields = ['date']

@admin.register(TherapyTask)
class TherapyTaskAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'type', 'status', 'assigned_at']
    list_filter = ['type', 'status', 'assigned_at']
    search_fields = ['user__username', 'title']
    readonly_fields = ['assigned_at']

@admin.register(TaskCompletion)
class TaskCompletionAdmin(admin.ModelAdmin):
    list_display = ['task', 'created_at', 'time_spent']
    readonly_fields = ['created_at']

@admin.register(TaskAnalysis)
class TaskAnalysisAdmin(admin.ModelAdmin):
    list_display = ['completion', 'quality_score', 'insights_updated']
    list_filter = ['quality_score', 'insights_updated']

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity_type', 'timestamp']
    list_filter = ['activity_type', 'timestamp']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'