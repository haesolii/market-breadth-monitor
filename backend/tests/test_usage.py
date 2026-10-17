from app import usage


def test_surge_level():
    assert usage.surge_level(1, 0.0, 0) is None            # below the first level
    assert usage.surge_level(3, 0.5, 0) == 3               # first level, way above normal
    assert usage.surge_level(4, 0.5, 3) is None            # level 3 already alerted today
    assert usage.surge_level(12, 1.0, 3) == 10             # jumps straight to the highest new level
    assert usage.surge_level(6, 4.0, 0) is None            # busy but not 3x the usual day
    assert usage.visitor_id("1.2.3.4", "ua") == usage.visitor_id("1.2.3.4", "ua") != usage.visitor_id("1.2.3.5", "ua")
