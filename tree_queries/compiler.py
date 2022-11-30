from django.db import connections, models
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query


SEPARATOR = "\x1f"


class TreeQuery(Query):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_query()

    def _setup_query(self):
        """
        Run on initialization and at the end of chaining. Any attributes that
        would normally be set in __init__() should go here instead.
        """
        # Only add the sibling_order attribute if the query doesn't already have one to preserve cloning behavior
        if not hasattr(self, "sibling_order"):
            # Add an attribute to control the ordering of siblings within trees
            self.sibling_order = (
                self.model._meta.ordering[0]
                if self.model._meta.ordering
                else self.model._meta.pk.attname
            )

    def get_compiler(self, using=None, connection=None, **kwargs):
        # Copied from django/db/models/sql/query.py
        if using is None and connection is None:
            raise ValueError("Need either using or connection")
        if using:
            connection = connections[using]
        # Difference: Not connection.ops.compiler, but our own compiler which
        # adds the CTE.

        # **kwargs passes on elide_empty from Django 4.0 onwards
        return TreeCompiler(self, connection, using, **kwargs)


class TreeCompiler(SQLCompiler):
    CTE_POSTGRESQL_WITH_TEXT_ORDERING = """
    WITH RECURSIVE __tree (
        "tree_depth",
        "tree_path",
        "tree_ordering",
        "tree_pk"
    ) AS (
        SELECT
            0 AS tree_depth,
            array[T.{pk}] AS tree_path,
            array[{order_by}]::text[] AS tree_ordering,
            T."{pk}"
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1 AS tree_depth,
            __tree.tree_path || T.{pk},
            __tree.tree_ordering || {order_by}::text,
            T."{pk}"
        FROM {db_table} T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    CTE_POSTGRESQL_WITH_INTEGER_ORDERING = """
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

    CTE_MYSQL_WITH_INTEGER_ORDERING = """
    WITH RECURSIVE __tree(tree_depth, tree_path, tree_ordering, tree_pk) AS (
        SELECT
            0,
            -- Limit to max. 50 levels...
            CAST(CONCAT("{sep}", {pk}, "{sep}") AS char(1000)),
            CAST(CONCAT("{sep}", LPAD(CONCAT({order_by}, "{sep}"), 20, "0"))
                AS char(1000)),
            T.{pk}
        FROM {db_table} T
        WHERE T.{parent} IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1,
            CONCAT(__tree.tree_path, T2.{pk}, "{sep}"),
            CONCAT(__tree.tree_ordering, LPAD(CONCAT(T2.{order_by}, "{sep}"), 20, "0")),
            T2.{pk}
        FROM __tree, {db_table} T2
        WHERE __tree.tree_pk = T2.{parent}
    )
    """

    CTE_MYSQL_WITH_TEXT_ORDERING = """
    WITH RECURSIVE __tree(tree_depth, tree_path, tree_ordering, tree_pk) AS (
        SELECT
            0,
            -- Limit to max. 50 levels...
            CAST(CONCAT("{sep}", {pk}, "{sep}") AS char(1000)),
            CAST(CONCAT("{sep}", CONCAT({order_by}, "{sep}"))
                AS char(1000)),
            T.{pk}
        FROM {db_table} T
        WHERE T.{parent} IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1,
            CONCAT(__tree.tree_path, T2.{pk}, "{sep}"),
            CONCAT(__tree.tree_ordering, CONCAT(T2.{order_by}, "{sep}")),
            T2.{pk}
        FROM __tree, {db_table} T2
        WHERE __tree.tree_pk = T2.{parent}
    )
    """

    CTE_SQLITE3_WITH_INTEGER_ORDERING = """
    WITH RECURSIVE __tree(tree_depth, tree_path, tree_ordering, tree_pk) AS (
        SELECT
            0 tree_depth,
            printf("{sep}%%s{sep}", {pk}) tree_path,
            printf("{sep}%%020s{sep}", {order_by}) tree_ordering,
            T."{pk}" tree_pk
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1,
            __tree.tree_path || printf("%%s{sep}", T.{pk}),
            __tree.tree_ordering || printf("%%020s{sep}", T.{order_by}),
            T."{pk}"
        FROM {db_table} T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    CTE_SQLITE3_WITH_TEXT_ORDERING = """
    WITH RECURSIVE __tree(tree_depth, tree_path, tree_ordering, tree_pk) AS (
        SELECT
            0 tree_depth,
            printf("{sep}%%s{sep}", {pk}) tree_path,
            printf("{sep}%%s{sep}", {order_by}) tree_ordering,
            T."{pk}" tree_pk
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1,
            __tree.tree_path || printf("%%s{sep}", T.{pk}),
            __tree.tree_ordering || printf("%%s{sep}", T.{order_by}),
            T."{pk}"
        FROM {db_table} T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    def as_sql(self, *args, **kwargs):
        # The general idea is that if we have a summary query (e.g. .count())
        # then we do not want to ask Django to add the tree fields to the query
        # using .query.add_extra. The way to determine whether we have a
        # summary query on our hands is to check the is_summary attribute of
        # all annotations.
        #
        # A new case appeared in the GitHub issue #26: Queries using
        # .distinct().count() crashed. The reason for this is that Django uses
        # a distinct subquery *without* annotations -- the annotations are kept
        # in the surrounding query. Because of this we look at the distinct and
        # subquery attributes.
        #
        # I am not confident that this is the perfect way to approach this
        # problem but I just gotta stop worrying and trust the testsuite.
        skip_tree_fields = (
            self.query.distinct and self.query.subquery
        ) or any(  # pragma: no branch
            # OK if generator is not consumed completely
            annotation.is_summary
            for alias, annotation in self.query.annotations.items()
        )
        opts = self.query.model._meta

        params = {
            "parent": "parent_id",  # XXX Hardcoded.
            "pk": opts.pk.attname,
            "db_table": opts.db_table,
            "order_by": self.query.sibling_order,
            "sep": SEPARATOR,
        }

        if "__tree" not in self.query.extra_tables:  # pragma: no branch - unlikely
            tree_params = params.copy()

            # use aliased table name (U0, U1, U2)
            base_table = self.query.__dict__.get("base_table")
            if base_table is not None:
                tree_params["db_table"] = base_table

            # When using tree queries in subqueries our base table may use
            # an alias. Let's hope using the first alias is correct.
            aliases = self.query.table_map.get(tree_params["db_table"])
            if aliases:
                tree_params["db_table"] = aliases[0]

            self.query.add_extra(
                # Do not add extra fields to the select statement when it is a
                # summary query
                select={}
                if skip_tree_fields
                else {
                    "tree_depth": "__tree.tree_depth",
                    "tree_path": "__tree.tree_path",
                    "tree_ordering": "__tree.tree_ordering",
                },
                select_params=None,
                where=["__tree.tree_pk = {db_table}.{pk}".format(**tree_params)],
                params=None,
                tables=["__tree"],
                order_by=(
                    []
                    # Do not add ordering for aggregates, or if the ordering
                    # has already been specified using .extra()
                    if skip_tree_fields or self.query.extra_order_by
                    else ["__tree.tree_ordering"]  # DFS is the only true way
                ),
            )

        if self.connection.vendor == "postgresql":
            CTE = (
                self.CTE_POSTGRESQL_WITH_INTEGER_ORDERING
                if _ordered_by_integer(opts, params)
                else self.CTE_POSTGRESQL_WITH_TEXT_ORDERING
            )
        elif self.connection.vendor == "sqlite":
            CTE = (
                self.CTE_SQLITE3_WITH_INTEGER_ORDERING
                if _ordered_by_integer(opts, params)
                else self.CTE_SQLITE3_WITH_TEXT_ORDERING
            )
        elif self.connection.vendor == "mysql":
            CTE = (
                self.CTE_MYSQL_WITH_INTEGER_ORDERING
                if _ordered_by_integer(opts, params)
                else self.CTE_MYSQL_WITH_TEXT_ORDERING
            )
        sql_0, sql_1 = super().as_sql(*args, **kwargs)
        explain = ""
        if sql_0.startswith("EXPLAIN "):
            explain, sql_0 = sql_0.split(" ", 1)
        return ("".join([explain, CTE.format(**params), sql_0]), sql_1)

    def get_converters(self, expressions):
        converters = super().get_converters(expressions)
        for i, expression in enumerate(expressions):
            # We care about tree fields and annotations only
            if not hasattr(expression, "sql"):
                continue

            if expression.sql in {"__tree.tree_path", "__tree.tree_ordering"}:
                converters[i] = ([converter], expression)
        return converters


def converter(value, expression, connection, context=None):
    # context can be removed as soon as we only support Django>=2.0
    if isinstance(value, str):
        # MySQL/MariaDB and sqlite3 do not support arrays. Split the value on
        # the ASCII unit separator (chr(31)).
        # NOTE: The representation of array is NOT part of the API.
        value = value.split(SEPARATOR)[1:-1]

    try:
        # Either all values are convertible to int or don't bother
        return [int(v) for v in value]  # Maybe Field.to_python()?
    except ValueError:
        return value


def _ordered_by_integer(opts, params):
    try:
        ordering_field = opts.get_field(params["order_by"])
        return isinstance(ordering_field, models.IntegerField)
    except Exception:
        return False
