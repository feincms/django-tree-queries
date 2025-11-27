from django.test import TestCase

from .models import OrderedModel


class OrderableTreeNodeTestCase(TestCase):
    def test_automatic_position_assignment(self):
        """Test that position is automatically assigned to new nodes"""
        root = OrderedModel.objects.create(name="Root")
        assert root.position == 10

        child1 = OrderedModel.objects.create(name="Child 1", parent=root)
        assert child1.position == 10

        child2 = OrderedModel.objects.create(name="Child 2", parent=root)
        assert child2.position == 20

        child3 = OrderedModel.objects.create(name="Child 3", parent=root)
        assert child3.position == 30

    def test_manual_position_respected(self):
        """Test that manually set positions are not overwritten"""
        root = OrderedModel.objects.create(name="Root", position=100)
        assert root.position == 100

        child = OrderedModel.objects.create(name="Child", parent=root, position=50)
        assert child.position == 50

    def test_position_increments_from_max(self):
        """Test that positions increment from the current maximum"""
        root = OrderedModel.objects.create(name="Root")

        # Create children with custom positions
        OrderedModel.objects.create(name="Child 1", parent=root, position=100)
        OrderedModel.objects.create(name="Child 2", parent=root, position=200)

        # Next auto-assigned position should be max + 10
        child3 = OrderedModel.objects.create(name="Child 3", parent=root)
        assert child3.position == 210

    def test_siblings_ordered_by_position(self):
        """Test that siblings are correctly ordered by position"""
        root = OrderedModel.objects.create(name="Root")

        child1 = OrderedModel.objects.create(name="Child 1", parent=root)
        child2 = OrderedModel.objects.create(name="Child 2", parent=root)
        child3 = OrderedModel.objects.create(name="Child 3", parent=root)

        siblings = list(root.children.all())
        assert siblings[0] == child1
        assert siblings[1] == child2
        assert siblings[2] == child3

    def test_reordering_siblings(self):
        """Test that siblings can be manually reordered"""
        root = OrderedModel.objects.create(name="Root")

        child1 = OrderedModel.objects.create(name="Child 1", parent=root)  # position=10
        child2 = OrderedModel.objects.create(name="Child 2", parent=root)  # position=20
        child3 = OrderedModel.objects.create(name="Child 3", parent=root)  # position=30

        # Move child3 between child1 and child2
        child3.position = 15
        child3.save()

        siblings = list(root.children.all())
        assert siblings[0] == child1
        assert siblings[1] == child3
        assert siblings[2] == child2

    def test_position_per_parent(self):
        """Test that positions are assigned per parent"""
        root1 = OrderedModel.objects.create(name="Root 1")
        root2 = OrderedModel.objects.create(name="Root 2")

        child1_1 = OrderedModel.objects.create(name="Child 1-1", parent=root1)
        child2_1 = OrderedModel.objects.create(name="Child 2-1", parent=root2)

        # Both should get position 10 since they have different parents
        assert child1_1.position == 10
        assert child2_1.position == 10

        child1_2 = OrderedModel.objects.create(name="Child 1-2", parent=root1)
        child2_2 = OrderedModel.objects.create(name="Child 2-2", parent=root2)

        # Both should get position 20
        assert child1_2.position == 20
        assert child2_2.position == 20

    def test_ordering_with_tree_queries(self):
        """Test that ordering works correctly with tree queries"""
        root = OrderedModel.objects.create(name="Root")
        child1 = OrderedModel.objects.create(name="Child 1", parent=root)
        OrderedModel.objects.create(name="Grandchild 1", parent=child1)
        OrderedModel.objects.create(name="Grandchild 2", parent=child1)
        OrderedModel.objects.create(name="Child 2", parent=root)

        # Get tree with tree fields
        nodes = list(OrderedModel.objects.with_tree_fields())

        # Verify depth-first order respects position ordering
        assert nodes[0].name == "Root"
        assert nodes[1].name == "Child 1"
        assert nodes[2].name == "Grandchild 1"
        assert nodes[3].name == "Grandchild 2"
        assert nodes[4].name == "Child 2"

    def test_update_preserves_position(self):
        """Test that updating a node doesn't change its position"""
        root = OrderedModel.objects.create(name="Root")
        child = OrderedModel.objects.create(name="Child", parent=root)

        original_position = child.position
        assert original_position == 10

        # Update the name
        child.name = "Updated Child"
        child.save()

        # Position should remain the same
        assert child.position == original_position

    def test_zero_position_is_replaced(self):
        """Test that position=0 triggers auto-assignment"""
        root = OrderedModel.objects.create(name="Root")

        # Even if we explicitly set position=0, it should be replaced on create
        child = OrderedModel(name="Child", parent=root, position=0)
        child.save()

        assert child.position == 10

        # Create another child to verify positions increment correctly
        child2 = OrderedModel.objects.create(name="Child 2", parent=root)
        assert child2.position == 20

    def test_ordering_inherited_from_meta(self):
        """Test that ordering is inherited from OrderableTreeNode.Meta"""
        # This test verifies that the Meta.ordering is properly inherited
        root = OrderedModel.objects.create(name="Root")
        OrderedModel.objects.create(name="Child 2", parent=root, position=20)
        OrderedModel.objects.create(name="Child 1", parent=root, position=10)
        OrderedModel.objects.create(name="Child 3", parent=root, position=30)

        # Query without explicit ordering should use Meta.ordering
        children = list(OrderedModel.objects.filter(parent=root))

        assert children[0].name == "Child 1"
        assert children[1].name == "Child 2"
        assert children[2].name == "Child 3"
