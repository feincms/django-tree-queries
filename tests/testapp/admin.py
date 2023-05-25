from django.contrib import admin

from testapp import models


@admin.register(models.Model)
class ModelAdmin(admin.ModelAdmin):
    list_display = ("name",)
