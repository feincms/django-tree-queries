from django.contrib import admin

from testapp import models
from tree_queries.admin import TreeAdmin


@admin.register(models.Model)
class ModelAdmin(TreeAdmin):
    position_field = "order"
    list_display = [*TreeAdmin.list_display, "name"]


@admin.register(models.UnorderedModel)
class UnorderedModelAdmin(TreeAdmin):
    list_display = [*TreeAdmin.list_display, "name"]


@admin.register(models.StringOrderedModel)
class StringOrderedModelAdmin(TreeAdmin):
    list_display = [*TreeAdmin.list_display, "name"]
