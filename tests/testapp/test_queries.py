from django import forms
from django.core.exceptions import ValidationError
from django.db import connections, models
from django.db.models import Count, Q, Sum
from django.db.models.expressions import RawSQL
from django.test import TestCase, override_settings

from tree_queries.compiler import SEPARATOR, TreeQuery
from tree_queries.query import pk

from .models import (
    AlwaysTreeQueryModel,
    AlwaysTreeQueryModelCategory,
    Model,
    MultiOrderedModel,
    ReferenceModel,
    StringOrderedModel,
    TreeNodeIsOptional,
    UnorderedModel,
    UUIDModel,
)


@override_settings(DEBUG=True)
class Test(TestCase):
    def create_tree(self):
        tree = type("Namespace", (), {})()  # SimpleNamespace for PY2...
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
        self.assertEqual(Model.objects.with_tree_fields().distinct().count(), 6)

        self.assertEqual(list(Model.objects.descendants(tree.child1)), [tree.child1_1])
        self.assertEqual(Model.objects.descendants(tree.child1).count(), 1)
        self.assertEqual(Model.objects.descendants(tree.child1).distinct().count(), 1)

        # .distinct() shouldn't always remove tree fields
        qs = list(Model.objects.with_tree_fields().distinct())
        self.assertEqual(qs[0].tree_depth, 0)
        self.assertEqual(qs[5].tree_depth, 2)

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

        html = f"{Form().as_table()}"
        self.assertIn(f'<option value="{tree.child2_1.pk}">--- --- 2-1</option>', html)
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

        html = f"{OtherForm().as_table()}"
        self.assertIn(f'<option value="{tree.child2_1.pk}">*** *** 2-1</option>', html)
        self.assertNotIn("root", html)

    def test_string_ordering(self):
        tree = type("Namespace", (), {})()  # SimpleNamespace for PY2...

        tree.americas = StringOrderedModel.objects.create(name="Americas")
        tree.europe = StringOrderedModel.objects.create(name="Europe")
        tree.france = StringOrderedModel.objects.create(
            name="France", parent=tree.europe
        )
        tree.south_america = StringOrderedModel.objects.create(
            name="South America", parent=tree.americas
        )
        tree.ecuador = StringOrderedModel.objects.create(
            name="Ecuador", parent=tree.south_america
        )
        tree.colombia = StringOrderedModel.objects.create(
            name="Colombia", parent=tree.south_america
        )
        tree.peru = StringOrderedModel.objects.create(
            name="Peru", parent=tree.south_america
        )
        tree.north_america = StringOrderedModel.objects.create(
            name="North America", parent=tree.americas
        )

        self.assertEqual(
            list(StringOrderedModel.objects.with_tree_fields()),
            [
                tree.americas,
                tree.north_america,
                tree.south_america,
                tree.colombia,
                tree.ecuador,
                tree.peru,
                tree.europe,
                tree.france,
            ],
        )

        self.assertEqual(
            list(tree.peru.ancestors(include_self=True)),
            [tree.americas, tree.south_america, tree.peru],
        )

        self.assertEqual(
            list(
                StringOrderedModel.objects.descendants(tree.americas, include_self=True)
            ),
            [
                tree.americas,
                tree.north_america,
                tree.south_america,
                tree.colombia,
                tree.ecuador,
                tree.peru,
            ],
        )

    def test_many_ordering(self):
        root = Model.objects.create(position=1, name="root")
        for i in range(20, 0, -1):
            Model.objects.create(parent=root, name=f"Node {i}", position=i * 10)

        positions = [m.position for m in Model.objects.with_tree_fields()]
        self.assertEqual(positions, list(sorted(positions)))

    def test_bfs_ordering(self):
        tree = self.create_tree()
        nodes = Model.objects.with_tree_fields().extra(
            order_by=["__tree.tree_depth", "__tree.tree_ordering"]
        )
        self.assertEqual(
            list(nodes),
            [
                tree.root,
                tree.child1,
                tree.child2,
                tree.child1_1,
                tree.child2_1,
                tree.child2_2,
            ],
        )

    def test_always_tree_query(self):
        AlwaysTreeQueryModel.objects.create(name="Nothing")
        obj = AlwaysTreeQueryModel.objects.get()

        self.assertTrue(hasattr(obj, "tree_depth"))
        self.assertTrue(hasattr(obj, "tree_ordering"))
        self.assertTrue(hasattr(obj, "tree_path"))

        self.assertEqual(obj.tree_depth, 0)

        AlwaysTreeQueryModel.objects.update(name="Something")
        obj.refresh_from_db()
        self.assertEqual(obj.name, "Something")
        AlwaysTreeQueryModel.objects.all().delete()

    def test_always_tree_query_relations(self):
        c = AlwaysTreeQueryModelCategory.objects.create()

        m1 = AlwaysTreeQueryModel.objects.create(name="Nothing", category=c)
        m2 = AlwaysTreeQueryModel.objects.create(name="Something")

        m1.related.add(m2)

        m3 = m2.related.get()

        self.assertEqual(m1, m3)
        self.assertEqual(m3.tree_depth, 0)

        m4 = c.instances.get()
        self.assertEqual(m1, m4)
        self.assertEqual(m4.tree_depth, 0)

    def test_reference(self):
        tree = self.create_tree()

        references = type("Namespace", (), {})()  # SimpleNamespace for PY2...
        references.none = ReferenceModel.objects.create(position=0)
        references.root = ReferenceModel.objects.create(
            position=1, tree_field=tree.root
        )
        references.child1 = ReferenceModel.objects.create(
            position=2, tree_field=tree.child1
        )
        references.child2 = ReferenceModel.objects.create(
            position=3, tree_field=tree.child2
        )
        references.child1_1 = ReferenceModel.objects.create(
            position=4, tree_field=tree.child1_1
        )
        references.child2_1 = ReferenceModel.objects.create(
            position=5, tree_field=tree.child2_1
        )
        references.child2_2 = ReferenceModel.objects.create(
            position=6, tree_field=tree.child2_2
        )

        self.assertEqual(
            list(
                ReferenceModel.objects.filter(
                    tree_field__in=tree.child2.descendants(include_self=True)
                )
            ),
            [references.child2, references.child2_1, references.child2_2],
        )

        self.assertEqual(
            list(
                ReferenceModel.objects.filter(
                    Q(tree_field__in=tree.child2.ancestors(include_self=True))
                    | Q(tree_field__in=tree.child2.descendants(include_self=True))
                )
            ),
            [
                references.root,
                references.child2,
                references.child2_1,
                references.child2_2,
            ],
        )

        self.assertEqual(
            list(
                ReferenceModel.objects.filter(
                    Q(tree_field__in=tree.child2_2.descendants(include_self=True))
                    | Q(tree_field__in=tree.child1.descendants())
                    | Q(tree_field__in=tree.child1.ancestors())
                )
            ),
            [references.root, references.child1_1, references.child2_2],
        )

        self.assertEqual(
            list(
                ReferenceModel.objects.exclude(
                    Q(tree_field__in=tree.child2.ancestors(include_self=True))
                    | Q(tree_field__in=tree.child2.descendants(include_self=True))
                    | Q(tree_field__isnull=True)
                )
            ),
            [references.child1, references.child1_1],
        )

        self.assertEqual(
            list(
                ReferenceModel.objects.exclude(
                    Q(tree_field__in=tree.child2.descendants())
                    | Q(tree_field__in=tree.child2.ancestors())
                    | Q(tree_field__in=tree.child1.descendants(include_self=True))
                    | Q(tree_field__in=tree.child1.ancestors())
                )
            ),
            [references.none, references.child2],
        )

        self.assertEqual(
            list(
                ReferenceModel.objects.filter(
                    Q(
                        Q(tree_field__in=tree.child2.descendants())
                        & ~Q(id=references.child2_2.id)
                    )
                    | Q(tree_field__isnull=True)
                    | Q(tree_field__in=tree.child1.ancestors())
                )
            ),
            [references.none, references.root, references.child2_1],
        )

        self.assertEqual(
            list(
                ReferenceModel.objects.filter(
                    tree_field__in=tree.child2.descendants(include_self=True).filter(
                        parent__in=tree.child2.descendants(include_self=True)
                    )
                )
            ),
            [references.child2_1, references.child2_2],
        )

    def test_annotate_tree(self):
        tree = self.create_tree()
        qs = Model.objects.with_tree_fields().filter(
            Q(pk__in=tree.child2.ancestors(include_self=True))
            | Q(pk__in=tree.child2.descendants(include_self=True))
        )
        if connections[Model.objects.db].vendor == "postgresql":
            qs = qs.annotate(
                is_my_field=RawSQL(
                    "%s = ANY(__tree.tree_path)",
                    [pk(tree.child2_1)],
                    output_field=models.BooleanField(),
                )
            )
        else:
            qs = qs.annotate(
                is_my_field=RawSQL(
                    'instr(__tree.tree_path, "{sep}{pk}{sep}") <> 0'.format(
                        pk=pk(tree.child2_1), sep=SEPARATOR
                    ),
                    [],
                    output_field=models.BooleanField(),
                )
            )

        self.assertEqual(
            [(node, node.is_my_field) for node in qs],
            [
                (tree.root, False),
                (tree.child2, False),
                (tree.child2_1, True),
                (tree.child2_2, False),
            ],
        )

    def test_uuid_queries(self):
        root = UUIDModel.objects.create(name="root")
        child1 = UUIDModel.objects.create(parent=root, name="child1")
        child2 = UUIDModel.objects.create(parent=root, name="child2")

        self.assertCountEqual(
            root.descendants(),
            {child1, child2},
        )

        self.assertEqual(
            list(child1.ancestors(include_self=True)),
            [root, child1],
        )

    def test_sibling_ordering(self):
        tree = type("Namespace", (), {})()  # SimpleNamespace for PY2...

        tree.root = MultiOrderedModel.objects.create(name="root")
        tree.child1 = MultiOrderedModel.objects.create(
            parent=tree.root, first_position=0, second_position=1, name="1"
        )
        tree.child2 = MultiOrderedModel.objects.create(
            parent=tree.root, first_position=1, second_position=0, name="2"
        )
        tree.child1_1 = MultiOrderedModel.objects.create(
            parent=tree.child1, first_position=0, second_position=1, name="1-1"
        )
        tree.child2_1 = MultiOrderedModel.objects.create(
            parent=tree.child2, first_position=0, second_position=1, name="2-1"
        )
        tree.child2_2 = MultiOrderedModel.objects.create(
            parent=tree.child2, first_position=1, second_position=0, name="2-2"
        )

        first_order = [
            tree.root,
            tree.child1,
            tree.child1_1,
            tree.child2,
            tree.child2_1,
            tree.child2_2,
        ]

        second_order = [
            tree.root,
            tree.child2,
            tree.child2_2,
            tree.child2_1,
            tree.child1,
            tree.child1_1,
        ]

        nodes = MultiOrderedModel.objects.order_siblings_by("second_position")
        self.assertEqual(list(nodes), second_order)

        nodes = MultiOrderedModel.objects.with_tree_fields()
        self.assertEqual(list(nodes), first_order)

        nodes = MultiOrderedModel.objects.order_siblings_by("second_position").all()
        self.assertEqual(list(nodes), second_order)

    def test_depth_filter(self):
        tree = self.create_tree()

        nodes = Model.objects.with_tree_fields().extra(
            where=["__tree.tree_depth between %s and %s"],
            params=[0, 1],
        )
        self.assertEqual(
            list(nodes),
            [
                tree.root,
                tree.child1,
                # tree.child1_1,
                tree.child2,
                # tree.child2_1,
                # tree.child2_2,
            ],
        )

    def test_explain(self):
        if connections[Model.objects.db].vendor == "postgresql":
            explanation = Model.objects.with_tree_fields().explain()
            self.assertIn("CTE", explanation)

    def test_tree_queries_without_tree_node(self):
        TreeNodeIsOptional.objects.create(parent=TreeNodeIsOptional.objects.create())

        nodes = list(TreeNodeIsOptional.objects.with_tree_fields())
        self.assertEqual(nodes[0].tree_depth, 0)
        self.assertEqual(nodes[1].tree_depth, 1)
