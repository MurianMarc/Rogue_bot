from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
ASK_MODEL = "qwen3:8b"
SUPER_MODEL = "qwen3:14b"


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize Rogue Bot Ollama models.")
    parser.add_argument("--pull", action="store_true", help="Pull qwen3:8b and qwen3:14b.")
    parser.add_argument("--warm", action="store_true", help="Warm the models after writing config.")
    parser.add_argument("--benchmark", action="store_true", help="Run a short benchmark.")
    args = parser.parse_args()

    ensure_env()
    threads = recommended_threads()
    vram = total_vram_mib()

    print(f"[optimize] CPU threads: {threads}")
    print(f"[optimize] NVIDIA VRAM: {vram} MiB")
    print("[optimize] Ask model: qwen3:8b")
    print("[optimize] Super model: qwen3:14b")

    if args.pull:
        pull_model(ASK_MODEL)
        pull_model(SUPER_MODEL)

    set_env_values(
        {
            "OLLAMA_MODEL": ASK_MODEL,
            "OLLAMA_SUPER_MODEL": SUPER_MODEL,
            "OLLAMA_TIMEOUT_SECONDS": "240",
            "OLLAMA_KEEP_ALIVE": "45m",
            "OLLAMA_NUM_PREDICT": "240",
            "OLLAMA_SUPER_NUM_PREDICT": "220",
            "OLLAMA_THINK": "false",
            "OLLAMA_SUPER_THINK": "false",
            "OLLAMA_NUM_THREAD": str(threads),
            "OLLAMA_NUM_GPU": "",
            "OLLAMA_SUPER_NUM_GPU": "",
            "SUPER_COOLDOWN_SECONDS": "120",
            "REQUIRE_INIT": "true",
            "ANNOUNCE_ONLINE": "true",
            "ONLINE_MESSAGE": "bot is now online",
        }
    )

    if args.warm:
        ensure_ollama_ready()
        benchmark_model(ASK_MODEL, threads, "ask")
        benchmark_model(SUPER_MODEL, threads, "super")
    elif args.benchmark:
        ensure_ollama_ready()
        benchmark_model(ASK_MODEL, threads, "ask")
        benchmark_model(SUPER_MODEL, threads, "super")

    print("[optimize] Done. Restart the bot for .env changes to apply.")
    return 0


def ensure_env() -> None:
    if ENV_FILE.exists():
        return
    if ENV_EXAMPLE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        return
    ENV_FILE.write_text("", encoding="utf-8")


def recommended_threads() -> int:
    cpu_count = os.cpu_count() or 8
    if cpu_count >= 24:
        return 16
    if cpu_count >= 16:
        return 12
    return max(4, cpu_count - 2)


def total_vram_mib() -> int:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0

    if result.returncode != 0:
        return 0

    first = (result.stdout.strip().splitlines() or ["0"])[0].strip()
    try:
        return int(first)
    except ValueError:
        return 0


def pull_model(model: str) -> None:
    ollama = find_ollama()
    print(f"[optimize] Pulling {model}.")
    subprocess.run([ollama, "pull", model], check=True)


def find_ollama() -> str:
    candidates = ["ollama"]
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        candidates.append(str(Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe"))

    for candidate in candidates:
        try:
            subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return candidate
        except OSError:
            continue
    raise RuntimeError("Ollama was not found on PATH.")


def ensure_ollama_ready() -> None:
    try:
        http_json("GET", f"{OLLAMA_URL}/api/tags")
    except Exception as exc:
        raise RuntimeError(f"Ollama is not ready at {OLLAMA_URL}: {exc}") from exc


def benchmark_model(model: str, threads: int, label: str) -> None:
    payload = {
        "model": model,
        "stream": False,
        "keep_alive": "45m",
        "think": False,
        "messages": [
            {
                "role": "user",
                "content": "Reply with a tight 60 word explanation of why local AI can be useful.",
            }
        ],
        "options": {
            "num_predict": 80,
            "num_thread": threads,
        },
    }
    started = time.perf_counter()
    try:
        data = http_json("POST", f"{OLLAMA_URL}/api/chat", payload)
    except Exception as exc:
        print(f"[optimize] {label} benchmark failed: {exc}")
        return

    elapsed = time.perf_counter() - started
    answer = (data.get("message") or {}).get("content", "").strip()
    print(f"[optimize] {label} {model}: {elapsed:.1f}s, {len(answer)} chars")


def http_json(method: str, url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def set_env_values(values: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    for name, value in values.items():
        replacement = f"{name}={value}"
        for index, line in enumerate(lines):
            if line.startswith(f"{name}="):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[optimize] Updated {ENV_FILE}")


if __name__ == "__main__":
    raise SystemExit(main())
