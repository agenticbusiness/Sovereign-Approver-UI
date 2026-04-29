import unittest
from engine_multi_part_inference import (
    check_dimensional_symmetry,
    extract_lexical_root,
    check_lexical_proximity,
    check_spatial_geometry,
    check_header_multiplicity,
    infer_multi_part_row
)

class TestMultiPartInference(unittest.TestCase):
    
    def test_gate_01_dimensional_symmetry(self):
        vars_a = {"size": "1/2", "outside_diam": "3.50", "extra_notes": "foo"}
        vars_b = {"size": "1/2", "outside_diam": "3.50", "galvanized": "G123"}
        self.assertTrue(check_dimensional_symmetry(vars_a, vars_b))
        
        vars_c = {"size": "3/4", "outside_diam": "3.88"}
        self.assertFalse(check_dimensional_symmetry(vars_a, vars_c))
        
    def test_gate_02_lexical_proximity(self):
        self.assertEqual(extract_lexical_root("SFWN-R0012"), "R0012")
        self.assertEqual(extract_lexical_root("SFWX-R0012"), "R0012")
        self.assertTrue(check_lexical_proximity("SFWN-R0012", "SFWX-R0012"))
        self.assertFalse(check_lexical_proximity("SFWN-R0012", "SFWN-R0034"))
        
    def test_gate_03_spatial_geometry(self):
        bbox_a = [100, 200, 150, 220] # y_center = 210
        bbox_b = [300, 202, 350, 218] # y_center = 210
        self.assertTrue(check_spatial_geometry(bbox_a, bbox_b, threshold=5.0))
        
        bbox_c = [300, 250, 350, 270] # y_center = 260
        self.assertFalse(check_spatial_geometry(bbox_a, bbox_c, threshold=5.0))
        
    def test_gate_04_schema_multiplicity(self):
        headers_multi = ["Part # Raised Face", "Part # Flat Face", "Size", "Weight"]
        headers_single = ["Item No", "Size", "Weight"]
        
        self.assertTrue(check_header_multiplicity(headers_multi))
        self.assertFalse(check_header_multiplicity(headers_single))
        
    def test_full_4_stage_lock(self):
        part_a = "SFWN-R0012"
        part_b = "SFWX-R0012"
        vars_a = {"size": "1/2", "outside_diam": "3.50"}
        vars_b = {"size": "1/2", "outside_diam": "3.50"}
        bbox_a = [100, 200, 150, 220]
        bbox_b = [300, 202, 350, 218]
        headers = ["Part # Raised Face", "Part # Raised Face XH Bore", "Size"]
        
        result = infer_multi_part_row(part_a, part_b, vars_a, vars_b, bbox_a, bbox_b, headers)
        self.assertTrue(result["is_shared"])
        self.assertIn("dimensional", result["passed_stages"])
        self.assertIn("lexical", result["passed_stages"])
        self.assertIn("spatial", result["passed_stages"])
        self.assertIn("schema", result["passed_stages"])

if __name__ == '__main__':
    unittest.main()
