from django.db import connections, models

from tree_queries.compiler import TreeQuery


def pk(of):
    return of.pk if hasattr(of, "pk") else of


class TreeQuerySet(models.QuerySet):
    def with_tree_fields(self):
        self.query.__class__ = TreeQuery
        return self

    def ancestors(self, of, *, include_self=False):
        if not hasattr(of, "tree_path"):
            of = self.with_tree_fields().get(pk=pk(of))

        ids = of.tree_path if include_self else of.tree_path[:-1]
        return (
            self.with_tree_fields()  # TODO tree fields not strictly required
            .filter(id__in=ids)
            .order_by("__tree.tree_depth")
        )

    def descendants(self, of, *, include_self=False):
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
