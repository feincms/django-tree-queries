import django
from django.core.exceptions import FieldDoesNotExist, FieldError
from django.db import connections
from django.db.models import Expression, F, Field, IntegerField, QuerySet, Value, Window
from django.db.models.expressions import RawSQL
from django.db.models.functions import RowNumber
from django.db.models.lookups import Lookup
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.constants import INNER
from django.db.models.sql.query import Query


SEPARATOR = "\x1f"


class TreeArrayField(Field):
    """
    Output field of the array-ish tree columns (``tree_path``,
    ``tree_ordering`` and the custom columns added by ``tree_fields()``).

    ``from_db_value()`` replaces the compiler's ``get_converters()`` override,
    and the ``__contains`` lookup below replaces the raw SQL fragments which
    ``descendants()`` used to add using ``.extra(where=[...])``.
    """

    def __init__(self, *args, column_name=None, source_field=None, **kwargs):
        self.column_name = column_name
        # The model field whose values the tree column contains, or None if the
        # column doesn't hold plain field values.
        self.source_field = source_field
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        if isinstance(value, str):
            # MySQL/MariaDB and sqlite3 do not support arrays. Split the value
            # on the ASCII unit separator (chr(31)).
            # NOTE: The representation of array is NOT part of the API.
            value = value.split(SEPARATOR)[1:-1]

        try:
            # Either all values are convertible to int or don't bother
            return [int(v) for v in value]  # Maybe Field.to_python()?
        except ValueError:
            return value


@TreeArrayField.register_lookup
class TreeArrayContains(Lookup):
    """
    ``tree_path__contains=node.pk`` -- does the tree column contain this value?
    """

    lookup_name = "contains"
    prepare_rhs = False

    def _rhs(self, connection):
        output_field = self.lhs.output_field
        if output_field.source_field is None:
            raise FieldError(
                f"Filtering '{output_field.column_name}' is not supported; its"
                f" representation is not part of the public API."
            )
        # Accept model instances, not just primary keys.
        value = getattr(self.rhs, "pk", self.rhs)
        return output_field.source_field.get_db_prep_value(
            value, connection, prepared=False
        )

    def as_sql(self, compiler, connection):
        # MySQL/MariaDB and sqlite3 do not support arrays; the tree columns are
        # separator-delimited strings there.
        lhs, params = self.process_lhs(compiler, connection)
        value = self._rhs(connection)
        return f"instr({lhs}, %s) <> 0", [
            *params,
            f"{SEPARATOR}{value}{SEPARATOR}",
        ]

    def as_postgresql(self, compiler, connection):
        lhs, params = self.process_lhs(compiler, connection)
        return f"%s = ANY({lhs})", [self._rhs(connection), *params]


class TreeJoin:
    """
    Joins the ``__tree`` CTE into the query.

    ``Query.alias_map`` entries have to be "Join compatible"; see the docstring
    of ``django.db.models.sql.datastructures.Join`` for the interface. Adding
    ourselves to the alias map replaces both the ``.extra(tables=["__tree"])``
    entry in the FROM clause and the ``.extra(where=[...])`` join condition
    which django-tree-queries used before.
    """

    table_name = "__tree"
    table_alias = "__tree"
    join_type = INNER
    filtered_relation = None
    nullable = False

    def __init__(self, pk_col):
        # ``pk_col`` is the resolved primary key column of the tree model; it
        # knows its own (possibly aliased, possibly inherited) table.
        self.pk_col = pk_col
        self.parent_alias = pk_col.alias

    def as_sql(self, compiler, connection):
        pk_sql, pk_params = compiler.compile(self.pk_col)
        qn = connection.ops.quote_name
        on = f"{qn(self.table_alias)}.tree_pk = {pk_sql}"
        return f"{self.join_type} {qn(self.table_name)} ON ({on})", pk_params

    def relabeled_clone(self, change_map):
        return self.__class__(self.pk_col.relabeled_clone(change_map))

    # relabeled_clone() above and demote()/promote() below are part of the
    # interface, but unreachable in practice: we only add ourselves to the
    # alias map while generating the SQL, long after Django is done rewriting
    # aliases and promoting joins.

    def demote(self):
        return self

    def promote(self):
        # Never promote to a LEFT OUTER JOIN; a node always has a tree row.
        return self


class TreeColumn(RawSQL):
    """
    A single column of the ``__tree`` CTE.
    """

    def __init__(self, name, output_field):
        super().__init__(f"__tree.{name}", (), output_field=output_field)


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

        self.add_tree_annotations()

    def tree_column_names(self):
        return ("tree_depth", "tree_path", "tree_ordering", *self.tree_fields)

    def add_tree_annotations(self):
        """
        Register the tree columns as annotations.

        This makes them usable in ``.filter()``, ``.order_by()``,
        ``.values()``, ... as any other annotation; the tree columns are only
        added to the SELECT clause by the compiler though (see
        ``TreeCompiler.as_sql``) since we do not always want them there.
        """
        names = self.tree_column_names()

        # Drop tree columns which are no longer part of the query, e.g. after
        # calling tree_fields() a second time with different names. Leaving
        # them around would produce SQL referencing columns the CTE doesn't
        # have.
        self.remove_tree_annotations(keep=names)

        opts = _find_tree_model(self.model)._meta
        for name in names:
            if name in self.annotations:
                continue
            if name == "tree_depth":
                output_field = IntegerField()
            elif name == "tree_ordering":
                # tree_ordering contains sibling ordering values, possibly from
                # more than one field and possibly transformed (see the CTE
                # templates), so there is no single source field for it.
                output_field = TreeArrayField(column_name=name)
            elif name in self.tree_fields:
                output_field = TreeArrayField(
                    column_name=name,
                    source_field=opts.get_field(self.tree_fields[name]),
                )
            else:  # tree_path
                output_field = TreeArrayField(column_name=name, source_field=opts.pk)
            # select=False: only the compiler decides whether the tree columns
            # end up in the SELECT clause.
            self.add_annotation(TreeColumn(name, output_field), name, select=False)

    def set_values(self, fields):
        # Promote explicitly requested tree columns so that
        # .values("tree_depth") and friends work.
        if promote := [
            field for field in fields or () if field in self.tree_column_names()
        ]:
            self.append_annotation_mask(promote)
        return super().set_values(fields)

    def remove_tree_annotations(self, keep=()):
        names = [
            name
            for name, annotation in self.annotations.items()
            if isinstance(annotation, TreeColumn) and name not in keep
        ]
        for name in names:
            del self.annotations[name]
        if names and self.annotation_select_mask is not None:
            self.set_annotation_mask(set(self.annotation_select_mask).difference(names))

    def get_compiler(self, using=None, connection=None, *args, **kwargs):
        # Copied from django/db/models/sql/query.py
        if using is None and connection is None:
            raise ValueError("Need either using or connection")
        if using:
            connection = connections[using]
        # Difference: Not connection.ops.compiler, but our own compiler which
        # adds the CTE.

        # *args and **kwargs pass on elide_empty, which Django 4.0 and better
        # sometimes pass positionally (see SQLCompiler.get_combinator_sql()).
        return TreeCompiler(self, connection, using, *args, **kwargs)

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
            for column in tree_fields.values():
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
        return field_type in (
            "AutoField",
            "BigAutoField",
            "IntegerField",
            "BigIntegerField",
            "PositiveIntegerField",
            "PositiveSmallIntegerField",
            "SmallIntegerField",
        )

    def get_rank_table(self):
        # Get and validate sibling_order
        sibling_order = self.query.get_sibling_order()

        if isinstance(sibling_order, (list, tuple)):
            order_fields = sibling_order
        elif isinstance(sibling_order, str):
            order_fields = [sibling_order]
        else:
            raise TypeError(
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
        tree_column_names = self.query.tree_column_names()
        if (
            self.query.subquery
            and (
                ann := {
                    alias: annotation
                    for alias, annotation in self.query.annotations.items()
                    if alias not in tree_column_names
                }
            )
            and ann == {"a": Value(1)}
        ):
            return super().as_sql(*args, **kwargs)

        # The general idea is that if we have a summary query (e.g. .count())
        # then we do not want the tree fields in the SELECT clause. The way to
        # determine whether we have a summary query on our hands is to check
        # the is_summary attribute of all annotations.
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
            for annotation in self.query.annotations.values()
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
            # The simple CTE references the column directly on the base
            # table, so we need the actual DB column name, not the field's
            # (possibly different) attribute name.
            params["order_field"] = opts.get_field(order_field).column
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

        # The simple CTE references columns directly on the base table, so it
        # needs the actual DB column names, not the fields' (possibly
        # different) attribute names. The rank table already exposes its
        # columns using the tree_fields attribute names (see
        # tree_fields_columns above), so no translation is needed there.
        def _resolved_column(column):
            return column if use_rank_table else opts.get_field(column).column

        # Generate unified tree field parameters
        params.update({
            "tree_fields_names": "".join(f"{qn(name)}, " for name in tree_fields),
            "tree_fields_initial": "".join(
                cte_initial.format(
                    column=column_ref_format.format(
                        column=qn(_resolved_column(column))
                    ),
                    name=qn(name),
                    sep=SEPARATOR,
                )
                for name, column in tree_fields.items()
            ),
            "tree_fields_recursive": "".join(
                cte_recursive.format(
                    column=column_ref_format.format(
                        column=qn(_resolved_column(column))
                    ),
                    name=qn(name),
                    sep=SEPARATOR,
                )
                for name, column in tree_fields.items()
            ),
        })

        if "__tree" not in self.query.alias_map:  # pragma: no branch - unlikely
            # Join the CTE. Resolving the base table's alias first means we do
            # not have to guess it ourselves.
            self.query.join(TreeJoin(self.query.resolve_ref(opts.pk.attname)))

            # Only add the tree columns to the SELECT clause when the query
            # returns model instances: not for summary queries, and not for
            # .values()/.values_list() or subqueries (which select their own
            # list of columns; the tree columns are still available there when
            # explicitly requested since they are annotations).
            if not skip_tree_fields and self.query.default_cols:
                self.query.append_annotation_mask(tree_column_names)

            if not (skip_tree_fields or self.query.order_by):
                # No ordering for aggregates, and an explicit .order_by() wins.
                self.query.add_ordering("tree_ordering")  # DFS is the only true way

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
