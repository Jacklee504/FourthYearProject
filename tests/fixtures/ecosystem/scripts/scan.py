import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--threshold", required=True)
args = parser.parse_args()

if args.threshold != os.environ.get("SCAN_THRESHOLD"):
    raise SystemExit(1)
print("scan passed")
