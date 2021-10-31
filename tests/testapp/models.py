import uuid

from django.db import models

from tree_queries.models import TreeNode
from tree_queries.query import TreeQuerySet


class Model(TreeNode):
    custom_id = models.AutoField(primary_key=True)
    position = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("position",)

    def __str__(self):
        return self.name


class UnorderedModel(TreeNode):
    pass


class StringOrderedModel(TreeNode):
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("name",)
        unique_together = (("name", "parent"),)

    def __str__(self):
        return self.name


class AlwaysTreeQueryModelCategory(models.Model):
    pass


class ReferenceModel(models.Model):
    position = models.PositiveIntegerField(default=0)
    tree_field = models.ForeignKey(
        Model,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("position",)


class AlwaysTreeQueryModel(TreeNode):
    name = models.CharField(max_length=100)
    related = models.ManyToManyField("self", symmetrical=True)
    category = models.ForeignKey(
        AlwaysTreeQueryModelCategory,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="instances",
    )

    objects = TreeQuerySet.as_manager(with_tree_fields=True)

    class Meta:
        base_manager_name = "objects"


class UUIDModel(TreeNode):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)

    objects = TreeQuerySet.as_manager(with_tree_fields=True)

    def __str__(self):
        return self.name
