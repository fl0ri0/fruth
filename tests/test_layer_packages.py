import unittest

from fruth_runtime.registry import read_registry_entries
from fruth_runtime.lifecycle import list_running_instances
from fruth_services.file_inputs import file_kind_from_name
from fruth_services.inference import InferArtifacts, InferContext


class LayerPackageTests(unittest.TestCase):
    def test_runtime_layer_exports_registry_and_runtime(self):
        self.assertTrue(callable(read_registry_entries))
        self.assertTrue(callable(list_running_instances))

    def test_services_layer_exports_infer_and_file_helpers(self):
        self.assertEqual(file_kind_from_name("note.txt"), "text")
        self.assertEqual(file_kind_from_name("index.html"), "text")
        self.assertEqual(file_kind_from_name("style.css"), "text")
        self.assertIsNotNone(InferContext)
        self.assertIsNotNone(InferArtifacts)


if __name__ == "__main__":
    unittest.main()
