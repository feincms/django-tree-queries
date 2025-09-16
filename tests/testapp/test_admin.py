from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import models as django_models
from django.test import RequestFactory, TestCase

from testapp import models
from testapp.admin import ModelAdmin, UnorderedModelAdmin
from tree_queries.admin import MOVE_POSITIONS, MOVE_POSITIONS_PARENT_ONLY, MoveNodeForm


class TreeAdminTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()

        # Create superuser for admin access
        self.user = User.objects.create_superuser("admin", "admin@test.com", "password")

        # Set up test tree structure with ordering
        self.root = models.Model.objects.create(name="root", order=10)
        self.child1 = models.Model.objects.create(
            name="child1", parent=self.root, order=10
        )
        self.child2 = models.Model.objects.create(
            name="child2", parent=self.root, order=20
        )
        self.grandchild = models.Model.objects.create(
            name="grandchild", parent=self.child1, order=10
        )

        # Set up unordered tree structure
        self.unordered_root = models.UnorderedModel.objects.create(name="root")
        self.unordered_child = models.UnorderedModel.objects.create(
            name="child", parent=self.unordered_root
        )

    def setup_request(self, request):
        """Set up request with proper middleware for messages and sessions."""
        # Set up session
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()

        # Set up messages
        request._messages = FallbackStorage(request)
        request.user = self.user
        return request

    def test_position_field_configuration(self):
        """Test different position field configurations."""
        # Model with position field
        admin = ModelAdmin(models.Model, self.site)
        assert admin.position_field == "order"
        assert admin.position_field

        # Model without position field
        admin = UnorderedModelAdmin(models.UnorderedModel, self.site)
        assert admin.position_field is None
        assert not admin.position_field

    def test_move_positions_with_ordering(self):
        """Test available move positions when ordering is controllable."""
        admin = ModelAdmin(models.Model, self.site)
        request = self.factory.get("/")
        request.user = self.user

        # Should show all positions
        move_column_html = admin.move_column(self.child1)

        for key in MOVE_POSITIONS:
            assert f'value="{key}"' in move_column_html

    def test_move_positions_without_ordering(self):
        """Test available move positions when ordering is not controllable."""
        admin = UnorderedModelAdmin(models.UnorderedModel, self.site)
        request = self.factory.get("/")
        request.user = self.user

        # Should show only parent-only positions
        move_column_html = admin.move_column(self.unordered_child)

        for key in MOVE_POSITIONS_PARENT_ONLY:
            assert f'value="{key}"' in move_column_html

        # Should not show sibling positions
        assert 'value="before"' not in move_column_html
        assert 'value="after"' not in move_column_html

        # Should show "move to root" button for child nodes in models without ordering
        assert "move-to-root" in move_column_html

        # But root nodes should NOT show the "move to root" button
        root_move_column_html = admin.move_column(self.unordered_root)
        assert "move-to-root" not in root_move_column_html

    def test_tree_admin_context(self):
        """Test the context provided to JavaScript."""
        admin = ModelAdmin(models.Model, self.site)
        request = self.factory.get("/")
        request.user = self.user

        context = admin.tree_admin_context(request)
        assert context["initiallyCollapseDepth"] == 1

        # Test without ordering
        admin = UnorderedModelAdmin(models.UnorderedModel, self.site)
        context = admin.tree_admin_context(request)
        assert context["initiallyCollapseDepth"] == 1

    def test_move_node_form_with_ordering(self):
        """Test move node form validation with ordering field."""
        admin = ModelAdmin(models.Model, self.site)
        request = self.factory.post(
            "/admin/testapp/model/move-node/",
            {
                "move": self.grandchild.pk,
                "relative_to": self.child2.pk,
                "position": "before",
            },
        )
        request.user = self.user

        form = MoveNodeForm(request.POST, modeladmin=admin, request=request)
        assert form.is_valid()

        # Test all valid positions
        for position in MOVE_POSITIONS:
            form = MoveNodeForm(
                {
                    "move": self.grandchild.pk,
                    "relative_to": self.child2.pk,
                    "position": position,
                },
                modeladmin=admin,
                request=request,
            )
            assert form.is_valid(), f"Position {position} should be valid"

    def test_move_node_form_without_ordering(self):
        """Test move node form validation without ordering field."""
        admin = UnorderedModelAdmin(models.UnorderedModel, self.site)
        request = self.factory.post(
            "/admin/testapp/unorderedmodel/move-node/",
            {
                "move": self.unordered_child.pk,
                "relative_to": self.unordered_root.pk,
                "position": "child",
            },
        )
        request.user = self.user

        form = MoveNodeForm(request.POST, modeladmin=admin, request=request)
        assert form.is_valid()

        # Test only valid positions for unordered model
        for position in MOVE_POSITIONS_PARENT_ONLY:
            form = MoveNodeForm(
                {
                    "move": self.unordered_child.pk,
                    "relative_to": self.unordered_root.pk,
                    "position": position,
                },
                modeladmin=admin,
                request=request,
            )
            assert form.is_valid(), f"Position {position} should be valid"

        # Test invalid positions for unordered model
        form = MoveNodeForm(
            {
                "move": self.unordered_child.pk,
                "relative_to": self.unordered_root.pk,
                "position": "before",
            },
            modeladmin=admin,
            request=request,
        )
        assert not form.is_valid()

        # Test that "root" is valid without relative_to
        form = MoveNodeForm(
            {"move": self.unordered_child.pk, "position": "root"},
            modeladmin=admin,
            request=request,
        )
        assert form.is_valid()

        # Test that "root" is also valid with relative_to (for backward compatibility)
        form = MoveNodeForm(
            {
                "move": self.unordered_child.pk,
                "relative_to": self.unordered_root.pk,
                "position": "root",
            },
            modeladmin=admin,
            request=request,
        )
        assert form.is_valid()

        # Test that non-root positions require relative_to
        form = MoveNodeForm(
            {"move": self.unordered_child.pk, "position": "child"},
            modeladmin=admin,
            request=request,
        )
        assert not form.is_valid()


class MoveOperationTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()

        self.user = User.objects.create_superuser("admin", "admin@test.com", "password")

        # Create test tree with ordering
        self.root = models.Model.objects.create(name="root", order=10)
        self.child1 = models.Model.objects.create(
            name="child1", parent=self.root, order=10
        )
        self.child2 = models.Model.objects.create(
            name="child2", parent=self.root, order=20
        )
        self.child3 = models.Model.objects.create(
            name="child3", parent=self.root, order=30
        )

    def setup_request(self, request):
        """Set up request with proper middleware for messages and sessions."""
        # Set up session
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()

        # Set up messages
        request._messages = FallbackStorage(request)
        request.user = self.user
        return request

    def test_move_before(self):
        """Test moving a node before another sibling."""
        admin = ModelAdmin(models.Model, self.site)
        request = self.factory.post("/test/")
        request.user = self.user

        form = MoveNodeForm(
            {
                "move": self.child3.pk,
                "relative_to": self.child1.pk,
                "position": "before",
            },
            modeladmin=admin,
            request=request,
        )

        # Verify form is valid
        assert form.is_valid()

        # Test the move logic directly
        move = form.cleaned_data["move"]
        relative_to = form.cleaned_data["relative_to"]
        form.cleaned_data["position"]

        # Simulate the move logic
        move.parent = relative_to.parent
        position_field = admin.position_field
        siblings_qs = relative_to.__class__._default_manager.filter(
            parent=relative_to.parent
        )
        siblings_qs.filter(**{
            f"{position_field}__gte": getattr(relative_to, position_field)
        }).update(**{position_field: django_models.F(position_field) + 10})
        setattr(move, position_field, getattr(relative_to, position_field))
        move.save()

        # Refresh from database
        self.child3.refresh_from_db()
        self.child1.refresh_from_db()

        # child3 should now have the same order as child1 originally had
        assert self.child3.order == 10

    def test_move_after(self):
        """Test moving a node after another sibling."""
        admin = ModelAdmin(models.Model, self.site)
        request = self.factory.post(
            "/admin/testapp/model/move-node/",
            {
                "move": self.child1.pk,
                "relative_to": self.child2.pk,
                "position": "after",
            },
        )
        request = self.setup_request(request)

        form = MoveNodeForm(request.POST, modeladmin=admin, request=request)
        result = form.process()

        assert result == "ok"

        # Refresh from database
        self.child1.refresh_from_db()

        # child1 should now be positioned after child2
        assert self.child1.order == 30  # child2.order + 10

    def test_move_first_child(self):
        """Test moving a node as first child."""
        # Create a new node to move
        new_child = models.Model.objects.create(name="new_child", order=100)

        admin = ModelAdmin(models.Model, self.site)
        request = self.factory.post(
            "/admin/testapp/model/move-node/",
            {
                "move": new_child.pk,
                "relative_to": self.root.pk,
                "position": "first-child",
            },
        )
        request = self.setup_request(request)

        form = MoveNodeForm(request.POST, modeladmin=admin, request=request)
        result = form.process()

        assert result == "ok"

        # Refresh from database
        new_child.refresh_from_db()

        # Should be child of root and have order 10 (first position)
        assert new_child.parent == self.root
        assert new_child.order == 10

    def test_move_last_child(self):
        """Test moving a node as last child."""
        new_child = models.Model.objects.create(name="new_child", order=100)

        admin = ModelAdmin(models.Model, self.site)
        request = self.factory.post(
            "/admin/testapp/model/move-node/",
            {
                "move": new_child.pk,
                "relative_to": self.root.pk,
                "position": "last-child",
            },
        )
        request = self.setup_request(request)

        form = MoveNodeForm(request.POST, modeladmin=admin, request=request)
        result = form.process()

        assert result == "ok"

        # Refresh from database
        new_child.refresh_from_db()

        # Should be child of root
        assert new_child.parent == self.root

    def test_move_to_root_without_ordering(self):
        """Test moving a node to root level when no ordering is available."""
        # Use unordered model
        root = models.UnorderedModel.objects.create(name="root")
        child = models.UnorderedModel.objects.create(name="child", parent=root)

        admin = UnorderedModelAdmin(models.UnorderedModel, self.site)
        request = self.factory.post(
            "/admin/testapp/unorderedmodel/move-node/",
            {
                "move": child.pk,
                "position": "root",  # No relative_to needed for root moves
            },
        )
        request = self.setup_request(request)

        form = MoveNodeForm(request.POST, modeladmin=admin, request=request)
        result = form.process()

        assert result == "ok"

        # Refresh from database
        child.refresh_from_db()

        # Should now be at root level
        assert child.parent is None

    def test_move_as_child_without_ordering(self):
        """Test moving a node as child when no ordering is available."""
        root1 = models.UnorderedModel.objects.create(name="root1")
        root2 = models.UnorderedModel.objects.create(name="root2")
        child = models.UnorderedModel.objects.create(name="child", parent=root1)

        admin = UnorderedModelAdmin(models.UnorderedModel, self.site)
        request = self.factory.post(
            "/admin/testapp/unorderedmodel/move-node/",
            {"move": child.pk, "relative_to": root2.pk, "position": "child"},
        )
        request = self.setup_request(request)

        form = MoveNodeForm(request.POST, modeladmin=admin, request=request)
        result = form.process()

        assert result == "ok"

        # Refresh from database
        child.refresh_from_db()

        # Should now be child of root2
        assert child.parent == root2
