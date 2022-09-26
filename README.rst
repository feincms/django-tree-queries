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

Supports Django 2.2 or better, Python 3.6 or better. See the GitHub actions
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
  ordering nodes within their siblings.
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
  <https://en.wikipedia.org/wiki/Depth-first_search>`__. It's not possible to
  order siblings by more than one field either.
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


Form fields
~~~~~~~~~~~

django-tree-queries ships a model field and some form fields which augment the
default foreign key field and the choice fields with a version where the tree
structure is visualized using dashes etc. Those fields are
``tree_queries.fields.TreeNodeForeignKey``,
``tree_queries.forms.TreeNodeChoiceField``,
``tree_queries.forms.TreeNodeMultipleChoiceField``.
