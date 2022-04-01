Change log
==========

`Next version`_
~~~~~~~~~~~~~~~

.. _Next version: https://github.com/matthiask/django-tree-queries/compare/0.9...main


`0.9`_ (2022-04-01)
~~~~~~~~~~~~~~~~~~~

.. _0.9: https://github.com/matthiask/django-tree-queries/compare/0.8...0.9

- Added ``TreeQuerySet.order_siblings_by`` which allows specifying an ordering
  for siblings per-query.


`0.8`_ (2022-03-09)
~~~~~~~~~~~~~~~~~~~

.. _0.8: https://github.com/matthiask/django-tree-queries/compare/0.7...0.8

- Added pre-commit configuration to automatically remove some old-ish code
  patterns.
- Fixed a compatibility problem with the upcoming Django 4.1.


`0.7`_ (2021-10-31)
~~~~~~~~~~~~~~~~~~~

.. _0.7: https://github.com/matthiask/django-tree-queries/compare/0.6...0.7

- Added a test with a tree node having a UUID as its primary key.


`0.6`_ (2021-07-21)
~~~~~~~~~~~~~~~~~~~

- Fixed ``TreeQuerySet.ancestors`` to support primary keys not named ``id``.
- Changed the tree compiler to only post-process its own database results.
- Added ``**kwargs``-passing to ``TreeQuery.get_compiler`` for compatibility
  with Django 4.0.


`0.5`_ (2021-05-12)
~~~~~~~~~~~~~~~~~~~

- Added support for adding tree fields to queries by default. Create a
  manager using ``TreeQuerySet.as_manager(with_tree_fields=True)``.
- Ensured the availability of the ``with_tree_fields`` configuration
  also on subclassed managers, e.g. those used for traversing reverse
  relations.
- Dropped compatibility with Django 1.8 to avoid adding workarounds to
  the testsuite.
- Made it possible to use django-tree-queries in more situations involving
  JOINs. Thanks Safa Alfulaij for the contribution!


`0.4`_ (2020-09-13)
~~~~~~~~~~~~~~~~~~~

- Fixed a grave bug where a position of ``110`` would be sorted before
  ``20`` for obvious reasons.
- Added a custom ``TreeNodeForeignKey.deconstruct`` method to avoid
  migrations because of changing field types.
- Removed one case of unnecessary fumbling in ``Query``'s internals
  making things needlessly harder than they need to be. Made
  django-tree-queries compatible with Django's master branch.
- Removed Python 3.4 from the Travis CI job list.
- Dropped the conversion of primary keys to text on PostgreSQL. It's a
  documented constraint that django-tree-queries only supports integer
  primary keys, therefore the conversion wasn't necessary at all.
- Reverted to using integer arrays on PostgreSQL for ordering if
  possible instead of always converting everything to padded strings.


`0.3`_ (2018-11-15)
~~~~~~~~~~~~~~~~~~~

- Added a ``label_from_instance`` override to the form fields.
- Removed the limitation that nodes can only be ordered using an integer
  field within their siblings.
- Changed the representation of ``tree_path`` and ``tree_ordering`` used
  on MySQL/MariaDB and sqlite3. Also made it clear that the
  representation isn't part of the public interface of this package.


`0.2`_ (2018-10-04)
~~~~~~~~~~~~~~~~~~~

- Added an optional argument to ``TreeQuerySet.with_tree_fields()`` to
  allow reverting to a standard queryset (without tree fields).
- Added ``tree_queries.fields.TreeNodeForeignKey``,
  ``tree_queries.forms.TreeNodeChoiceField`` and
  ``tree_queries.forms.TreeNodeMultipleChoiceField`` with node depth
  visualization.
- Dropped Python 3.4 from the CI.


`0.1`_ (2018-07-30)
~~~~~~~~~~~~~~~~~~~

- Initial release!

.. _0.1: https://github.com/matthiask/django-tree-queries/commit/93d70046a2
.. _0.2: https://github.com/matthiask/django-tree-queries/compare/0.1...0.2
.. _0.3: https://github.com/matthiask/django-tree-queries/compare/0.2...0.3
.. _0.4: https://github.com/matthiask/django-tree-queries/compare/0.3...0.4
.. _0.5: https://github.com/matthiask/django-tree-queries/compare/0.4...0.5
.. _0.6: https://github.com/matthiask/django-tree-queries/compare/0.5...0.6
