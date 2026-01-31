import subprocess
import json
import os
import click
from typing import Dict, Any, Optional

class RinexQC:
    def __init__(self, gfzrnx_path: str = "gfzrnx"):
        self.gfzrnx_path = gfzrnx_path

    def run_qc(self, rinex_file: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """Runs gfzrnx QC and returns the parsed JSON result."""
        if not os.path.exists(rinex_file):
            raise FileNotFoundError(f"RINEX file not found: {rinex_file}")

        # Basic QC command to get JSON output
        # gfzrnx -finp <file> -qc -json
        cmd = [self.gfzrnx_path, "-finp", rinex_file, "-qc", "-json"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            # If it fails, maybe try to capture stderr
            raise RuntimeError(f"gfzrnx failed: {e.stderr}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse gfzrnx JSON output: {e}")

@click.command()
@click.option("--file", "-f", required=True, type=click.Path(exists=True), help="Path to RINEX file")
@click.option("--bin", "gfzrnx_bin", default="gfzrnx", help="Path to gfzrnx binary")
def main(file: str, gfzrnx_bin: str):
    """RINEX Quality Control CLI"""
    qc = RinexQC(gfzrnx_bin)
    try:
        results = qc.run_qc(file)
        click.echo(json.dumps(results, indent=2))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

if __name__ == "__main__":
    main()
