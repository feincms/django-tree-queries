from django.test import TestCase

from .models import Model


class Test(TestCase):
    def test_stuff(self):
        Model.objects.create()

        self.assertEqual(len(Model.objects.with_tree_fields()), 1)

        instance = Model.objects.with_tree_fields().get()
        self.assertEqual(instance.tree_depth, 1)
        self.assertEqual(instance.tree_path, [instance.pk])
