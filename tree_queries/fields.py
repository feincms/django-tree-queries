from django.db import models

from tree_queries.forms import TreeNodeChoiceField


class TreeNodeForeignKey(models.ForeignKey):
    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return (name, "django.db.models.ForeignKey", args, kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault("form_class", TreeNodeChoiceField)
        return super().formfield(**kwargs)
