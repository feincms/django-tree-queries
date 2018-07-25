from django.db import models

from tree_queries.query import TreeManager, TreeBase


class Model(TreeBase):
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, related_name="children", blank=True, null=True
    )
    position = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=100)

    objects = TreeManager()
