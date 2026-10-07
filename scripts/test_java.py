#!/usr/bin/env python3
"""Run explicitly inventoried existing JVM tests without Android/ATAK stubs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request


def download_verified(url, destination, expected):
    """Verify Maven Central's published SHA-1, including cached artifacts."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        data = destination.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    if hashlib.sha1(data).hexdigest() != expected:
        raise ValueError("checksum mismatch: " + destination.name)
    if not destination.exists():
        destination.write_bytes(data)
    return destination


def inventory(root):
    manifest = json.loads((root / "verification/java-tests.json").read_text())
    included = manifest["included_tests"]
    excluded = manifest["excluded_tests"]
    actual = {str(p.relative_to(root / "plugin/app/src/test/java"))
              for p in (root / "plugin/app/src/test/java").rglob("*.java")}
    accounted = set(included) | set(excluded)
    if actual != accounted:
        raise ValueError("unaccounted or missing tests: " + ", ".join(sorted(actual ^ accounted)))
    if len(included) != len(set(included)) or set(included) & set(excluded):
        raise ValueError("duplicate or overlapping test inventory")
    if any(not reason.strip() for reason in excluded.values()):
        raise ValueError("excluded tests require reasons")
    if not included:
        raise ValueError("no included tests: empty JVM verification is not success")
    return included, excluded


def write_report(report_dir, run_dir, report):
    """Keep a run snapshot and atomically replace the canonical latest summary."""
    data = json.dumps(report, indent=2) + "\n"
    (run_dir / "summary.json").write_text(data)
    pending = run_dir / ".latest-summary.json"
    pending.write_text(data)
    pending.replace(report_dir / "summary.json")


def run_suite(root, java_home, cache, report_dir):
    """Compile fresh sources; run actual JUnitCore from plugin/app for asset paths."""
    report_dir = report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=report_dir))
    report = {
        "run_dir": run_dir.name, "status": "running", "tests_run": 0,
        "test_classes": [], "commands": [],
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "coverage": "SDK-independent JVM subset; NOT Android/ATAK build or device validation",
    }
    try:
        write_report(report_dir, run_dir, report)
        if java_home is None:
            raise ValueError("JAVA_HOME or --java-home must point to JDK 17; no SDK stubs or skipped tests")
        return _execute_suite(root.resolve(), java_home.resolve(), cache.resolve(),
                              report_dir, run_dir, report)
    except BaseException as error:
        # Also finalize interruptions before safely rethrowing to direct callers.
        report["status"] = "failed"
        report["error"] = str(error) or type(error).__name__
        raise
    finally:
        if report["status"] == "running":
            report["status"] = "failed"
        report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_report(report_dir, run_dir, report)


def run_logged(command, log, **kwargs):
    """Persist actual child output even when the process times out or is interrupted."""
    with log.open("w") as output:
        return subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                              text=True, **kwargs)


def _execute_suite(root, java_home, cache, report_dir, run_dir, report):
    included, excluded = inventory(root)
    report.update(included_tests=included, excluded_tests=excluded)
    manifest = json.loads((root / "verification/java-tests.json").read_text())
    sources = [root / "plugin/app/src/main/java" / p
               for p in manifest["included_sources"]]
    tests = [root / "plugin/app/src/test/java" / p for p in included]
    dependencies = json.loads((root / "verification/dependencies.json").read_text())
    jars = [download_verified(d["url"], cache / d["url"].rsplit("/", 1)[1], d["sha1"])
            for d in dependencies]
    inputs = sources + tests + sorted((root / "plugin/app/src/main/assets").rglob("*.json"))
    inputs += [root / "verification/java-tests.json", root / "verification/dependencies.json"]
    if (root / "scripts/test_java.py").is_file():
        inputs.append(root / "scripts/test_java.py")
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in inputs}
    report.update({
        "included_sources": manifest["included_sources"],
        "excluded_sources": sorted(str(p.relative_to(root / "plugin/app/src/main/java"))
                                   for p in (root / "plugin/app/src/main/java").rglob("*.java")
                                   if p not in sources),
        "excluded_sources_reason": "Outside explicitly selected JVM source set; integration, UI, sensors and SDK-dependent code are not compiled",
        "inputs_sha256": hashes,
        "dependencies": [dict(d, sha256=hashlib.sha256(j.read_bytes()).hexdigest())
                         for d, j in zip(dependencies, jars)],
    })
    environment = dict(os.environ)
    for name in ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH"):
        environment.pop(name, None)
    for tool in ("java", "javac"):
        version = subprocess.run([str(java_home / "bin" / tool), "-version"],
                                 env=environment, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, timeout=30, check=True).stdout
        pattern = r'"17(?:\.|")' if tool == "java" else r"^javac 17(?:\.|\s|$)"
        if not re.search(pattern, version):
            raise ValueError("JDK 17 required for " + tool)
        report[tool + "_version"] = version.strip()
    with tempfile.TemporaryDirectory(prefix="classes-", dir=run_dir) as folder:
        classpath = os.pathsep.join(str(p) for p in jars)
        compile_command = [str(java_home / "bin/javac"), "--release", "17", "-encoding", "UTF-8",
                           "-cp", classpath, "-d", folder] + [str(p) for p in sources + tests]
        report["commands"].append(compile_command)
        report["compile_log"] = str((run_dir / "compile.log").relative_to(report_dir))
        report.update(compile_status="running", compile_exit_code=None)
        try:
            compiled = run_logged(compile_command, report_dir / report["compile_log"],
                                  cwd=root / "plugin/app", env=environment, timeout=120)
        except BaseException as error:
            report["compile_status"] = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
            raise
        report["compile_exit_code"] = compiled.returncode
        report["compile_status"] = "passed" if compiled.returncode == 0 else "failed"
        if compiled.returncode != 0:
            report["status"] = "failed"
            print("Compilation failed; see " + str(report_dir / report["compile_log"]), file=sys.stderr)
            return 1
        for name in included:
            class_name = name[:-5].replace("/", ".")
            command = [str(java_home / "bin/java"), "-cp", folder + os.pathsep + classpath,
                       "org.junit.runner.JUnitCore", class_name]
            report["commands"].append(command)
            log = str((run_dir / (class_name + ".log")).relative_to(report_dir))
            entry = {"class": class_name, "tests_run": 0, "exit_code": None,
                     "status": "running", "log": log}
            report["test_classes"].append(entry)
            try:
                result = run_logged(command, report_dir / log, cwd=root / "plugin/app",
                                    env=environment, timeout=120)
            except BaseException as error:
                entry["status"] = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
                raise
            output = (report_dir / log).read_text()
            match = re.search(r"^OK \((\d+) tests?\)$", output, re.MULTILINE)
            failure = re.search(r"^Tests run: (\d+),\s+Failures: (\d+)", output, re.MULTILINE)
            count = int(match.group(1)) if match else int(failure.group(1)) if failure else 0
            entry.update(tests_run=count, exit_code=result.returncode, status="passed")
            if result.returncode != 0 or not match or count == 0:
                report["status"] = "failed"
                entry["status"] = "failed"
            report["tests_run"] += count
            print(class_name + ": " + output.strip(), flush=True)
    if report["status"] != "failed":
        report["status"] = "passed"
    print("JVM subset: {} tests in {} classes; excluded tests: {}. NOT Android/ATAK validation."
          .format(report["tests_run"], len(included), len(excluded)), flush=True)
    return 0 if report["status"] == "passed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list included/excluded tests without running")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--java-home", type=Path, default=os.environ.get("JAVA_HOME"))
    parser.add_argument("--cache-dir", type=Path, default=os.environ.get("JAVA_TEST_CACHE", str(Path.home() / ".hermes/cache/scratch/emcon-java-tests/dependencies")))
    parser.add_argument("--report-dir", type=Path, default=os.environ.get("JAVA_TEST_REPORT_DIR"))
    args = parser.parse_args(argv)
    report_dir = args.report_dir or args.repo / "verification/build/jvm"
    try:
        if args.list:
            included, excluded = inventory(args.repo)
            print(json.dumps({"included_tests": included, "excluded_tests": excluded,
                              "coverage": "JVM subset, not full Android/ATAK validation"}, indent=2))
            return 0
        return run_suite(args.repo, args.java_home, args.cache_dir, report_dir)
    except Exception as error:
        # run_suite already persisted this run's failure and any partial results.
        if args.list:
            report_dir.mkdir(parents=True, exist_ok=True)
            run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=report_dir))
            write_report(report_dir, run_dir, {
                "run_dir": run_dir.name, "status": "failed", "error": str(error),
                "operation": "list", "tests_run": 0, "test_classes": [],
                "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "coverage": "JVM subset, not full Android/ATAK validation",
            })
        print("JVM verification failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
