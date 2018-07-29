from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from tree_queries.query import TreeQuerySet


class TreeNode(models.Model):
    parent = models.ForeignKey(
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

    def ancestors(self, *, include_self=False):
        return self.__class__._default_manager.ancestors(
            self, include_self=include_self
        )

    def descendants(self, *, include_self=False):
        return self.__class__._default_manager.descendants(
            self, include_self=include_self
        )

    def clean(self):
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
