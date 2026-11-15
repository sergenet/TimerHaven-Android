#!/usr/bin/env python3
"""Bump the app version, regenerate the store listings, and sync them with Play.

This automates the mechanical half of RELEASE.md:

    1. bump versionCode / versionName in app/build.gradle.kts
    2. regenerate fastlane/metadata/android from tools/write_store_listings.py
    3. compare the regenerated copy with what Play is serving
    4. with --publish, push the regenerated copy to Play after confirmation and
       verify the live listings match again

Then it prints the steps that still need a human: building the bundle,
uploading the AAB and watching the next scheduled check.

    python tools/prepare_release.py --dry-run               # show what would change
    python tools/prepare_release.py                        # versionCode + 1
    python tools/prepare_release.py --version-name 1.2.0   # bump code, name the release
    python tools/prepare_release.py --publish              # also publish drift to Play
    python tools/prepare_release.py --publish --yes        # without the prompt (CI/unattended)

Publishing writes a live store asset: it opens one Play edit, PUTs all seven
listings, commits the edit and then re-runs the comparison. Nothing is sent
unless drift exists and the prompt is answered (or --yes is given).

The Play calls need PLAY_ACCESS_TOKEN; without it the script says so and
continues, exactly like the Gradle release guard.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRADLE = os.path.join(BASE, "app", "build.gradle.kts")
CODE_RE = re.compile(r"(versionCode\s*=\s*)(\d+)")
NAME_RE = re.compile(r'(versionName\s*=\s*")([^"]*)(")')

PACKAGE = "com.sergenet.TimerHavenApp"
PLAY = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/" + PACKAGE
META = os.path.join(BASE, "fastlane", "metadata", "android")
# fastlane folder -> Play locale code
LOCALES = {
    "ar": "ar",
    "de": "de-DE",
    "el": "el-GR",
    "en-US": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "ru": "ru-RU",
}
FIELDS = (
    ("title", "title.txt"),
    ("shortDescription", "short_description.txt"),
    ("fullDescription", "full_description.txt"),
)

NEXT_STEPS = """\
Still to do by hand:
  1. ./gradlew bundleRelease          (the drift check runs first; commit the bump)
  2. Play Console -> create release -> upload
     app/build/outputs/bundle/release/app-release.aab
  3. Watch the next 06:17 UTC drift run; any open drift issue should close itself."""


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


def call(token, url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        raw = response.read()
        return response.status, (json.loads(raw) if raw else None)


def ask(question, assume_yes):
    """Confirm a store change; unattended runs must opt in with --yes."""
    if assume_yes:
        print(question + " [y/N] yes (--yes)")
        return True
    if not sys.stdin.isatty():
        print("not publishing: no terminal to confirm in; re-run with --yes")
        return False
    return input(question + " [y/N] ").strip().lower() in ("y", "yes")


def publish_listings(token):
    """PUT every fastlane listing in one Play edit, then commit it."""
    _, edit = call(token, PLAY + "/edits", method="POST", body={})
    edit_id = edit["id"]
    print("opened Play edit %s" % edit_id)
    try:
        for folder, locale in sorted(LOCALES.items()):
            body = {}
            for field, filename in FIELDS:
                body[field] = read(os.path.join(META, folder, filename)).strip()
            status, _ = call(
                token, PLAY + "/edits/" + edit_id + "/listings/" + locale, method="PUT", body=body
            )
            print("  %-6s %s" % (locale, "updated" if status < 300 else "HTTP %d" % status))
    except Exception:
        # A half-written edit is never committed, so drop it rather than leave it open.
        call(token, PLAY + "/edits/" + edit_id, method="DELETE")
        print("  aborted; the uncommitted edit was deleted")
        raise
    status, _ = call(token, PLAY + "/edits/" + edit_id + ":commit", method="POST")
    print("committed the edit (HTTP %s)" % status)


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
    parser.add_argument(
        "--publish",
        action="store_true",
        help="push the regenerated listings to Play when they differ, after confirming",
    )
    parser.add_argument(
        "--yes", action="store_true", help="skip the publish confirmation (unattended runs)"
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
        drifted = [" ".join(line.split()) for line in drifted]
        print("\ndrift detected:")
        for line in drifted:
            print("  " + line)

        if not args.publish:
            print("\nnothing published: re-run with --publish to push the regenerated copy to Play")
            return 1

        token = os.environ.get("PLAY_ACCESS_TOKEN") or os.environ.get("TH_TOKEN")
        if not token:
            print("\nnot publishing: set PLAY_ACCESS_TOKEN (see README) and re-run")
            return 2

        question = "Publish all %d listings to Play (%s)?" % (
            len(LOCALES),
            ", ".join(line.split()[0] for line in drifted),
        )
        if not ask(question, args.yes):
            print("nothing published")
            return 1

        publish_listings(token)
        code, output = run("check_store_listings.py")
        if code != 0:
            print("\npublished, but the comparison does not agree yet; re-run the check in a minute")
            return 1
        print("\npublished and verified: Play now serves the regenerated listings")
    else:
        print("\ndrift check skipped: set PLAY_ACCESS_TOKEN to verify before uploading")

    print()
    print(NEXT_STEPS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
