import pytest
import os
from bernese_workflow.orchestrator import BerneseOrchestrator

@pytest.fixture
def orchestrator(tmp_path):
    bernese_path = str(tmp_path / "bernese")
    template_dir = str(tmp_path / "templates")
    os.makedirs(bernese_path)
    os.makedirs(template_dir)
    return BerneseOrchestrator(bernese_path, template_dir)

def test_generate_pcf(orchestrator, tmp_path):
    # Setup template
    template_name = "test.pcf.j2"
    template_content = "PCF content for {{ campaign_name }}"
    template_path = os.path.join(orchestrator.template_env.loader.searchpath[0], template_name)
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(template_content)

    # Test inputs
    context = {"campaign_name": "TEST_CAMPAIGN"}
    output_path = str(tmp_path / "output.pcf")

    # Run the method
    orchestrator.generate_pcf(template_name, context, output_path)

    # Verify output
    assert os.path.exists(output_path)
    with open(output_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == "PCF content for TEST_CAMPAIGN"
