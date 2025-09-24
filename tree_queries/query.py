from django.db import connections, models
from django.db.models import Count, OuterRef, Subquery
from django.db.models.sql.query import Query

from tree_queries.compiler import SEPARATOR, TreeQuery


def pk(of):
    """
    Returns the primary key of the argument if it is an instance of a model, or
    the argument as-is otherwise
    """
    return of.pk if hasattr(of, "pk") else of


class TreeManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.with_tree_fields() if self._with_tree_fields else queryset


class TreeQuerySet(models.QuerySet):
    def with_tree_fields(self, tree_fields=True):  # noqa: FBT002
        """
        Requests tree fields on this queryset

        Pass ``False`` to revert to a queryset without tree fields.
        """
        if tree_fields:
            self.query.__class__ = TreeQuery
            self.query._setup_query()
        else:
            self.query.__class__ = Query
        return self

    def without_tree_fields(self):
        """
        Requests no tree fields on this queryset
        """
        return self.with_tree_fields(tree_fields=False)

    def order_siblings_by(self, *order_by):
        """
        Sets TreeQuery sibling_order attribute

        Pass the names of model fields as a list of strings
        to order tree siblings by those model fields
        """
        self.query.__class__ = TreeQuery
        self.query._setup_query()
        self.query.sibling_order = order_by
        return self

    def tree_filter(self, *args, **kwargs):
        """
        Adds a filter to the TreeQuery rank_table_query

        Takes the same arguements as a Django QuerySet .filter()
        """
        self.query.__class__ = TreeQuery
        self.query._setup_query()
        self.query.rank_table_query = self.query.rank_table_query.filter(
            *args, **kwargs
        )
        return self

    def tree_exclude(self, *args, **kwargs):
        """
        Adds a filter to the TreeQuery rank_table_query

        Takes the same arguements as a Django QuerySet .exclude()
        """
        self.query.__class__ = TreeQuery
        self.query._setup_query()
        self.query.rank_table_query = self.query.rank_table_query.exclude(
            *args, **kwargs
        )
        return self

    def tree_fields(self, **tree_fields):
        self.query.__class__ = TreeQuery
        self.query._setup_query()
        self.query.tree_fields = tree_fields
        return self

    @classmethod
    def as_manager(cls, *, with_tree_fields=False):
        manager_class = TreeManager.from_queryset(cls)
        # Only used in deconstruct:
        manager_class._built_with_as_manager = True
        # Set attribute on class, not on the instance so that the automatic
        # subclass generation used e.g. for relations also finds this
        # attribute.
        manager_class._with_tree_fields = with_tree_fields
        return manager_class()

    as_manager.queryset_only = True

    def ancestors(self, of, *, include_self=False):
        """
        Returns ancestors of the given node ordered from the root of the tree
        towards deeper levels, optionally including the node itself
        """
        if not include_self and of.parent_id is None:
            # Node without parent cannot have ancestors.
            return self.none()

        if not hasattr(of, "tree_path"):
            of = self.with_tree_fields().get(pk=pk(of))

        ids = of.tree_path if include_self else of.tree_path[:-1]
        return (
            self.with_tree_fields()  # TODO tree fields not strictly required
            .filter(pk__in=ids)
            .extra(order_by=["__tree.tree_depth"])
        )

    def descendants(self, of, *, include_self=False):
        """
        Returns descendants of the given node in depth-first order, optionally
        including and starting with the node itself
        """
        connection = connections[self.db]
        if connection.vendor == "postgresql":
            queryset = self.with_tree_fields().extra(
                where=["%s = ANY(__tree.tree_path)"],
                params=[self.model._meta.pk.get_db_prep_value(pk(of), connection)],
            )

        else:
            queryset = self.with_tree_fields().extra(
                # NOTE! The representation of tree_path is NOT part of the API.
                where=[
                    # XXX This *may* be unsafe with some primary key field types.
                    # It is certainly safe with integers.
                    f'instr(__tree.tree_path, "{SEPARATOR}{self.model._meta.pk.get_db_prep_value(pk(of), connection)}{SEPARATOR}") <> 0'
                ]
            )

        if not include_self:
            return queryset.exclude(pk=pk(of))
        return queryset

    def add_related_count(
        self,
        queryset,
        rel_model,
        rel_field,
        count_attr,
        cumulative=False,
    ):
        """
        Annotates each instance in the queryset with a count of related objects.
        
        This is a replacement for django-mptt's add_related_count method, adapted
        to work with django-tree-queries' CTE-based approach.
        
        Args:
            queryset: The queryset to annotate
            rel_model: The related model to count instances of  
            rel_field: Field name on rel_model that points to the tree model
            count_attr: Name of the annotation to add to each instance
            cumulative: If True, count includes related objects from descendants
            
        Returns:
            An annotated queryset
            
        Example:
            Region.objects.add_related_count(
                Region.objects.all(),
                Site,
                'region', 
                'site_count',
                cumulative=True
            )
        """
        # If not cumulative, use simple annotation based on direct relationships
        if not cumulative:
            # Get the related field to find the reverse relationship name
            rel_field_obj = rel_model._meta.get_field(rel_field)
            if hasattr(rel_field_obj, 'remote_field') and rel_field_obj.remote_field:
                related_name = rel_field_obj.remote_field.related_name
                if related_name:
                    # Use the explicitly defined related_name
                    return queryset.annotate(**{
                        count_attr: Count(related_name, distinct=True)
                    })
            
            # Fall back to generic reverse lookup
            reverse_name = f"{rel_model._meta.model_name}_set"
            return queryset.annotate(**{
                count_attr: Count(reverse_name, distinct=True)
            })
        
        # For cumulative counts, we need to count related objects for each node
        # and all its descendants using tree_path
        base_queryset = queryset.with_tree_fields()
        connection = connections[queryset.db]
        
        if connection.vendor == "postgresql":
            # PostgreSQL: Use array operations with tree_path
            # Create a subquery that gets all descendants of each node (including self)
            # and counts their related objects
            descendants_subquery = self.model.objects.with_tree_fields().extra(
                where=["%s = ANY(__tree.tree_path)"],
                params=[OuterRef('pk')]
            ).values('pk')
            
            count_subquery = Subquery(
                rel_model.objects.filter(
                    **{f"{rel_field}__in": descendants_subquery}
                ).aggregate(total=Count('pk')).values('total')[:1]
            )
        else:
            # Other databases: Use string operations on tree_path
            # Find nodes whose tree_path contains the current node's pk
            descendants_subquery = self.model.objects.with_tree_fields().extra(
                where=[
                    f'instr(__tree.tree_path, "{SEPARATOR}" || %s || "{SEPARATOR}") <> 0'
                ],
                params=[OuterRef('pk')]
            ).values('pk')
            
            count_subquery = Subquery(
                rel_model.objects.filter(
                    **{f"{rel_field}__in": descendants_subquery}
                ).aggregate(total=Count('pk')).values('total')[:1]
            )
        
        return base_queryset.annotate(**{count_attr: count_subquery})
