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
  primary keys and ``tree_ordering`` an array of values used for
  ordering nodes within their siblings. Note that the contents of the
  ``tree_path`` and ``tree_ordering`` are subject to change. You shouldn't rely
  on their contents.
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

.. code-block:: python

    from tree_queries.models import TreeNode

    class Node(TreeNode):
        name = models.CharField(max_length=100)
        position = models.PositiveIntegerField(default=0)

        class Meta:
            ordering = ["position"]


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

Note that the tree queryset doesn't support all types of queries Django
supports. For example, updating all descendants directly isn't supported. The
reason for that is that the recursive CTE isn't added to the UPDATE query
correctly. Workarounds often include moving the tree query into a subquery:

.. code-block:: python

    # Doesn't work:
    node.descendants().update(is_active=False)

    # Use this workaround instead:
    Node.objects.filter(pk__in=node.descendants()).update(is_active=False)


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
