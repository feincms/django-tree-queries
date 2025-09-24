import uuid

from django.db import models

from tree_queries.models import TreeNode
from tree_queries.query import TreeQuerySet


class Model(TreeNode):
    custom_id = models.AutoField(primary_key=True)
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("order",)

    def __str__(self):
        return self.name


class UnorderedModel(TreeNode):
    name = models.CharField(max_length=100)


class StringOrderedModel(TreeNode):
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("name",)
        unique_together = (("name", "parent"),)

    def __str__(self):
        return self.name


class AlwaysTreeQueryModelCategory(models.Model):
    def __str__(self):
        return ""


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

    def __str__(self):
        return ""


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

    def __str__(self):
        return self.name


class UUIDModel(TreeNode):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class MultiOrderedModel(TreeNode):
    first_position = models.PositiveIntegerField(default=0)
    second_position = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("first_position",)

    def __str__(self):
        return self.name


class TreeNodeIsOptional(models.Model):
    parent = models.ForeignKey("self", null=True, on_delete=models.CASCADE)

    objects = TreeQuerySet.as_manager()

    def __str__(self):
        return ""


class InheritParentModel(TreeNode):
    name = models.CharField(max_length=100)


class InheritChildModel(InheritParentModel):
    pass


class InheritGrandChildModel(InheritChildModel):
    pass


class InheritAbstractChildModel(InheritParentModel):
    class Meta:
        abstract = True


class InheritConcreteGrandChildModel(InheritAbstractChildModel):
    pass


class RelatedOrderModel(TreeNode):
    name = models.CharField(max_length=100)


class OneToOneRelatedOrder(models.Model):
    relatedmodel = models.OneToOneField(
        RelatedOrderModel,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="related",
    )
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return ""


# Models for testing add_related_count functionality
class Region(TreeNode):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Site(models.Model):
    name = models.CharField(max_length=100)
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name="sites",
    )

    def __str__(self):
        return self.name
