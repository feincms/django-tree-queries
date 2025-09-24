# django-tree-queries
Django package for tree queries using adjacency lists and recursive CTEs. Supports PostgreSQL, SQLite 3.8.3+, MariaDB 10.2.2+, and MySQL 8.0+.

**Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Working Effectively

### Repository Setup and Installation
- **NEVER CANCEL: Dependencies installation takes 5-10 minutes depending on network. Set timeout to 15+ minutes.**
- `pip install -e .` - Install core package in development mode (no admin features)
- `pip install -e .[admin]` - Install with admin functionality (includes django-js-asset)
- `pip install -e .[tests]` - Install with all testing dependencies (includes pytest, coverage, django-js-asset)
- `pip install tox` - Install tox for comprehensive testing across Python/Django combinations

### Build and Test Commands
- **NEVER CANCEL: tox full test suite takes 20-45 minutes across all combinations. Set timeout to 60+ minutes.**
- `tox` - Run complete test suite across all supported Python/Django/database combinations
- `tox -e py312-dj52-sqlite` - Run tests for specific Python/Django combination (fastest, ~2-5 minutes)
- `tox -e py312-dj52-postgresql` - Run with PostgreSQL (requires service setup)
- `tox -e py312-dj52-mysql` - Run with MySQL/MariaDB (requires service setup)
- **Alternative testing without tox (faster for development):**
  - `pip install Django>=5.0 pytest pytest-django` - Install minimal test dependencies
  - `cd tests && python -m pytest testapp/test_admin.py -v --override-ini addopts=""` - Run admin tests (~4 seconds for 12 tests)
  - `cd tests && python -m pytest testapp/test_queries.py -v --override-ini addopts=""` - Run core tests (~1 second for 55 tests)
  - `cd tests && python -m pytest testapp/test_templatetags.py -v --override-ini addopts=""` - Run template tag tests

### Code Quality and Linting
- **NEVER CANCEL: pre-commit takes 2-3 minutes on first run. Set timeout to 5+ minutes.**
- `pip install ruff` - Install Python linter/formatter
- `pre-commit install` - Install git hooks for automated checks
- `pre-commit run --all-files` - Run all linting and formatting checks manually
- `ruff check .` - Run Python linting (~0.02 seconds, very fast)
- `ruff format .` - Format Python code (part of pre-commit)
- `biome check .` - Check JavaScript/CSS files (part of pre-commit, requires Node.js)

## Validation Scenarios

### Core Functionality Testing
Always test these scenarios after making changes to core tree functionality:
1. **Tree Structure Operations**: Create nodes with parent-child relationships, verify `with_tree_fields()` adds `tree_depth`, `tree_path`, `tree_ordering`
2. **Query Methods**: Test `ancestors()`, `descendants()`, `order_siblings_by()` methods
3. **Performance Filters**: Test `tree_filter()` and `tree_exclude()` with large datasets

### Admin Interface Testing
When modifying admin functionality, always test:
1. **TreeAdmin Display**: Navigate to Django admin, verify tree structure shows with indentation and collapse/expand
2. **Node Moving**: Test cut/paste workflow - click "Cut" button, select destination from dropdown, verify move operations
3. **Position Field Handling**: Test both positioned models (with `position_field`) and unpositioned models
4. **Validation**: Test move validation (preventing loops, invalid positions)

### Manual Validation Commands
```bash
# Start test Django admin server (requires Django and ALLOWED_HOSTS configuration)
cd tests
python manage.py migrate
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'testapp.settings')
import django
from django.conf import settings
settings.DEBUG = True
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
django.setup()
from django.core.management import execute_from_command_line
execute_from_command_line(['manage.py', 'runserver', '127.0.0.1:8000', '--noreload'])
"

# Server starts in ~5 seconds, then navigate to:
# http://127.0.0.1:8000/admin/testapp/model/ (positioned trees)
# http://127.0.0.1:8000/admin/testapp/unorderedmodel/ (unpositioned trees)

# Test complete workflows:
# 1. Create tree structure with 3+ levels
# 2. Use collapse/expand buttons
# 3. Cut a node and move it to different positions
# 4. Verify tree structure integrity after moves
```

## Repository Structure

### Core Package (`tree_queries/`)
- `models.py` - TreeNode abstract model class with parent ForeignKey
- `query.py` - TreeQuerySet with CTE-based tree methods
- `admin.py` - TreeAdmin class and MoveNodeForm for Django admin
- `fields.py` - TreeNodeForeignKey and form fields
- `forms.py` - TreeNodeChoiceField and TreeNodeMultipleChoiceField
- `compiler.py` - Custom SQL compiler for tree queries
- `templatetags/tree_queries.py` - Template tags (tree_info, recursetree)
- `static/tree_queries/` - CSS and JavaScript for admin interface

### Test Suite (`tests/`)
- `testapp/models.py` - Test models (Model, UnorderedModel, StringOrderedModel)
- `testapp/admin.py` - Example admin classes for testing
- `testapp/test_admin.py` - 12 comprehensive admin test cases
- `testapp/test_queries.py` - Core tree query functionality tests
- `testapp/test_templatetags.py` - Template tag tests
- `manage.py` - Django management script for test project

### Configuration Files
- `pyproject.toml` - Package configuration with optional dependencies
- `tox.ini` - Test environment configuration for multiple Python/Django versions
- `.pre-commit-config.yaml` - Code quality hooks (ruff, biome, django-upgrade)
- `biome.json` - JavaScript/CSS linting configuration

## Common Tasks

### Running Admin Demo
```bash
cd tests
python manage.py migrate
python manage.py createsuperuser  # Create admin user
python manage.py runserver
# Visit http://localhost:8000/admin/
```

### Database Backends
```bash
# SQLite (default, fastest)
DB_BACKEND=sqlite3 DB_NAME=":memory:" tox -e py312-dj52-sqlite

# PostgreSQL (requires service)
DB_BACKEND=postgresql DB_HOST=localhost DB_PORT=5432 tox -e py312-dj52-postgresql

# MySQL/MariaDB (requires service)
DB_BACKEND=mysql DB_HOST=localhost DB_PORT=3306 tox -e py312-dj52-mysql
```

### Tree Query Examples
```python
# Basic tree operations
nodes = Node.objects.with_tree_fields()  # Adds tree_depth, tree_path, tree_ordering
ancestors = node.ancestors()  # All ancestors from root
descendants = node.descendants(include_self=True)  # All descendants including self

# Performance optimizations for large trees
filtered_tree = Node.objects.with_tree_fields().tree_filter(category="products")
nodes_with_names = Node.objects.with_tree_fields().tree_fields(tree_names="name")
```

### Admin Configuration Examples
```python
# Positioned tree (controllable sibling ordering)
@admin.register(Category)
class CategoryAdmin(TreeAdmin):
    list_display = [*TreeAdmin.list_display, "name", "is_active"]
    position_field = "order"  # Field used for sibling positioning

# Unpositioned tree (ordering by other criteria)
@admin.register(Department)
class DepartmentAdmin(TreeAdmin):
    list_display = [*TreeAdmin.list_display, "name"]
    # position_field = None (default) - uses direct root moves
```

## Performance and Timing Expectations

- **Package Installation**: 5-10 minutes (network dependent)
- **Full tox Test Suite**: 20-45 minutes (all Python/Django/DB combinations)
- **Single Environment Tests**: 2-5 minutes (e.g., py312-dj52-sqlite)
- **Direct pytest Tests**: 1-4 seconds (individual test files without tox)
- **Pre-commit Hooks**: 2-3 minutes (first run with downloads)
- **Admin Server Startup**: 5 seconds
- **Python Linting (ruff)**: 0.02 seconds (extremely fast)

### Validated Test Timings
- Admin tests: 4.19 seconds (12 tests)
- Core query tests: 0.52 seconds (55 tests)
- Single test case: 0.57 seconds

## Critical Notes

- **Tree Path Limitations**: Max 50 levels on MySQL/MariaDB due to array length constraints
- **Parent Field Name**: Must be named `"parent"` (not configurable)
- **Update Queries**: `node.descendants().update()` doesn't work - use `Model.objects.filter(pk__in=node.descendants()).update()` instead
- **Admin Dependencies**: TreeAdmin requires `django-js-asset` (included in `[admin]` extra)
- **Loop Prevention**: TreeNode.clean() validates against tree loops, but CTE doesn't protect against them for performance
- **Database Support**: PostgreSQL, SQLite 3.8.3+, MariaDB 10.2.2+, MySQL 8.0+ (without ONLY_FULL_GROUP_BY)

## Always Run Before Committing
```bash
# Fast development validation (recommended for quick checks)
ruff check .  # Python linting - 0.02 seconds
cd tests && python -m pytest testapp/test_admin.py --override-ini addopts=""  # Admin tests - 4 seconds
cd tests && python -m pytest testapp/test_queries.py --override-ini addopts=""  # Core tests - 1 second

# Full validation (before final commit)
pre-commit run --all-files  # NEVER CANCEL: Takes 2-3 minutes
tox -e py312-dj52-sqlite  # Full single-env test suite - 2-5 minutes
```

The CI will fail if pre-commit checks don't pass or if any tests fail across the supported Python/Django matrix.
