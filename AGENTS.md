# Agent Notes for django-tree-queries

This document contains information for AI agents working on this project.

## Project Structure

- **Library code**: `tree_queries/` — the Django app
  - `models.py`: `TreeNode` and `OrderableTreeNode` base classes
  - `query.py`: `TreeQuerySet` with `.with_tree_fields()`, `.ancestors()`, `.descendants()`
  - `compiler.py`: SQL generation for the recursive CTE
  - `templatetags/tree_queries.py`: `{% recursetree %}` tag and `|tree_info` filter
  - `admin.py`: `TreeAdmin` class (requires `django-js-asset`)
- **Tests**: `tests/testapp/` — pytest-based, uses SQLite by default
- **Documentation**: ReStructuredText in `docs/`
- **Changelog**: `CHANGELOG.rst`

## Running Tests

Use `tox` with a SQLite environment for fast local runs:

```bash
tox -e py313-djmain-sqlite
```

Available environments follow the pattern `py{version}-dj{version}-{db}`. Use
`tox list` to see all options. PostgreSQL and MySQL environments require a
running database server.

## Code Style

The project uses `ruff` for linting and formatting (configured in
`pyproject.toml`). `prek` hooks run automatically on commit. To run manually:

```bash
prek run --all-files
```

## Changelog

Add entries for user-visible changes under the `Next version` heading in
`CHANGELOG.rst`, following the existing style (plain RST bullet points, no
date).

## GitHub Issues

Commit messages that start with `Fix #123: ` or `Fixes #123: ` will
automatically close the referenced issue when merged to the main branch. Use
this pattern when addressing specific issues.

## Key Concepts

### Tree fields

Calling `.with_tree_fields()` on a queryset adds three annotation attributes
to each node:

- `tree_depth` — 0-based depth in the tree
- `tree_path` — array of ancestor PKs (used for ordering/filtering)
- `tree_ordering` — array used for correct sibling ordering

### Template tags

`{% recursetree nodes %}...{% endrecursetree %}` renders a tree recursively.
Inside the block, `node` is the current node, `children` is the pre-rendered
HTML of its children, and `is_leaf` is `True` when the node has no children in
the queryset. The tag uses `context.render_context` (not instance state) to
cache child relationships, keeping it thread-safe and fresh on every render.

### Testing approach

Tests are written with pytest and `@pytest.mark.django_db` (or the class-level
equivalent). Prefer functional tests that exercise the public API over tests
that reach into private implementation details.
