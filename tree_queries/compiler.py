from django.db import connections
from django.db.models import Value
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query


SEPARATOR = "\x1f"


def _find_tree_model(cls):
    return cls._meta.get_field("parent").model


class TreeQuery(Query):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_query()

    def _setup_query(self):
        """
        Run on initialization and at the end of chaining. Any attributes that
        would normally be set in __init__() should go here instead.
        """
        # We add the variables for `sibling_order` and `pre_filter` here so they
        # act as instance variables which do not persist between user queries
        # the way class variables do

        # Only add the sibling_order attribute if the query doesn't already have one to preserve cloning behavior
        if not hasattr(self, "sibling_order"):
            # Add an attribute to control the ordering of siblings within trees
            opts = _find_tree_model(self.model)._meta
            self.sibling_order = (
                opts.ordering
                if opts.ordering
                else opts.pk.attname
            )

        # Only add the pre_filter attribute if the query doesn't already have one to preserve cloning behavior
        if not hasattr(self, "pre_filter"):
            self.pre_filter = []


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

    def get_sibling_order(self):
        return self.sibling_order

    def get_pre_filter(self):
        return self.pre_filter

class TreeCompiler(SQLCompiler):
    CTE_POSTGRESQL = """
    WITH RECURSIVE __rank_table(
        "{pk}",
        "{parent}",
        "rank_order"
    ) AS (
        SELECT
            {rank_pk},
            {rank_parent},
            ROW_NUMBER() OVER (ORDER BY {rank_order_by})
        FROM {rank_from}
        {pre_filter}
    ),
    __tree (
        "tree_depth",
        "tree_path",
        "tree_ordering",
        "tree_pk"
    ) AS (
        SELECT
            0 AS tree_depth,
            array[T.{pk}] AS tree_path,
            array[T.rank_order] AS tree_ordering,
            T."{pk}"
        FROM __rank_table T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1 AS tree_depth,
            __tree.tree_path || T.{pk},
            __tree.tree_ordering || T.rank_order,
            T."{pk}"
        FROM __rank_table T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    CTE_MYSQL = """
    WITH RECURSIVE __rank_table({pk}, {parent}, rank_order) AS (
        SELECT
            {rank_pk},
            {rank_parent},
            ROW_NUMBER() OVER (ORDER BY {rank_order_by})
        FROM {rank_from}
        {pre_filter}
    ),
    __tree(tree_depth, tree_path, tree_ordering, tree_pk) AS (
        SELECT
            0,
            -- Limit to max. 50 levels...
            CAST(CONCAT("{sep}", {pk}, "{sep}") AS char(1000)),
            CAST(CONCAT("{sep}", LPAD(CONCAT(T.rank_order, "{sep}"), 20, "0"))
                AS char(1000)),
            T.{pk}
        FROM __rank_table T
        WHERE T.{parent} IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1,
            CONCAT(__tree.tree_path, T2.{pk}, "{sep}"),
            CONCAT(__tree.tree_ordering, LPAD(CONCAT(T2.rank_order, "{sep}"), 20, "0")),
            T2.{pk}
        FROM __tree, __rank_table T2
        WHERE __tree.tree_pk = T2.{parent}
    )
    """

    CTE_SQLITE3 = """
    WITH RECURSIVE __rank_table({pk}, {parent}, rank_order) AS (
        SELECT
            {rank_pk},
            {rank_parent},
            row_number() OVER (ORDER BY {rank_order_by})
        FROM {rank_from}
        {pre_filter}
    ),
    __tree(tree_depth, tree_path, tree_ordering, tree_pk) AS (
        SELECT
            0 tree_depth,
            printf("{sep}%%s{sep}", {pk}) tree_path,
            printf("{sep}%%020s{sep}", T.rank_order) tree_ordering,
            T."{pk}" tree_pk
        FROM __rank_table T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            __tree.tree_depth + 1,
            __tree.tree_path || printf("%%s{sep}", T.{pk}),
            __tree.tree_ordering || printf("%%020s{sep}", T.rank_order),
            T."{pk}"
        FROM __rank_table T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    def get_rank_table_params(self):
        """
        This method uses a simple django queryset to generate sql
        that can be used to create the __rank_table that pre-filters
        and orders siblings. This is done so that any joins required
        by order_by or filter/exclude are pre-calculated by django
        """
        # Get can validate sibling_order
        sibling_order = self.query.get_sibling_order()

        if isinstance(sibling_order, (list, tuple)):
            order_fields = sibling_order
        elif isinstance(sibling_order, str):
            order_fields = [sibling_order]
        else:
            raise ValueError(
                "Sibling order must be a string or a list or tuple of strings."
            )
        
        # Get pre_filter
        pre_filter = self.query.get_pre_filter()

        # Use Django to make a SQL query that can be repurposed for __rank_table
        base_query = _find_tree_model(self.query.model).objects.only("pk", "parent")

        # Add pre_filters if they exist
        if pre_filter:
            # Apply filters and excludes to the query in the order provided by the user
            for is_filter, filter_fields in pre_filter:
                if is_filter:
                    base_query = base_query.filter(**filter_fields)
                else:
                    base_query = base_query.exclude(**filter_fields)

        # Apply sibling_order
        base_query = base_query.order_by(*order_fields).query

        # Get SQL and parameters
        base_compiler = SQLCompiler(base_query, self.connection, None)
        base_sql, base_params = base_compiler.as_sql()

        # Split sql on the last ORDER BY to get the rank_order param
        head, sep, tail = base_sql.rpartition("ORDER BY")

        # Add rank_order_by to params
        rank_table_params = {
            "rank_order_by": tail.strip(),
        }

        # Split on the first WHERE if present to get the pre_filter param
        if pre_filter:
            head, sep, tail = head.partition("WHERE")
            rank_table_params["pre_filter"] = "WHERE " + tail.strip() # Note the space after WHERE
        else:
            rank_table_params["pre_filter"] = ""

        # Split on the first FROM to get any joins etc.
        head, sep, tail = head.partition("FROM")
        rank_table_params["rank_from"] = tail.strip()

        # Identify the parent and primary key fields
        head, sep, tail = head.partition("SELECT")
        for field in tail.split(","):
            if "parent_id" in field:  # XXX Taking advantage of Hardcoded.
                rank_table_params["rank_parent"] = field.strip()
            else:
                rank_table_params["rank_pk"] = field.strip()

        return rank_table_params, base_params

    def as_sql(self, *args, **kwargs):
        # Try detecting if we're used in a EXISTS(1 as "a") subquery like
        # Django's sql.Query.exists() generates. If we detect such a query
        # we're skipping the tree generation since it's not necessary in the
        # best case and references unused table aliases (leading to SQL errors)
        # in the worst case. See GitHub issue #63.
        if (
            self.query.subquery
            and (ann := self.query.annotations)
            and ann == {"a": Value(1)}
        ):
            return super().as_sql(*args, **kwargs)

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
        opts = _find_tree_model(self.query.model)._meta

        params = {
            "parent": "parent_id",  # XXX Hardcoded.
            "pk": opts.pk.attname,
            "db_table": opts.db_table,
            "sep": SEPARATOR,
        }

        # Get params needed by the rank_table
        rank_table_params, rank_table_sql_params = self.get_rank_table_params()
        params.update(rank_table_params)

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
                # summary query or when using .values() or .values_list()
                select={}
                if skip_tree_fields or self.query.values_select
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
            cte = self.CTE_POSTGRESQL
        elif self.connection.vendor == "sqlite":
            cte = self.CTE_SQLITE3
        elif self.connection.vendor == "mysql":
            cte = self.CTE_MYSQL
        sql_0, sql_1 = super().as_sql(*args, **kwargs)
        explain = ""
        if sql_0.startswith("EXPLAIN "):
            explain, sql_0 = sql_0.split(" ", 1)

        # Pass any additional rank table sql paramaters so that the db backend can handle them.
        # This only works because we know that the CTE is at the start of the query.
        return ("".join([explain, cte.format(**params), sql_0]), rank_table_sql_params + sql_1)

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
