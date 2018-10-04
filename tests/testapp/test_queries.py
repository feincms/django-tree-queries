from __future__ import unicode_literals

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.test import TestCase

from tree_queries.compiler import TreeQuery
from .models import Model, UnorderedModel


class Test(TestCase):
    def create_tree(self):
        tree = type(str("Namespace"), (), {})()  # SimpleNamespace for PY2...
        tree.root = Model.objects.create(name="root")
        tree.child1 = Model.objects.create(parent=tree.root, position=0, name="1")
        tree.child2 = Model.objects.create(parent=tree.root, position=1, name="2")
        tree.child1_1 = Model.objects.create(parent=tree.child1, position=0, name="1-1")
        tree.child2_1 = Model.objects.create(parent=tree.child2, position=0, name="2-1")
        tree.child2_2 = Model.objects.create(parent=tree.child2, position=1, name="2-2")
        return tree

    def test_stuff(self):
        Model.objects.create()

        self.assertEqual(len(Model.objects.with_tree_fields()), 1)

        instance = Model.objects.with_tree_fields().get()
        self.assertEqual(instance.tree_depth, 0)
        self.assertEqual(instance.tree_path, [instance.pk])

    def test_no_attributes(self):
        tree = self.create_tree()

        root = Model.objects.get(pk=tree.root.pk)
        self.assertFalse(hasattr(root, "tree_depth"))
        self.assertFalse(hasattr(root, "tree_ordering"))
        self.assertFalse(hasattr(root, "tree_path"))
        self.assertFalse(hasattr(root, "tree_pk"))

    def test_attributes(self):
        tree = self.create_tree()
        child2_2 = Model.objects.with_tree_fields().get(pk=tree.child2_2.pk)
        self.assertEqual(child2_2.tree_depth, 2)
        self.assertEqual(child2_2.tree_ordering, [0, 1, 1])
        self.assertEqual(
            child2_2.tree_path, [tree.root.pk, tree.child2.pk, tree.child2_2.pk]
        )

    def test_ancestors(self):
        tree = self.create_tree()
        with self.assertNumQueries(2):
            self.assertEqual(list(tree.child2_2.ancestors()), [tree.root, tree.child2])
        self.assertEqual(
            list(tree.child2_2.ancestors(include_self=True)),
            [tree.root, tree.child2, tree.child2_2],
        )
        self.assertEqual(
            list(tree.child2_2.ancestors().reverse()), [tree.child2, tree.root]
        )

        self.assertEqual(list(tree.root.ancestors()), [])
        self.assertEqual(list(tree.root.ancestors(include_self=True)), [tree.root])

        child2_2 = Model.objects.with_tree_fields().get(pk=tree.child2_2.pk)
        with self.assertNumQueries(1):
            self.assertEqual(list(child2_2.ancestors()), [tree.root, tree.child2])

    def test_descendants(self):
        tree = self.create_tree()
        self.assertEqual(
            list(tree.child2.descendants()), [tree.child2_1, tree.child2_2]
        )
        self.assertEqual(
            list(tree.child2.descendants(include_self=True)),
            [tree.child2, tree.child2_1, tree.child2_2],
        )

    def test_queryset_or(self):
        tree = self.create_tree()
        qs = Model.objects.with_tree_fields()
        self.assertEqual(
            list(qs.filter(pk=tree.child1.pk) | qs.filter(pk=tree.child2.pk)),
            [tree.child1, tree.child2],
        )

    def test_twice(self):
        self.assertEqual(list(Model.objects.with_tree_fields().with_tree_fields()), [])

    def test_boring_coverage(self):
        with self.assertRaises(ValueError):
            TreeQuery(Model).get_compiler()

    def test_count(self):
        tree = self.create_tree()
        self.assertEqual(Model.objects.count(), 6)
        self.assertEqual(Model.objects.with_tree_fields().count(), 6)

        self.assertEqual(list(Model.objects.descendants(tree.child1)), [tree.child1_1])
        self.assertEqual(Model.objects.descendants(tree.child1).count(), 1)

    def test_annotate(self):
        tree = self.create_tree()
        self.assertEqual(
            [
                (node, node.children__count, node.tree_depth)
                for node in Model.objects.with_tree_fields().annotate(Count("children"))
            ],
            [
                (tree.root, 2, 0),
                (tree.child1, 1, 1),
                (tree.child1_1, 0, 2),
                (tree.child2, 2, 1),
                (tree.child2_1, 0, 2),
                (tree.child2_2, 0, 2),
            ],
        )

    def test_update_aggregate(self):
        self.create_tree()
        Model.objects.with_tree_fields().update(position=3)
        self.assertEqual(
            Model.objects.with_tree_fields().aggregate(Sum("position")),
            {"position__sum": 18},
            # TODO Sum("tree_depth") does not work because the field is not
            # known yet.
        )

    def test_values(self):
        tree = self.create_tree()
        self.assertEqual(
            list(
                Model.objects.ancestors(tree.child2_1).values_list("parent", flat=True)
            ),
            [tree.root.parent_id, tree.child2.parent_id],
        )

    def test_loops(self):
        tree = self.create_tree()
        tree.root.parent_id = tree.child1.pk
        with self.assertRaises(ValidationError) as cm:
            tree.root.full_clean()
        self.assertEqual(
            cm.exception.messages, ["A node cannot be made a descendant of itself."]
        )

        # No error.
        tree.child1.full_clean()

    def test_unordered(self):
        self.assertEqual(list(UnorderedModel.objects.all()), [])

    def test_revert(self):
        tree = self.create_tree()
        obj = (
            Model.objects.with_tree_fields()
            .with_tree_fields(False)
            .get(pk=tree.root.pk)
        )
        self.assertFalse(hasattr(obj, "tree_depth"))

    def test_form_field(self):
        tree = self.create_tree()

        class Form(forms.ModelForm):
            class Meta:
                model = Model
                fields = ["parent"]

        html = "{}".format(Form())
        self.assertIn(
            '<option value="{}">--- --- 2-1</option>'.format(tree.child2_1.pk), html
        )
        self.assertIn("root", html)

        class OtherForm(forms.Form):
            node = Model._meta.get_field("parent").formfield(
                label_from_instance=lambda obj: "{}{}".format(
                    "".join(
                        ["*** " if obj == tree.child2_1 else "--- "] * obj.tree_depth
                    ),
                    obj,
                ),
                queryset=tree.child2.descendants(),
            )

        html = "{}".format(OtherForm())
        self.assertIn(
            '<option value="{}">*** *** 2-1</option>'.format(tree.child2_1.pk), html
        )
        self.assertNotIn("root", html)
