# From https://raw.githubusercontent.com/triopter/django-tree-query-template/refs/heads/main/tq_template/templatetags/tq_template.py

import copy
import itertools

from django import template
from django.utils.safestring import mark_safe


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
def tree_info(items):
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
       ancestors
          A list of ancestors of the current node, in descending order
          (root node first, immediate parent last).
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
    return tree_item_iterator(items, ancestors=True)


class RecurseTreeNode(template.Node):
    """
    Template node for recursive tree rendering, similar to django-mptt's recursetree.

    Renders a section of template recursively for each node in a tree, providing
    'node' and 'children' context variables. Only considers nodes from the provided
    queryset - will not fetch additional children beyond what's in the queryset.
    """

    def __init__(self, nodelist, queryset_var):
        self.nodelist = nodelist
        self.queryset_var = queryset_var
        self._cached_children = None

    def _cache_tree_children(self, queryset):
        """
        Cache children relationships for all nodes in the queryset.
        This avoids additional database queries and respects the queryset boundaries.
        """
        if self._cached_children is not None:
            return self._cached_children

        self._cached_children = {}

        # Group nodes by their parent_id for efficient lookup
        for node in queryset:
            parent_id = getattr(node, "parent_id", None)
            if parent_id not in self._cached_children:
                self._cached_children[parent_id] = []
            self._cached_children[parent_id].append(node)

        # Sort children by tree_ordering if available, otherwise by pk
        for children_list in self._cached_children.values():
            if children_list and hasattr(children_list[0], "tree_ordering"):
                children_list.sort(key=lambda x: (x.tree_ordering, x.pk))
            else:
                children_list.sort(key=lambda x: x.pk)

        return self._cached_children

    def _get_children_from_cache(self, node):
        """Get children of a node from the cached children, not from database"""
        if self._cached_children is None:
            return []
        return self._cached_children.get(node.pk, [])

    def _render_node(self, context, node):
        """Recursively render a node and its children from the cached queryset"""
        bits = []
        context.push()

        # Get children from cache (only nodes that were in the original queryset)
        children = self._get_children_from_cache(node)
        for child in children:
            bits.append(self._render_node(context, child))

        # Set context variables that templates can access
        context["node"] = node
        context["children"] = mark_safe("".join(bits))
        context["is_leaf"] = len(children) == 0

        # Render the template with the current node context
        rendered = self.nodelist.render(context)
        context.pop()
        return rendered

    def render(self, context):
        """Render the complete tree starting from root nodes in the queryset"""
        queryset = self.queryset_var.resolve(context)

        # Ensure we have tree fields for proper traversal
        if hasattr(queryset, "with_tree_fields"):
            queryset = queryset.with_tree_fields()

        # Convert to list to avoid re-evaluation and cache the children relationships
        queryset_list = list(queryset)
        self._cache_tree_children(queryset_list)

        # Get root nodes (nodes without parents or whose parents are not in the queryset)
        queryset_pks = {node.pk for node in queryset_list}
        roots = []

        for node in queryset_list:
            parent_id = getattr(node, "parent_id", None)
            if parent_id is None or parent_id not in queryset_pks:
                roots.append(node)

        # Sort roots by tree_ordering if available, otherwise by pk
        if roots and hasattr(roots[0], "tree_ordering"):
            roots.sort(key=lambda x: (x.tree_ordering, x.pk))
        else:
            roots.sort(key=lambda x: x.pk)

        # Render each root node and its descendants
        bits = [self._render_node(context, node) for node in roots]
        return "".join(bits)


@register.tag
def recursetree(parser, token):
    """
    Recursively render a tree structure.

    Usage:
        {% recursetree nodes %}
            <li>
                {{ node.name }}
                {% if children %}
                    <ul>{{ children }}</ul>
                {% elif is_leaf %}
                    <span class="leaf">Leaf node</span>
                {% endif %}
            </li>
        {% endrecursetree %}

    This tag will render the template content for each node in the tree,
    providing these variables in the template context:
    - 'node': the current tree node
    - 'children': rendered HTML of all child nodes in the queryset
    - 'is_leaf': True if the node has no children in the queryset, False otherwise
    """
    bits = token.contents.split()
    if len(bits) != 2:
        raise template.TemplateSyntaxError(f"{bits[0]} tag requires a queryset")

    queryset_var = template.Variable(bits[1])
    nodelist = parser.parse(("endrecursetree",))
    parser.delete_first_token()

    return RecurseTreeNode(nodelist, queryset_var)
