#!/usr/bin/env python3
"""Offline build-prerequisite check. Does not run or validate the application."""
import argparse
import json
import os
import re
import shutil
import subprocess
import zipfile
import zlib
from pathlib import Path


def read_properties(path):
    """Read a fail-closed ASCII/POSIX subset of Java properties.

    Do not log this mapping: it can contain signing/repository credentials.
    Unsupported syntax or unreadable inputs raise only a value-free error.
    """
    error = "Unsupported or unreadable local configuration."
    try:
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError(error)
        text = path.read_text(encoding="ascii")
    except (OSError, UnicodeError):
        raise ValueError(error) from None
    if any((ord(char) < 32 and char not in "\t\n\r\f") or ord(char) == 127 for char in text):
        raise ValueError(error)
    props = {}
    # read_text normalizes CR/CRLF. Form feeds are whitespace, not line breaks.
    for line in text.split("\n"):
        line = line.lstrip(" \t\f")
        if not line or line.startswith(("#", "!")):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)[ \t\f]*=(.*)", line)
        if not match or "\\" in line:
            raise ValueError(error)
        # Java drops leading separator whitespace but keeps ALL trailing value whitespace.
        props[match.group(1)] = match.group(2).lstrip(" \t\f")
    return props


def sdk_archives_present(props):
    sdk = Path(props.get("sdk.path", ""))
    plugin = Path(props.get("takdev.plugin", ""))
    if not sdk.is_absolute() or not plugin.is_absolute():
        return False
    try:
        if not (sdk / "main.jar").is_file() or not plugin.is_file():
            return False
        with zipfile.ZipFile(sdk / "main.jar") as archive:
            if archive.getinfo("com/atakmap/android/maps/MapView.class").file_size == 0:
                return False
        with zipfile.ZipFile(plugin) as archive:
            info = archive.getinfo("META-INF/gradle-plugins/atak-takdev-plugin.properties")
            if info.file_size > 4096 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                return False
            descriptor = archive.read(info).decode("ascii").replace("\r\n", "\n").replace("\r", "\n")
            if any((ord(char) < 32 and char not in "\t\n\f") or ord(char) == 127 for char in descriptor):
                return False
            implementations = []
            for line in descriptor.split("\n"):
                line = line.lstrip(" \t\f")
                if not line or line.startswith(("#", "!")):
                    continue
                assignment = re.fullmatch(r"([A-Za-z0-9_.-]+)[ \t\f]*=(.*)", line)
                if not assignment or "\\" in line:
                    return False
                if assignment.group(1) == "implementation-class":
                    implementations.append(assignment.group(2).lstrip(" \t\f"))
            # Unlike local configuration, duplicate implementation keys are always blocked.
            if len(implementations) != 1:
                return False
            match = re.fullmatch(r"([\w.$]+)[ \t]*", implementations[0])
            if not match:
                return False
            return archive.getinfo(match.group(1).replace(".", "/") + ".class").file_size > 0
    except (OSError, KeyError, ValueError, UnicodeError, zipfile.BadZipFile,
            RuntimeError, EOFError, zlib.error):
        return False


def signing_configuration_present(props):
    # Both configs are evaluated eagerly by the current Android build file.
    # Never unlock/inspect keystores or print credentials here.
    for kind in ("Debug", "Release"):
        fields = [props.get("tak" + kind + suffix, "")
                  for suffix in ("KeyFile", "KeyFilePassword", "KeyAlias", "KeyPassword")]
        if any(not value or re.fullmatch(r"<[^<>\r\n]+>", value) for value in fields):
            return False
        key = Path(fields[0])
        try:
            if not key.is_absolute() or not key.is_file() or key.stat().st_size == 0:
                return False
        except OSError:
            return False
    return True


def inspect(root, environment=None, java_version=None):
    env = os.environ if environment is None else environment
    try:
        props = read_properties(Path(root) / "plugin/local.properties")
        configuration_ok = True
    except ValueError:
        props = {}
        configuration_ok = False
    sdk = props.get("sdk.dir") or env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT")
    try:
        sdk_root = Path(sdk) if sdk else None
        sdk_ok = bool(sdk_root and sdk_root.is_absolute()
                      and (sdk_root / "platforms/android-34/android.jar").is_file()
                      and all((sdk_root / "build-tools/34.0.0" / tool).is_file()
                              for tool in ("aapt2", "apksigner", "zipalign")))
    except (OSError, ValueError):
        sdk_ok = False
    checks = [{"id": "configuration_format", "status": "ok" if configuration_ok else "blocked",
               "message": "Use a readable regular local.properties file (at most 1 MiB): ASCII key=value, no escapes or continuations. See scripts/README.md for the supported POSIX subset."},
              {"id": "jdk_17", "status": "ok" if java_version == 17 else "blocked",
               "message": "Use JDK 17 for the checked-in Android/Gradle toolchain."},
              {"id": "android_sdk", "status": "ok" if sdk_ok else "blocked",
               "message": "Install Android platform 34 and build-tools 34.0.0; set an absolute ANDROID_HOME, ANDROID_SDK_ROOT, or sdk.dir path."},
              {"id": "atak_sdk", "status": "ok" if sdk_archives_present(props) else "blocked",
               "message": "Configure absolute sdk.path and takdev.plugin with SDK archives of the expected structure; repository-based SDK setup requires separate verification."},
              {"id": "signing_configuration", "status": "ok" if signing_configuration_present(props) else "blocked",
               "message": "Configure both debug and release signing fields with absolute keystore paths locally. Host certificate compatibility must be verified separately."}]
    return {"ready_for_build": all(c["status"] == "ok" for c in checks), "checks": checks,
            "scope": "Prerequisites only; not evidence of APK build, host compatibility, or product readiness."}


def detect_java_major(environment=None, run=subprocess.run):
    env = os.environ if environment is None else environment
    java = str(Path(env["JAVA_HOME"]) / "bin/java") if env.get("JAVA_HOME") else shutil.which("java", path=env.get("PATH", ""))
    if not java:
        return None
    try:
        result = run([java, "-version"], capture_output=True, text=True, errors="replace",
                     timeout=10, env=dict(env))
        if result.returncode:
            return None
        match = re.search(r'(?:openjdk|java) version "(\d+)(?:\.(\d+))?', result.stdout + result.stderr)
        if not match:
            return None
        return int(match.group(2)) if match.group(1) == "1" and match.group(2) else int(match.group(1))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = inspect(args.root, java_version=detect_java_major())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for check in report["checks"]:
            print("{status}: {id}: {message}".format(**check))
        print(report["scope"])
    return 0 if report["ready_for_build"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
