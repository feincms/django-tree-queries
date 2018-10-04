==========
Change log
==========

`Next version`_
~~~~~~~~~~~~~~~

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
.. _Next version: https://github.com/matthiask/django-tree-queries/compare/0.2...master
