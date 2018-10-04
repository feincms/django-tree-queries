from __future__ import unicode_literals

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .fields import TreeNodeForeignKey
from .query import TreeQuerySet


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
        Returns all ancestors of the current node

        See ``TreeQuerySet.descendants`` for details and optional arguments.
        """
        return self.__class__._default_manager.descendants(self, **kwargs)

    def clean(self):
        """
        Raises a validation error if saving this instance would result in loops
        in the tree structure
        """
        super(TreeNode, self).clean()
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
