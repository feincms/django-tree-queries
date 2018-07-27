from django.db import connections, models
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query


__all__ = ("TreeQuerySet", "TreeManager", "TreeBase")


class TreeQuery(Query):
    def get_compiler(self, using=None, connection=None):
        # Copied from django/db/models/sql/query.py
        if using is None and connection is None:
            raise ValueError("Need either using or connection")
        if connection is None:  # pragma: no branch - how would this happen?
            connection = connections[using]
        return TreeCompiler(self, connection, using)


class TreeCompiler(SQLCompiler):
    CTE_POSTGRESQL = """
    WITH RECURSIVE __tree (
        "tree_depth",
        "tree_path",
        "tree_ordering",
        "tree_pk"
    ) AS (
        SELECT
            0 AS tree_depth,
            array[T.{pk}] AS tree_path,
            array[{order_by}] AS tree_ordering,
            T."{pk}"
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1 AS tree_depth,
            __tree.tree_path || T.{pk},
            __tree.tree_ordering || {order_by},
            T."{pk}"
        FROM {db_table} T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    CTE_SQLITE3 = """
    WITH RECURSIVE __tree(tree_depth, tree_path, tree_ordering, tree_pk) AS (
        SELECT
            0 tree_depth,
            printf("x%09x", {pk}) tree_path,
            printf("x%09x", {order_by}) tree_ordering,
            T."{pk}" tree_pk
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1,
            __tree.tree_path || printf("x%09x", T.{pk}),
            __tree.tree_ordering || printf("x%09x", T.{order_by}),
            T."{pk}"
        FROM {db_table} T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    def as_sql(self, *args, **kwargs):

        if self.query._annotations and any(  # pragma: no branch
            # OK if generator is not consumed completely
            annotation.is_summary
            for alias, annotation in self.query._annotations.items()
        ):
            # No CTEs for summary queries
            return super().as_sql(*args, **kwargs)

        opts = self.query.model._meta

        params = {
            "parent": "parent_id",
            "pk": opts.pk.attname,
            "db_table": opts.db_table,
            "order_by": opts.ordering[0] if opts.ordering else opts.pk.attname,
        }

        if "__tree" not in self.query.extra_tables:  # pragma: no branch - unlikely
            self.query.add_extra(
                select={
                    "tree_depth": "__tree.tree_depth",
                    "tree_path": "__tree.tree_path",
                    "tree_ordering": "__tree.tree_ordering",
                },
                select_params=None,
                where=['__tree.tree_pk = {db_table}."{pk}"'.format(**params)],
                params=None,
                tables=["__tree"],
                order_by=["tree_ordering"],
            )

        sql = super().as_sql(*args, **kwargs)
        CTE = self.CTE_SQLITE3
        return ("".join([CTE.format(**params), sql[0]]), sql[1])

    def get_converters(self, expressions):
        converters = super().get_converters(expressions)
        for i, expression in enumerate(expressions):
            if any(f in str(expression) for f in ("tree_path", "tree_ordering")):
                converters[i] = ([converter], expression)
        return converters


def converter(value, expression, connection):
    if not isinstance(value, str):
        return value
    array = []
    while value:
        array.append(int(value[1:10], 16))
        value = value[10:]
    return array


class TreeQuerySet(models.QuerySet):
    def with_tree_fields(self):
        self.query.__class__ = TreeQuery
        return self

    def ancestors(self, of, *, include_self=True):
        if not hasattr(of, "tree_path"):
            of = self.with_tree_fields().get(pk=of.pk)

        ids = of.tree_path if include_self else of.tree_path[:-1]
        return (
            self.with_tree_fields()  # TODO tree fields not strictly required
            .filter(id__in=ids)
            .order_by("tree_depth")
        )

    def descendants(self, of, *, include_self=True):
        queryset = self.with_tree_fields().extra(
            # where=["{pk} = ANY(tree_path)".format(pk=of.pk)]
            where=['instr(tree_path, "x{:09x}") <> 0'.format(of.pk)]
        )
        if not include_self:
            return queryset.exclude(pk=of.pk)
        return queryset


class TreeManagerBase(models.Manager):
    def _ensure_parameters(self):
        # Compatibility with django-cte-forest
        pass


TreeManager = TreeManagerBase.from_queryset(TreeQuerySet)


class TreeBase(models.Model):
    objects = TreeManager()

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
