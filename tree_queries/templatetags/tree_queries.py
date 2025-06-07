# From https://raw.githubusercontent.com/triopter/django-tree-query-template/refs/heads/main/tq_template/templatetags/tq_template.py

import copy
import itertools

from django import template


register = template.Library()


def previous_current_next(items):
    """
    From http://www.wordaligned.org/articles/zippy-triples-served-with-python
    Creates an iterator which returns (previous, current, next) triples,
    with ``None`` filling in when there is no previous or next
    available.
    """
    extend = itertools.chain([None], items, [None])
    prev, cur, nex = itertools.tee(extend, 3)
    # Advancing an iterator twice when we know there are two items (the
    # two Nones at the start and at the end) will never fail except if
    # `items` is some funny StopIteration-raising generator. There's no point
    # in swallowing this exception.
    next(cur)
    next(nex)
    next(nex)
    return zip(prev, cur, nex)


def tree_item_iterator(items, *, ancestors=False, callback=str):
    """
    Given a list of tree items, iterates over the list, generating
    two-tuples of the current tree item and a ``dict`` containing
    information about the tree structure around the item, with the
    following keys:
       ``'new_level'``
          ``True`` if the current item is the start of a new level in
          the tree, ``False`` otherwise.
       ``'closed_levels'``
          A list of levels which end after the current item. This will
          be an empty list if the next item is at the same level as the
          current item.
    If ``ancestors`` is ``True``, the following key will also be
    available:
       ``'ancestors'``
          A list of representations of the ancestors of the current
          node, in descending order (root node first, immediate parent
          last).
          For example: given the sample tree below, the contents of the
          list which would be available under the ``'ancestors'`` key
          are given on the right::
             Books                    ->  []
                Sci-fi                ->  ['Books']
                   Dystopian Futures  ->  ['Books', 'Sci-fi']
          You can overload the default representation by providing an
          optional ``callback`` function which takes a single argument
          and performs coersion as required.
    """
    structure = {}
    first_item_level = 0
    for previous, current, next_ in previous_current_next(items):
        current_level = current.tree_depth
        if previous:
            structure["new_level"] = previous.tree_depth < current_level
            if ancestors:
                # If the previous node was the end of any number of
                # levels, remove the appropriate number of ancestors
                # from the list.
                if structure["closed_levels"]:
                    structure["ancestors"] = structure["ancestors"][
                        : -len(structure["closed_levels"])
                    ]
                # If the current node is the start of a new level, add its
                # parent to the ancestors list.
                if structure["new_level"]:
                    structure["ancestors"].append(callback(previous))
        else:
            structure["new_level"] = True
            if ancestors:
                # Set up the ancestors list on the first item
                structure["ancestors"] = []

            first_item_level = current_level
        if next_:
            structure["closed_levels"] = list(
                range(current_level, next_.tree_depth, -1)
            )
        else:
            # All remaining levels need to be closed
            structure["closed_levels"] = list(
                range(current_level, first_item_level - 1, -1)
            )

        # Return a deep copy of the structure dict so this function can
        # be used in situations where the iterator is consumed
        # immediately.
        yield current, copy.deepcopy(structure)


@register.filter
def tree_info(items, features=None):
    """
    Given a list of tree items, produces doubles of a tree item and a
    ``dict`` containing information about the tree structure around the
    item, with the following contents:
       new_level
          ``True`` if the current item is the start of a new level in
          the tree, ``False`` otherwise.
       closed_levels
          A list of levels which end after the current item. This will
          be an empty list if the next item is at the same level as the
          current item.
    Using this filter with unpacking in a ``{% for %}`` tag, you should
    have enough information about the tree structure to create a
    hierarchical representation of the tree.
    Example::
       {% for genre,structure in genres|tree_info %}
       {% if structure.new_level %}<ul><li>{% else %}</li><li>{% endif %}
       {{ genre.name }}
       {% for level in structure.closed_levels %}</li></ul>{% endfor %}
       {% endfor %}
    """
    kwargs = {}
    if features:
        feature_names = features.split(",")
        if "ancestors" in feature_names:
            kwargs["ancestors"] = True
    return tree_item_iterator(items, **kwargs)
