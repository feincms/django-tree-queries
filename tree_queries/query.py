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
    WITH RECURSIVE {cte} ("{depth}", "{path}", "{ordering}", "{pk}") AS (
        SELECT
            1 AS depth,
            array[T.{pk_path}] AS {path},
            array[{order}] AS {ordering},
            T."{pk}"
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            {cte}.{depth} + 1 AS {depth},
            {cte}.{path} || T.{pk_path},
            {cte}.{ordering} || {order},
            T."{pk}"
        FROM {db_table} T
        JOIN {cte} ON T."{parent}" = {cte}."{pk}"
    )
    """

    def as_sql(self, *args, **kwargs):
        if "cte" not in self.query.extra_tables:

            def __maybe_alias(table):
                return (
                    self.query.table_map[table][0]
                    if table in self.query.table_map
                    else table
                )

            self.query.add_extra(
                select={
                    "depth": "{cte}.{depth}".format(cte="cte", depth="depth"),
                    "cte_path": "{cte}.{path}".format(cte="cte", path="cte_path"),
                    "ordering": "{cte}.{ordering}".format(
                        cte="cte", ordering="ordering"
                    ),
                },
                select_params=None,
                where=[
                    '{cte}."{pk}" = {table}."{pk}"'.format(
                        cte="cte",
                        pk=self.query.model._meta.pk.attname,
                        table=__maybe_alias(self.query.model._meta.db_table),
                    )
                ],
                params=None,
                tables=["cte"],
                order_by=["ordering"],
            )

        # cte_columns = (
        #     "depth",
        #     "cte_path",
        #     # "ordering",
        # )

        pk_path = self.query.model._meta.pk.attname

        sql = super().as_sql(*args, **kwargs)
        return (
            "".join(
                [
                    self.CTE.format(
                        cte="cte",
                        depth="depth",
                        path="cte_path",
                        parent="parent_id",
                        pk=self.query.model._meta.pk.attname,
                        pk_path=pk_path,
                        db_table=self.query.model._meta.db_table,
                        ordering="ordering",
                        order="position",
                    ),
                    sql[0],
                ]
            ),
            sql[1],
        )


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
