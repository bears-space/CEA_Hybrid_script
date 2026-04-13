import unittest

from src.ui.workflow_map import workflow_map_payload


class WorkflowMapTests(unittest.TestCase):
    def test_workflow_payload_contains_expected_nodes_and_edges(self):
        payload = workflow_map_payload()

        phase_keys = {phase["key"] for phase in payload["phases"]}
        node_ids = {node["id"] for node in payload["nodes"]}
        edge_pairs = {(edge["from"], edge["to"]) for edge in payload["edges"]}

        self.assertIn("configs", phase_keys)
        self.assertIn("verification", phase_keys)
        self.assertIn("geometry", node_ids)
        self.assertIn("structural_size", node_ids)
        self.assertIn("test_readiness", node_ids)
        self.assertIn(("nominal", "geometry"), edge_pairs)
        self.assertIn(("geometry", "structural_size"), edge_pairs)
        self.assertIn(("test_compare_model", "test_readiness"), edge_pairs)

    def test_workflow_nodes_define_inputs_and_outputs(self):
        payload = workflow_map_payload()
        nodes = {node["id"]: node for node in payload["nodes"]}

        self.assertTrue(nodes["geometry"]["outputs"])
        self.assertTrue(nodes["structural_size"]["inputs"])
        self.assertIn("geometry/geometry_definition.json", nodes["geometry"]["outputs"])
        self.assertIn("testing/readiness_summary.json", nodes["test_readiness"]["outputs"])


if __name__ == "__main__":
    unittest.main()
