# Release checklist

Ship a build to Play in this order. Each gate exists because the next step relies on it.
Reasoning and tool details live in [README.md](README.md).

## 1. Start from a clean, current `main`

- [ ] `git status` is clean and `git pull` brings nothing new
- [ ] `python tools/check_store_listings.py` exits `0`, meaning all seven live listings still
      match this repo — or an open *Store listing drift detected* issue covers copy you are
      about to publish in step 5

## 2. Decide what the release contains

- [ ] Bump `versionCode` in [app/build.gradle.kts](app/build.gradle.kts) — it must be higher
      than the code already live on Play, and Play never re-accepts an old one
- [ ] Set `versionName` to what this release is called
- [ ] Listing copy changing? Edit [tools/write_store_listings.py](tools/write_store_listings.py),
      run `python tools/write_store_listings.py`, and commit the regenerated files under
      [fastlane/metadata/android](fastlane/metadata/android). Never hand-edit those `.txt` files;
      the next generator run overwrites them

## 3. Build the bundle

- [ ] `./gradlew bundleRelease`
- [ ] The `checkStoreListings` task runs first: real drift fails the build, so a green build
      means Play and fastlane agree at build time
- [ ] If it prints `checkStoreListings skipped`, the listing was **not** verified — export
      `PLAY_ACCESS_TOKEN` (command in the README) and build again
- [ ] Bundle lands at `app/build/outputs/bundle/release/app-release.aab` (git-ignored)
- [ ] Commit the version bump before uploading, so history matches what shipped

## 4. Upload to Play

- [ ] Play Console → Timer Haven → create the release, upload the AAB
- [ ] Fill in release notes and the rollout percentage
- [ ] If the change touches the WebView shell, ship to internal or closed testing first

## 5. Publish listing copy (only if step 2 changed it)

- [ ] Push the copy through the Play Developer API with the same service account: open an edit,
      `PUT` `edits/<id>/listings/<locale>` for each locale, then commit the edit
- [ ] `python tools/check_store_listings.py` exits `0` again
- [ ] Any open drift issue closes on the next scheduled run; close it by hand only after
      confirming the live pages show the new copy

## 6. Afterwards

- [ ] The next 06:17 UTC drift run is green
- [ ] The version code in Play Console matches `app/build.gradle.kts` on `main`

## If something goes wrong

- [ ] Halt the rollout in Play Console — the release stays, distribution stops
- [ ] Fix forward with a new `versionCode`; editing a released bundle is not possible
- [ ] Published copy can be corrected the same way, and the drift check reports exactly which
      lines disagree before you republish
