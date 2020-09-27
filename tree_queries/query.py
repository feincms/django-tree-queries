from __future__ import unicode_literals

from functools import wraps

from django.db import connections, models
from django.db.models.sql.query import Query

from tree_queries.compiler import SEPARATOR, TreeQuery


def pk(of):
    """
    Returns the primary key of the argument if it is an instance of a model, or
    the argument as-is otherwise
    """
    return of.pk if hasattr(of, "pk") else of


def positional(count):
    """
    Only allows ``count`` positional arguments to the decorated callable

    Will be removed as soon as we drop support for Python 2.
    """

    def _dec(fn):
        @wraps(fn)
        def _fn(*args, **kwargs):
            if len(args) > count:
                raise TypeError(
                    "Only %s positional argument%s allowed"
                    % (count, "" if count == 1 else "s")
                )
            return fn(*args, **kwargs)

        return _fn

    return _dec


class TreeManager(models.Manager):
    def get_queryset(self):
        queryset = super(TreeManager, self).get_queryset()
        return queryset.with_tree_fields() if self._with_tree_fields else queryset


class TreeQuerySet(models.QuerySet):
    def with_tree_fields(self, tree_fields=True):
        """
        Requests tree fields on this queryset

        Pass ``False`` to revert to a queryset without tree fields.
        """
        self.query.__class__ = TreeQuery if tree_fields else Query
        return self

    @positional(1)
    def as_manager(cls, with_tree_fields=False):
        class _TreeManager(TreeManager.from_queryset(cls)):
            # Only used in deconstruct:
            _built_with_as_manager = True
            # Set attribute on class, not on the instance so that the automatic
            # subclass generation used e.g. for relations also finds this
            # attribute.
            _with_tree_fields = with_tree_fields

        return _TreeManager()

    as_manager.queryset_only = True
    as_manager = classmethod(as_manager)

    @positional(2)
    def ancestors(self, of, include_self=False):
        """ancestors(self, of, *, include_self=False)
        Returns ancestors of the given node ordered from the root of the tree
        towards deeper levels, optionally including the node itself
        """
        if not hasattr(of, "tree_path"):
            of = self.with_tree_fields().get(pk=pk(of))

        ids = of.tree_path if include_self else of.tree_path[:-1]
        return (
            self.with_tree_fields()  # TODO tree fields not strictly required
            .filter(id__in=ids)
            .extra(order_by=["__tree.tree_depth"])
        )

    @positional(2)
    def descendants(self, of, include_self=False):
        """descendants(self, of, *, include_self=False)
        Returns descendants of the given node in depth-first order, optionally
        including and starting with the node itself
        """
        connection = connections[self.db]
        if connection.vendor == "postgresql":
            queryset = self.with_tree_fields().extra(
                where=["{pk} = ANY(__tree.tree_path)".format(pk=pk(of))]
            )

        else:
            queryset = self.with_tree_fields().extra(
                # NOTE! The representation of tree_path is NOT part of the API.
                where=[
                    'instr(__tree.tree_path, "{sep}{pk}{sep}") <> 0'.format(
                        pk=pk(of), sep=SEPARATOR
                    )
                ]
            )

        if not include_self:
            return queryset.exclude(pk=pk(of))
        return queryset
