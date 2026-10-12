"""Run a project service from the repository root."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SERVICES = {'web': ('apps/travel_web', 'app.py'), 'agent': ('apps/travel_agent', 'main.py'), 'init-db': ('apps/travel_web', 'init_db.py')}

def main():
    parser = argparse.ArgumentParser(description='TravelFrog services')
    parser.add_argument("service", choices=SERVICES)
    parser.add_argument("--init-config", action="store_true", help="Create local config.json from the example, then exit")
    args = parser.parse_args()
    directory, entry = SERVICES[args.service]
    directory = ROOT / directory
    if args.init_config:
        example, target = directory / "config.example.json", directory / "config.json"
        if not example.is_file():
            parser.error("This service does not use config.json")
        if target.exists():
            parser.error("config.json already exists; it will not be overwritten")
        shutil.copyfile(example, target)
        print("Created " + str(target.relative_to(ROOT)))
        return 0
    return subprocess.call([sys.executable, entry], cwd=directory)

if __name__ == "__main__":
    raise SystemExit(main())
