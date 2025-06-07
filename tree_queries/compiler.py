import django
from django.db import connections
from django.db.models import Expression, F, QuerySet, Value, Window
from django.db.models.functions import RowNumber
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
        # We add the variables for `sibling_order` and `rank_table_query` here so they
        # act as instance variables which do not persist between user queries
        # the way class variables do

        # Only add the sibling_order attribute if the query doesn't already have one to preserve cloning behavior
        if not hasattr(self, "sibling_order"):
            # Add an attribute to control the ordering of siblings within trees
            opts = _find_tree_model(self.model)._meta
            self.sibling_order = opts.ordering if opts.ordering else opts.pk.attname

        # Only add the rank_table_query attribute if the query doesn't already have one to preserve cloning behavior
        if not hasattr(self, "rank_table_query"):
            # Create a default QuerySet for the rank_table to use
            # so we can avoid recursion
            self.rank_table_query = QuerySet(model=_find_tree_model(self.model))

        if not hasattr(self, "tree_fields"):
            self.tree_fields = {}

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

    def get_rank_table_query(self):
        return self.rank_table_query

    def get_tree_fields(self):
        return self.tree_fields


class TreeCompiler(SQLCompiler):
    CTE_POSTGRESQL = """
    WITH RECURSIVE __rank_table(
        {tree_fields_columns}
        "{pk}",
        "{parent}",
        "rank_order"
    ) AS (
        {rank_table}
    ),
    __tree (
        {tree_fields_names}
        "tree_depth",
        "tree_path",
        "tree_ordering",
        "tree_pk"
    ) AS (
        SELECT
            {tree_fields_initial}
            0,
            array[T.{pk}],
            array[T.rank_order],
            T."{pk}"
        FROM __rank_table T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            {tree_fields_recursive}
            __tree.tree_depth + 1,
            __tree.tree_path || T.{pk},
            __tree.tree_ordering || T.rank_order,
            T."{pk}"
        FROM __rank_table T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    CTE_MYSQL = """
    WITH RECURSIVE __rank_table(
        {tree_fields_columns}
        {pk},
        {parent},
        rank_order
    ) AS (
        {rank_table}
    ),
    __tree(
        {tree_fields_names}
        tree_depth,
        tree_path,
        tree_ordering,
        tree_pk
    ) AS (
        SELECT
            {tree_fields_initial}
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
            {tree_fields_recursive}
            __tree.tree_depth + 1,
            CONCAT(__tree.tree_path, T2.{pk}, "{sep}"),
            CONCAT(__tree.tree_ordering, LPAD(CONCAT(T2.rank_order, "{sep}"), 20, "0")),
            T2.{pk}
        FROM __tree, __rank_table T2
        WHERE __tree.tree_pk = T2.{parent}
    )
    """

    CTE_SQLITE = """
    WITH RECURSIVE __rank_table(
        {tree_fields_columns}
        {pk},
        {parent},
        rank_order
    ) AS (
        {rank_table}
    ),
    __tree(
        {tree_fields_names}
        tree_depth,
        tree_path,
        tree_ordering,
        tree_pk
    ) AS (
        SELECT
            {tree_fields_initial}
            0,
            printf("{sep}%%s{sep}", {pk}),
            printf("{sep}%%020s{sep}", T.rank_order),
            T."{pk}" tree_pk
        FROM __rank_table T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            {tree_fields_recursive}
            __tree.tree_depth + 1,
            __tree.tree_path || printf("%%s{sep}", T.{pk}),
            __tree.tree_ordering || printf("%%020s{sep}", T.rank_order),
            T."{pk}"
        FROM __rank_table T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    # Optimized CTEs without rank table for simple cases
    CTE_POSTGRESQL_SIMPLE = """
    WITH RECURSIVE __tree (
        {tree_fields_names}"tree_depth",
        "tree_path",
        "tree_ordering",
        "tree_pk"
    ) AS (
        SELECT
            {tree_fields_initial}0,
            array[T.{pk}],
            array[T."{order_field}"],
            T.{pk}
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            {tree_fields_recursive}__tree.tree_depth + 1,
            __tree.tree_path || T.{pk},
            __tree.tree_ordering || T."{order_field}",
            T.{pk}
        FROM {db_table} T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    CTE_MYSQL_SIMPLE = """
    WITH RECURSIVE __tree(
        {tree_fields_names}tree_depth,
        tree_path,
        tree_ordering,
        tree_pk
    ) AS (
        SELECT
            {tree_fields_initial}0,
            CAST(CONCAT("{sep}", T.{pk}, "{sep}") AS char(1000)),
            CAST(CONCAT("{sep}", LPAD(CONCAT(T.`{order_field}`, "{sep}"), 20, "0")) AS char(1000)),
            T.{pk}
        FROM {db_table} T
        WHERE T.`{parent}` IS NULL

        UNION ALL

        SELECT
            {tree_fields_recursive}__tree.tree_depth + 1,
            CONCAT(__tree.tree_path, T.{pk}, "{sep}"),
            CONCAT(__tree.tree_ordering, LPAD(CONCAT(T.`{order_field}`, "{sep}"), 20, "0")),
            T.{pk}
        FROM {db_table} T, __tree
        WHERE __tree.tree_pk = T.`{parent}`
    )
    """

    CTE_SQLITE_SIMPLE = """
    WITH RECURSIVE __tree(
        {tree_fields_names}tree_depth,
        tree_path,
        tree_ordering,
        tree_pk
    ) AS (
        SELECT
            {tree_fields_initial}0,
            "{sep}" || T."{pk}" || "{sep}",
            "{sep}" || printf("%%020s", T."{order_field}") || "{sep}",
            T."{pk}"
        FROM {db_table} T
        WHERE T."{parent}" IS NULL

        UNION ALL

        SELECT
            {tree_fields_recursive}__tree.tree_depth + 1,
            __tree.tree_path || T."{pk}" || "{sep}",
            __tree.tree_ordering || printf("%%020s", T."{order_field}") || "{sep}",
            T."{pk}"
        FROM {db_table} T
        JOIN __tree ON T."{parent}" = __tree.tree_pk
    )
    """

    def _can_skip_rank_table(self):
        """
        Determine if we can skip the rank table optimization.
        We can skip it when:
        1. No tree filters are applied (rank_table_query is unchanged)
        2. Simple ordering (single field, ascending)
        3. No custom tree fields
        """

        # Check if tree filters have been applied
        original_query = QuerySet(model=_find_tree_model(self.query.model))
        if str(self.query.get_rank_table_query().query) != str(original_query.query):
            return False

        # Check if custom tree fields are simple column references
        tree_fields = self.query.get_tree_fields()
        if tree_fields:
            model = _find_tree_model(self.query.model)
            for name, column in tree_fields.items():
                # Only allow simple column names (no complex expressions)
                if not isinstance(column, str):
                    return False
                # Check if it's a valid field on the model
                try:
                    model._meta.get_field(column)
                except FieldDoesNotExist:
                    return False

        # Check for complex ordering
        sibling_order = self.query.get_sibling_order()
        if isinstance(sibling_order, (list, tuple)):
            if len(sibling_order) > 1:
                return False
            order_field = sibling_order[0]
        else:
            order_field = sibling_order

        # Check for descending order or complex expressions
        if (
            isinstance(order_field, str)
            and order_field.startswith("-")
            or not isinstance(order_field, str)
        ):
            return False

        # Check for related field lookups (contains __)
        if "__" in order_field:
            return False

        # Check if the ordering field is numeric/integer
        # For string fields, the optimization might not preserve correct order
        # because we bypass the ROW_NUMBER() ranking that the complex CTE uses
        field = _find_tree_model(self.query.model)._meta.get_field(order_field)
        if not hasattr(field, "get_internal_type"):
            return False
        field_type = field.get_internal_type()
        if field_type not in (
            "AutoField",
            "BigAutoField",
            "IntegerField",
            "BigIntegerField",
            "PositiveIntegerField",
            "PositiveSmallIntegerField",
            "SmallIntegerField",
        ):
            return False

        return True

    def get_rank_table(self):
        # Get and validate sibling_order
        sibling_order = self.query.get_sibling_order()

        if isinstance(sibling_order, (list, tuple)):
            order_fields = sibling_order
        elif isinstance(sibling_order, str):
            order_fields = [sibling_order]
        else:
            raise ValueError(
                "Sibling order must be a string or a list or tuple of strings."
            )

        # Convert strings to expressions. This is to maintain backwards compatibility
        # with Django versions < 4.1
        if django.VERSION < (4, 1):
            base_order = []
            for field in order_fields:
                if isinstance(field, Expression):
                    base_order.append(field)
                elif isinstance(field, str):
                    if field[0] == "-":
                        base_order.append(F(field[1:]).desc())
                    else:
                        base_order.append(F(field).asc())
            order_fields = base_order

        # Get the rank table query
        rank_table_query = self.query.get_rank_table_query()

        rank_table_query = (
            rank_table_query.order_by()  # Ensure there is no ORDER BY at the end of the SQL
            # Values allows us to both limit and specify the order of
            # the columns selected so that they match the CTE
            .values(
                *self.query.get_tree_fields().values(),
                "pk",
                "parent",
                rank_order=Window(
                    expression=RowNumber(),
                    order_by=order_fields,
                ),
            )
        )

        rank_table_sql, rank_table_params = rank_table_query.query.sql_with_params()

        return rank_table_sql, rank_table_params

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

        # Check if we can use the optimized path without rank table
        use_rank_table = not self._can_skip_rank_table()

        if use_rank_table:
            # Get the rank_table SQL and params
            rank_table_sql, rank_table_params = self.get_rank_table()
            params["rank_table"] = rank_table_sql
        else:
            # Use optimized path - get the order field for simple CTE
            sibling_order = self.query.get_sibling_order()
            if isinstance(sibling_order, (list, tuple)):
                order_field = sibling_order[0]
            else:
                order_field = sibling_order
            params["order_field"] = order_field
            rank_table_params = []

        # Set database-specific CTE template and column reference format
        if self.connection.vendor == "postgresql":
            cte = (
                self.CTE_POSTGRESQL_SIMPLE
                if not use_rank_table
                else self.CTE_POSTGRESQL
            )
            cte_initial = "array[{column}]::text[], "
            cte_recursive = "__tree.{name} || {column}::text, "
        elif self.connection.vendor == "sqlite":
            cte = self.CTE_SQLITE_SIMPLE if not use_rank_table else self.CTE_SQLITE
            cte_initial = 'printf("{sep}%%s{sep}", {column}), '
            cte_recursive = '__tree.{name} || printf("%%s{sep}", {column}), '
        elif self.connection.vendor == "mysql":
            cte = self.CTE_MYSQL_SIMPLE if not use_rank_table else self.CTE_MYSQL
            cte_initial = 'CAST(CONCAT("{sep}", {column}, "{sep}") AS char(1000)), '
            cte_recursive = 'CONCAT(__tree.{name}, {column}, "{sep}"), '

        tree_fields = self.query.get_tree_fields()
        qn = self.connection.ops.quote_name

        # Generate tree field parameters using unified templates
        # Set column reference format based on CTE type
        if use_rank_table:
            # Complex CTE uses rank table references
            column_ref_format = "{column}"
            params.update({
                "tree_fields_columns": "".join(
                    f"{qn(column)}, " for column in tree_fields.values()
                ),
            })
        else:
            # Simple CTE uses direct table references
            column_ref_format = "T.{column}"

        # Generate unified tree field parameters
        params.update({
            "tree_fields_names": "".join(f"{qn(name)}, " for name in tree_fields),
            "tree_fields_initial": "".join(
                cte_initial.format(
                    column=column_ref_format.format(column=qn(column)),
                    name=qn(name),
                    sep=SEPARATOR,
                )
                for name, column in tree_fields.items()
            ),
            "tree_fields_recursive": "".join(
                cte_recursive.format(
                    column=column_ref_format.format(column=qn(column)),
                    name=qn(name),
                    sep=SEPARATOR,
                )
                for name, column in tree_fields.items()
            ),
        })

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

            select = {
                "tree_depth": "__tree.tree_depth",
                "tree_path": "__tree.tree_path",
                "tree_ordering": "__tree.tree_ordering",
            }
            # Add custom tree fields for both simple and complex CTEs
            select.update({name: f"__tree.{name}" for name in tree_fields})
            self.query.add_extra(
                # Do not add extra fields to the select statement when it is a
                # summary query or when using .values() or .values_list()
                select={} if skip_tree_fields or self.query.values_select else select,
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

        sql_0, sql_1 = super().as_sql(*args, **kwargs)
        explain = ""
        if sql_0.startswith("EXPLAIN "):
            explain, sql_0 = sql_0.split(" ", 1)

        # Pass any additional rank table sql paramaters so that the db backend can handle them.
        # This only works because we know that the CTE is at the start of the query.
        return (
            "".join([explain, cte.format(**params), sql_0]),
            (*rank_table_params, *sql_1),
        )

    def get_converters(self, expressions):
        converters = super().get_converters(expressions)
        tree_fields = {"__tree.tree_path", "__tree.tree_ordering"} | {
            f"__tree.{name}" for name in self.query.tree_fields
        }
        for i, expression in enumerate(expressions):
            # We care about tree fields and annotations only
            if not hasattr(expression, "sql"):
                continue

            if expression.sql in tree_fields:
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
