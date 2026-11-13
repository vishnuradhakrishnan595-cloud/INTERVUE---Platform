"""
Code execution engine for coding assessments.

WARNING: this runs candidate code in a local subprocess with CPU/memory/file-size limits and a timeout.
That is NOT a security sandbox. In production run it inside isolated, network-less containers
(Docker / gVisor / Firecracker) via a Celery worker, and set CODE_EXECUTION_ENABLED=False on the web tier.
"""
import os
import shutil
import subprocess
import tempfile
import time

from django.conf import settings

LANGUAGES = {
    "python": {"file": "main.py", "compile": None, "run": ["python3", "main.py"], "limit_as": True},
    "javascript": {"file": "main.js", "compile": None, "run": ["node", "main.js"], "limit_as": False},
    "cpp": {"file": "main.cpp", "compile": ["g++", "-O2", "-std=c++17", "-o", "main", "main.cpp"],
            "run": ["./main"], "limit_as": True},
    "java": {"file": "Main.java", "compile": ["javac", "Main.java"], "run": ["java", "-Xmx256m", "Main"],
             "limit_as": False},
}
MAX_OUTPUT = 10_000


def _limits(cpu_seconds, memory_mb, limit_as):
    def apply():
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024,) * 2)
        if limit_as:
            resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2)
        os.setsid()
    return apply


def _normalize(text):
    return "\n".join(line.rstrip() for line in (text or "").strip().splitlines())


def execute(language, code, stdin="", time_limit=2, memory_mb=256):
    """Run `code` once. Returns {status, stdout, stderr, time_ms}; status in ok|error|timeout|compile_error."""
    cfg = LANGUAGES.get(language)
    if not cfg:
        return {"status": "error", "stdout": "", "stderr": f"Unsupported language: {language}", "time_ms": 0}
    if not settings.CODE_EXECUTION_ENABLED:
        return {"status": "error", "stdout": "", "stderr": "Code execution is disabled on this server.", "time_ms": 0}

    workdir = tempfile.mkdtemp(prefix="run_")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": workdir, "LANG": "C.UTF-8"}
    try:
        with open(os.path.join(workdir, cfg["file"]), "w", encoding="utf-8") as f:
            f.write(code)
        if cfg["compile"]:
            try:
                c = subprocess.run(cfg["compile"], cwd=workdir, capture_output=True, text=True, timeout=30, env=env)
            except subprocess.TimeoutExpired:
                return {"status": "compile_error", "stdout": "", "stderr": "Compilation timed out", "time_ms": 0}
            if c.returncode != 0:
                return {"status": "compile_error", "stdout": "", "stderr": c.stderr[:MAX_OUTPUT], "time_ms": 0}
        started = time.time()
        pre = _limits(int(time_limit) + 1, memory_mb, cfg["limit_as"]) if os.name == "posix" else None
        try:
            p = subprocess.run(cfg["run"], cwd=workdir, input=stdin, capture_output=True, text=True,
                               timeout=time_limit + (3 if language == "java" else 0), env=env, preexec_fn=pre)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "stdout": "", "stderr": "Time limit exceeded",
                    "time_ms": int(time_limit * 1000)}
        elapsed = int((time.time() - started) * 1000)
        return {"status": "ok" if p.returncode == 0 else "error", "stdout": p.stdout[:MAX_OUTPUT],
                "stderr": p.stderr[:MAX_OUTPUT], "time_ms": elapsed}
    except FileNotFoundError as exc:  # interpreter / compiler not installed
        return {"status": "error", "stdout": "", "stderr": f"Runtime not available: {exc}", "time_ms": 0}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_against_tests(language, code, problem):
    """Execute `code` on all test cases of `problem` and return score/verdict/per-case results."""
    results, earned, total_weight, passed_cases = [], 0, 0, 0
    verdict_flags = set()
    cases = list(problem.test_cases.all())
    for i, tc in enumerate(cases, start=1):
        total_weight += tc.weight
        r = execute(language, code, tc.input_data, problem.time_limit_seconds, problem.memory_limit_mb)
        ok = r["status"] == "ok" and _normalize(r["stdout"]) == _normalize(tc.expected_output)
        if ok:
            earned += tc.weight
            passed_cases += 1
        else:
            verdict_flags.add(r["status"] if r["status"] != "ok" else "wrong")
        entry = {"case": i, "passed": ok, "status": r["status"] if r["status"] != "ok" or ok else "wrong_answer",
                 "time_ms": r["time_ms"], "hidden": tc.is_hidden}
        if not tc.is_hidden:
            entry.update({"input": tc.input_data, "expected": tc.expected_output,
                          "actual": r["stdout"], "stderr": r["stderr"]})
        elif r["status"] in ("compile_error",):
            entry["stderr"] = r["stderr"]
        results.append(entry)
        if r["status"] == "compile_error":  # no point running the remaining cases
            break

    score = round(100.0 * earned / total_weight, 1) if total_weight else 0.0
    if cases and passed_cases == len(cases):
        verdict = "accepted"
    elif "timeout" in verdict_flags:
        verdict = "timeout"
    elif verdict_flags & {"error", "compile_error"} and passed_cases == 0:
        verdict = "error"
    elif passed_cases > 0:
        verdict = "partial"
    else:
        verdict = "wrong"
    return {"score": score, "verdict": verdict, "passed_cases": passed_cases,
            "total_cases": len(cases), "results": results}
