from drive_archaeologist.strategies.gnss import GNSSStrategy, TrimbleStrategy


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


# ---------------------------------------------------------------------------
# TrimbleStrategy
# ---------------------------------------------------------------------------

def test_trimble_matches_all_extensions():
    s = TrimbleStrategy()
    for ext in (".t01", ".t02", ".t04", ".tgd", ".T01", ".T02", ".T04", ".TGD"):
        assert s.match(f"BOST001a{ext}") is True, f"Should match {ext}"


def test_trimble_rejects_rinex_and_others():
    s = TrimbleStrategy()
    assert s.match("BOST0010.22O") is False
    assert s.match("archive.zip") is False
    assert s.match("data.dat") is False


def test_trimble_extract_sets_requires_conversion():
    s = TrimbleStrategy()
    result = s.extract("BOST001a.T01")
    assert result is not None
    assert result["requires_conversion"] is True
    assert result["type"] == "gnss_trimble_raw"
    assert result["extension"] == ".t01"


def test_trimble_extract_preserves_filename():
    s = TrimbleStrategy()
    result = s.extract("/deep/path/PBIS003b.TGD")
    assert result["filename"] == "PBIS003b.TGD"
