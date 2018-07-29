from functools import wraps

from django.db import connections, models

from tree_queries.compiler import TreeQuery


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


class TreeQuerySet(models.QuerySet):
    def with_tree_fields(self):
        """
        Requests tree fields on this queryset
        """
        self.query.__class__ = TreeQuery
        return self

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
                where=['instr(__tree.tree_path, "x{:09x}") <> 0'.format(pk(of))]
            )

        if not include_self:
            return queryset.exclude(pk=pk(of))
        return queryset
