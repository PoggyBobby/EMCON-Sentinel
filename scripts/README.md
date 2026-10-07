# Release prerequisite checker

> **Offline structural diagnostics only.** The descriptor parsing fixes passed independent review, and all 34 regression tests pass on Python 3.14. This is still not a build, signature, SDK-authenticity, host-compatibility, or production-release gate.

From the repository root (Python 3.9+; standard library only):

```sh
python3 -m unittest discover -s tests -v
python3 scripts/release_doctor.py
python3 scripts/release_doctor.py --json
```

Exit 0 means the **offline structural prerequisite checks** passed. Exit 1 means at least one prerequisite is blocked. This is not an APK builder, certificate verifier, SDK authenticity check, Android integration test, or production-readiness certificate.

Checks cover JDK 17, Android platform 34/build-tools 34.0.0 file presence, a local ATAK SDK JAR/Gradle plugin descriptor, and both signing configurations required by the existing build. The checker reads `plugin/local.properties` without printing its paths, passwords, or aliases. Copy `plugin/template.local.properties` and fill values locally; never send private signing material in chat or commit it.

Supported configuration is deliberately a **POSIX/ASCII subset**, not a complete Java-properties parser. `configuration_format` is blocked if `plugin/local.properties` is missing, unreadable, not a regular file, over 1 MiB, non-ASCII, or uses unsupported syntax. No partial properties are trusted after a format error, and diagnostics never include property contents.

- Use one `key=value` assignment per line, with keys matching `[A-Za-z0-9_.-]+`. Spaces, tabs, and form feeds may precede a key, surround `=`, or start a value; this leading whitespace is ignored as in Java properties. **Trailing value whitespace is preserved** (including on paths and passwords). Duplicate keys use the last value. Empty values are allowed by the parser, but required fields must be populated.
- Blank lines and lines whose first non-whitespace character is `#` or `!` are comments. LF, CRLF, and CR line endings are supported. Within values, `=`, `:`, `#`, `!`, and quotes are literal characters; quoting does not remove quotes. Other control characters except tab/form feed and line endings are unsupported.
- Backslash escapes (including `\uXXXX`), continuation lines, `:`/whitespace assignment separators, non-ASCII text, and Windows escaped paths are **rejected**, not silently interpreted. A valid Java-properties file outside this subset must be verified separately; a blocked format does not imply Gradle would reject it.
- All configured paths must be absolute POSIX paths using forward slashes, including `sdk.dir`, `sdk.path`, `takdev.plugin`, and both keystores. Relative Android SDK paths are rejected, not resolved against the working directory or `--root`. `sdk.dir` takes precedence over `ANDROID_HOME`, then `ANDROID_SDK_ROOT`; environment SDK paths must also be absolute. A selected nonempty invalid path does not fall back to another source.
- A signing value consisting entirely of a `<placeholder>` token is rejected. Angle characters inside other values are permitted. Keystore checks cover only regular-file presence and nonzero size; passwords and aliases are not authenticated.

The launcher probe checks `JAVA_HOME/bin/java`, otherwise `java` on `PATH`, not Gradle daemon overrides such as `org.gradle.java.home`. Failed probes or version numbers that exceed Python's integer-conversion digit limit report blocked. Android tool checks use POSIX names (`aapt2`, `apksigner`, `zipalign`) and only file presence, not executable permissions or tool functionality; inaccessible or invalid SDK paths report blocked without printing paths. SDK JAR checks inspect class-entry metadata and read a small Gradle descriptor; they are not a full archive integrity or class-validity check. Malformed, encrypted, unsupported-compression, or corrupt descriptor reads report blocked instead of raising a traceback. Non-regular configuration/archive inputs are rejected before opening to avoid ordinary FIFO hangs. Authenticated `takrepo.*` builds need separate validation; they are not falsely marked ready by this local-SDK checker.

The Gradle plugin descriptor has its own enforced **structural ASCII subset**:

- Its uncompressed entry must be at most 4096 bytes and use **ZIP_STORED or ZIP_DEFLATED**; other methods (including LZMA and BZIP2) are blocked before decompression.
- LF, CRLF, and CR are normalized before parsing every physical line, including mixed endings. Blank lines and `#`/`!` comments after leading space/tab/form feed are accepted. Every other line must be a `key=value` assignment with a key matching `[A-Za-z0-9_.-]+`; `:`/whitespace separators and malformed unrelated assignments are rejected, not ignored.
- Backslashes in assignments are rejected, including escaped keys (`implementation\-class`, `\u0069mplementation-class`), escaped values, and continuation lines. Non-ASCII bytes anywhere in the descriptor are rejected, including non-ASCII class names. ASCII controls other than tab/form feed and supported line endings are rejected even in comments; DEL is also rejected.
- Exactly one `implementation-class` assignment is required. Duplicates are blocked even if their values are identical, empty, invalid, or point at a missing class. The value must match `[A-Za-z0-9_.$]+` after ignoring leading separator space/tab/form feed and tolerating trailing spaces/tabs for structural lookup. Its dot-to-slash `.class` entry must have nonzero size. Other assignment values may contain literal punctuation and whitespace but cannot use escapes.

This subset is not a complete Java-properties parser or proof that Gradle can load the plugin. Matching archive entries are structural evidence only; no SDK authenticity or host compatibility is certified.

Even when structural checks pass, you must actually build, verify SDK provenance and artifact signatures, test installation and plugin loading against the exact ATAK host, and finish the release checklist in `docs/release-readiness.md`. The test suite uses isolated temporary roots, never the developer's `plugin/local.properties`, and explicitly labeled structural fixtures—not substitutes for a working SDK or signer.
