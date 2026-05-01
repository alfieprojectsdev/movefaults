from drive_archaeologist.strategies.gnss import GNSSStrategy


def test_match_valid_rinex_obs():
    s = GNSSStrategy()
    assert s.match("ALGO0010.22O") is True
    assert s.match("site0010.23o") is True
    assert s.match("/some/path/PBIS0010.22O") is True


def test_match_valid_rinex_nav_and_gnav():
    s = GNSSStrategy()
    assert s.match("ALGO0010.22N") is True
    assert s.match("ALGO0010.22G") is True


def test_match_rejects_false_positives():
    s = GNSSStrategy()
    assert s.match("photo.video") is False      # ends in 'o' but not RINEX
    assert s.match("document.photo") is False   # ends in 'o' but not RINEX
    assert s.match("foo.portfolio") is False    # ends in 'o' but not RINEX
    assert s.match("compile_output.o") is False # .o object file, not RINEX


def test_extract_parses_rinex_fields():
    s = GNSSStrategy()
    result = s.extract("ALGO0010.22O")
    assert result is not None
    assert result["station"] == "ALGO"
    assert result["doy"] == 1
    assert result["year"] == 22
    assert result["file_type"] == "O"
