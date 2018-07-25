from django.db import models
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query


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
    WITH RECURSIVE {cte_table} ("{depth}", "{path}", "{ordering}", "{pk}") AS (
        SELECT
            1 AS depth,
            array[T.{pk_path}] AS {path},
            array[{order}] AS {ordering},
            T."{pk}"
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            {cte_table}.{depth} + 1 AS {depth},
            {cte_table}.{path} || T.{pk_path},
            {cte_table}.{ordering} || {order},
            T."{pk}"
        FROM {db_table} T
        JOIN {cte_table} ON T."{parent}" = {cte_table}."{pk}"
    )
    """

    def as_sql(self, *args, **kwargs):
        pk_path = self.query.model._meta.pk.attname
        params = {
            "cte_table": "cte_table",
            "depth": "depth",
            "path": "cte_path",
            "parent": "parent_id",
            "pk": self.query.model._meta.pk.attname,
            "pk_path": pk_path,
            "db_table": self.query.model._meta.db_table,
            "ordering": "ordering",
            "order": "position",
        }

        if params["cte_table"] not in self.query.extra_tables:

            def __maybe_alias(table):
                return (
                    self.query.table_map[table][0]
                    if table in self.query.table_map
                    else table
                )

            self.query.add_extra(
                select={
                    "depth": "{cte_table}.{depth}".format(**params),
                    "cte_path": "{cte_table}.{path}".format(**params),
                    "ordering": "{cte_table}.{ordering}".format(**params),
                },
                select_params=None,
                where=['{cte_table}."{pk}" = {db_table}."{pk}"'.format(**params)],
                params=None,
                tables=[params["cte_table"]],
                order_by=["ordering"],
            )

        # cte_columns = (
        #     "depth",
        #     "cte_path",
        #     # "ordering",
        # )

        sql = super().as_sql(*args, **kwargs)
        return ("".join([self.CTE.format(**params), sql[0]]), sql[1])


class TreeQuerySet(models.QuerySet):
    def with_tree_fields(self):
        self.query.__class__ = TreeQuery
        return self


class TreeManagerBase(models.Manager):
    def _ensure_parameters(self):
        # Compatibility with django-cte-forest
        pass


TreeManager = TreeManagerBase.from_queryset(TreeQuerySet)


class TreeBase(models.Model):
    class Meta:
        abstract = True

    def ancestors(self):
        return (
            self.__class__.objects.with_tree_fields()
            .filter(id__in=self.cte_path)
            .order_by("depth")
        )
