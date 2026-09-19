"""Extract measurements from a saved real OTA baseline job."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analog_optimizer.measurements.opamp import analyze

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("job", type=Path)
    result = analyze(p.parse_args().job)
    print(json.dumps({"job_id": result["job_id"], "metrics": result["metrics"]}, indent=2))
