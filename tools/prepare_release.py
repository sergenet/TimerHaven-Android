#!/usr/bin/env python3
"""Bump the app version, regenerate the store listings, and check Play.

This automates the mechanical half of RELEASE.md:

    1. bump versionCode / versionName in app/build.gradle.kts
    2. regenerate fastlane/metadata/android from tools/write_store_listings.py
    3. compare the regenerated copy with what Play is serving

Then it prints the steps that still need a human: building the bundle,
uploading the AAB, publishing copy and watching the next scheduled check.

    python tools/prepare_release.py --dry-run               # show what would change
    python tools/prepare_release.py                        # versionCode + 1
    python tools/prepare_release.py --version-name 1.2.0   # bump code, name the release

The Play comparison needs PLAY_ACCESS_TOKEN; without it the script says so and
continues, exactly like the Gradle release guard.
"""
import argparse
import io
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRADLE = os.path.join(BASE, "app", "build.gradle.kts")
CODE_RE = re.compile(r"(versionCode\s*=\s*)(\d+)")
NAME_RE = re.compile(r'(versionName\s*=\s*")([^"]*)(")')

NEXT_STEPS = """\
Still to do by hand:
  1. ./gradlew bundleRelease          (the drift check runs first; commit the bump)
  2. Play Console -> create release -> upload
     app/build/outputs/bundle/release/app-release.aab
  3. If listing copy changed in this release: publish it through the Play API,
     then re-run: python tools/check_store_listings.py
  4. Watch the next 06:17 UTC drift run; any open drift issue should close itself."""


def read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def find_one(pattern, text, label):
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise SystemExit(
            "expected exactly one %s in %s, found %d" % (label, GRADLE, len(matches))
        )
    return matches[0]


def run(script, args=()):
    command = [sys.executable, os.path.join("tools", script)] + list(args)
    result = subprocess.run(command, cwd=BASE, capture_output=True, text=True)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--version-code",
        type=int,
        help="versionCode to set (default: the current one plus one)",
    )
    parser.add_argument("--version-name", help="versionName to set (default: unchanged)")
    parser.add_argument(
        "--dry-run", action="store_true", help="show the planned bump without writing files"
    )
    args = parser.parse_args(argv)

    text = read(GRADLE)
    current_code = int(find_one(CODE_RE, text, "versionCode")[1])
    current_name = find_one(NAME_RE, text, "versionName")[1]

    new_code = args.version_code if args.version_code is not None else current_code + 1
    new_name = args.version_name if args.version_name is not None else current_name
    if new_code <= current_code:
        raise SystemExit(
            "versionCode must increase: current %d, requested %d" % (current_code, new_code)
        )

    print("versionCode  %d -> %d" % (current_code, new_code))
    print("versionName  %s -> %s" % (current_name, new_name))

    if args.dry_run:
        print("\ndry run: nothing written, generator and drift check not run")
        return 0

    text = CODE_RE.sub(lambda m: m.group(1) + str(new_code), text, count=1)
    text = NAME_RE.sub(lambda m: m.group(1) + new_name + m.group(3), text, count=1)
    with io.open(GRADLE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("updated %s" % os.path.relpath(GRADLE, BASE))

    code, output = run("write_store_listings.py")
    tail = [line for line in output.strip().splitlines() if line][-4:]
    for line in tail:
        print("  " + line)
    if code != 0:
        print("\ngenerator failed: fix the copy in tools/write_store_listings.py and re-run")
        return 1

    code, output = run("check_store_listings.py")
    if code == 0:
        print("\nPlay still matches the regenerated listings")
    elif code == 1:
        drifted = [line.strip() for line in output.splitlines() if " DRIFT" in line]
        print("\ndrift detected, publish the copy before building for upload:")
        for line in drifted:
            print("  " + " ".join(line.split()))
        return 1
    else:
        print("\ndrift check skipped: set PLAY_ACCESS_TOKEN to verify before uploading")

    print()
    print(NEXT_STEPS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
