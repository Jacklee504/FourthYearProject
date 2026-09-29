import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--registry", required=True)
parser.add_argument("--cmd", required=True)
args = parser.parse_args()

if args.registry != os.environ.get("REGISTRY_URL") or args.cmd != os.environ.get("BUILD_CMD"):
    raise SystemExit(1)
print(f"build: {args.cmd} -> {args.registry}")
