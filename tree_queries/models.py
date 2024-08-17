from django.core.exceptions import ValidationError
from django.db import models
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
    position = models.PositiveIntegerField(
        ("position"), editable=False, blank=True, null=True
    )

    objects = TreeQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["position", "-pk"]

    def save(self, *args, **kwargs):
        if self.parent_id:
            sibling_max_position = self.__class__.objects.filter(
                parent=self.parent
            ).aggregate(models.Max("position"))["position__max"]
            if sibling_max_position is not None:
                self.position = sibling_max_position + 1
            else:
                self.position = (self.parent.position or 0) + 1
        else:
            self.position = 0
        super().save(*args, **kwargs)

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
