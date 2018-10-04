from __future__ import unicode_literals

from django import forms


class TreeNodeIndentedLabels(object):
    def __init__(self, queryset, *args, **kwargs):
        if hasattr(queryset, "with_tree_fields"):
            queryset = queryset.with_tree_fields()
        if "label_from_instance" in kwargs:
            self.label_from_instance = kwargs.pop("label_from_instance")
        super(TreeNodeIndentedLabels, self).__init__(queryset, *args, **kwargs)

    def label_from_instance(self, obj):
        depth = getattr(obj, "tree_depth", 0)
        return "{}{}".format("".join(["--- "] * depth), obj)


class TreeNodeChoiceField(TreeNodeIndentedLabels, forms.ModelChoiceField):
    pass


class TreeNodeMultipleChoiceField(
    TreeNodeIndentedLabels, forms.ModelMultipleChoiceField
):
    pass
