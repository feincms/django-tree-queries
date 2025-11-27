from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from tree_queries.fields import TreeNodeForeignKey
from tree_queries.query import TreeQuerySet


class TreeNode(models.Model):
    parent = TreeNodeForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        verbose_name=_("parent"),
        related_name="children",
    )

    objects = TreeQuerySet.as_manager()

    class Meta:
        abstract = True

    def ancestors(self, **kwargs):
        """
        Returns all ancestors of the current node

        See ``TreeQuerySet.ancestors`` for details and optional arguments.
        """
        return self.__class__._default_manager.ancestors(self, **kwargs)

    def descendants(self, **kwargs):
        """
        Returns all descendants of the current node

        See ``TreeQuerySet.descendants`` for details and optional arguments.
        """
        return self.__class__._default_manager.descendants(self, **kwargs)

    def clean(self):
        """
        Raises a validation error if saving this instance would result in loops
        in the tree structure
        """
        super().clean()
        if (
            self.parent_id
            and self.pk
            and (
                self.__class__._default_manager.ancestors(
                    self.parent_id, include_self=True
                )
                .filter(pk=self.pk)
                .exists()
            )
        ):
            raise ValidationError(_("A node cannot be made a descendant of itself."))


class OrderableTreeNode(TreeNode):
    """
    A TreeNode with automatic position management for consistent sibling ordering.

    This mixin provides automatic position value assignment when creating new nodes,
    ensuring siblings are properly ordered. When a node is saved without an explicit
    position value, it automatically receives a position 10 units higher than the
    maximum position among its siblings.

    Usage:
        class Category(OrderableTreeNode):
            name = models.CharField(max_length=100)
            # position field and ordering are provided by OrderableTreeNode

    The position field increments by 10 (rather than 1) to make it explicit that
    the position values themselves have no inherent meaning - they are purely for
    relative ordering, not a sibling counter or index. This approach is identical
    to the one used in feincms3's AbstractPage.
    """

    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        abstract = True
        ordering = ["position"]

    def save(self, *args, **kwargs):
        """
        Automatically assigns a position value if not set.

        If the position is 0 (the default), calculates a new position by finding
        the maximum position among siblings and adding 10.
        """
        if not self.position:
            self.position = 10 + (
                self.__class__._default_manager.filter(parent_id=self.parent_id)
                .order_by()
                .aggregate(p=Max("position"))["p"]
                or 0
            )
        super().save(*args, **kwargs)

    save.alters_data = True
