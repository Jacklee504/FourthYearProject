import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--channel", required=True)
args = parser.parse_args()

if args.channel != os.environ.get("NOTIFICATION_CHANNEL"):
    raise SystemExit(1)
print(f"notify: {args.channel}")
