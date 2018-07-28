from django.db import models

from tree_queries.models import TreeNode


class Model(TreeNode):
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, related_name="children", blank=True, null=True
    )
    position = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("position",)

    def __str__(self):
        return self.name
