===================
django-tree-queries
===================

.. image:: https://travis-ci.org/matthiask/django-tree-queries.svg?branch=master
   :target: https://travis-ci.org/matthiask/django-tree-queries

Query Django model trees using adjacency lists and recursive common
table expressions. Supports PostgreSQL, sqlite3 (3.8.3 or higher) and
MariaDB (10.2.2 or higher) and MySQL (8.0 or higher, if running without
``ONLY_FULL_GROUP_BY``).

Supports Django 1.8, 1.11 or better, Python 2.7 and 3.4 or better. See
the Travis CI build for more details.


Features and limitations
========================

- Supports only integer primary keys.
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
- Besides adding the fields mentioned above the package only adds
  queryset methods for filtering ancestors and descendants. Other
  features may be useful, but will not be added to the package just
  because it's possible to do so.
- Little code, and relatively simple when compared to other tree
  management solutions for Django. No redundant values so the only way
  to end up with corrupt data is by introducing a loop in the tree
  structure (making it a graph). The ``TreeNode`` abstract model class
  has some protection against this.


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
- Until documentation is more complete I'll have to refer you to the
  `test suite
  <https://github.com/matthiask/django-tree-queries/blob/master/tests/testapp/test_queries.py>`_
  for additional instructions and usage examples.
