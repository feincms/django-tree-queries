from django.db import models

from tree_queries.query import TreeQuerySet


class TreeNode(models.Model):
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
