from types import SimpleNamespace

import pytest
from django.template import Context, Template

from testapp.models import Model
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
        tree = self.create_tree()
        items = list(Model.objects.with_tree_fields())

        result = list(tree_info(items))

        # Should return same as tree_item_iterator without features
        expected = list(tree_item_iterator(items))
        assert len(result) == len(expected)

        # Check that structure matches
        for (item1, struct1), (item2, struct2) in zip(result, expected):
            assert item1 == item2
            assert struct1["new_level"] == struct2["new_level"]
            assert struct1["closed_levels"] == struct2["closed_levels"]

    def test_tree_info_filter_with_ancestors(self):
        """Test the tree_info template filter with ancestors feature"""
        tree = self.create_tree()
        items = list(Model.objects.with_tree_fields())

        result = list(tree_info(items, "ancestors"))

        # Check that ancestors are included
        item, structure = result[2]  # child1_1
        assert item == tree.child1_1
        assert "ancestors" in structure
        assert structure["ancestors"] == [str(tree.root), str(tree.child1)]

    def test_tree_info_filter_multiple_features(self):
        """Test the tree_info template filter with multiple features"""
        tree = self.create_tree()
        items = list(Model.objects.with_tree_fields())

        # Test with ancestors feature in a comma-separated list
        result = list(tree_info(items, "ancestors,other"))

        # Check that ancestors are included
        item, structure = result[2]  # child1_1
        assert "ancestors" in structure

    def test_tree_info_in_template(self):
        """Test tree_info filter used in an actual Django template"""
        tree = self.create_tree()
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
        """Test tree_info filter with ancestors feature in template"""
        tree = self.create_tree()
        items = list(Model.objects.with_tree_fields())

        template = Template("""
        {% load tree_queries %}
        {% for item, structure in items|tree_info:"ancestors" %}
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
