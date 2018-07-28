from django.db import connections
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query


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

    CTE_MYSQL = """
    WITH RECURSIVE __tree(tree_depth, tree_path, tree_ordering, tree_pk) AS (
        SELECT
            0,
            -- Limit to max. 10 levels...
            CAST(CONCAT("x", LPAD(HEX({pk}), 9, "0")) AS char(100)),
            CAST(CONCAT("x", LPAD(HEX({order_by}), 9, "0")) AS char(100)),
            T.{pk}
        FROM {db_table} T
        WHERE T.{parent} IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1,
            CONCAT(__tree.tree_path, "x", LPAD(HEX(T2.{pk}), 9, "0")),
            CONCAT(__tree.tree_ordering, "x", LPAD(HEX(T2.{order_by}), 9, "0")),
            T2.{pk}
        FROM __tree, {db_table} T2
        WHERE __tree.tree_pk = T2.{parent}
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

        is_summary = self.query._annotations and any(  # pragma: no branch
            # OK if generator is not consumed completely
            annotation.is_summary
            for alias, annotation in self.query._annotations.items()
        )
        opts = self.query.model._meta

        params = {
            "parent": "parent_id",
            "pk": opts.pk.attname,
            "db_table": opts.db_table,
            "order_by": opts.ordering[0] if opts.ordering else opts.pk.attname,
        }

        if "__tree" not in self.query.extra_tables:  # pragma: no branch - unlikely
            self.query.add_extra(
                select={}
                if is_summary
                else {
                    "tree_depth": "__tree.tree_depth",
                    "tree_path": "__tree.tree_path",
                    "tree_ordering": "__tree.tree_ordering",
                },
                select_params=None,
                where=["__tree.tree_pk = {db_table}.{pk}".format(**params)],
                params=None,
                tables=["__tree"],
                order_by=[] if is_summary else ["__tree.tree_ordering"],
            )

        sql = super().as_sql(*args, **kwargs)
        CTE = {
            "postgresql": self.CTE_POSTGRESQL,
            "sqlite": self.CTE_SQLITE3,
            "mysql": self.CTE_MYSQL,
        }[self.connection.vendor]
        return ("".join([CTE.format(**params), sql[0]]), sql[1])

    def get_converters(self, expressions):
        converters = super().get_converters(expressions)
        for i, expression in enumerate(expressions):
            if any(f in str(expression) for f in ("tree_path", "tree_ordering")):
                converters[i] = ([converter], expression)
        return converters


def converter(value, expression, connection, context=None):
    # context can be removed as soon as we only support Django>=2.0
    if not isinstance(value, str):
        return value
    array = []
    while value:
        array.append(int(value[1:10], 16))
        value = value[10:]
    return array
