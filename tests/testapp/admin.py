from django.contrib import admin

from tree_queries import TranslatedFieldAdmin

from . import models


@admin.register(models.TestModel)
class TestModelAdmin(TranslatedFieldAdmin, admin.ModelAdmin):
    list_display = ("name", "other")
