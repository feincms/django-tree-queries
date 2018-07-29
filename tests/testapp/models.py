from django.db import models

from tree_queries.models import TreeNode


class Model(TreeNode):
    position = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("position",)

    def __str__(self):
        return self.name


class UnorderedModel(TreeNode):
    pass
