from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from bernese_workflow.backends import BPEResult
from bernese_workflow.orchestrator import BerneseOrchestrator
from bernese_workflow.pcf_context import PCFContext


@pytest.fixture
def orchestrator(tmp_path):
    bernese_path = str(tmp_path / "bernese")
    template_dir = str(tmp_path / "templates")
    os.makedirs(bernese_path)
    os.makedirs(template_dir)
    mock_backend = MagicMock()
    return BerneseOrchestrator(bernese_path, template_dir, backend=mock_backend)


def test_generate_pcf(orchestrator, tmp_path):
    template_name = "test.pcf.j2"
    template_content = "PCF content for {{ campaign_name }}"
    template_path = os.path.join(orchestrator.template_env.loader.searchpath[0], template_name)
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(template_content)

    context = {"campaign_name": "TEST_CAMPAIGN"}
    output_path = str(tmp_path / "output.pcf")

    orchestrator.generate_pcf(template_name, context, output_path)

    assert os.path.exists(output_path)
    with open(output_path, encoding="utf-8") as f:
        content = f.read()
    assert content == "PCF content for TEST_CAMPAIGN"


def test_run_bpe_calls_backend(orchestrator):
    mock_result = BPEResult(
        success=True,
        stations_survived=10,
        ambiguity_fixing_rate=0.85,
        helmchk_failed=False,
        comparf_failed=False,
    )
    orchestrator._backend.run.return_value = mock_result

    result = orchestrator.run_bpe("TESTCAMP", 2023, "0100")

    orchestrator._backend.run.assert_called_once_with("TESTCAMP", 2023, "0100")
    assert result.success is True
    assert result.stations_survived == 10


def test_generate_pcf_phivol_template(tmp_path):
    """Render the real PHIVOL_REL-derived template and verify structure."""
    template_dir = Path(__file__).parent.parent / "templates"
    mock_backend = MagicMock()
    orch = BerneseOrchestrator(str(tmp_path / "b"), str(template_dir), backend=mock_backend)

    ctx = PCFContext(v_crdinf="PIVSMIND", v_rnxdir="PIVSMIND")
    output_path = str(tmp_path / "output.pcf")
    orch.generate_pcf("basic_processing.pcf.j2", ctx.to_dict(), output_path)

    with open(output_path, encoding="utf-8") as f:
        content = f.read()

    assert "PIVSMIND" in content
    assert "000 FTP_DWLD" in content
    assert "443 AMBXTR" in content
    assert "514 HELMCHK" in content
    assert "IGS" in content   # v_b default


def test_generate_pcf_strict_undefined_raises(tmp_path):
    """StrictUndefined: rendering with a missing required var raises UndefinedError."""
    import jinja2

    template_dir = str(tmp_path / "templates")
    Path(template_dir).mkdir()
    (Path(template_dir) / "strict.j2").write_text("{{ v_required }}")

    mock_backend = MagicMock()
    orch = BerneseOrchestrator(str(tmp_path / "b"), template_dir, backend=mock_backend)

    with pytest.raises(jinja2.UndefinedError):
        orch.generate_pcf("strict.j2", {}, str(tmp_path / "out.pcf"))
