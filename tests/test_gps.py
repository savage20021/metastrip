import pytest

from metastrip.gps import dms_to_decimal, parse_gps_ifd


def test_dms_north_east_positive():
    # 48° 51' 30.24" — plain tuple-of-rationals form
    lat = dms_to_decimal(((48, 1), (51, 1), (302400, 10000)), b"N")
    assert lat == pytest.approx(48.8584, abs=1e-6)


def test_dms_south_west_negative():
    lat = dms_to_decimal(((48, 1), (51, 1), (302400, 10000)), b"S")
    lon = dms_to_decimal(((2, 1), (17, 1), (402000, 10000)), "W")
    assert lat == pytest.approx(-48.8584, abs=1e-6)
    assert lon == pytest.approx(-2.2945, abs=1e-6)


def test_dms_missing_seconds():
    assert dms_to_decimal(((10, 1), (30, 1)), "N") == pytest.approx(10.5)


def test_dms_zero_denominator_raises():
    with pytest.raises(ValueError):
        dms_to_decimal(((48, 0), (0, 1), (0, 1)), "N")


def test_parse_gps_ifd_full():
    ifd = {
        1: b"S", 2: ((48, 1), (51, 1), (302400, 10000)),
        3: b"E", 4: ((2, 1), (17, 1), (402000, 10000)),
        5: 0, 6: (2750, 100),
        7: ((4, 1), (29, 1), (55, 1)), 29: b"2026:08:01",
    }
    gps = parse_gps_ifd(ifd)
    assert gps is not None
    assert gps["latitude"] == pytest.approx(-48.8584, abs=1e-6)
    assert gps["longitude"] == pytest.approx(2.2945, abs=1e-6)
    assert gps["altitude_m"] == pytest.approx(27.5)
    assert "-48.85" in gps["maps_url"] and "2.29" in gps["maps_url"]
    assert gps["gps_timestamp"].startswith("2026:08:01 04:29:55")


def test_parse_gps_ifd_missing_coords():
    assert parse_gps_ifd({}) is None
    assert parse_gps_ifd({1: b"N", 2: ((48, 1), (0, 1), (0, 1))}) is None


def test_parse_gps_ifd_out_of_range():
    ifd = {1: b"N", 2: ((999, 1), (0, 1), (0, 1)),
           3: b"E", 4: ((10, 1), (0, 1), (0, 1))}
    assert parse_gps_ifd(ifd) is None
