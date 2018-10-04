from __future__ import unicode_literals

from django.db import models

from .forms import TreeNodeChoiceField


class TreeNodeForeignKey(models.ForeignKey):
    def formfield(self, **kwargs):
        kwargs.setdefault("form_class", TreeNodeChoiceField)
        return super(TreeNodeForeignKey, self).formfield(**kwargs)
