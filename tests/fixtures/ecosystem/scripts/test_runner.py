import argparse
import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--flags", required=True)
    args = parser.parse_args()

    if args.flags != os.environ.get("FEATURE_FLAGS"):
        raise SystemExit(1)
    print("tests passed")
