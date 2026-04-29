import re

def check_dimensional_symmetry(vars_a, vars_b):
    def clean(v):
        return {k: val for k, val in v.items() if not k.startswith('extra_') and k != 'galvanized'}
    return clean(vars_a) == clean(vars_b)

def extract_lexical_root(part_number):
    match = re.search(r'[-_]([A-Za-z0-9]+)$', part_number)
    if match:
        return match.group(1)
    match = re.search(r'([0-9]+[A-Za-z]*)$', part_number)
    if match:
        return match.group(1)
    return part_number

def check_lexical_proximity(part_a, part_b):
    root_a = extract_lexical_root(part_a)
    root_b = extract_lexical_root(part_b)
    return root_a == root_b and len(root_a) >= 3

def check_spatial_geometry(bbox_a, bbox_b, threshold=5.0):
    if not bbox_a or not bbox_b:
        return False
    cent_y_a = (bbox_a[1] + bbox_a[3]) / 2.0
    cent_y_b = (bbox_b[1] + bbox_b[3]) / 2.0
    return abs(cent_y_a - cent_y_b) <= threshold

def check_header_multiplicity(headers):
    part_headers = [h for h in headers if 'part' in h.lower() or 'item' in h.lower()]
    return len(part_headers) > 1

def infer_multi_part_row(part_a, part_b, vars_a, vars_b, bbox_a, bbox_b, headers):
    stages = {
        "dimensional": check_dimensional_symmetry(vars_a, vars_b),
        "lexical": check_lexical_proximity(part_a, part_b),
        "spatial": check_spatial_geometry(bbox_a, bbox_b),
        "schema": check_header_multiplicity(headers)
    }
    
    is_shared = stages["dimensional"] and (stages["lexical"] or stages["spatial"])
    
    return {
        "is_shared": is_shared,
        "passed_stages": [k for k, v in stages.items() if v]
    }

