Change log
==========

`Next version`_
~~~~~~~~~~~~~~~

- Fixed a grave bug where a position of ``110`` would be sorted before
  ``20`` for obvious reasons.
- Added a custom ``TreeNodeForeignKey.deconstruct`` method to avoid
  migrations because of changing field types.
- Removed one case of unnecessary fumbling in ``Query``'s internals
  making things needlessly harder than they need to be. Made
  django-tree-queries compatible with Django's master branch.
- Removed Python 3.4 from the Travis CI job list.


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
.. _Next version: https://github.com/matthiask/django-tree-queries/compare/0.3...master
