===================
django-tree-queries
===================

.. image:: https://travis-ci.org/matthiask/django-tree-queries.svg?branch=master
   :target: https://travis-ci.org/matthiask/django-tree-queries

Query Django model trees using adjacency lists and recursive common
table expressions. Supports PostgreSQL, sqlite3 (3.8.3 or higher) and
MariaDB (10.2.2 or higher), maybe also MySQL 8.0 but I found no easy way
to test against it.

Supports Django 1.11 or better, Python 2.7 and 3.4 or better.


Features and limitations
========================

- Supports only integer primary keys.
- Allows adding an integer field to order nodes on a given level.
- Uses the correct definition of depth, where root nodes have a depth of
  zero.
- Only supports 10 levels of nodes on MariaDB.
- Only supports maximum primary key values of 16^9 on sqlite3 and
  MariaDB (this may change if the database engines implement proper
  array support).
- The parent foreign key must be named ``"parent"`` at the moment (but
  why would you want to name it differently?)
- The fields added by the common table expression always are
  ``tree_depth``, ``tree_path`` and ``tree_ordering``. The names cannot
  be changed. The first field is always an integer, the other fields are
  lists of integers.
- Besides adding the fields mentioned above the package only adds
  queryset methods for filtering ancestors and descendants. Other
  features may be useful, but will not be added to the package just
  because it's possible to do so.
- Little code, and relatively simple when compared to other tree
  management solutions for Django.


Usage
=====

- Install ``django-tree-queries`` using pip.
- Extend ``tree_queries.models.TreeNode`` or build your own queryset
  and/or manager using ``tree_queries.query.TreeQuerySet`` The
  ``TreeNode`` abstract model already contains a ``parent`` foreign key
  for your convenience.
- Call the ``with_tree_fields()`` queryset method if you require the
  additional fields respectively the CTE.
- Until documentation is more complete I'll have to refer you to the
  `test suite
  <https://github.com/matthiask/django-tree-queries/blob/master/tests/testapp/test_queries.py>`_
  for additional instructions and usage examples.
