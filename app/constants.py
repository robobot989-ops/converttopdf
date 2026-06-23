PAGE_WIDTH = 842
PAGE_HEIGHT = 595
PAGE_MARGIN = 36
FLATTENING_DISTANCE = 0.05
POINTS_PER_MM = 72 / 25.4

DXF_INSUNITS_TO_MM = {
    0: 1.0,  # unitless; assume millimeters for typical packaging drawings
    1: 25.4,
    2: 304.8,
    3: 1609344.0,
    4: 1.0,
    5: 10.0,
    6: 1000.0,
    7: 1_000_000.0,
    8: 0.0000254,
    9: 0.000254,
    10: 914.4,
    11: 1e-7,
    12: 1e-6,
    13: 0.001,
    14: 100.0,
    15: 10_000.0,
    16: 100_000.0,
    17: 1_000_000_000.0,
    18: 149_597_870_700_000.0,
    19: 9.4607e18,
    20: 3.0857e19,
}
