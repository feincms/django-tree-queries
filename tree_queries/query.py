from django.db import models
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query


__all__ = ("TreeQuerySet", "TreeManager", "TreeBase")


class TreeQuery(Query):
    def chain(self, klass=None):
        assert (
            klass is None
        ), "Cannot change query type after with_tree_fields()"  # noqa
        return super().chain(TreeQuery)

    def get_compiler(self, using=None, connection=None):
        if connection is None:
            from django.db import connections

            connection = connections[using]
        return TreeCompiler(self, connection, using)


class TreeCompiler(SQLCompiler):
    CTE = """
    WITH RECURSIVE tree_table (
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
            tree_table.tree_depth + 1 AS tree_depth,
            tree_table.tree_path || T.{pk},
            tree_table.tree_ordering || {order_by},
            T."{pk}"
        FROM {db_table} T
        JOIN tree_table ON T."{parent}" = tree_table.tree_pk
    )
    """

    def as_sql(self, *args, **kwargs):
        params = {
            "parent": "parent_id",
            "pk": self.query.model._meta.pk.attname,
            "db_table": self.query.model._meta.db_table,
            "order_by": "position",
        }

        if "tree_table" not in self.query.extra_tables:

            def __maybe_alias(table):
                return (
                    self.query.table_map[table][0]
                    if table in self.query.table_map
                    else table
                )

            self.query.add_extra(
                select={
                    "tree_depth": "tree_table.tree_depth",
                    "tree_path": "tree_table.tree_path",
                    "tree_ordering": "tree_table.tree_ordering",
                },
                select_params=None,
                where=['tree_table.tree_pk = {db_table}."{pk}"'.format(**params)],
                params=None,
                tables=["tree_table"],
                order_by=["tree_ordering"],
            )

        sql = super().as_sql(*args, **kwargs)
        return ("".join([self.CTE.format(**params), sql[0]]), sql[1])


class TreeQuerySet(models.QuerySet):
    def with_tree_fields(self):
        self.query.__class__ = TreeQuery
        return self

    def ancestors(self, of, *, include_self=True):
        ids = of.tree_path if include_self else of.tree_path[:-1]
        return (
            self.with_tree_fields()  # TODO tree fields not strictly required
            .filter(id__in=ids)
            .order_by("tree_depth")
        )

    def descendants(self, of, *, include_self=True):
        queryset = self.with_tree_fields().extra(
            where=["{pk} = ANY(tree_table.tree_path)".format(pk=of.pk)]
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
