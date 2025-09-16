import json

from django import forms
from django.contrib import messages
from django.contrib.admin import ModelAdmin, SimpleListFilter, display, helpers
from django.contrib.admin.options import IncorrectLookupParameters, csrf_protect_m
from django.core.exceptions import ValidationError
from django.db.models import F
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html, format_html_join, mark_safe
from django.utils.translation import gettext_lazy as _
from js_asset.js import JS


__all__ = (
    "TreeAdmin",
    "AncestorFilter",
)


MOVE_POSITIONS = {
    "before": _("before"),
    "first-child": _("as first child"),
    "last-child": _("as last child"),
    "after": _("after"),
}

# Positions available when we don't control sibling ordering
MOVE_POSITIONS_PARENT_ONLY = {
    "child": _("as child"),
}


class TreeAdmin(ModelAdmin):
    """
    Position field configuration. Set to the name of the field used for positioning
    siblings, or None if no position field exists or if positioning is not controllable.
    """

    position_field = None

    # Lazy loading configuration
    lazy_loading = True
    max_initial_depth = 1
    lazy_load_batch_size = 50

    """
    ``ModelAdmin`` subclass for managing models using `django-tree-queries
    <https://github.com/matthiask/django-tree-queries>`_ trees.

    Shows the tree's hierarchy and adds a view to move nodes around. To use
    this class the three columns ``collapse_column``, ``indented_title`` and
    ``move_column`` should be added to subclasses ``list_display``::

        class NodeAdmin(TreeAdmin):
            list_display = [*TreeAdmin.list_display, ...]
            # This is the default:
            # list_display_links = ["indented_title"]

        admin.site.register(Node, NodeAdmin)
    """

    list_display = ["collapse_column", "indented_title", "move_column"]
    list_display_links = ["indented_title"]

    @csrf_protect_m
    def changelist_view(self, request, **kwargs):
        response = super().changelist_view(request, **kwargs)
        if not hasattr(response, "context_data"):
            return response
        context = self.tree_admin_context(request)
        response.context_data["media"] += forms.Media(
            css={
                "all": [
                    "tree_queries/tree_admin.css",
                ]
            },
            js=[
                JS(
                    "tree_queries/tree_admin.js",
                    {"id": "tree-admin-context", "data-context": json.dumps(context)},
                ),
            ],
        )
        return response

    def tree_admin_context(self, request):
        context = {
            "initiallyCollapseDepth": 1,
            "lazyLoading": self.lazy_loading,
            "maxInitialDepth": self.max_initial_depth,
            "lazyLoadBatchSize": self.lazy_load_batch_size,
        }

        # Add list of parent IDs that have children
        if self.lazy_loading:
            context["parentIdsWithChildren"] = list(
                self.get_parent_ids_with_children(request)
            )

        return context

    def get_queryset(self, request):
        queryset = self.model._default_manager.with_tree_fields()

        # Apply lazy loading depth limit if enabled
        if self.lazy_loading and not request.GET.get("load_children"):
            queryset = queryset.extra(where=[f"tree_depth <= {self.max_initial_depth}"])

        return queryset

    def get_parent_ids_with_children(self, request):
        """Get a set of parent IDs that have children, for lazy loading."""
        if not self.lazy_loading:
            return set()

        # Get all nodes that are parents (have at least one child)
        parent_ids = (
            self.model._default_manager.exclude(parent=None)
            .values_list("parent_id", flat=True)
            .distinct()
        )

        return set(parent_ids)

    @display(description="")
    def collapse_column(self, instance):
        return format_html(
            '<div class="collapse-toggle collapse-hide" data-pk="{}" data-tree-depth="{}"></div>',
            instance.pk,
            instance.tree_depth,
        )

    def indented_title(self, instance, *, ellipsize=True):
        """
        Use Unicode box-drawing characters to visualize the tree hierarchy.
        """
        box_drawing = []
        for _i in range(instance.tree_depth - 1):
            box_drawing.append('<i class="l"></i>')
        if instance.tree_depth > 0:
            box_drawing.append('<i class="a"></i>')

        return format_html(
            '<div class="box">'
            '<div class="box-drawing">{}</div>'
            '<div class="box-text{}" style="text-indent:{}px">{}</div>'
            "</div>",
            mark_safe("".join(box_drawing)),
            " ellipsize" if ellipsize else "",
            instance.tree_depth * 30,
            instance,
        )

    indented_title.short_description = _("title")

    def move_column(self, instance):
        """
        Show a ``move`` link which leads to a separate page where the move
        destination may be selected.
        """
        positions = (
            MOVE_POSITIONS if self.position_field else MOVE_POSITIONS_PARENT_ONLY
        )
        options = format_html_join(
            "", '<option value="{}">{}</option>', positions.items()
        )

        # Add "to root" button for models without controllable positioning
        # Only show for nodes that aren't already at root level
        root_button = ""
        if not self.position_field and instance.parent_id is not None:
            root_button = format_html(
                '<button class="move-to-root" type="button" data-pk="{}" title="{}">'
                '<span class="tree-icon"></span>'
                "</button>",
                instance.pk,
                _("Move '{}' to root level").format(instance),
            )

        return format_html(
            """\
<div class="move-controls">
<button class="move-cut" type="button" data-pk="{}" title="{}">
  <span class="tree-icon"></span>
</button>
{}
<select class="move-paste" data-pk="{}" title="{}">
  <option value="">---</option>
  {}
</select>
</div>
""",
            instance.pk,
            _("Move '{}' to a new location").format(instance),
            root_button,
            instance.pk,
            _("Choose new location"),
            options,
        )

    move_column.short_description = _("move")

    def get_urls(self):
        """
        Add our own ``move`` and ``load_children`` views.
        """

        return [
            path(
                "move-node/",
                self.admin_site.admin_view(self.move_node_view),
            ),
            path(
                "load-children/<int:parent_pk>/",
                self.admin_site.admin_view(self.load_children_view),
            ),
        ] + super().get_urls()

    def move_node_view(self, request):
        kw = {"request": request, "modeladmin": self}
        form = MoveNodeForm(request.POST, **kw)
        return HttpResponse(form.process())

    def load_children_view(self, request, parent_pk):
        """
        AJAX view to load children of a specific node for lazy loading.
        Returns rendered HTML rows using Django's actual changelist rendering.
        """
        try:
            parent = self.get_queryset(request).get(pk=parent_pk)
        except self.model.DoesNotExist:
            return HttpResponse(
                json.dumps({"error": "Parent not found"}),
                content_type="application/json",
                status=404,
            )

        # Get children with tree fields
        children_queryset = (
            self.model._default_manager.with_tree_fields()
            .filter(parent=parent)
            .order_by(
                self.get_ordering(request)[0]
                if self.get_ordering(request)
                else self.position_field or "pk"
            )
        )

        # Apply batch size limit
        if self.lazy_load_batch_size:
            children_queryset = children_queryset[: self.lazy_load_batch_size]

        # Get parent IDs for proper toggle rendering
        parent_ids_with_children = self.get_parent_ids_with_children(request)

        # Use Django's actual changelist rendering
        from django.contrib.admin.views.main import ChangeList

        # Create a real ChangeList instance
        changelist = ChangeList(
            request=request,
            model=self.model,
            list_display=self.list_display,
            list_display_links=self.list_display_links,
            list_filter=(),
            date_hierarchy=None,
            search_fields=(),
            list_select_related=self.list_select_related,
            list_per_page=self.list_per_page,
            list_max_show_all=self.list_max_show_all,
            list_editable=self.list_editable,
            model_admin=self,
            sortable_by=self.sortable_by,
            search_help_text=self.search_help_text,
        )

        # Override the queryset with our children
        changelist.result_count = children_queryset.count()
        changelist.full_result_count = changelist.result_count
        changelist.result_list = children_queryset
        changelist.formset = None

        # Create template context
        {
            "cl": changelist,
            "results": list(changelist.result_list),
            "has_add_permission": self.has_add_permission(request),
            "has_change_permission": self.has_change_permission(request),
            "has_delete_permission": self.has_delete_permission(request),
            "has_view_permission": self.has_view_permission(request),
        }

        # Process results using Django's result processing

        # Create the results using Django's internal processing
        processed_results = []
        for obj in changelist.result_list:
            row = []
            for field_name in changelist.list_display:
                # Use Django's result processing
                if hasattr(changelist, "lookup_opts"):
                    f, attr, value = changelist.lookup_field(field_name, obj, self)
                    formatted_value = changelist.display_for_field(f, value, None)
                    if field_name in (changelist.list_display_links or []):
                        url = changelist.url_for_result(obj)
                        formatted_value = f'<a href="{url}">{formatted_value}</a>'
                else:
                    # Fallback
                    if hasattr(self, field_name):
                        formatted_value = getattr(self, field_name)(obj)
                    else:
                        formatted_value = getattr(obj, field_name, "")

                # Wrap in proper cell
                css_class = f"field-{field_name}"
                if field_name == "collapse_column":
                    css_class = "action-select"

                row.append(f'<td class="{css_class}">{formatted_value}</td>')

            processed_results.append(
                f'<tr data-pk="{obj.pk}" data-tree-depth="{obj.tree_depth}">{"".join(row)}</tr>'
            )

        rendered_html = "\n".join(processed_results)

        return HttpResponse(
            json.dumps({
                "html": rendered_html.strip(),
                "parent_ids_with_children": list(parent_ids_with_children),
            }),
            content_type="application/json",
        )

    def action_form_view(self, request, obj, *, form_class, title):
        kw = {"request": request, "obj": obj, "modeladmin": self}
        form = form_class(request.POST if request.method == "POST" else None, **kw)
        if form.is_valid():
            return form.process()
        return self.render_action_form(request, form, title=title, obj=obj)

    def render_action_form(self, request, form, *, title, obj):
        adminform = helpers.AdminForm(
            form,
            [
                (None, {"fields": form.fields.keys()})
            ],  # list(self.get_fieldsets(request, obj)),
            {},  # self.get_prepopulated_fields(request, obj),
            (),  # self.get_readonly_fields(request, obj),
            model_admin=self,
        )
        media = self.media + adminform.media

        context = dict(
            self.admin_site.each_context(request),
            title=title,
            object_id=obj.pk,
            original=obj,
            adminform=adminform,
            errors=helpers.AdminErrorList(form, ()),
            preserved_filters=self.get_preserved_filters(request),
            media=media,
            is_popup=False,
            inline_admin_formsets=[],
            save_as_new=False,
            show_save_and_add_another=False,
            show_save_and_continue=False,
            show_delete=False,
        )

        response = self.render_change_form(
            request, context, add=False, change=True, obj=obj
        )

        # Suppress the rendering of the "save and add another" button.
        response.context_data["has_add_permission"] = False
        return response


class MoveNodeForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.modeladmin = kwargs.pop("modeladmin")
        self.request = kwargs.pop("request")
        super().__init__(*args, **kwargs)

        self.fields["move"] = forms.ModelChoiceField(
            queryset=self.modeladmin.get_queryset(self.request)
        )
        self.fields["relative_to"] = forms.ModelChoiceField(
            queryset=self.modeladmin.get_queryset(self.request), required=False
        )
        positions = (
            MOVE_POSITIONS
            if self.modeladmin.position_field
            else MOVE_POSITIONS_PARENT_ONLY
        )
        # Always allow "root" position even if not shown in dropdown (handled by separate button)
        all_choices = list(positions.items())
        if ("root", _("to root")) not in all_choices:
            all_choices.append(("root", _("to root")))

        self.fields["position"] = forms.ChoiceField(choices=all_choices)

    def clean(self):
        cleaned_data = super().clean()
        position = cleaned_data.get("position")
        relative_to = cleaned_data.get("relative_to")

        # relative_to is required for all positions except "root"
        if position != "root" and not relative_to:
            raise forms.ValidationError(
                _("A target node is required for this move position.")
            )

        return cleaned_data

    def process(self):
        if not self.is_valid():
            messages.error(self.request, _("Invalid node move request."))
            messages.error(self.request, str(self.errors))
            return "error"

        move = self.cleaned_data["move"]
        relative_to = self.cleaned_data["relative_to"]
        position = self.cleaned_data["position"]

        if position == "root":
            move.parent = None
            siblings_qs = move.__class__._default_manager.filter(parent=None)
        elif position in {"first-child", "last-child"} or position == "child":
            move.parent = relative_to
            siblings_qs = relative_to.children
        else:
            move.parent = relative_to.parent
            siblings_qs = relative_to.__class__._default_manager.filter(
                parent=relative_to.parent
            )

        try:
            # All fields of model are not in this form
            move.full_clean(exclude=[f.name for f in move._meta.get_fields()])
        except ValidationError as exc:
            messages.error(
                self.request,
                _("Error while validating the new position of '{}'.").format(move),
            )
            messages.error(self.request, str(exc))
            return "error"

        position_field = self.modeladmin.position_field

        if position == "before" and position_field:
            siblings_qs.filter(**{
                f"{position_field}__gte": getattr(relative_to, position_field)
            }).update(**{position_field: F(position_field) + 10})
            setattr(move, position_field, getattr(relative_to, position_field))
            move.save()

        elif position == "after" and position_field:
            siblings_qs.filter(**{
                f"{position_field}__gt": getattr(relative_to, position_field)
            }).update(**{position_field: F(position_field) + 10})
            setattr(move, position_field, getattr(relative_to, position_field) + 10)
            move.save()

        elif position == "first-child" and position_field:
            siblings_qs.update(**{position_field: F(position_field) + 10})
            setattr(move, position_field, 10)
            move.save()

        elif position == "last-child" and position_field:
            setattr(
                move, position_field, 0
            )  # Let model's save method handle the position
            move.save()

        elif position in {"child", "root"}:
            # Parent already set above, just save
            if position_field and position == "root":
                setattr(move, position_field, 0)  # Let model handle positioning
            move.save()

        else:  # pragma: no cover
            pass

        messages.success(
            self.request,
            _("Node '{}' has been moved to its new position.").format(move),
        )
        return "ok"


class AncestorFilter(SimpleListFilter):
    """
    Only show the subtree of an ancestor

    By default, the first two levels are shown in the ``list_filter`` sidebar.
    This can be changed by setting the ``max_depth`` class attribute to a
    different value.

    Usage::

        class NodeAdmin(TreeAdmin):
            list_display = ("indented_title", "move_column", ...)
            list_filter = ("is_active", AncestorFilter, ...)

        admin.site.register(Node, NodeAdmin)
    """

    title = _("subtree")
    parameter_name = "ancestor"
    max_depth = 1

    def indent(self, depth):
        return mark_safe("&#x251c;" * depth)

    def lookups(self, request, model_admin):
        return [
            (node.id, format_html("{} {}", self.indent(node.tree_depth), node))
            for node in model_admin.model._default_manager.with_tree_fields().extra(
                where=[f"tree_depth <= {self.max_depth}"]
            )
        ]

    def queryset(self, request, queryset):
        if self.value():
            try:
                node = queryset.model._default_manager.get(pk=self.value())
            except (TypeError, ValueError, queryset.model.DoesNotExist) as exc:
                raise IncorrectLookupParameters() from exc
            return queryset.descendants(node, include_self=True)
        return queryset
