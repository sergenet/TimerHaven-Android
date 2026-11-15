# Timer Haven (Android)

The Android app for [Timer Haven](https://timerhaven.com): a Kotlin + Jetpack Compose shell
around the shared web app, with native pieces where the browser cannot reach — ongoing
Pomodoro notifications, a Pomodoro widget and launcher shortcuts for single tools.

- Package: `com.sergenet.TimerHavenApp`
- Play: <https://play.google.com/store/apps/details?id=com.sergenet.TimerHavenApp>
- Version: `versionCode` and `versionName` in [app/build.gradle.kts](app/build.gradle.kts)

## Requirements

| Tool | Version |
|---|---|
| JDK | 17 (Android Gradle Plugin 8.10.1) |
| Android SDK | Platform 36 (`compileSdk`/`targetSdk` 36, `minSdk` 24) |
| Gradle | 8.11.1 — the wrapper fetches it, nothing to install |
| Python | 3 for the scripts in [tools](tools) (standard library only) |

## Layout

| Path | Holds |
|---|---|
| [app](app) | the application module |
| [app/src/main/assets](app/src/main/assets) | the web app bundle the WebView serves (shared with the website) |
| [app/src/main/java/com/sergenet/TimerHavenApp](app/src/main/java/com/sergenet/TimerHavenApp) | Kotlin sources: activities, foreground service, widget |
| [tools](tools) | store-listing generator and drift check |
| [fastlane/metadata/android](fastlane/metadata/android) | Play listing copy, one folder per locale |
| [.github/workflows](.github/workflows) | CI |

## Build

```bash
./gradlew assembleDebug      # APK: app/build/outputs/apk/debug/
./gradlew bundleRelease      # AAB for Play: app/build/outputs/bundle/release/
```

Release signing reads `keystore.properties` from the project root, which is git-ignored:

```properties
storeFile=/absolute/path/to/release.jks
storePassword=...
keyAlias=...
keyPassword=...
```

Without that file the release build is produced unsigned, so it cannot be uploaded.

Both release tasks depend on the `checkStoreListings` task (see below), so a bundle is only
built when the repo's listing copy and the live Play listing agree. If the check cannot
authenticate it logs a warning and the build continues; real drift fails the build.

## Store listings

Seven locales live under `fastlane/metadata/android/<locale>/`, one folder each for `en-US`,
`de`, `es`, `fr`, `ru`, `ar` and `el` — three files per locale: `title.txt` (≤ 30 chars),
`short_description.txt` (≤ 80) and `full_description.txt` (≤ 4000).

The copy is generated, not hand-edited:

```bash
python tools/write_store_listings.py
```

That rewrites every file from the table in the script, then exits non-zero if any value is
over Play's limits (`title` 30, `short_description` 80, `full_description` 4000). The files are
written either way, so shorten the copy and run it again. To change wording, edit the script,
run it, and commit the regenerated files — otherwise the next run overwrites the change.

## Drift check

`tools/check_store_listings.py` answers one question: is Play still serving exactly what this
repo says it should? It opens a read-only Play edit, reads all seven listings, compares them
with the fastlane files, and deletes the edit again. It never uploads or commits anything.

```bash
export PLAY_ACCESS_TOKEN=$(gcloud auth print-access-token \
    --scopes=https://www.googleapis.com/auth/androidpublisher \
    --account=play-publisher-sa@timerhaven-translation.iam.gserviceaccount.com)

python tools/check_store_listings.py           # per-line report
python tools/check_store_listings.py --json    # same findings as JSON
```

Exit status is `0` when everything matches, `1` when a locale has drifted, and `2` when the
check could not run at all (no token, or Play rejected it) — so a broken credential never
looks like drift.

## CI

[.github/workflows/store-listings-drift.yml](.github/workflows/store-listings-drift.yml) runs
the check daily at 06:17 UTC, on demand, and on every pull request into `main`.

- **Pull requests** report drift as a warning and stay green: a PR that changes listing copy is
  expected to differ from Play until that copy is published.
- **Scheduled and on-demand runs** fail on drift. They also open a single issue titled
  *Store listing drift detected*, with the differing lines, and comment on it on repeat
  failures instead of filing duplicates; the first run that matches fastlane closes it.
- Pull requests from forks skip the job, because they never receive repository secrets.

The workflow needs one repository secret, `PLAY_SERVICE_ACCOUNT_JSON`: the JSON key of a
service account invited in Play Console for this app with at least read access. It is exchanged
for a short-lived token scoped to `androidpublisher`; no other Google API has to be enabled.

## Publishing a release

[RELEASE.md](RELEASE.md) has the full ordered checklist; the shape of it:

1. Bump `versionCode`/`versionName` in [app/build.gradle.kts](app/build.gradle.kts).
2. `./gradlew bundleRelease` — the drift check runs first and fails the build on drift.
3. Upload the AAB in the Play Console.
4. Publish any listing changes, then run `python tools/check_store_listings.py` to confirm the
   live copy matches the repo again.

Listing copy is published through the Play Developer API with the same service account (open an
edit, `PUT` the listing per locale, commit the edit). There is no publisher script in the repo,
so that step is done by hand or by tooling outside this repository.
