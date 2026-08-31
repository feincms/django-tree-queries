import os
import re
import subprocess
import sys
from datetime import date


sys.path.append(os.path.abspath(".."))

project = "django-tree-queries"
author = "Feinheit AG"
copyright = f"2018-{date.today().year}, {author}"  # noqa: A001
version = __import__("tree_queries").__version__
release = subprocess.check_output(
    "git fetch --tags; git describe", shell=True, text=True
).strip()
language = "en"

#######################################
project_slug = re.sub(r"[^a-z]+", "", project)

extensions = []
templates_path = ["_templates"]
source_suffix = ".rst"
master_doc = "index"

exclude_patterns = ["build", "Thumbs.db", ".DS_Store"]
pygments_style = "sphinx"
todo_include_todos = False

html_theme = "alabaster"
# html_static_path = ["_static"]  # Commented out until needed
htmlhelp_basename = project_slug + "doc"

latex_elements = {
    "papersize": "a4",
}
latex_documents = [
    (
        master_doc,
        project_slug + ".tex",
        project + " Documentation",
        author,
        "manual",
    )
]
man_pages = [
    (
        master_doc,
        project_slug,
        project + " Documentation",
        [author],
        1,
    )
]
texinfo_documents = [
    (
        master_doc,
        project_slug,
        project + " Documentation",
        author,
        project_slug,
        "",  # Description
        "Miscellaneous",
    )
]
