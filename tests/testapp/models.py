from django.db import models
from django.utils.translation import gettext_lazy as _

from tree_queries import TranslatedField, translated_attributes


@translated_attributes("stuff")
class TestModel(models.Model):
    name = TranslatedField(models.CharField(_("name"), max_length=200))
    other = TranslatedField(
        models.CharField(_("other field"), max_length=200, blank=True)
    )

    def __str__(self):
        return self.name

    stuff_en = "eng"
    stuff_de = "ger"


def custom_attrgetter(name):
    # Nonsense example.
    return lambda self: self.name_fr or self.name_it or "NO VALUE"


class CustomLanguagesModel(models.Model):
    name = TranslatedField(
        models.CharField(_("name"), max_length=200),
        languages=("fr", "it"),
        attrgetter=custom_attrgetter,
    )


class SpecificModel(models.Model):
    name = TranslatedField(
        models.CharField(_("name"), max_length=200, blank=True),
        {"en": {"blank": False}},
    )
