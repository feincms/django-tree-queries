from types import SimpleNamespace

import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.db import connections, models
from django.db.models import Count, Q, Sum
from django.db.models.expressions import RawSQL
from django.test import TestCase

from testapp.models import (
    AlwaysTreeQueryModel,
    AlwaysTreeQueryModelCategory,
    InheritChildModel,
    InheritConcreteGrandChildModel,
    InheritGrandChildModel,
    InheritParentModel,
    Model,
    MultiOrderedModel,
    OneToOneRelatedOrder,
    ReferenceModel,
    RelatedOrderModel,
    StringOrderedModel,
    TreeNodeIsOptional,
    UnorderedModel,
    UUIDModel,
)
from tree_queries.compiler import SEPARATOR, TreeCompiler, TreeQuery
from tree_queries.query import pk


@pytest.mark.django_db
class TestTreeQueries:
    def create_tree(self):
        tree = SimpleNamespace()
        tree.root = Model.objects.create(name="root")
        tree.child1 = Model.objects.create(parent=tree.root, order=0, name="1")
        tree.child2 = Model.objects.create(parent=tree.root, order=1, name="2")
        tree.child1_1 = Model.objects.create(parent=tree.child1, order=0, name="1-1")
        tree.child2_1 = Model.objects.create(parent=tree.child2, order=0, name="2-1")
        tree.child2_2 = Model.objects.create(parent=tree.child2, order=42, name="2-2")
        return tree

    def test_stuff(self):
        Model.objects.create()

        assert len(Model.objects.with_tree_fields()) == 1

        instance = Model.objects.with_tree_fields().get()
        assert instance.tree_depth == 0
        assert instance.tree_path == [instance.pk]

    def test_no_attributes(self):
        tree = self.create_tree()

        root = Model.objects.get(pk=tree.root.pk)
        assert not hasattr(root, "tree_depth")
        assert not hasattr(root, "tree_ordering")
        assert not hasattr(root, "tree_path")

    def test_attributes(self):
        tree = self.create_tree()
        # Ordering should be deterministic
        child2_2 = (
            Model.objects.with_tree_fields()
            .order_siblings_by("order", "pk")
            .get(pk=tree.child2_2.pk)
        )
        assert child2_2.tree_depth == 2
        # Tree ordering is an array of the ranks assigned to a comment's
        # ancestors when they are ordered without respect for tree relations.
        assert child2_2.tree_ordering == [1, 5, 6]
        assert child2_2.tree_path == [tree.root.pk, tree.child2.pk, tree.child2_2.pk]

    def test_ancestors(self):
        tree = self.create_tree()

        tc = TestCase()
        with tc.assertNumQueries(2):
            assert list(tree.child2_2.ancestors()) == [tree.root, tree.child2]
        assert list(tree.child2_2.ancestors(include_self=True)) == [
            tree.root,
            tree.child2,
            tree.child2_2,
        ]
        assert list(tree.child2_2.ancestors().reverse()) == [tree.child2, tree.root]

        assert list(tree.root.ancestors()) == []
        assert list(tree.root.ancestors(include_self=True)) == [tree.root]

        child2_2 = Model.objects.with_tree_fields().get(pk=tree.child2_2.pk)

        tc = TestCase()
        with tc.assertNumQueries(1):
            assert list(child2_2.ancestors()) == [tree.root, tree.child2]

    def test_descendants(self):
        tree = self.create_tree()
        assert list(tree.child2.descendants()) == [tree.child2_1, tree.child2_2]
        assert list(tree.child2.descendants(include_self=True)) == [
            tree.child2,
            tree.child2_1,
            tree.child2_2,
        ]

    def test_queryset_or(self):
        tree = self.create_tree()
        qs = Model.objects.with_tree_fields()
        assert list(qs.filter(pk=tree.child1.pk) | qs.filter(pk=tree.child2.pk)) == [
            tree.child1,
            tree.child2,
        ]

    def test_twice(self):
        assert list(Model.objects.with_tree_fields().with_tree_fields()) == []

    def test_boring_coverage(self):
        with pytest.raises(ValueError, match="Need either using or connection"):
            TreeQuery(Model).get_compiler()

    def test_count(self):
        tree = self.create_tree()
        assert Model.objects.count() == 6
        assert Model.objects.with_tree_fields().count() == 6
        assert Model.objects.with_tree_fields().distinct().count() == 6

        assert list(Model.objects.descendants(tree.child1)) == [tree.child1_1]
        assert Model.objects.descendants(tree.child1).count() == 1
        assert Model.objects.descendants(tree.child1).distinct().count() == 1

        # .distinct() shouldn't always remove tree fields
        qs = list(Model.objects.with_tree_fields().distinct())
        assert qs[0].tree_depth == 0
        assert qs[5].tree_depth == 2

    def test_annotate(self):
        tree = self.create_tree()
        assert [
            (node, node.children__count, node.tree_depth)
            for node in Model.objects.with_tree_fields().annotate(Count("children"))
        ] == [
            (tree.root, 2, 0),
            (tree.child1, 1, 1),
            (tree.child1_1, 0, 2),
            (tree.child2, 2, 1),
            (tree.child2_1, 0, 2),
            (tree.child2_2, 0, 2),
        ]

    def test_update_aggregate(self):
        self.create_tree()
        Model.objects.with_tree_fields().update(order=3)
        assert Model.objects.with_tree_fields().aggregate(Sum("order")) == {
            "order__sum": 18
        }
        # TODO Sum("tree_depth") does not work because the field is not
        # known yet.

    def test_update_descendants(self):
        """UpdateQuery does not work with tree queries"""
        tree = self.create_tree()
        # OperationalError would probably be appropriate, but the psycopg2
        # backend raises psycopg2.errors.UndefinedTable, which isn't an
        # OperationalError subclass.
        with pytest.raises(Exception, match="__tree"):
            tree.root.descendants().update(name="test")

    def test_update_descendants_with_filter(self):
        """Updating works when using a filter"""
        tree = self.create_tree()
        Model.objects.filter(pk__in=tree.child2.descendants()).update(name="test")
        assert [node.name for node in Model.objects.with_tree_fields()] == [
            "root",
            "1",
            "1-1",
            "2",
            "test",
            "test",
        ]

    def test_delete_descendants(self):
        """DeleteQuery works with tree queries"""
        tree = self.create_tree()
        tree.child2.descendants(include_self=True).delete()

        assert list(Model.objects.with_tree_fields()) == [
            tree.root,
            tree.child1,
            tree.child1_1,
            # tree.child2,
            # tree.child2_1,
            # tree.child2_2,
        ]

    def test_aggregate_descendants(self):
        """AggregateQuery works with tree queries"""
        tree = self.create_tree()
        assert tree.root.descendants(include_self=True).aggregate(Sum("pk"))[
            "pk__sum"
        ] == sum(node.pk for node in Model.objects.all())

    def test_values(self):
        self.create_tree()
        assert list(Model.objects.with_tree_fields().values("name")) == [
            {"name": "root"},
            {"name": "1"},
            {"name": "1-1"},
            {"name": "2"},
            {"name": "2-1"},
            {"name": "2-2"},
        ]

    def test_values_ancestors(self):
        tree = self.create_tree()
        assert list(Model.objects.ancestors(tree.child2_1).values()) == [
            {
                "custom_id": tree.root.pk,
                "name": "root",
                "order": 0,
                "parent_id": None,
            },
            {
                "custom_id": tree.child2.pk,
                "name": "2",
                "order": 1,
                "parent_id": tree.root.pk,
            },
        ]

    def test_values_list(self):
        self.create_tree()
        assert list(
            Model.objects.with_tree_fields().values_list("name", flat=True)
        ) == ["root", "1", "1-1", "2", "2-1", "2-2"]

    def test_values_list_ancestors(self):
        tree = self.create_tree()
        assert list(
            Model.objects.ancestors(tree.child2_1).values_list("parent", flat=True)
        ) == [tree.root.parent_id, tree.child2.parent_id]

    def test_loops(self):
        tree = self.create_tree()
        tree.root.parent_id = tree.child1.pk
        with pytest.raises(ValidationError) as cm:
            tree.root.full_clean()
        assert cm.value.messages == ["A node cannot be made a descendant of itself."]

        # No error.
        tree.child1.full_clean()

    def test_unordered(self):
        assert list(UnorderedModel.objects.all()) == []

        u2 = UnorderedModel.objects.create(name="u2")
        u1 = UnorderedModel.objects.create(name="u1")
        u0 = UnorderedModel.objects.create(name="u0")

        u1.parent = u0
        u1.save()
        u2.parent = u0
        u2.save()

        # Siblings are ordered by primary key (in order of creation)
        assert [obj.name for obj in UnorderedModel.objects.with_tree_fields()] == [
            "u0",
            "u2",
            "u1",
        ]

    def test_revert(self):
        tree = self.create_tree()
        obj = (
            Model.objects.with_tree_fields().without_tree_fields().get(pk=tree.root.pk)
        )
        assert not hasattr(obj, "tree_depth")

    def test_form_field(self):
        tree = self.create_tree()

        class Form(forms.ModelForm):
            class Meta:
                model = Model
                fields = ["parent"]

        html = f"{Form().as_table()}"
        assert f'<option value="{tree.child2_1.pk}">--- --- 2-1</option>' in html
        assert "root" in html

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
        assert f'<option value="{tree.child2_1.pk}">*** *** 2-1</option>' in html
        assert "root" not in html

    def test_string_ordering(self):
        tree = SimpleNamespace()

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

        assert list(StringOrderedModel.objects.with_tree_fields()) == [
            tree.americas,
            tree.north_america,
            tree.south_america,
            tree.colombia,
            tree.ecuador,
            tree.peru,
            tree.europe,
            tree.france,
        ]

        assert list(tree.peru.ancestors(include_self=True)) == [
            tree.americas,
            tree.south_america,
            tree.peru,
        ]

        assert list(
            StringOrderedModel.objects.descendants(tree.americas, include_self=True)
        ) == [
            tree.americas,
            tree.north_america,
            tree.south_america,
            tree.colombia,
            tree.ecuador,
            tree.peru,
        ]

    def test_many_ordering(self):
        root = Model.objects.create(order=1, name="root")
        for i in range(20, 0, -1):
            Model.objects.create(parent=root, name=f"Node {i}", order=i * 10)

        positions = [m.order for m in Model.objects.with_tree_fields()]
        assert positions == sorted(positions)

    def test_bfs_ordering(self):
        tree = self.create_tree()
        nodes = Model.objects.with_tree_fields().extra(
            order_by=["__tree.tree_depth", "__tree.tree_ordering"]
        )
        assert list(nodes) == [
            tree.root,
            tree.child1,
            tree.child2,
            tree.child1_1,
            tree.child2_1,
            tree.child2_2,
        ]

    def test_always_tree_query(self):
        AlwaysTreeQueryModel.objects.create(name="Nothing")
        obj = AlwaysTreeQueryModel.objects.get()

        assert hasattr(obj, "tree_depth")
        assert hasattr(obj, "tree_ordering")
        assert hasattr(obj, "tree_path")

        assert obj.tree_depth == 0

        AlwaysTreeQueryModel.objects.update(name="Something")
        obj.refresh_from_db()
        assert obj.name == "Something"
        AlwaysTreeQueryModel.objects.all().delete()

    def test_always_tree_query_relations(self):
        c = AlwaysTreeQueryModelCategory.objects.create()

        m1 = AlwaysTreeQueryModel.objects.create(name="Nothing", category=c)
        m2 = AlwaysTreeQueryModel.objects.create(name="Something")

        m1.related.add(m2)

        m3 = m2.related.get()

        assert m1 == m3
        assert m3.tree_depth == 0

        m4 = c.instances.get()
        assert m1 == m4
        assert m4.tree_depth == 0

    def test_reference(self):
        tree = self.create_tree()

        references = SimpleNamespace()
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

        assert list(
            ReferenceModel.objects.filter(
                tree_field__in=tree.child2.descendants(include_self=True)
            )
        ) == [references.child2, references.child2_1, references.child2_2]

        assert list(
            ReferenceModel.objects.filter(
                Q(tree_field__in=tree.child2.ancestors(include_self=True))
                | Q(tree_field__in=tree.child2.descendants(include_self=True))
            )
        ) == [
            references.root,
            references.child2,
            references.child2_1,
            references.child2_2,
        ]

        assert list(
            ReferenceModel.objects.filter(
                Q(tree_field__in=tree.child2_2.descendants(include_self=True))
                | Q(tree_field__in=tree.child1.descendants())
                | Q(tree_field__in=tree.child1.ancestors())
            )
        ) == [references.root, references.child1_1, references.child2_2]

        assert list(
            ReferenceModel.objects.exclude(
                Q(tree_field__in=tree.child2.ancestors(include_self=True))
                | Q(tree_field__in=tree.child2.descendants(include_self=True))
                | Q(tree_field__isnull=True)
            )
        ) == [references.child1, references.child1_1]

        assert list(
            ReferenceModel.objects.exclude(
                Q(tree_field__in=tree.child2.descendants())
                | Q(tree_field__in=tree.child2.ancestors())
                | Q(tree_field__in=tree.child1.descendants(include_self=True))
                | Q(tree_field__in=tree.child1.ancestors())
            )
        ) == [references.none, references.child2]

        assert list(
            ReferenceModel.objects.filter(
                Q(
                    Q(tree_field__in=tree.child2.descendants())
                    & ~Q(id=references.child2_2.id)
                )
                | Q(tree_field__isnull=True)
                | Q(tree_field__in=tree.child1.ancestors())
            )
        ) == [references.none, references.root, references.child2_1]

        assert list(
            ReferenceModel.objects.filter(
                tree_field__in=tree.child2.descendants(include_self=True).filter(
                    parent__in=tree.child2.descendants(include_self=True)
                )
            )
        ) == [references.child2_1, references.child2_2]

    def test_reference_isnull_issue63(self):
        # https://github.com/feincms/django-tree-queries/issues/63
        assert (
            list(Model.objects.with_tree_fields().exclude(referencemodel__isnull=False))
            == []
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
                    f'instr(__tree.tree_path, "{SEPARATOR}{pk(tree.child2_1)}{SEPARATOR}") <> 0',
                    [],
                    output_field=models.BooleanField(),
                )
            )

        assert [(node, node.is_my_field) for node in qs] == [
            (tree.root, False),
            (tree.child2, False),
            (tree.child2_1, True),
            (tree.child2_2, False),
        ]

    def test_uuid_queries(self):
        root = UUIDModel.objects.create(name="root")
        child1 = UUIDModel.objects.create(parent=root, name="child1")
        child2 = UUIDModel.objects.create(parent=root, name="child2")

        assert set(root.descendants()) == {child1, child2}

        assert list(child1.ancestors(include_self=True)) == [root, child1]

    def test_sibling_ordering(self):
        tree = SimpleNamespace()

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
        assert list(nodes) == second_order

        nodes = MultiOrderedModel.objects.with_tree_fields()
        assert list(nodes) == first_order

        nodes = MultiOrderedModel.objects.order_siblings_by("second_position").all()
        assert list(nodes) == second_order

    def test_depth_filter(self):
        tree = self.create_tree()

        nodes = Model.objects.with_tree_fields().extra(
            where=["__tree.tree_depth between %s and %s"],
            params=[0, 1],
        )
        assert list(nodes) == [
            tree.root,
            tree.child1,
            # tree.child1_1,
            tree.child2,
            # tree.child2_1,
            # tree.child2_2,
        ]

    @pytest.mark.postgresql
    @pytest.mark.skipif(
        connections["default"].vendor != "postgresql",
        reason="EXPLAIN test only meaningful for PostgreSQL",
    )
    def test_explain(self):
        explanation = Model.objects.with_tree_fields().explain()
        assert "CTE" in explanation

    def test_tree_queries_without_tree_node(self):
        TreeNodeIsOptional.objects.create(parent=TreeNodeIsOptional.objects.create())

        nodes = list(TreeNodeIsOptional.objects.with_tree_fields())
        assert nodes[0].tree_depth == 0
        assert nodes[1].tree_depth == 1

    def test_polymorphic_queries(self):
        """test queries on concrete child classes in multi-table inheritance setup"""

        # create a tree with a random mix of classes/subclasses
        root = InheritChildModel.objects.create(name="root")
        child1 = InheritGrandChildModel.objects.create(parent=root, name="child1")
        child2 = InheritParentModel.objects.create(parent=root, name="child2")
        InheritParentModel.objects.create(parent=child1, name="child1_1")
        InheritChildModel.objects.create(parent=child2, name="child2_1")
        InheritConcreteGrandChildModel.objects.create(parent=child2, name="child2_2")

        # ensure we get the full tree if querying the super class
        objs = InheritParentModel.objects.with_tree_fields()
        assert {(p.name, tuple(p.tree_path)) for p in objs} == {
            ("root", (1,)),
            ("child1", (1, 2)),
            ("child1_1", (1, 2, 4)),
            ("child2", (1, 3)),
            ("child2_1", (1, 3, 5)),
            ("child2_2", (1, 3, 6)),
        }

        # ensure we still get the tree when querying only a subclass (including sub-subclasses)
        objs = InheritChildModel.objects.with_tree_fields()
        assert {(p.name, tuple(p.tree_path)) for p in objs} == {
            ("root", (1,)),
            ("child1", (1, 2)),
            ("child2_1", (1, 3, 5)),
        }

        # ensure we still get the tree when querying only a subclass
        objs = InheritGrandChildModel.objects.with_tree_fields()
        assert {(p.name, tuple(p.tree_path)) for p in objs} == {
            ("child1", (1, 2)),
        }

        # ensure we don't get confused by an intermediate abstract subclass
        objs = InheritConcreteGrandChildModel.objects.with_tree_fields()
        assert {(p.name, tuple(p.tree_path)) for p in objs} == {
            ("child2_2", (1, 3, 6)),
        }

    def test_descending_order(self):
        tree = self.create_tree()

        nodes = Model.objects.order_siblings_by("-order")
        assert list(nodes) == [
            tree.root,
            tree.child2,
            tree.child2_2,
            tree.child2_1,
            tree.child1,
            tree.child1_1,
        ]

    def test_multi_field_order(self):
        tree = SimpleNamespace()

        tree.root = MultiOrderedModel.objects.create(name="root")
        tree.child1 = MultiOrderedModel.objects.create(
            parent=tree.root, first_position=0, second_position=1, name="1"
        )
        tree.child2 = MultiOrderedModel.objects.create(
            parent=tree.root, first_position=0, second_position=0, name="2"
        )
        tree.child1_1 = MultiOrderedModel.objects.create(
            parent=tree.child1, first_position=1, second_position=1, name="1-1"
        )
        tree.child2_1 = MultiOrderedModel.objects.create(
            parent=tree.child2, first_position=0, second_position=1, name="2-1"
        )
        tree.child2_2 = MultiOrderedModel.objects.create(
            parent=tree.child2, first_position=1, second_position=0, name="2-2"
        )

        nodes = MultiOrderedModel.objects.order_siblings_by(
            "first_position", "-second_position"
        )
        assert list(nodes) == [
            tree.root,
            tree.child1,
            tree.child1_1,
            tree.child2,
            tree.child2_1,
            tree.child2_2,
        ]

    def test_order_by_related(self):
        tree = SimpleNamespace()

        tree.root = RelatedOrderModel.objects.create(name="root")
        tree.child1 = RelatedOrderModel.objects.create(parent=tree.root, name="1")
        tree.child1_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child1, order=0
        )
        tree.child2 = RelatedOrderModel.objects.create(parent=tree.root, name="2")
        tree.child2_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child2, order=1
        )
        tree.child1_1 = RelatedOrderModel.objects.create(parent=tree.child1, name="1-1")
        tree.child1_1_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child1_1, order=0
        )
        tree.child2_1 = RelatedOrderModel.objects.create(parent=tree.child2, name="2-1")
        tree.child2_1_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child2_1, order=0
        )
        tree.child2_2 = RelatedOrderModel.objects.create(parent=tree.child2, name="2-2")
        tree.child2_2_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child2_2, order=1
        )

        nodes = RelatedOrderModel.objects.order_siblings_by("related__order")
        assert list(nodes) == [
            tree.root,
            tree.child1,
            tree.child1_1,
            tree.child2,
            tree.child2_1,
            tree.child2_2,
        ]

    def test_tree_exclude(self):
        tree = self.create_tree()
        # Tree-filter should remove children if
        # the parent meets the filtering criteria
        nodes = Model.objects.tree_exclude(name="2")
        assert list(nodes) == [
            tree.root,
            tree.child1,
            tree.child1_1,
        ]

    def test_tree_filter(self):
        tree = self.create_tree()
        # Tree-filter should remove children if
        # the parent does not meet the filtering criteria
        nodes = Model.objects.tree_filter(name__in=["root", "1-1", "2", "2-1", "2-2"])
        assert list(nodes) == [
            tree.root,
            tree.child2,
            tree.child2_1,
            tree.child2_2,
        ]

    def test_tree_filter_chaining(self):
        tree = self.create_tree()
        # Tree-filter should remove children if
        # the parent does not meet the filtering criteria
        nodes = Model.objects.tree_exclude(name="2-2").tree_filter(
            name__in=["root", "1-1", "2", "2-1", "2-2"]
        )
        assert list(nodes) == [
            tree.root,
            tree.child2,
            tree.child2_1,
        ]

    def test_tree_filter_related(self):
        tree = SimpleNamespace()

        tree.root = RelatedOrderModel.objects.create(name="root")
        tree.root_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.root, order=0
        )
        tree.child1 = RelatedOrderModel.objects.create(parent=tree.root, name="1")
        tree.child1_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child1, order=0
        )
        tree.child2 = RelatedOrderModel.objects.create(parent=tree.root, name="2")
        tree.child2_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child2, order=1
        )
        tree.child1_1 = RelatedOrderModel.objects.create(parent=tree.child1, name="1-1")
        tree.child1_1_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child1_1, order=0
        )
        tree.child2_1 = RelatedOrderModel.objects.create(parent=tree.child2, name="2-1")
        tree.child2_1_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child2_1, order=0
        )
        tree.child2_2 = RelatedOrderModel.objects.create(parent=tree.child2, name="2-2")
        tree.child2_2_related = OneToOneRelatedOrder.objects.create(
            relatedmodel=tree.child2_2, order=1
        )

        nodes = RelatedOrderModel.objects.tree_filter(related__order=0)
        assert list(nodes) == [
            tree.root,
            tree.child1,
            tree.child1_1,
        ]

    def test_tree_filter_with_order(self):
        tree = SimpleNamespace()

        tree.root = MultiOrderedModel.objects.create(
            name="root",
            first_position=1,
        )
        tree.child1 = MultiOrderedModel.objects.create(
            parent=tree.root, first_position=0, second_position=1, name="1"
        )
        tree.child2 = MultiOrderedModel.objects.create(
            parent=tree.root, first_position=1, second_position=0, name="2"
        )
        tree.child1_1 = MultiOrderedModel.objects.create(
            parent=tree.child1, first_position=1, second_position=1, name="1-1"
        )
        tree.child2_1 = MultiOrderedModel.objects.create(
            parent=tree.child2, first_position=1, second_position=1, name="2-1"
        )
        tree.child2_2 = MultiOrderedModel.objects.create(
            parent=tree.child2, first_position=1, second_position=0, name="2-2"
        )

        nodes = MultiOrderedModel.objects.tree_filter(
            first_position__gt=0
        ).order_siblings_by("-second_position")
        assert list(nodes) == [
            tree.root,
            tree.child2,
            tree.child2_1,
            tree.child2_2,
        ]

    def test_tree_filter_q_objects(self):
        tree = self.create_tree()
        # Tree-filter should remove children if
        # the parent does not meet the filtering criteria
        nodes = Model.objects.tree_filter(
            Q(name__in=["root", "1-1", "2", "2-1", "2-2"])
        )
        assert list(nodes) == [
            tree.root,
            tree.child2,
            tree.child2_1,
            tree.child2_2,
        ]

    def test_tree_filter_q_mix(self):
        tree = SimpleNamespace()

        tree.root = MultiOrderedModel.objects.create(
            name="root", first_position=1, second_position=2
        )
        tree.child1 = MultiOrderedModel.objects.create(
            parent=tree.root, first_position=1, second_position=0, name="1"
        )
        tree.child2 = MultiOrderedModel.objects.create(
            parent=tree.root, first_position=1, second_position=2, name="2"
        )
        tree.child1_1 = MultiOrderedModel.objects.create(
            parent=tree.child1, first_position=1, second_position=1, name="1-1"
        )
        tree.child2_1 = MultiOrderedModel.objects.create(
            parent=tree.child2, first_position=1, second_position=1, name="2-1"
        )
        tree.child2_2 = MultiOrderedModel.objects.create(
            parent=tree.child2, first_position=1, second_position=2, name="2-2"
        )
        # Tree-filter should remove children if
        # the parent does not meet the filtering criteria
        nodes = MultiOrderedModel.objects.tree_filter(
            Q(first_position=1), second_position=2
        )
        assert list(nodes) == [
            tree.root,
            tree.child2,
            tree.child2_2,
        ]

    def test_tree_fields(self):
        self.create_tree()
        qs = Model.objects.tree_fields(tree_names="name", tree_orders="order")

        names = [obj.tree_names for obj in qs]
        assert names == [
            ["root"],
            ["root", "1"],
            ["root", "1", "1-1"],
            ["root", "2"],
            ["root", "2", "2-1"],
            ["root", "2", "2-2"],
        ]

        orders = [obj.tree_orders for obj in qs]
        assert orders == [[0], [0, 0], [0, 0, 0], [0, 1], [0, 1, 0], [0, 1, 42]]

        # ids = [obj.tree_pks for obj in Model.objects.tree_fields(tree_pks="custom_id")]
        # self.assertIsInstance(ids[0][0], int)

        # ids = [obj.tree_pks for obj in Model.objects.tree_fields(tree_pks="parent_id")]
        # self.assertEqual(ids[0], [""])

    def test_invalid_sibling_order_type(self):
        """Test that invalid sibling order types raise ValueError"""
        self.create_tree()

        # Create a TreeQuery directly to test the validation in get_rank_table

        query = TreeQuery(Model)
        query.sibling_order = 123  # Invalid type

        compiler = TreeCompiler(query, connections[Model.objects.db], Model.objects.db)

        # This should raise ValueError during get_rank_table
        with pytest.raises(
            ValueError,
            match="Sibling order must be a string or a list or tuple of strings",
        ):
            compiler.get_rank_table()

    @pytest.mark.postgresql
    @pytest.mark.skipif(
        connections["default"].vendor != "postgresql",
        reason="EXPLAIN test only meaningful for PostgreSQL",
    )
    def test_explain_query_handling(self):
        """Test that EXPLAIN queries are handled correctly"""
        self.create_tree()

        # This should not raise an error and should include EXPLAIN in output
        explanation = Model.objects.with_tree_fields().explain()
        assert "CTE" in explanation

    @pytest.mark.mysql
    @pytest.mark.skipif(
        connections["default"].vendor != "mysql",
        reason="MySQL-specific code path test only meaningful for MySQL",
    )
    def test_mysql_specific_code_paths(self):
        """Test MySQL-specific code paths"""
        tree = self.create_tree()

        # Test that queries work with MySQL-specific string concatenation
        nodes = list(Model.objects.with_tree_fields())
        assert len(nodes) == 6

        # This exercises the MySQL-specific CTE implementation
        descendants = list(tree.root.descendants())
        assert len(descendants) == 5

    @pytest.mark.postgresql
    @pytest.mark.skipif(
        connections["default"].vendor != "postgresql",
        reason="PostgreSQL-specific descendants query test only meaningful for PostgreSQL",
    )
    def test_postgresql_descendants_query_path(self):
        """Test PostgreSQL-specific descendants query logic"""
        tree = self.create_tree()

        # This exercises the PostgreSQL-specific path in query.py:120 using ANY() syntax
        descendants = list(Model.objects.descendants(tree.child2))
        expected_descendants = [tree.child2_1, tree.child2_2]

        assert len(descendants) == 2
        assert set(descendants) == set(expected_descendants)

    def test_rank_table_optimization(self):
        """Test that rank table optimization works correctly"""

        # Test that simple cases can skip rank table (all databases now support it)
        query = TreeQuery(Model)
        compiler = TreeCompiler(query, connections[Model.objects.db], Model.objects.db)
        # Default should allow optimization
        assert compiler._can_skip_rank_table()

        # Descending order should prevent optimization
        query.sibling_order = "-order"
        assert not compiler._can_skip_rank_table()

        # Multiple fields should prevent optimization
        query.sibling_order = ["order", "name"]
        assert not compiler._can_skip_rank_table()

        # String fields should prevent optimization
        query.sibling_order = "name"
        assert not compiler._can_skip_rank_table()

        # Test that tree filters prevent optimization
        self.create_tree()
        filtered_qs = Model.objects.tree_filter(name="root")
        query = filtered_qs.query
        compiler = TreeCompiler(query, connections[Model.objects.db], Model.objects.db)
        assert not compiler._can_skip_rank_table()

        # Test that simple custom tree fields now allow optimization
        custom_fields_qs = Model.objects.tree_fields(tree_names="name")
        query = custom_fields_qs.query
        compiler = TreeCompiler(query, connections[Model.objects.db], Model.objects.db)
        assert compiler._can_skip_rank_table()  # Now should allow optimization

    def test_optimization_sql_differences(self):
        """Test that the optimization produces different SQL"""

        self.create_tree()

        # Simple query that should use optimization
        simple_qs = Model.objects.with_tree_fields()
        simple_sql, _ = simple_qs.query.get_compiler(using=Model.objects.db).as_sql()

        # Complex query that should NOT use optimization (descending order)
        complex_qs = Model.objects.with_tree_fields().order_siblings_by("-order")
        complex_sql, _ = complex_qs.query.get_compiler(using=Model.objects.db).as_sql()

        # The optimized query should not contain "__rank_table"
        assert "__rank_table" not in simple_sql
        # The complex query should contain "__rank_table"
        assert "__rank_table" in complex_sql

        # Both should contain "__tree" CTE
        assert "__tree" in simple_sql
        assert "__tree" in complex_sql

    def test_tree_fields_optimization(self):
        """Test that tree fields work with the optimization"""

        self.create_tree()

        # Test that simple tree fields use optimization
        qs = Model.objects.tree_fields(tree_names="name")
        query = qs.query
        compiler = TreeCompiler(query, connections[Model.objects.db], Model.objects.db)
        assert compiler._can_skip_rank_table()

        # Test that the query works correctly
        results = list(qs)
        assert len(results) == 6

        # Check that tree_names field is populated correctly
        root = next(obj for obj in results if obj.name == "root")
        assert root.tree_names == ["root"]

        child2_2 = next(obj for obj in results if obj.name == "2-2")
        assert child2_2.tree_names == ["root", "2", "2-2"]
