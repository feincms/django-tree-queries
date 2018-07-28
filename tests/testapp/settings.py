import os


DATABASES = {
    "default": {"ENGINE": "django.db.backends.postgresql", "NAME": "tree-queries"}
    # "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    # "default": {"ENGINE": "django.db.backends.mysql", "NAME": "tree-queries"}
}

if os.environ.get("DB") == "mysql":
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.mysql", "NAME": "tree-queries"}
    }

INSTALLED_APPS = [
    # "django.contrib.auth",
    # "django.contrib.admin",
    # "django.contrib.contenttypes",
    # "django.contrib.sessions",
    # "django.contrib.staticfiles",
    # "django.contrib.messages",
    "testapp",
    # "tree_queries",
]

MEDIA_ROOT = "/media/"
STATIC_URL = "/static/"
BASEDIR = os.path.dirname(__file__)
MEDIA_ROOT = os.path.join(BASEDIR, "media/")
STATIC_ROOT = os.path.join(BASEDIR, "static/")
SECRET_KEY = "supersikret"
LOGIN_REDIRECT_URL = "/?login=1"

ROOT_URLCONF = "testapp.urls"
LANGUAGES = (("en", "English"), ("de", "German"))

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
