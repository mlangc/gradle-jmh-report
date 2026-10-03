"""Black-box check: runs the built plugin jar under several Gradle versions and compares the report
output with the golden snapshot in golden/. See CLAUDE.md in this folder."""

from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CONSUMER = HERE / "consumer"
INPUT_JSON = HERE / "data" / "results.json"
GOLDEN = HERE / "golden"
GOLDEN_FILES = GOLDEN / "visualizer-files.json"
GOLDEN_PROVIDED = GOLDEN / "provided.json"
LOGS = HERE / "build" / "logs"
VERSIONS_FILE = HERE / "gradle-versions.toml"
EVALUATE_SCRIPT = HERE / "evaluate_provided.mjs"

GOLDEN_RUN_NAME = "results"
REPORT_DIR = Path("build/reports/jmh")
CONSOLE_LINE = re.compile(r"^JMH Report generated, please open: file://(.+)/index\.html$", re.M)
MISSING_INPUT_LINE = re.compile(r"Input '(.+?)' does not exists!")
GRADLE_TIMEOUT_SECONDS = 900


class CheckError(Exception):
    """The check itself is broken (as opposed to the plugin misbehaving)."""


@dataclass(frozen=True)
class GradleVersion:
    name: str
    version: str
    mise_java: str
    known_failure: str | None
    distribution: str

    @property
    def major(self) -> int:
        return int(self.version.split(".")[0])


@dataclass(frozen=True)
class Scenario:
    id: str
    project: str
    input_name: str | None  # None: no input is provided
    min_major: int = 0

    @property
    def run_name(self) -> str:
        assert self.input_name is not None
        return self.input_name.removesuffix(".json")


SCENARIOS = [
    Scenario("S1", "s1", "results.json"),
    Scenario("S2", "s2", "results.json"),
    Scenario("S3", "s3", "my-run.json"),
    Scenario("S5", "s5", None),
    Scenario("S7", "s7", "results.json", min_major=5),  # Kotlin DSL
    Scenario("S8", "s8", "results.json"),  # run twice, see run_version
]


@dataclass
class Outcome:
    status: str  # "pass" | "fail" | "skipped"
    problems: list[str] = field(default_factory=list)


@dataclass
class VersionResult:
    gradle: GradleVersion
    outcomes: dict[str, Outcome] = field(default_factory=dict)
    deprecations: list[str] = field(default_factory=list)
    configuration_cache: str | None = None
    error: str | None = None
    log: str = ""

    @property
    def failed(self) -> bool:
        return self.error is not None or any(o.status == "fail" for o in self.outcomes.values())


# --------------------------------------------------------------------------------------------------
# Registry and tooling


def load_versions() -> list[GradleVersion]:
    with VERSIONS_FILE.open("rb") as f:
        entries = tomllib.load(f).get("gradle", [])
    versions = [
        GradleVersion(
            name=e["name"],
            version=e["version"],
            mise_java=e["mise-java"],
            known_failure=e.get("known-failure"),
            distribution=e.get("distribution", "bin"),
        )
        for e in entries
    ]
    names = [v.name for v in versions]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise CheckError(f"Duplicate names in {VERSIONS_FILE.name}: {', '.join(duplicates)}")
    return versions


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", **kwargs)


def resolve_java_home(spec: str) -> Path:
    install = run(["mise", "install", f"java@{spec}"])
    if install.returncode != 0:
        raise CheckError(f"mise install java@{spec} failed:\n{install.stderr}")
    where = run(["mise", "where", f"java@{spec}"])
    path = where.stdout.strip()
    if where.returncode != 0 or not path:
        raise CheckError(f"mise where java@{spec} failed:\n{where.stderr}")
    home = Path(path)
    for candidate in (home, home / "Contents" / "Home"):
        if (candidate / "bin" / "java").exists():
            return candidate
    raise CheckError(f"No bin/java below {home} (java@{spec})")


def resolve_node() -> str:
    which = run(["mise", "which", "node"], cwd=HERE)
    path = which.stdout.strip()
    if which.returncode != 0 or not path:
        raise CheckError(f"mise which node failed (run `mise install`):\n{which.stderr}")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def real(path: str | Path) -> str:
    return os.path.realpath(path)


# --------------------------------------------------------------------------------------------------
# Gradle runs


def prepare_consumer(workdir: Path, jar: Path, gradle: GradleVersion) -> Path:
    consumer = workdir / "consumer"
    shutil.copytree(CONSUMER, consumer, ignore=shutil.ignore_patterns("libs", "build", ".gradle"))
    libs = consumer / "libs"
    libs.mkdir()
    shutil.copy(jar, libs / "gradle-jmh-report.jar")

    shutil.copy(REPO / "gradlew", consumer / "gradlew")
    wrapper = consumer / "gradle" / "wrapper"
    wrapper.mkdir(parents=True)
    shutil.copy(REPO / "gradle" / "wrapper" / "gradle-wrapper.jar", wrapper)
    url = (
        f"https://services.gradle.org/distributions/"
        f"gradle-{gradle.version}-{gradle.distribution}.zip"
    )
    (wrapper / "gradle-wrapper.properties").write_text(
        "distributionBase=GRADLE_USER_HOME\n"
        "distributionPath=wrapper/dists\n"
        "zipStoreBase=GRADLE_USER_HOME\n"
        "zipStorePath=wrapper/dists\n"
        f"distributionUrl={url.replace(':', '\\:')}\n"
    )

    if gradle.major < SCENARIOS_BY_ID["S7"].min_major:
        shutil.rmtree(consumer / "s7")
    return consumer


def place_input(consumer: Path, scenario: Scenario, content: bytes) -> Path:
    assert scenario.input_name is not None
    target = consumer / scenario.project / REPORT_DIR / scenario.input_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def run_gradle(
    consumer: Path, java_home: Path, gradle: GradleVersion, extra: list[str], log: Path
) -> str:
    cmd = ["./gradlew", "--no-daemon", "--console=plain", "--stacktrace", "--continue"]
    if gradle.major >= 7:
        cmd += ["--warning-mode", "all"]
    cmd += extra
    env = dict(os.environ)
    env["JAVA_HOME"] = str(java_home)
    env["PATH"] = f"{java_home / 'bin'}{os.pathsep}{env['PATH']}"
    print(f"  $ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(
        cmd,
        cwd=consumer,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GRADLE_TIMEOUT_SECONDS,
    )
    text = f"$ {' '.join(cmd)}\n(exit code {proc.returncode})\n{proc.stdout}\n{proc.stderr}"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    # Success and failure of the scenarios is decided from files and log lines, not exit codes.
    return proc.stdout + "\n" + proc.stderr


# --------------------------------------------------------------------------------------------------
# Comparison


def dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def diff(expected: Any, actual: Any, what: str) -> str:
    lines = difflib.unified_diff(
        dump(expected).splitlines(keepends=True),
        dump(actual).splitlines(keepends=True),
        fromfile=f"golden {what}",
        tofile=f"actual {what}",
    )
    return "".join(lines)


def evaluate_provided(node: str, provided_js: Path) -> Any:
    proc = run([node, str(EVALUATE_SCRIPT), str(provided_js)])
    if proc.returncode != 0:
        raise ValueError(proc.stderr.strip() or f"node exited with {proc.returncode}")
    return json.loads(proc.stdout)


def with_run_name(provided: dict[str, Any], run_name: str) -> dict[str, Any]:
    (old_name,) = provided["providedBenchmarkStore"]
    return {
        "providedBenchmarks": [run_name],
        "providedBenchmarkStore": {run_name: provided["providedBenchmarkStore"][old_name]},
    }


# The edit S8 applies to its input between the two runs.
EDITED_SCORE = 123456.789


def edit_benchmarks(benchmarks: list[Any]) -> None:
    benchmarks[0]["primaryMetric"]["score"] = EDITED_SCORE


def edited_input() -> bytes:
    benchmarks = json.loads(INPUT_JSON.read_text(encoding="utf-8"))
    edit_benchmarks(benchmarks)
    return json.dumps(benchmarks, indent=2, ensure_ascii=False).encode("utf-8")


def edited_provided(provided: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(provided)
    for benchmarks in result["providedBenchmarkStore"].values():
        edit_benchmarks(benchmarks)
    return result


def hash_output(out_dir: Path, exclude: set[str]) -> dict[str, str]:
    return {
        p.relative_to(out_dir).as_posix(): sha256(p)
        for p in sorted(out_dir.rglob("*"))
        if p.is_file()
        and p.relative_to(out_dir).as_posix() not in exclude
        and p.name != "provided.js"
    }


def check_report(
    node: str,
    out_dir: Path,
    input_name: str,
    expected_input: bytes,
    expected_provided: dict[str, Any],
    golden_files: dict[str, str],
    log: str | None,
) -> list[str]:
    """Checks one generated report folder. `log` is None when the console line isn't checked."""
    problems: list[str] = []
    if not out_dir.is_dir():
        return [f"output folder {out_dir} doesn't exist"]

    actual_files = hash_output(out_dir, exclude={input_name})
    for name in sorted(golden_files.keys() - actual_files.keys()):
        problems.append(f"missing file: {name}")
    for name in sorted(actual_files.keys() - golden_files.keys()):
        problems.append(f"unexpected file: {name}")
    for name in sorted(golden_files.keys() & actual_files.keys()):
        if golden_files[name] != actual_files[name]:
            problems.append(f"content differs: {name}")

    input_file = out_dir / input_name
    if not input_file.is_file() or input_file.read_bytes() != expected_input:
        problems.append(f"input {input_name} was modified or removed")

    provided_js = out_dir / "provided.js"
    if not provided_js.is_file():
        problems.append("missing file: provided.js")
    else:
        try:
            actual = evaluate_provided(node, provided_js)
        except ValueError as e:
            problems.append(f"provided.js: {e}")
        else:
            if actual != expected_provided:
                problems.append(
                    "provided.js globals differ:\n" + diff(expected_provided, actual, "provided.js")
                )

    if log is not None:
        reported = {real(m) for m in CONSOLE_LINE.findall(log)}
        if real(out_dir) not in reported:
            problems.append(
                f"console line 'JMH Report generated, please open: file://{out_dir}/index.html'"
                " not found"
            )
    return problems


# --------------------------------------------------------------------------------------------------
# One Gradle version


def run_version(
    gradle: GradleVersion,
    jar: Path,
    node: str,
    golden: tuple[dict[str, str], dict[str, Any]] | None,
    keep: list[Path],
) -> tuple[VersionResult, Path]:
    """Runs all scenarios. Returns the result and the consumer dir (still existing).

    With golden=None (recording), no comparison is done."""
    result = VersionResult(gradle)
    java_home = resolve_java_home(gradle.mise_java)
    java_version = run([str(java_home / "bin" / "java"), "-version"]).stderr.splitlines()[0]
    print(f"== Gradle {gradle.name} ({gradle.version}) on {java_version}", flush=True)

    workdir = Path(tempfile.mkdtemp(prefix=f"jmhreport-blackbox-{gradle.name}-"))
    keep.append(workdir)
    consumer = prepare_consumer(workdir, jar, gradle)
    log_file = LOGS / f"gradle-{gradle.name}.log"
    log_file.unlink(missing_ok=True)

    original = INPUT_JSON.read_bytes()
    active = [s for s in SCENARIOS if gradle.major >= s.min_major]
    for s in active:
        if s.input_name is not None:
            place_input(consumer, s, original)

    log = run_gradle(consumer, java_home, gradle, ["jmhReport"], log_file)
    golden_files, golden_provided = golden if golden else ({}, {})

    def out_dir(s: Scenario) -> Path:
        return consumer / s.project / REPORT_DIR

    def verify(
        s: Scenario, expected_input: bytes, expected_provided: dict[str, Any], console: bool
    ) -> list[str]:
        assert s.input_name is not None
        return check_report(
            node,
            out_dir(s),
            s.input_name,
            expected_input,
            expected_provided,
            golden_files,
            log if console else None,
        )

    for s in SCENARIOS:
        if s not in active:
            result.outcomes[s.id] = Outcome("skipped")
        elif golden is None:
            continue  # recording: no comparison
        elif s.id == "S5":
            expected = real(out_dir(s) / "results.json")
            messages = {real(m) for m in MISSING_INPUT_LINE.findall(log)}
            problems = []
            if expected not in messages:
                problems.append(f"no 'Input '{expected}' does not exists!'")
            if f"Execution failed for task ':{s.project}:jmhReport'" not in log:
                problems.append("task didn't fail")
            if (out_dir(s) / "index.html").exists():
                problems.append("a report was written despite the missing input")
            result.outcomes[s.id] = Outcome("fail" if problems else "pass", problems)
        elif s.id == "S8":
            continue  # after the second run
        else:
            problems = verify(s, original, with_run_name(golden_provided, s.run_name), True)
            result.outcomes[s.id] = Outcome("fail" if problems else "pass", problems)

    s8 = SCENARIOS_BY_ID["S8"]
    if golden is not None:
        problems = [f"first run: {p}" for p in verify(s8, original, golden_provided, True)]
        place_input(consumer, s8, edited_input())
        log2 = run_gradle(consumer, java_home, gradle, [":s8:jmhReport"], log_file)
        log += "\n" + log2
        problems += [
            f"second run: {p}"
            for p in check_report(
                node,
                out_dir(s8),
                "results.json",
                edited_input(),
                edited_provided(golden_provided),
                golden_files,
                log2,
            )
        ]
        result.outcomes["S8"] = Outcome("fail" if problems else "pass", problems)

    result.deprecations = sorted(
        {
            ln.strip()
            for ln in log.splitlines()
            if re.search(r"deprecated", ln, re.I) and not ln.lstrip().startswith("at ")
        }
    )
    if gradle.major >= 8 and golden is not None:
        cc_log = run_gradle(
            consumer, java_home, gradle, ["--configuration-cache", ":s1:jmhReport"], log_file
        )
        s1_ok = real(out_dir(SCENARIOS_BY_ID["S1"])) in {
            real(m) for m in CONSOLE_LINE.findall(cc_log)
        }
        succeeded = s1_ok and "BUILD SUCCESSFUL" in cc_log
        result.configuration_cache = "passes" if succeeded else "fails"
    result.log = log
    return result, consumer


SCENARIOS_BY_ID = {s.id: s for s in SCENARIOS}


# --------------------------------------------------------------------------------------------------
# Golden


def read_golden() -> tuple[dict[str, str], dict[str, Any]]:
    if not GOLDEN_FILES.is_file() or not GOLDEN_PROVIDED.is_file():
        raise CheckError("golden/ is missing; record it with --update-golden --gradle <name>")
    files = json.loads(GOLDEN_FILES.read_text(encoding="utf-8"))
    provided = json.loads(GOLDEN_PROVIDED.read_text(encoding="utf-8"))
    return files, provided


def write_golden(node: str, consumer: Path, log: str) -> None:
    out = consumer / "s1" / REPORT_DIR
    if real(out) not in {real(m) for m in CONSOLE_LINE.findall(log)}:
        raise CheckError(f"S1 didn't report success; see the Gradle log in {LOGS}")
    files = hash_output(out, exclude={"results.json"})
    if not files:
        raise CheckError(f"S1 produced no output in {out}; see the Gradle log in {LOGS}")
    try:
        provided = evaluate_provided(node, out / "provided.js")
    except ValueError as e:
        raise CheckError(f"S1's provided.js is unusable: {e}") from e
    if provided["providedBenchmarks"] != [GOLDEN_RUN_NAME]:
        raise CheckError(f"Unexpected run name in S1: {provided['providedBenchmarks']}")
    GOLDEN.mkdir(exist_ok=True)
    GOLDEN_FILES.write_text(dump(files), encoding="utf-8")
    GOLDEN_PROVIDED.write_text(dump(provided), encoding="utf-8")
    print(f"Recorded golden: {len(files)} files + provided.js globals in {GOLDEN}")


# --------------------------------------------------------------------------------------------------
# Reporting


def cell(result: VersionResult, scenario: Scenario) -> str:
    if result.error:
        return "error"
    outcome = result.outcomes.get(scenario.id)
    if outcome is None:
        return "-"
    if outcome.status == "fail" and result.gradle.known_failure:
        return "known failure"
    return {"pass": "pass", "fail": "FAIL", "skipped": "skipped"}[outcome.status]


def report(results: list[VersionResult]) -> bool:
    """Prints details and the matrix; returns True if everything is as expected."""
    ok = True
    for r in results:
        g = r.gradle
        if r.error:
            print(f"\n[{g.name}] check error: {r.error}")
        for sid, o in r.outcomes.items():
            for p in o.problems:
                print(f"\n[{g.name}] {sid}: {p}")
        if r.error:
            ok = False  # an error in the check itself is never a known failure
        elif g.known_failure:
            if not r.failed:
                print(
                    f"\n[{g.name}] marked known-failure ({g.known_failure}) but passes: remove it"
                )
                ok = False
        elif r.failed:
            ok = False

    headers = ["Gradle"] + [s.id for s in SCENARIOS]
    rows = [[r.gradle.name] + [cell(r, s) for s in SCENARIOS] for r in results]
    widths = [max(len(row[i]) for row in [headers, *rows]) for i in range(len(headers))]
    print()
    for row in [headers, *rows]:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip())

    print("\nExtra signals (not failing):")
    for r in results:
        if r.error:
            continue
        deps = f"{len(r.deprecations)} deprecation line(s)" if r.deprecations else "no deprecations"
        cc = f", configuration cache: {r.configuration_cache}" if r.configuration_cache else ""
        print(f"  {r.gradle.name}: {deps}{cc}")
        for d in r.deprecations:
            print(f"      {d}")
    return ok


# --------------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", required=True, type=Path, help="the plugin jar to check")
    parser.add_argument("--gradle", help="comma-separated names from gradle-versions.toml")
    parser.add_argument(
        "--update-golden",
        action="store_true",
        help="record golden/ from exactly one Gradle version",
    )
    args = parser.parse_args()

    registry = load_versions()
    if args.gradle is None:
        selected = registry
    else:
        by_name = {v.name: v for v in registry}
        names = [n.strip() for n in args.gradle.split(",") if n.strip()]
        unknown = [n for n in names if n not in by_name]
        if unknown:
            parser.error(f"unknown Gradle name(s) {unknown}; known: {list(by_name)}")
        selected = [by_name[n] for n in names]
    if args.update_golden and len(selected) != 1:
        parser.error("--update-golden requires exactly one name in --gradle")
    if not args.jar.is_file():
        parser.error(f"{args.jar} doesn't exist")

    jar = args.jar.resolve()
    node = resolve_node()
    golden = None if args.update_golden else read_golden()

    keep: list[Path] = []
    results: list[VersionResult] = []
    consumers: dict[str, Path] = {}
    try:
        for g in selected:
            try:
                result, consumers[g.name] = run_version(g, jar, node, golden, keep)
            except (CheckError, subprocess.TimeoutExpired) as e:
                result = VersionResult(g, error=str(e))
            results.append(result)

        if args.update_golden:
            if results[0].error:
                raise CheckError(results[0].error)
            write_golden(node, consumers[selected[0].name], results[0].log)
            return 0

        ok = report(results)
        print(f"\nGradle logs: {LOGS}")
        if ok:
            for d in keep:
                shutil.rmtree(d, ignore_errors=True)
        else:
            print(f"Kept working directories: {', '.join(str(d) for d in keep)}")
        return 0 if ok else 1
    except CheckError as e:
        print(f"check error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
