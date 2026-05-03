from drive_archaeologist.classifier import Classifier
from drive_archaeologist.profiles import CLASSIFICATION_PROFILES


def test_gnss_extensions_classified():
    c = Classifier()
    assert c.classify_by_ext(".rnx") == "GNSS Data"
    assert c.classify_by_ext(".sp3") == "GNSS Data"
    assert c.classify_by_ext(".crx") == "GNSS Data"


def test_html_resolves_to_text():
    c = Classifier()
    assert c.classify_by_ext(".html") == "Text"
    assert c.classify_by_ext(".htm") == "Text"


def test_js_resolves_to_source_code():
    c = Classifier()
    assert c.classify_by_ext(".js") == "Source Code"


def test_ts_resolves_to_source_code():
    c = Classifier()
    assert c.classify_by_ext(".ts") == "Source Code"


def test_sh_resolves_to_source_code():
    c = Classifier()
    assert c.classify_by_ext(".sh") == "Source Code"


def test_rtf_resolves_to_document():
    c = Classifier()
    assert c.classify_by_ext(".rtf") == "Document"


def test_no_duplicate_extensions_in_profiles():
    seen = {}
    for category, exts in CLASSIFICATION_PROFILES.items():
        for ext in exts:
            assert ext not in seen, (
                f"Extension '{ext}' appears in both '{seen[ext]}' and '{category}'"
            )
            seen[ext] = category
