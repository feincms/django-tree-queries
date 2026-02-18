from types import SimpleNamespace

import pytest
from django import template
from django.template import Context, Template
from django.test import TestCase

from testapp.models import Model, UnorderedModel
from tree_queries.templatetags.tree_queries import (
    previous_current_next,
    tree_info,
    tree_item_iterator,
)


@pytest.mark.django_db
class TestTemplateTags:
    def create_tree(self):
        tree = SimpleNamespace()
        tree.root = Model.objects.create(name="root")
        tree.child1 = Model.objects.create(parent=tree.root, order=0, name="1")
        tree.child2 = Model.objects.create(parent=tree.root, order=1, name="2")
        tree.child1_1 = Model.objects.create(parent=tree.child1, order=0, name="1-1")
        tree.child2_1 = Model.objects.create(parent=tree.child2, order=0, name="2-1")
        tree.child2_2 = Model.objects.create(parent=tree.child2, order=42, name="2-2")
        return tree

    def test_previous_current_next_basic(self):
        """Test the previous_current_next utility function"""
        items = [1, 2, 3, 4]
        result = list(previous_current_next(items))
        expected = [(None, 1, 2), (1, 2, 3), (2, 3, 4), (3, 4, None)]
        assert result == expected

    def test_previous_current_next_empty(self):
        """Test previous_current_next with empty list"""
        items = []
        result = list(previous_current_next(items))
        assert result == []

    def test_previous_current_next_single(self):
        """Test previous_current_next with single item"""
        items = [42]
        result = list(previous_current_next(items))
        assert result == [(None, 42, None)]

    def test_tree_item_iterator_basic(self):
        """Test tree_item_iterator without ancestors"""
        tree = self.create_tree()
        items = list(Model.objects.with_tree_fields())

        result = list(tree_item_iterator(items))

        # Check that we get the expected number of items
        assert len(result) == 6

        # Check structure of first item (root)
        item, structure = result[0]
        assert item == tree.root
        assert structure["new_level"] is True
        assert structure["closed_levels"] == []

        # Check structure of second item (child1)
        item, structure = result[1]
        assert item == tree.child1
        assert structure["new_level"] is True
        assert structure["closed_levels"] == []

        # Check structure of third item (child1_1)
        item, structure = result[2]
        assert item == tree.child1_1
        assert structure["new_level"] is True
        assert structure["closed_levels"] == [2]

        # Check structure of last item (child2_2)
        item, structure = result[5]
        assert item == tree.child2_2
        assert structure["new_level"] is False
        assert structure["closed_levels"] == [2, 1, 0]

    def test_tree_item_iterator_with_ancestors(self):
        """Test tree_item_iterator with ancestors enabled"""
        tree = self.create_tree()
        items = list(Model.objects.with_tree_fields())

        result = list(tree_item_iterator(items, ancestors=True))

        # Check structure of root item
        item, structure = result[0]
        assert item == tree.root
        assert structure["ancestors"] == []

        # Check structure of child1_1 item
        item, structure = result[2]
        assert item == tree.child1_1
        assert structure["ancestors"] == [str(tree.root), str(tree.child1)]

        # Check structure of child2_1 item
        item, structure = result[4]
        assert item == tree.child2_1
        assert structure["ancestors"] == [str(tree.root), str(tree.child2)]

    def test_tree_item_iterator_with_custom_callback(self):
        """Test tree_item_iterator with custom callback for ancestors"""
        tree = self.create_tree()
        items = list(Model.objects.with_tree_fields())

        # Custom callback that returns the name attribute
        def name_callback(obj):
            return obj.name

        result = list(tree_item_iterator(items, ancestors=True, callback=name_callback))

        # Check structure of child1_1 item with custom callback
        item, structure = result[2]
        assert item == tree.child1_1
        assert structure["ancestors"] == ["root", "1"]

    def test_tree_info_filter_basic(self):
        """Test the tree_info template filter basic functionality"""
        self.create_tree()
        items = list(Model.objects.with_tree_fields())

        result = list(tree_info(items))

        # Should return same as tree_item_iterator with ancestors=True
        expected = list(tree_item_iterator(items, ancestors=True))
        assert len(result) == len(expected)

        # Check that structure matches
        for (item1, struct1), (item2, struct2) in zip(result, expected):
            assert item1 == item2
            assert struct1["new_level"] == struct2["new_level"]
            assert struct1["closed_levels"] == struct2["closed_levels"]
            assert struct1["ancestors"] == struct2["ancestors"]

    def test_tree_info_filter_always_has_ancestors(self):
        """Test that tree_info filter always includes ancestors"""
        tree = self.create_tree()
        items = list(Model.objects.with_tree_fields())

        result = list(tree_info(items))

        # Check that ancestors are always included
        item, structure = result[2]  # child1_1
        assert item == tree.child1_1
        assert "ancestors" in structure
        assert structure["ancestors"] == [str(tree.root), str(tree.child1)]

        # Check root has empty ancestors
        item, structure = result[0]  # root
        assert item == tree.root
        assert "ancestors" in structure
        assert structure["ancestors"] == []

    def test_tree_info_in_template(self):
        """Test tree_info filter used in an actual Django template"""
        self.create_tree()
        items = list(Model.objects.with_tree_fields())

        template = Template("""
        {% load tree_queries %}
        {% for item, structure in items|tree_info %}
        {% if structure.new_level %}<ul><li>{% else %}</li><li>{% endif %}
        {{ item.name }}
        {% for level in structure.closed_levels %}</li></ul>{% endfor %}
        {% endfor %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Check that the template renders without errors
        assert "root" in result
        assert "1" in result
        assert "1-1" in result
        assert "2" in result
        assert "2-1" in result
        assert "2-2" in result

        # Check for proper nesting structure
        assert "<ul><li>" in result
        assert "</li></ul>" in result

    def test_tree_info_with_ancestors_in_template(self):
        """Test tree_info filter with ancestors in template"""
        self.create_tree()
        items = list(Model.objects.with_tree_fields())

        template = Template("""
        {% load tree_queries %}
        {% for item, structure in items|tree_info %}
        {{ item.name }}{% if structure.ancestors %} (ancestors: {% for ancestor in structure.ancestors %}{{ ancestor }}{% if not forloop.last %}, {% endif %}{% endfor %}){% endif %}
        {% endfor %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Check that ancestors are properly displayed
        assert "root" in result
        assert "(ancestors: root)" in result
        assert "(ancestors: root, 1)" in result
        assert "(ancestors: root, 2)" in result

    def test_empty_items_list(self):
        """Test template tags with empty items list"""
        result = list(tree_info([]))
        assert result == []

        result = list(tree_item_iterator([]))
        assert result == []

    def test_single_item_tree(self):
        """Test template tags with single item"""
        root = Model.objects.create(name="root")
        items = list(Model.objects.with_tree_fields())

        result = list(tree_info(items))
        assert len(result) == 1

        item, structure = result[0]
        assert item == root
        assert structure["new_level"] is True
        assert structure["closed_levels"] == [0]

    def test_recursetree_basic(self):
        """Test basic recursetree functionality"""
        self.create_tree()
        items = Model.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        <ul>
        {% recursetree items %}
            <li>
                {{ node.name }}
                {% if children %}
                    <ul>{{ children }}</ul>
                {% endif %}
            </li>
        {% endrecursetree %}
        </ul>
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Check that all nodes are rendered
        assert "root" in result
        assert "1" in result
        assert "1-1" in result
        assert "2" in result
        assert "2-1" in result
        assert "2-2" in result

        # Check nested structure
        assert "<ul>" in result
        assert "<li>" in result
        assert "</li>" in result
        assert "</ul>" in result

    def test_recursetree_with_depth_info(self):
        """Test recursetree with node depth information"""
        self.create_tree()
        items = Model.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div class="depth-{{ node.tree_depth }}">
                {{ node.name }}
                {{ children }}
            </div>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Check depth classes are applied correctly
        assert 'class="depth-0"' in result  # root
        assert 'class="depth-1"' in result  # child1, child2
        assert 'class="depth-2"' in result  # child1_1, child2_1, child2_2

    def test_recursetree_empty_queryset(self):
        """Test recursetree with empty queryset"""
        template = Template("""
        {% load tree_queries %}
        <ul>
        {% recursetree items %}
            <li>{{ node.name }}</li>
        {% endrecursetree %}
        </ul>
        """)

        context = Context({"items": Model.objects.none()})
        result = template.render(context)

        # Should render just the outer ul
        assert "<ul>" in result
        assert "</ul>" in result
        assert "<li>" not in result

    def test_recursetree_single_root(self):
        """Test recursetree with single root node"""
        Model.objects.create(name="lone-root")
        items = Model.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <span>{{ node.name }}</span>{{ children }}
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        assert "lone-root" in result
        assert "<span>" in result

    def test_recursetree_without_tree_fields(self):
        """Test recursetree with queryset that doesn't have tree fields"""
        self.create_tree()
        # Use regular queryset without tree fields
        items = Model.objects.all()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div>{{ node.name }}{{ children }}</div>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Should still render root node (the one with parent_id=None)
        assert "root" in result

    def test_recursetree_conditional_children(self):
        """Test recursetree with conditional children rendering"""
        self.create_tree()
        items = Model.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <li>
                {{ node.name }}
                {% if children %}
                    <ul class="has-children">{{ children }}</ul>
                {% else %}
                    <span class="leaf-node"></span>
                {% endif %}
            </li>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Check that leaf nodes get the leaf class
        assert 'class="leaf-node"' in result
        # Check that parent nodes get the has-children class
        assert 'class="has-children"' in result

    def test_recursetree_complex_template(self):
        """Test recursetree with more complex template logic"""
        self.create_tree()
        items = Model.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div data-id="{{ node.pk }}" data-depth="{{ node.tree_depth }}">
                <h{{ node.tree_depth|add:1 }}>{{ node.name }}</h{{ node.tree_depth|add:1 }}>
                {% if children %}
                    <div class="children-container">
                        {{ children }}
                    </div>
                {% endif %}
            </div>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Check data attributes are present
        assert "data-id=" in result
        assert "data-depth=" in result
        # Check heading levels (h1 for root, h2 for level 1, etc.)
        assert "<h1>" in result  # root
        assert "<h2>" in result  # children
        assert "<h3>" in result  # grandchildren

    def test_recursetree_syntax_error(self):
        """Test that recursetree raises proper syntax error for invalid usage"""
        with pytest.raises(template.TemplateSyntaxError) as excinfo:
            Template("""
            {% load tree_queries %}
            {% recursetree %}
            {% endrecursetree %}
            """)

        assert "tag requires a queryset" in str(excinfo.value)

        with pytest.raises(template.TemplateSyntaxError) as excinfo:
            Template("""
            {% load tree_queries %}
            {% recursetree items extra_arg %}
            {% endrecursetree %}
            """)

        assert "tag requires a queryset" in str(excinfo.value)

    def test_recursetree_limited_queryset_depth(self):
        """Test recursetree with queryset limited to specific depth"""
        self.create_tree()
        # Only get nodes up to depth 1 (root and first level children)
        items = Model.objects.with_tree_fields().extra(
            where=["__tree.tree_depth <= %s"], params=[1]
        )

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <li data-depth="{{ node.tree_depth }}">
                {{ node.name }}
                {% if children %}
                    <ul>{{ children }}</ul>
                {% endif %}
            </li>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Should include root, child1, child2 but NOT child1_1, child2_1, child2_2
        assert "root" in result
        assert "1" in result  # child1
        assert "2" in result  # child2
        assert "1-1" not in result  # should not be rendered
        assert "2-1" not in result  # should not be rendered
        assert "2-2" not in result  # should not be rendered

        # Check depth attributes
        assert 'data-depth="0"' in result  # root
        assert 'data-depth="1"' in result  # children
        assert 'data-depth="2"' not in result  # grandchildren excluded

    def test_recursetree_filtered_by_name(self):
        """Test recursetree with queryset filtered by specific criteria"""
        self.create_tree()
        # Only get nodes with specific names (partial tree)
        items = Model.objects.with_tree_fields().filter(
            name__in=["root", "2", "2-1", "1"]  # Excludes "1-1" and "2-2"
        )

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <span class="node">{{ node.name }}</span>{{ children }}
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Should include filtered nodes
        assert "root" in result
        assert ">1<" in result  # child1
        assert ">2<" in result  # child2
        assert "2-1" in result  # child2_1
        # Should NOT include excluded nodes
        assert "1-1" not in result
        assert "2-2" not in result

    def test_recursetree_subtree_only(self):
        """Test recursetree with queryset containing only a subtree"""
        tree = self.create_tree()
        # Only get child2 and its descendants (excludes root, child1, child1_1)
        items = Model.objects.descendants(tree.child2, include_self=True)

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div>{{ node.name }}{{ children }}</div>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Should include only child2 and its descendants
        assert "2" in result  # child2 (root of subtree)
        assert "2-1" in result
        assert "2-2" in result
        # Should NOT include nodes outside the subtree
        assert "root" not in result
        assert 'data-name="1"' not in result  # child1
        assert "1-1" not in result

    def test_recursetree_orphaned_nodes(self):
        """Test recursetree with queryset that has orphaned nodes (parent not in queryset)"""
        self.create_tree()
        # Get only leaf nodes (their parents are not included)
        items = Model.objects.with_tree_fields().filter(name__in=["1-1", "2-1", "2-2"])

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <li>{{ node.name }}{{ children }}</li>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # All nodes should be treated as roots since their parents aren't in queryset
        assert "1-1" in result
        assert "2-1" in result
        assert "2-2" in result
        # Should render three separate root nodes
        assert result.count("<li>") == 3

    def test_recursetree_mixed_levels(self):
        """Test recursetree with queryset containing nodes from different levels"""
        self.create_tree()
        # Mix of root, some children, and some grandchildren
        items = Model.objects.with_tree_fields().filter(
            name__in=["root", "1-1", "2", "2-2"]  # Skip child1 and child2_1
        )

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div data-name="{{ node.name }}">
                {{ node.name }}
                {% if children %}[{{ children }}]{% endif %}
            </div>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # root should be a root with child2 as its child
        assert 'data-name="root"' in result
        assert 'data-name="2"' in result
        # 1-1 should be orphaned (parent "1" not in queryset)
        assert 'data-name="1-1"' in result
        # 2-2 should be child of 2
        assert 'data-name="2-2"' in result
        # Check nesting - root should contain 2, and 2 should contain 2-2
        assert "root" in result
        assert "[" in result
        assert "]" in result  # 2 has children (contains closing bracket)

    def test_recursetree_no_database_queries_for_children(self):
        """Test that recursetree doesn't make additional database queries for children"""
        self.create_tree()
        items = Model.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div>{{ node.name }}{{ children }}</div>
        {% endrecursetree %}
        """)

        context = Context({"items": items})

        # Force evaluation of queryset to count queries
        list(items)

        # Count queries during template rendering

        tc = TestCase()
        with tc.assertNumQueries(0):  # Should not make any additional queries
            result = template.render(context)

        # Verify the result still contains all expected nodes
        assert "root" in result
        assert "1" in result
        assert "1-1" in result
        assert "2" in result
        assert "2-1" in result
        assert "2-2" in result

    def test_recursetree_is_leaf_context_variable(self):
        """Test that is_leaf context variable is properly set"""
        self.create_tree()
        items = Model.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div data-name="{{ node.name }}" data-is-leaf="{{ is_leaf }}">
                {{ node.name }}
                {% if is_leaf %}[LEAF]{% endif %}
                {{ children }}
            </div>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Check that leaf nodes are marked as such
        assert 'data-name="1-1" data-is-leaf="True"' in result  # child1_1 is leaf
        assert 'data-name="2-1" data-is-leaf="True"' in result  # child2_1 is leaf
        assert 'data-name="2-2" data-is-leaf="True"' in result  # child2_2 is leaf

        # Check that non-leaf nodes are marked as such
        assert 'data-name="root" data-is-leaf="False"' in result  # root has children
        assert 'data-name="1" data-is-leaf="False"' in result  # child1 has children
        assert 'data-name="2" data-is-leaf="False"' in result  # child2 has children

        # Check that [LEAF] appears for leaf nodes
        assert "[LEAF]" in result  # Should appear for leaf nodes
        assert (
            result.count("[LEAF]") == 3
        )  # Should appear exactly 3 times (for 1-1, 2-1, 2-2)

        # Check that [LEAF] doesn't appear for non-leaf nodes
        assert "root[LEAF]" not in result
        assert "1[LEAF]" not in result  # This might match "1-1[LEAF]", so be specific
        assert ">2[LEAF]" not in result

    def test_recursetree_is_leaf_with_limited_queryset(self):
        """Test is_leaf behavior with limited queryset"""
        self.create_tree()
        # Only get nodes up to depth 1 - so child1 and child2 appear as leaves
        items = Model.objects.with_tree_fields().extra(
            where=["__tree.tree_depth <= %s"], params=[1]
        )

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <span data-node="{{ node.name }}">
                {% if is_leaf %}LEAF:{{ node.name }}{% else %}BRANCH:{{ node.name }}{% endif %}
                {{ children }}
            </span>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # In this limited queryset, child1 and child2 should appear as leaves
        # even though they have children in the full tree
        assert "LEAF:1" in result  # child1 appears as leaf (no children in queryset)
        assert "LEAF:2" in result  # child2 appears as leaf (no children in queryset)
        assert "BRANCH:root" in result  # root has children (child1, child2) in queryset

        # These shouldn't appear since they're not in the queryset
        assert "1-1" not in result
        assert "2-1" not in result
        assert "2-2" not in result

    def test_recursetree_is_leaf_orphaned_nodes(self):
        """Test is_leaf with orphaned nodes (parent not in queryset)"""
        self.create_tree()
        # Get only leaf nodes - they should all be treated as leaf nodes
        items = Model.objects.with_tree_fields().filter(name__in=["1-1", "2-1", "2-2"])

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <li data-leaf="{{ is_leaf }}">{{ node.name }}</li>
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # All nodes should be leaves since they have no children in the queryset
        assert 'data-leaf="True"' in result
        assert 'data-leaf="False"' not in result
        assert result.count('data-leaf="True"') == 3  # All three nodes are leaves

    def test_recursetree_cache_reuse(self):
        """Test that recursetree cache is reused properly"""
        self.create_tree()
        items = Model.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div>{{ node.name }}{{ children }}</div>
        {% endrecursetree %}
        """)

        context = Context({"items": items})

        # First render should cache the children
        result1 = template.render(context)

        # Second render should reuse the cache
        result2 = template.render(context)

        assert result1 == result2
        assert "root" in result1

    def test_recursetree_nodes_without_tree_ordering(self):
        """Test recursetree with nodes that don't have tree_ordering attribute"""

        # Create tree without tree_ordering
        u0 = UnorderedModel.objects.create(name="u0")
        UnorderedModel.objects.create(name="u1", parent=u0)
        UnorderedModel.objects.create(name="u2", parent=u0)

        items = UnorderedModel.objects.with_tree_fields()

        template = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <span>{{ node.name }}</span>{{ children }}
        {% endrecursetree %}
        """)

        context = Context({"items": items})
        result = template.render(context)

        # Should render correctly even without tree_ordering
        assert "u0" in result
        assert "u1" in result
        assert "u2" in result

    def test_recursetree_reflects_database_changes_on_rerender(self):
        """Test that recursetree shows updated data after database changes (issue #102)"""
        tree = self.create_tree()

        t = Template("""
        {% load tree_queries %}
        {% recursetree items %}
            <div>{{ node.name }}{{ children }}</div>
        {% endrecursetree %}
        """)

        result1 = t.render(Context({"items": Model.objects.with_tree_fields()}))
        assert "1-1" in result1

        tree.child1_1.name = "updated-child"
        tree.child1_1.save()

        result2 = t.render(Context({"items": Model.objects.with_tree_fields()}))
        assert "updated-child" in result2
        assert "1-1" not in result2

    def test_tree_item_iterator_edge_cases(self):
        """Test edge cases in tree_item_iterator"""

        # Test with single item that has tree_depth attribute
        class MockNode:
            def __init__(self, name, tree_depth=0):
                self.name = name
                self.tree_depth = tree_depth  # Include required attribute

        mock_item = MockNode("test", tree_depth=0)

        # This should work correctly with tree_depth
        result = list(tree_item_iterator([mock_item], ancestors=True))
        assert len(result) == 1

        item, structure = result[0]
        assert item == mock_item
        assert structure["new_level"] is True
        assert "ancestors" in structure

    def test_previous_current_next_edge_cases(self):
        """Test edge cases in previous_current_next function"""

        # Test with generator that raises StopIteration
        def empty_generator():
            return
            yield  # Never reached

        result = list(previous_current_next(empty_generator()))
        assert result == []

        # Test with None items
        result = list(previous_current_next([None, None]))
        expected = [(None, None, None), (None, None, None)]
        assert result == expected
