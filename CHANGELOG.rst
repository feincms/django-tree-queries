Change log
==========

Next version
~~~~~~~~~~~~

0.20 (2025-06-11)
~~~~~~~~~~~~~~~~~

- Added Python 3.13, Django 5.1 and 5.2 to the testsuite.
- Added tests showing that ``.descendants().update(...)`` doesn't work, but
  ``.filter(pk__in=....descendants()).update(...)`` does.
- Added Python 3.13 to the testsuite.
- Converted the tests to use pytest.
- Added a ``tree_info`` template tag and a ``recursetree`` template block.
- Optimized the performance by avoiding the rank table altogether in the simple
  case of an ascending ordering on a single field. If that's not possible, the
  README now documents using ``.tree_filter()`` and ``.tree_exclude()`` to
  filter the queryset before running the recursive CTE.
- Improved the test coverage.


0.19 (2024-04-25)
~~~~~~~~~~~~~~~~~

- Reimplemented the rank table construction using a real queryset; this enables
  support for pre-filtering the tree queryset using ``.tree_filter()`` and
  ``.tree_exclude()``. Thanks rhomboss!
- Added a ``.tree_fields()`` method to allow adding additional columns to the
  tree queryset, allowing collecting ancestors fields directly when running the
  initial query. For example, ``.tree_fields(tree_names="name")`` will collect
  all ``name`` fields in a ``tree_fields`` array on the model instances. For
  now the code only supports string fields and integer fields.


0.18 (2024-04-03)
~~~~~~~~~~~~~~~~~

- Fixed broken SQL which was generated when using a tree query with
  ``EXISTS()`` subqueries.


0.17 (2024-03-26)
~~~~~~~~~~~~~~~~~

- Preserved the tree ordering even when using ``.values()`` or
  ``.values_list()``. Thanks Glenn Matthews!
- Added support for descending sibling ordering, multi-field sibling ordering,
  and related field sibling ordering. Thanks rhomboss!


0.16 (2023-11-29)
~~~~~~~~~~~~~~~~~

- Added Python 3.12, Django 5.0.
- Fixed a problem where ``.values()`` would return an incorrect mapping. Thanks
  Glenn Matthews!
- Started running tests periodically to catch bugs earlier.


0.15 (2023-06-19)
~~~~~~~~~~~~~~~~~

- Switched to ruff and hatchling.
- Dropped Django 4.0.
- Added Python 3.11.
- Added a ``.without_tree_fields()`` method which calls
  ``.with_tree_fields(False)`` in a way which doesn't trigger the flake8
  boolean trap linter.


`0.14`_ (2023-01-30)
~~~~~~~~~~~~~~~~~~~~

.. _0.14: https://github.com/matthiask/django-tree-queries/compare/0.13...0.14

- Changed the behavior around sibling ordering to warn if using
  ``Meta.ordering`` where ordering contains more than one field.
- Added Django 4.2a1 to the CI.
- Django 5.0 will require Python 3.10 or better, pruned the CI jobs list.
- Added quoting to the field name for the ordering between siblings so that
  fields named ``order`` can be used. Thanks Tao Bojlén!
- Narrowed exception catching when determining whether the ordering field is an
  integer field or not. Thanks Tao Bojlén.


`0.13`_ (2022-12-08)
~~~~~~~~~~~~~~~~~~~~

.. _0.13: https://github.com/matthiask/django-tree-queries/compare/0.12...0.13

- Made it possible to use tree queries with multiple table inheritance. Thanks
  Olivier Dalang for the testcases and the initial implementation!


`0.12`_ (2022-11-30)
~~~~~~~~~~~~~~~~~~~~

.. _0.12: https://github.com/matthiask/django-tree-queries/compare/0.11...0.12

- Removed compatibility with Django < 3.2, Python < 3.8.
- Added Django 4.1 to the CI.
- Fixed ``.with_tree_fields().explain()`` on some databases. Thanks Bryan
  Culver!


`0.11`_ (2022-06-10)
~~~~~~~~~~~~~~~~~~~~

.. _0.11: https://github.com/matthiask/django-tree-queries/compare/0.10...0.11

- Fixed a crash when running ``.with_tree_fields().distinct().count()`` by 1.
  avoiding to select tree fields in distinct subqueries and 2. trusting the
  testsuite.


`0.10`_ (2022-06-07)
~~~~~~~~~~~~~~~~~~~~

.. _0.10: https://github.com/matthiask/django-tree-queries/compare/0.9...0.10

- Fixed ordering by string fields to actually work correctly in the presence of
  values of varying length.


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
