#!/usr/bin/env python3
"""Offline, allowlisted support summary. Never run application code or upload."""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

REPORT_OUTPUT = "dist/support-report.json"
SCOPE = ("Local offline summary of saved development checks. Not CI, APK, "
         "device, accuracy, or release evidence.")
JVM_SUMMARY = "verification/build/jvm/summary.json"
JVM_METADATA_INPUTS = ("verification/java-tests.json", "verification/dependencies.json",
                       "scripts/test_java.py")
DOCTOR_OUTPUT = "dist/release-doctor.json"
WRAPPER_PROPERTIES = "plugin/gradle/wrapper/gradle-wrapper.properties"
DEPENDENCIES = "verification/dependencies.json"
INVENTORY = "verification/java-tests.json"
DOCTOR_CHECKS = ("configuration_format", "jdk_17", "android_sdk", "atak_sdk",
                 "signing_configuration")
STATUSES = ("passed", "failed", "running")
CLASS_STATUSES = ("passed", "failed", "running", "timed_out")
MAX_BYTES = 256 * 1024
MAX_COUNT = 100000


class Invalid(Exception):
    """Value-free validation failure; never carries input text."""


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Invalid()
        result[key] = value
    return result


def _reject_constant(_):
    raise Invalid()


def _read_bytes(root, relative):
    """Open an allowlisted relative path without following symlinks inside root."""
    parts = relative.split("/")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    descriptors = []
    try:
        current = os.open(root, flags | os.O_DIRECTORY)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(part, flags | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(current)
        handle = os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        descriptors.append(handle)
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise Invalid()
        chunks, total = [], 0
        while True:
            chunk = os.read(handle, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise Invalid()
            chunks.append(chunk)
        return b"".join(chunks)
    except FileNotFoundError:
        return None
    except OSError:
        raise Invalid() from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_json(root, relative):
    data = _read_bytes(root, relative)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates,
                          parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError):
        raise Invalid() from None


def _count(value):
    if type(value) is not int or not 0 <= value <= MAX_COUNT:
        raise Invalid()
    return value


def _status(value):
    if value not in STATUSES:
        raise Invalid()
    return value


def _jvm(root):
    try:
        data = _read_json(root, JVM_SUMMARY)
        if data is None:
            return {"status": "missing"}
        if not isinstance(data, dict) or not isinstance(data.get("test_classes"), list):
            raise Invalid()
        status, total = _status(data.get("status")), _count(data.get("tests_run"))
        class_statuses, class_total = [], 0
        for entry in data["test_classes"]:
            if not isinstance(entry, dict) or entry.get("status") not in CLASS_STATUSES:
                raise Invalid()
            class_statuses.append(entry["status"])
            class_total += _count(entry.get("tests_run"))
        if class_total != total:
            raise Invalid()
        if status == "passed" and (total == 0 or not class_statuses
                                   or any(s != "passed" for s in class_statuses)):
            raise Invalid()
        return {"status": status, "tests_run": total,
                "class_count": _count(len(class_statuses))}
    except Invalid:
        return {"status": "invalid"}


def _prerequisites(root):
    try:
        data = _read_json(root, DOCTOR_OUTPUT)
        if data is None:
            return {"status": "missing"}
        if (not isinstance(data, dict) or type(data.get("ready_for_build")) is not bool
                or not isinstance(data.get("checks"), list)):
            raise Invalid()
        checks = {}
        for check in data["checks"]:
            if not isinstance(check, dict):
                raise Invalid()
            name, status = check.get("id"), check.get("status")
            if name not in DOCTOR_CHECKS or name in checks or status not in ("ok", "blocked"):
                raise Invalid()
            checks[name] = status
        if set(checks) != set(DOCTOR_CHECKS):
            raise Invalid()
        ready = all(status == "ok" for status in checks.values())
        if ready != data["ready_for_build"]:
            raise Invalid()
        return {"status": "ok" if ready else "blocked",
                "checks": {name: checks[name] for name in DOCTOR_CHECKS}}
    except Invalid:
        return {"status": "invalid"}


WRAPPER_URL_KEY = "distributionUrl"
_PROPERTIES_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_PROPERTIES_ENTRY = re.compile(r"([A-Za-z0-9_.-]+)=([\x20-\x7e]*)", re.ASCII)
_PROPERTIES_COMMENT = re.compile(r"[#!][\t\x20-\x7e]*", re.ASCII)
_WRAPPER_URL = re.compile(r"https\\://services\.gradle\.org/distributions/"
                          r"gradle-(\d{1,3}(?:\.\d{1,3}){1,2})-(?:bin|all)\.zip", re.ASCII)


def _gradle_wrapper(root):
    """Return the Gradle version only when java.util.Properties cannot disagree.

    Accept a strict subset of the properties format: lines split on CR, LF, or
    CRLF only; each line is empty, a column-0 comment, or ``key=value`` with a
    plain column-0 key. Any leading whitespace, escaped or continued line,
    ``:``/whitespace separator, control character, or extra mention of
    ``distributionUrl`` makes the file ambiguous and therefore invalid.
    """
    data = _read_bytes(root, WRAPPER_PROPERTIES)
    if data is None:
        return None
    try:
        text = data.decode("ascii")
    except UnicodeError:
        raise Invalid() from None
    urls = []
    for line in _PROPERTIES_LINE_BREAK.split(text):
        if line.endswith("\\"):
            raise Invalid()
        expected_mentions = 0
        if line and not _PROPERTIES_COMMENT.fullmatch(line):
            entry = _PROPERTIES_ENTRY.fullmatch(line)
            if not entry:
                raise Invalid()
            if entry.group(1) == WRAPPER_URL_KEY:
                urls.append(entry.group(2))
                expected_mentions = 1
        if line.count(WRAPPER_URL_KEY) != expected_mentions:
            raise Invalid()
    if len(urls) != 1:
        raise Invalid()
    match = _WRAPPER_URL.fullmatch(urls[0])
    if not match:
        raise Invalid()
    return match.group(1)


def _jvm_dependencies(root):
    data = _read_json(root, DEPENDENCIES)
    if data is None:
        return None
    if not isinstance(data, list) or not 0 < len(data) <= 50:
        raise Invalid()
    result = {}
    for entry in data:
        if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
            raise Invalid()
        match = re.fullmatch(r"https://repo\.maven\.apache\.org/maven2/((?:[a-z0-9_-]{1,64}/){1,8})"
                             r"([a-z0-9_-]{1,64})/(\d[A-Za-z0-9_.-]{0,63})/\2-\3\.jar", entry["url"], re.ASCII)
        if not match or ".." in match.group(3):
            raise Invalid()
        name = match.group(1).rstrip("/").replace("/", ".") + ":" + match.group(2)
        if name in result:
            raise Invalid()
        result[name] = match.group(3)
    return result


def _java_inventory(root):
    data = _read_json(root, INVENTORY)
    if data is None:
        return None
    if not isinstance(data, dict):
        raise Invalid()
    shapes = {"included_sources": list, "included_tests": list, "excluded_tests": dict}
    if any(not isinstance(data.get(key), kind) for key, kind in shapes.items()):
        raise Invalid()
    return {key: _count(len(data[key])) for key in shapes}


def _tool_metadata(root):
    try:
        values = {"gradle_wrapper": _gradle_wrapper(root),
                  "jvm_dependencies": _jvm_dependencies(root),
                  "java_inventory": _java_inventory(root)}
    except Invalid:
        return {"status": "invalid"}
    if any(value is None for value in values.values()):
        return {"status": "missing"}
    return dict(status="ok", **values)


def collect(root):
    """Return only allowlisted statuses and counts; never raw strings."""
    return {
        "schema_version": 1,
        "scope": SCOPE,
        "verification": {"jvm": _jvm(root),
                         "prerequisites": _prerequisites(root)},
        "tool_metadata": _tool_metadata(root),
    }


def write_report(root, report):
    """Atomically write dist/support-report.json (0600) without following symlinks."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    data = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("ascii")
    temporary = ".support-report-{}.tmp".format(os.getpid())
    root_fd = os.open(root, flags | os.O_DIRECTORY)
    try:
        try:
            os.mkdir("dist", 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        dist_fd = os.open("dist", flags | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                             | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=dist_fd)
            try:
                try:
                    os.fchmod(handle, 0o600)
                    view = memoryview(data)
                    while view:
                        view = view[os.write(handle, view):]
                    os.fsync(handle)
                finally:
                    os.close(handle)
                os.replace(temporary, REPORT_OUTPUT.split("/")[-1],
                           src_dir_fd=dist_fd, dst_dir_fd=dist_fd)
            except BaseException:
                # Any failure after creation (fchmod/write/fsync/close/replace)
                # removes the temporary file so no partial report is left behind.
                try:
                    os.unlink(temporary, dir_fd=dist_fd)
                except OSError:
                    pass
                raise
        finally:
            os.close(dist_fd)
    finally:
        os.close(root_fd)


def jvm_metadata_matches(root):
    """Compare only three fixed manifest/runner byte digests, not execution."""
    try:
        saved = _read_json(root, JVM_SUMMARY)
        if not isinstance(saved, dict) or not isinstance(saved.get("inputs_sha256"), dict):
            return False
        hashes = saved["inputs_sha256"]
        for relative in JVM_METADATA_INPUTS:
            data = _read_bytes(root, relative)
            if data is None or hashlib.sha256(data).hexdigest() != hashes.get(relative):
                return False
        return True
    except Invalid:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository root (default: this checkout)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true",
                       help="compare saved snapshot with current allowlisted values without writing; "
                            "does not rerun underlying checks")
    modes.add_argument("--check-jvm-metadata", action="store_true",
                       help="compare saved JVM manifest/runner hashes only; no test execution")
    args = parser.parse_args(argv)
    if args.check_jvm_metadata:
        if not jvm_metadata_matches(args.root):
            print("Saved JVM manifest/runner linkage is missing, unsafe, invalid or differs; "
                  "nothing was written.", file=sys.stderr)
            return 1
        print("Saved JVM manifest/runner hashes match current bytes; "
              "test execution and source/assets were not verified.")
        return 0
    if args.check:
        try:
            saved = _read_json(args.root, REPORT_OUTPUT)
            # Canonical JSON preserves type distinctions such as true/1 and 1.0/1;
            # ordinary Python object equality would accept those schema aliases.
            matches = (json.dumps(saved, sort_keys=True, separators=(",", ":")) ==
                       json.dumps(collect(args.root), sort_keys=True, separators=(",", ":")))
        except Invalid:
            matches = False
        if not matches:
            print("Saved support snapshot is missing, unsafe, invalid or differs from current "
                  "allowlisted values; nothing was written.", file=sys.stderr)
            return 1
        print("Saved support snapshot matches current allowlisted values; "
              "underlying checks were not rerun.")
        return 0
    try:
        write_report(args.root, collect(args.root))
    except (OSError, ValueError):
        print("Could not write " + REPORT_OUTPUT + " safely; no report was written.", file=sys.stderr)
        return 2
    print("Wrote " + REPORT_OUTPUT + " (review before sharing; nothing was uploaded).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
