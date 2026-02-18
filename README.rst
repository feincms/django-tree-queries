===================
django-tree-queries
===================

.. image:: https://github.com/matthiask/django-tree-queries/actions/workflows/test.yml/badge.svg
    :target: https://github.com/matthiask/django-tree-queries/
    :alt: CI Status

Query Django model trees using adjacency lists and recursive common
table expressions. Supports PostgreSQL, sqlite3 (3.8.3 or higher) and
MariaDB (10.2.2 or higher) and MySQL (8.0 or higher, if running without
``ONLY_FULL_GROUP_BY``).

Supports Django 3.2 or better, Python 3.8 or better. See the GitHub actions
build for more details.

Features and limitations
========================

- Supports only integer and UUID primary keys (for now).
- Allows specifying ordering among siblings.
- Uses the correct definition of depth, where root nodes have a depth of
  zero.
- The parent foreign key must be named ``"parent"`` at the moment (but
  why would you want to name it differently?)
- The fields added by the common table expression always are
  ``tree_depth``, ``tree_path`` and ``tree_ordering``. The names cannot
  be changed. ``tree_depth`` is an integer, ``tree_path`` an array of
  primary keys representing the path from the root to the current node
  (including the current node itself), and ``tree_ordering`` an array of
  values used for ordering nodes within their siblings at each level of
  the tree hierarchy. Note that the contents of the ``tree_path`` and
  ``tree_ordering`` are subject to change. You shouldn't rely on their
  contents.
- Besides adding the fields mentioned above the package only adds queryset
  methods for ordering siblings and filtering ancestors and descendants. Other
  features may be useful, but will not be added to the package just because
  it's possible to do so.
- Little code, and relatively simple when compared to other tree
  management solutions for Django. No redundant values so the only way
  to end up with corrupt data is by introducing a loop in the tree
  structure (making it a graph). The ``TreeNode`` abstract model class
  has some protection against this.
- Supports only trees with max. 50 levels on MySQL/MariaDB, since those
  databases do not support arrays and require us to provide a maximum
  length for the ``tree_path`` and ``tree_ordering`` upfront.
- **Performance optimization**: The library automatically detects simple cases
  (single field ordering, no tree filters, no custom tree fields) and uses an
  optimized CTE that avoids creating a rank table, significantly improving
  performance for basic tree queries.

Here's a blog post offering some additional insight (hopefully) into the
reasons for `django-tree-queries' existence <https://406.ch/writing/django-tree-queries/>`_.


Usage
=====

- Install ``django-tree-queries`` using pip.
- Extend ``tree_queries.models.TreeNode`` or build your own queryset
  and/or manager using ``tree_queries.query.TreeQuerySet``. The
  ``TreeNode`` abstract model already contains a ``parent`` foreign key
  for your convenience and also uses model validation to protect against
  loops.
- Call the ``with_tree_fields()`` queryset method if you require the
  additional fields respectively the CTE.
- Call the ``order_siblings_by("field_name")`` queryset method if you want to
  order tree siblings by a specific model field. Note that Django's standard
  ``order_by()`` method isn't supported -- nodes are returned according to the
  `depth-first search algorithm
  <https://en.wikipedia.org/wiki/Depth-first_search>`__.
- Use ``tree_filter()`` and ``tree_exclude()`` for better performance when
  working with large tables - these filter the base table before building
  the tree structure.
- Use ``tree_fields()`` to aggregate ancestor field values into arrays.
- Create a manager using
  ``TreeQuerySet.as_manager(with_tree_fields=True)`` if you want to add
  tree fields to queries by default.
- Until documentation is more complete I'll have to refer you to the
  `test suite
  <https://github.com/matthiask/django-tree-queries/blob/main/tests/testapp/test_queries.py>`_
  for additional instructions and usage examples, or check the recipes below.


Recipes
=======

Basic models
~~~~~~~~~~~~

The following two examples both extend the ``TreeNode`` which offers a few
agreeable utilities and a model validation method that prevents loops in the
tree structure. The common table expression could be hardened against such
loops but this would involve a performance hit which we don't want -- this is a
documented limitation (non-goal) of the library after all.

Basic tree node
---------------

.. code-block:: python

    from tree_queries.models import TreeNode

    class Node(TreeNode):
        name = models.CharField(max_length=100)


Tree node with ordering among siblings
--------------------------------------

Nodes with the same parent may be ordered among themselves. The default is to
order siblings by their primary key but that's not always very useful.

**Manual position management:**

.. code-block:: python

    from tree_queries.models import TreeNode

    class Node(TreeNode):
        name = models.CharField(max_length=100)
        position = models.PositiveIntegerField(default=0)

        class Meta:
            ordering = ["position"]

**Automatic position management:**

For automatic position management, use ``OrderableTreeNode`` which automatically
assigns sequential position values to new nodes:

.. code-block:: python

    from tree_queries.models import OrderableTreeNode

    class Category(OrderableTreeNode):
        name = models.CharField(max_length=100)
        # position field and ordering are inherited from OrderableTreeNode

When creating new nodes without an explicit position, ``OrderableTreeNode``
automatically assigns a position value 10 units higher than the maximum position
among siblings. The increment of 10 (rather than 1) makes it explicit that the
position values themselves have no inherent meaning - they are purely for relative
ordering, not a sibling counter or index.

If you need to customize the Meta class (e.g., to add verbose names or additional
ordering fields), inherit from ``OrderableTreeNode.Meta``:

.. code-block:: python

    from tree_queries.models import OrderableTreeNode

    class Category(OrderableTreeNode):
        name = models.CharField(max_length=100)

        class Meta(OrderableTreeNode.Meta):
            verbose_name = "category"
            verbose_name_plural = "categories"
            # ordering = ["position"] is inherited from OrderableTreeNode.Meta

.. code-block:: python

    # Create nodes - positions are assigned automatically
    root = Category.objects.create(name="Root")  # position=10
    child1 = Category.objects.create(name="Child 1", parent=root)  # position=10
    child2 = Category.objects.create(name="Child 2", parent=root)  # position=20
    child3 = Category.objects.create(name="Child 3", parent=root)  # position=30

    # Manual reordering is still possible
    child3.position = 15  # Move between child1 and child2
    child3.save()

This approach is identical to the pattern used in feincms3's ``AbstractPage``.


Add custom methods to queryset
------------------------------

.. code-block:: python

    from tree_queries.models import TreeNode
    from tree_queries.query import TreeQuerySet

    class NodeQuerySet(TreeQuerySet):
        def active(self):
            return self.filter(is_active=True)

    class Node(TreeNode):
        is_active = models.BooleanField(default=True)

        objects = NodeQuerySet.as_manager()


Querying the tree
~~~~~~~~~~~~~~~~~

All examples assume the ``Node`` class from above.

Basic usage
-----------

.. code-block:: python

    # Basic usage, disregards the tree structure completely.
    nodes = Node.objects.all()

    # Fetch nodes in depth-first search order. All nodes will have the
    # tree_path, tree_ordering and tree_depth attributes.
    nodes = Node.objects.with_tree_fields()

    # Fetch any node.
    node = Node.objects.order_by("?").first()

    # Fetch direct children and include tree fields. (The parent ForeignKey
    # specifies related_name="children")
    children = node.children.with_tree_fields()

    # Fetch all ancestors starting from the root.
    ancestors = node.ancestors()

    # Fetch all ancestors including self, starting from the root.
    ancestors_including_self = node.ancestors(include_self=True)

    # Fetch all ancestors starting with the node itself.
    ancestry = node.ancestors(include_self=True).reverse()

    # Fetch all descendants in depth-first search order, including self.
    descendants = node.descendants(include_self=True)

    # Temporarily override the ordering by siblings.
    nodes = Node.objects.order_siblings_by("id")

    # Revert to a queryset without tree fields (improves performance).
    nodes = Node.objects.with_tree_fields().without_tree_fields()


Understanding tree fields
-------------------------

When using ``with_tree_fields()``, each node gets three additional attributes:

- **``tree_depth``**: An integer representing the depth of the node in the tree
  (root nodes have depth 0)
- **``tree_path``**: An array containing the primary keys of all ancestors plus
  the current node itself, representing the path from root to current node
- **``tree_ordering``**: An array containing the ordering/ranking values used
  for sibling ordering at each level of the tree hierarchy

The key difference between ``tree_path`` and ``tree_ordering``:

.. code-block:: python

    # Example tree structure:
    #   Root (pk=1, order=0)
    #   ├── Child A (pk=2, order=10)
    #   │   └── Grandchild (pk=4, order=5)
    #   └── Child B (pk=3, order=20)

    # For the Grandchild node:
    grandchild = Node.objects.with_tree_fields().get(pk=4)

    # tree_path shows the route through primary keys: Root -> Child A -> Grandchild
    assert grandchild.tree_path == [1, 2, 4]  # [root.pk, child_a.pk, grandchild.pk]

    # tree_ordering shows ordering values at each level: Root's order, Child A's order, Grandchild's order
    assert grandchild.tree_ordering == [0, 10, 5]  # [root.order, child_a.order, grandchild.order]

**Important note**: When not using an explicit ordering (like a ``position``
field), siblings are ordered by their primary key by default. This means
``tree_path`` and ``tree_ordering`` will contain the same values. While this
may be fine for your use case consider adding an explicit ordering field:

.. code-block:: python

    class Node(TreeNode):
        id = models.UUIDField(primary_key=True, default=uuid.uuid4)
        name = models.CharField(max_length=100)
        position = models.PositiveIntegerField(default=0)

        class Meta:
            ordering = ["position"]


When are tree fields available?
--------------------------------

Tree fields (``tree_depth``, ``tree_path``, ``tree_ordering``) are only available
on objects returned by queries that use ``with_tree_fields()`` or a manager
configured with ``with_tree_fields=True``. They are **NOT** available after
``Model.objects.create()``, ``instance.save()``, or ``instance.refresh_from_db()``.

Why? Tree fields are calculated by the recursive CTE at query time and are not
stored in the database. They only exist as annotations on the queryset results.

.. code-block:: python

    # Tree fields are NOT available after creation
    node = Node.objects.create(name="New Node", parent=root)
    # node.tree_depth  # AttributeError: 'Node' object has no attribute 'tree_depth'

    # refresh_from_db() only updates database fields, not tree fields
    node.refresh_from_db()
    # node.tree_depth  # Still AttributeError

    # To get tree fields, re-query the object with with_tree_fields()
    node = Node.objects.with_tree_fields().get(pk=node.pk)
    print(node.tree_depth)  # Now it works! e.g., 1

    # Or use a manager with tree fields enabled by default
    class Node(TreeNode):
        name = models.CharField(max_length=100)
        objects = TreeQuerySet.as_manager(with_tree_fields=True)

    # Now tree fields are available on all queries automatically
    node = Node.objects.get(pk=some_pk)
    print(node.tree_depth)  # Works!

    # But still not after create/save/refresh_from_db
    new_node = Node.objects.create(name="Another")
    # new_node.tree_depth  # Still AttributeError - need to re-query

**Common pattern when creating nodes:**

.. code-block:: python

    # Create a new node
    new_node = Node.objects.create(name="New Child", parent=parent_node)

    # Re-query to get tree fields if you need them
    new_node = Node.objects.with_tree_fields().get(pk=new_node.pk)

    # Now you can access tree fields
    print(f"Depth: {new_node.tree_depth}")
    print(f"Path: {new_node.tree_path}")


Filtering tree subsets
----------------------

**IMPORTANT**: For large tables, always use ``tree_filter()`` or ``tree_exclude()``
to limit which nodes are processed by the recursive CTE. Without these filters,
the database evaluates the entire table, which can be extremely slow.

.. code-block:: python

    # Get a specific tree from a forest by filtering on root category
    product_tree = Node.objects.with_tree_fields().tree_filter(category="products")

    # Get organizational chart for a specific department
    engineering_tree = Node.objects.with_tree_fields().tree_filter(department="engineering")

    # Exclude entire trees/sections you don't need
    content_trees = Node.objects.with_tree_fields().tree_exclude(category="archived")

    # Chain multiple tree filters for more specific trees
    recent_products = (Node.objects.with_tree_fields()
                      .tree_filter(category="products")
                      .tree_filter(created_date__gte=datetime.date.today()))

    # Get descendants within a filtered tree subset
    product_descendants = (Node.objects.with_tree_fields()
                          .tree_filter(category="products")
                          .descendants(some_product_node))

    # Filter by site/tenant in multi-tenant applications
    site_content = Node.objects.with_tree_fields().tree_filter(site_id=request.site.id)

Performance note: ``tree_filter()`` and ``tree_exclude()`` filter the base table
before the recursive CTE processes relationships, dramatically improving performance
for large datasets compared to using regular ``filter()`` after ``with_tree_fields()``.
Best used for selecting complete trees or tree sections rather than scattered nodes.

**Limitations and workarounds**

The tree queryset doesn't support all types of queries Django supports.

**UPDATE queries on tree querysets:**

Updating all descendants directly isn't supported because the recursive CTE isn't
added to the UPDATE query correctly. Use a subquery workaround instead:

.. code-block:: python

    # Doesn't work:
    node.descendants().update(is_active=False)

    # Use this workaround instead:
    Node.objects.filter(pk__in=node.descendants()).update(is_active=False)

**select_related() with tree fields:**

Using ``select_related()`` works when querying **from** the tree model to fetch
related objects. However, querying from a related model and trying to get tree
fields on the tree model via ``select_related()`` is not supported.

.. code-block:: python

    # This works - tree model is the base, select_related fetches the category
    nodes = Node.objects.with_tree_fields().select_related("category")
    for node in nodes:
        print(node.tree_depth, node.category.name)

    # This doesn't work - ReferenceModel is the base, tree fields won't be present
    # on the related Node objects
    references = ReferenceModel.objects.select_related("tree_field")
    for ref in references:
        # ref.tree_field.tree_depth  # AttributeError - tree fields not available

**Workaround:** Query from the tree model and use ``prefetch_related()`` or
``Prefetch()`` to fetch the related objects:

.. code-block:: python

    from django.db.models import Prefetch

    # Approach 1: Query from tree model, prefetch references
    nodes = Node.objects.with_tree_fields().prefetch_related("referencemodel_set")
    for node in nodes:
        print(node.tree_depth)
        for ref in node.referencemodel_set.all():
            print(f"  Reference: {ref.id}")

    # Approach 2: Query references, then fetch tree nodes separately
    references = ReferenceModel.objects.all()
    tree_node_ids = [ref.tree_field_id for ref in references]
    nodes_by_id = {
        node.pk: node
        for node in Node.objects.with_tree_fields().filter(pk__in=tree_node_ids)
    }
    for ref in references:
        node = nodes_by_id[ref.tree_field_id]
        print(f"Reference {ref.id}: tree depth = {node.tree_depth}")


Breadth-first search
--------------------

Nobody wants breadth-first search but if you still want it you can achieve it
as follows:

.. code-block:: python

    nodes = Node.objects.with_tree_fields().extra(
        order_by=["__tree.tree_depth", "__tree.tree_ordering"]
    )


Filter by depth
---------------

If you only want nodes from the top two levels:

.. code-block:: python

    nodes = Node.objects.with_tree_fields().extra(
        where=["__tree.tree_depth <= %s"],
        params=[1],
    )


Using tree fields with values()
--------------------------------

By default, ``.values()`` only returns model fields, not tree fields. If you need
tree fields in a ``.values()`` call, you can access them using ``RawSQL``:

.. code-block:: python

    from django.db.models.expressions import RawSQL

    # Include tree fields in values() output
    data = Node.objects.with_tree_fields().values(
        "name",
        tree_depth=RawSQL("tree_depth", ()),
        tree_path=RawSQL("tree_path", ()),
    )
    # Returns: [{'name': 'root', 'tree_depth': 0, 'tree_path': [1]}, ...]

**Important caveats:**

- **PostgreSQL only**: ``tree_path`` returns a proper array only on PostgreSQL.
  Other databases return the internal string representation used by
  django-tree-queries (subject to change).
- **Not guaranteed stable**: The internal representation of tree fields may change
  in future versions. Avoid relying on the exact format of these values in
  application logic.
- **Performance**: Using ``.values()`` with tree fields doesn't provide performance
  benefits over regular querysets with tree fields. Use this only when you
  specifically need dictionary output.

If you need tree field values for application logic, prefer accessing them as
attributes on model instances rather than through ``.values()``:

.. code-block:: python

    # Preferred approach
    nodes = Node.objects.with_tree_fields()
    for node in nodes:
        depth = node.tree_depth
        path = node.tree_path  # Consistent across all databases

    # Only use RawSQL with values() when you need dictionary output
    data = Node.objects.with_tree_fields().values(
        "name",
        tree_depth=RawSQL("tree_depth", ()),
    )


Aggregating ancestor fields
---------------------------

Use ``tree_fields()`` to aggregate values from ancestor nodes into arrays. This is
useful for collecting paths, permissions, categories, or any field that should be
inherited down the tree hierarchy.

.. code-block:: python

    # Aggregate names from all ancestors into an array
    nodes = Node.objects.with_tree_fields().tree_fields(
        tree_names="name",
    )
    # Each node now has a tree_names attribute: ['root', 'parent', 'current']

    # Aggregate multiple fields
    nodes = Node.objects.with_tree_fields().tree_fields(
        tree_names="name",
        tree_categories="category",
        tree_permissions="permission_level",
    )

    # Build a full path string from ancestor names
    nodes = Node.objects.with_tree_fields().tree_fields(tree_names="name")
    for node in nodes:
        full_path = " > ".join(node.tree_names)  # "Root > Section > Subsection"

    # Combine with tree filtering for better performance
    active_nodes = (Node.objects.with_tree_fields()
                    .tree_filter(is_active=True)
                    .tree_fields(tree_names="name"))

The aggregated fields contain values from all ancestors (root to current node) in
hierarchical order, including the current node itself.


Form fields
~~~~~~~~~~~

django-tree-queries ships a model field and some form fields which augment the
default foreign key field and the choice fields with a version where the tree
structure is visualized using dashes etc. Those fields are
``tree_queries.fields.TreeNodeForeignKey``,
``tree_queries.forms.TreeNodeChoiceField``,
``tree_queries.forms.TreeNodeMultipleChoiceField``.


Templates
~~~~~~~~~

django-tree-queries includes template tags to help render tree structures in
Django templates. These template tags are designed to work efficiently with
tree querysets and respect queryset boundaries.

Setup
-----

Add ``tree_queries`` to your ``INSTALLED_APPS`` setting:

.. code-block:: python

    INSTALLED_APPS = [
        # ... other apps
        'tree_queries',
    ]

Then load the template tags in your template:

.. code-block:: html

    {% load tree_queries %}


tree_info filter
----------------

The ``tree_info`` filter provides detailed information about each node's
position in the tree structure. It's useful when you need fine control over
the tree rendering.

.. code-block:: html

    {% load tree_queries %}
    <ul>
    {% for node, structure in nodes|tree_info %}
        {% if structure.new_level %}<ul><li>{% else %}</li><li>{% endif %}
        {{ node.name }}
        {% for level in structure.closed_levels %}</li></ul>{% endfor %}
    {% endfor %}
    </ul>

The filter returns tuples of ``(node, structure_info)`` where ``structure_info``
contains:

- ``new_level``: ``True`` if this node starts a new level, ``False`` otherwise
- ``closed_levels``: List of levels that close after this node
- ``ancestors``: List of ancestor node representations from root to immediate parent

Example showing ancestor information:

.. code-block:: html

    {% for node, structure in nodes|tree_info %}
        {{ node.name }}
        {% if structure.ancestors %}
            (Path: {% for ancestor in structure.ancestors %}{{ ancestor }}{% if not forloop.last %} > {% endif %}{% endfor %})
        {% endif %}
    {% endfor %}


recursetree tag
---------------

The ``recursetree`` tag provides recursive rendering similar to django-mptt's
``recursetree`` tag, but optimized for django-tree-queries. It only considers
nodes within the provided queryset and doesn't make additional database queries.

Basic usage:

.. code-block:: html

    {% load tree_queries %}
    <ul>
    {% recursetree nodes %}
        <li>
            {{ node.name }}
            {% if children %}
                <ul>{{ children }}</ul>
            {% endif %}
        </li>
    {% endrecursetree %}
    </ul>

The ``recursetree`` tag provides these context variables within the template:

- ``node``: The current tree node
- ``children``: Rendered HTML of child nodes (from the queryset)
- ``is_leaf``: ``True`` if the node has no children in the queryset

Using ``is_leaf`` for conditional rendering:

.. code-block:: html

    {% recursetree nodes %}
        <div class="{% if is_leaf %}leaf-node{% else %}branch-node{% endif %}">
            <span class="node-name">{{ node.name }}</span>
            {% if children %}
                <div class="children">{{ children }}</div>
            {% elif is_leaf %}
                <span class="leaf-indicator">🍃</span>
            {% endif %}
        </div>
    {% endrecursetree %}

Advanced example with depth information:

.. code-block:: html

    {% recursetree nodes %}
        <div class="node depth-{{ node.tree_depth }}"
             data-id="{{ node.pk }}"
             data-has-children="{{ children|yesno:'true,false' }}">
            <h{{ node.tree_depth|add:1 }}>{{ node.name }}</h{{ node.tree_depth|add:1 }}>
            {% if children %}
                <div class="node-children">{{ children }}</div>
            {% endif %}
        </div>
    {% endrecursetree %}


Working with limited querysets
-------------------------------

Both template tags respect queryset boundaries and work efficiently with
filtered or limited querysets:

.. code-block:: python

    # Only nodes up to depth 2
    limited_nodes = Node.objects.with_tree_fields().extra(
        where=["__tree.tree_depth <= %s"], params=[2]
    )

    # Only specific branches
    branch_nodes = Node.objects.descendants(some_node, include_self=True)

When using these limited querysets:

- ``recursetree`` will only render nodes from the queryset
- ``is_leaf`` reflects whether nodes have children *in the queryset*, not in the full tree
- No additional database queries are made
- Nodes whose parents aren't in the queryset are treated as root nodes

Example with depth-limited queryset:

.. code-block:: html

    <!-- Template -->
    {% recursetree limited_nodes %}
        <li>
            {{ node.name }}
            {% if is_leaf %}
                <small>(leaf in limited view)</small>
            {% endif %}
            {{ children }}
        </li>
    {% endrecursetree %}

This is particularly useful for creating expandable tree interfaces or
rendering only portions of large trees for performance.


Django Admin Integration
~~~~~~~~~~~~~~~~~~~~~~~~

django-tree-queries includes a ``TreeAdmin`` class for Django's admin interface
that provides an intuitive tree management experience with drag-and-drop style
node moving capabilities.

Installation
------------

To use the admin functionality, install with the ``admin`` extra:

.. code-block:: bash

    pip install django-tree-queries[admin]

Usage
-----

**With automatic position management:**

For the best admin experience with proper ordering, use ``OrderableTreeNode``:

.. code-block:: python

    from django.contrib import admin
    from tree_queries.admin import TreeAdmin
    from tree_queries.models import OrderableTreeNode

    class Category(OrderableTreeNode):
        name = models.CharField(max_length=100)
        # position field and ordering are inherited from OrderableTreeNode

    @admin.register(Category)
    class CategoryAdmin(TreeAdmin):
        list_display = [*TreeAdmin.list_display, "name"]
        position_field = "position"  # Enables sibling ordering controls

**With manual position management:**

If you prefer to manage positions yourself:

.. code-block:: python

    from django.contrib import admin
    from django.db.models import Max
    from tree_queries.admin import TreeAdmin
    from tree_queries.models import TreeNode

    class Category(TreeNode):
        name = models.CharField(max_length=100)
        position = models.PositiveIntegerField(default=0)

        class Meta:
            ordering = ["position"]

        def save(self, *args, **kwargs):
            # Custom position logic here
            if not self.position:
                self.position = (
                    10
                    + (
                        self.__class__._default_manager.filter(parent_id=self.parent_id)
                        .order_by()
                        .aggregate(p=Max("position"))["p"]
                        or 0
                    )
                )
            super().save(*args, **kwargs)

        save.alters_data = True

    @admin.register(Category)
    class CategoryAdmin(TreeAdmin):
        list_display = [*TreeAdmin.list_display, "name"]
        position_field = "position"

The ``TreeAdmin`` provides:

- **Tree visualization**: Nodes are displayed with indentation and visual tree structure
- **Collapsible nodes**: Click to expand/collapse branches for better navigation
- **Node moving**: Cut and paste nodes to reorganize the tree structure
- **Flexible ordering**: Supports both ordered (with position field) and unordered trees
- **Root moves**: Direct "move to root" buttons for trees without sibling ordering

**Configuration:**

- Set ``position_field`` to the field name used for positioning siblings (e.g., ``"position"``, ``"order"``)
- Leave ``position_field = None`` for trees positioned by other criteria (pk, name, etc.)
- The admin automatically adapts its interface based on whether positioning is controllable

**Required list_display columns:**

- ``collapse_column``: Shows expand/collapse toggles
- ``indented_title``: Displays the tree structure with indentation
- ``move_column``: Provides move controls (cut, paste, move-to-root)

These are included by default in ``TreeAdmin.list_display``.


Migrating from django-mptt
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When migrating from django-mptt to django-tree-queries, you'll need to populate
the ``position`` field (or whatever field you use for sibling ordering) based on
the existing MPTT ``lft`` values. Here's an example migration:

.. code-block:: python

    def fill_position(apps, schema_editor):
        ModelWithMPTT = apps.get_model("your_app", "ModelWithMPTT")
        db_alias = schema_editor.connection.alias
        position_map = ModelWithMPTT.objects.using(db_alias).annotate(
            lft_rank=Window(
                expression=RowNumber(),
                partition_by=[F("parent_id")],
                order_by=["lft"],
            ),
        ).in_bulk()
        # Update batches of 2000 objects.
        batch_size = 2000
        qs = ModelWithMPTT.objects.all()
        batches = (qs[i : i + batch_size] for i in range(0, qs.count(), batch_size))
        for batch in batches:
            for obj in batch:
                obj.position = position_map[obj.pk].lft_rank
            ModelWithMPTT.objects.bulk_update(batch, ["position"])

    class Migration(migrations.Migration):

        dependencies = [...]

        operations = [
            migrations.RunPython(
                code=fill_position,
                reverse_code=migrations.RunPython.noop,
            )
        ]

This migration uses Django's ``Window`` function with ``RowNumber()`` to assign
position values based on the original MPTT ``lft`` ordering, ensuring that siblings
maintain their relative order after the migration.

Note that the position field is used purely for ordering siblings and is not an
index. By default, django-tree-queries' admin interface starts with a position
value of 10 and increments by 10 (10, 20, 30, etc.) to make it explicit that the
position values themselves have no inherent meaning - they are purely for relative
ordering, not a sibling counter or index.

**Replacing add_related_count():**

django-mptt's ``add_related_count()`` method for cumulative related object counts
is not directly supported in django-tree-queries. The implementation would be
complex and database-specific. For community-contributed solutions and discussion
of alternative approaches, see `mptt-related issues on GitHub
<https://github.com/matthiask/django-tree-queries/issues?q=label:mptt>`_.
