import json

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin, SimpleListFilter, display, helpers
from django.contrib.admin.options import (
    IncorrectLookupParameters,
    csrf_protect_m,
)
from django.core import checks
from django.core.exceptions import ValidationError
from django.db.models import F
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html, format_html_join, mark_safe
from django.utils.translation import gettext_lazy as _


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

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        if "tree_queries" not in settings.INSTALLED_APPS:
            errors.append(
                checks.Error(
                    '"tree_queries" must be in INSTALLED_APPS.',
                    obj=self.__class__,
                    id="tree_queries.E001",
                )
            )
        return errors

    @csrf_protect_m
    def changelist_view(self, request, **kwargs):
        from js_asset.js import JS  # noqa: PLC0415

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
        return {
            "initiallyCollapseDepth": 1,
        }

    def get_queryset(self, request):
        return self.model._default_manager.with_tree_fields()

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

    @admin.display(description=_("move"))
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

    def get_urls(self):
        """
        Add our own ``move`` view.
        """

        return [
            path(
                "move-node/",
                self.admin_site.admin_view(self.move_node_view),
            ),
        ] + super().get_urls()

    def move_node_view(self, request):
        kw = {"request": request, "modeladmin": self}
        form = MoveNodeForm(request.POST, **kw)
        return HttpResponse(form.process())

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
