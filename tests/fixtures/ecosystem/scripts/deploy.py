import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--registry", required=True)
parser.add_argument("--strategy")
args = parser.parse_args()

if args.registry != os.environ.get("REGISTRY_URL"):
    raise SystemExit(1)
if args.strategy is not None and args.strategy != os.environ.get("DEPLOY_STRATEGY"):
    raise SystemExit(1)
print(f"deploy: {args.registry}")
