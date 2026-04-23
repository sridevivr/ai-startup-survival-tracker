"""
Classify each company on TWO axes using the Anthropic API.

Input sources (all merged into a per-company record):
    - data/startups.csv                  → name, website, tagline, current category
    - data/scraped_content.json          → homepage title / h1 / meta description / first para
    - data/manual_categories.json        → AI-cross-checked notes, where available

Output: data/classifications.json
    {
      "version": 1,
      "model": "claude-sonnet-...",
      "generated_at": "2026-04-22T...",
      "classifications": {
        "Anthropic": {
          "sector": "Cross-industry",
          "function": "Foundation Models",
          "reasoning": "Trains frontier LLMs; cross-sector usage."
        },
        ...
      }
    }

Design:

  * Batched prompts — 15-20 companies per API call. Each call returns a
    JSON array of classifications. Far fewer tokens than per-company
    calls, still fits comfortably in context.
  * Claude Haiku by default for speed / cost. Pass --model to override.
  * Progress saved every batch so a mid-run crash doesn't lose work. The
    script is resumable — re-running skips companies already classified.
  * Strict JSON output enforced by a minimal schema in the prompt.

Usage:

    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/classify_with_llm.py
    python scripts/classify_with_llm.py --batch-size 20 --model claude-sonnet-4-6
    python scripts/classify_with_llm.py --only "Cursor,Anthropic"   # re-classify specific rows
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path


SECTORS = [
    "Healthcare", "Finance", "Legal", "Real Estate", "Education",
    "E-commerce", "Engineering", "HR", "Customer Support", "Logistics",
    "ClimateTech", "Gaming", "Consumer", "Security",
    "Cross-industry",
]

FUNCTIONS = [
    "Foundation Models",
    "ML Infrastructure",
    "Data Infrastructure",
    "AI Agent",
    "Copilot / Assistant",
    "Generative Product",
    "Analytics & Decisioning",
    "Research Lab",
]


SYSTEM_PROMPT = f"""You are classifying AI startups on two orthogonal axes based on public information.

Sectors (pick ONE — the vertical the company serves):
{chr(10).join("  - " + s for s in SECTORS)}

"Cross-industry" is for tools sold across verticals (developer tooling, general LLM infra, etc.).

Functions (pick ONE — where the company sits in the AI stack):
  - Foundation Models: they train base models themselves.
  - ML Infrastructure: training platforms, inference engines, evals, deployment.
  - Data Infrastructure: vector DBs, memory, pipelines, retrieval infrastructure.
  - AI Agent: autonomous software that takes multi-step actions.
  - Copilot / Assistant: human-in-the-loop augmentation; suggests / drafts.
  - Generative Product: the core output IS content (image, video, music, code, prose).
  - Analytics & Decisioning: reads data and outputs score / insight / classification / report.
  - Research Lab: fundamental AI research rather than shipping a product.

Rules:
  - If a tool doubles as agent and copilot (like Cursor), pick the one the company leads with in marketing.
  - Coding tools for developers → sector "Cross-industry".
  - Customer support chatbots that resolve end-to-end → "AI Agent"; ones that draft for a human to send → "Copilot / Assistant".
  - A voice AI handling a full customer call is an "AI Agent".
  - If truly unclassifiable (stealth, dead site, too generic), return sector "Cross-industry" and function "Copilot / Assistant" with reasoning "insufficient info".

Output format: a JSON array, one object per company, in the same order as input:
[
  {{"name": "...", "sector": "...", "function": "...", "reasoning": "one concise sentence"}},
  ...
]
Return ONLY the JSON array. No preamble, no code fences, no trailing commentary."""


def _load_inputs(root: Path) -> list[dict]:
    """Merge all signal sources into one record per company."""
    with (root / "data/startups.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    scraped: dict[str, dict] = {}
    scraped_path = root / "data/scraped_content.json"
    if scraped_path.exists():
        with scraped_path.open(encoding="utf-8") as f:
            for entry in json.load(f):
                scraped[(entry.get("name") or "").strip().lower()] = entry
    manual: dict[str, dict] = {}
    manual_path = root / "data/manual_categories.json"
    if manual_path.exists():
        with manual_path.open(encoding="utf-8") as f:
            data = json.load(f)
            manual = {k.strip().lower(): v for k, v in data.get("classifications", {}).items()}

    merged: list[dict] = []
    for r in rows:
        key = (r.get("name") or "").strip().lower()
        s = scraped.get(key, {})
        m = manual.get(key, {})
        merged.append({
            "name": r.get("name", ""),
            "website": r.get("website", ""),
            "tagline": (r.get("tagline") or "").strip(),
            "current_category": r.get("category", ""),
            "title": s.get("title", ""),
            "h1": s.get("h1", ""),
            "meta_description": s.get("meta_description", ""),
            "og_description": s.get("og_description", ""),
            "first_paragraph": s.get("first_paragraph", ""),
            "h2_list": s.get("h2_list", []),
            "scrape_status": s.get("status", "not_scraped"),
            "manual_note": m.get("note", ""),
        })
    return merged


def _company_payload(rec: dict, max_chars: int = 600) -> dict:
    """Compact per-company payload sent to the model. Cap text length."""
    def trunc(x: str) -> str:
        x = x or ""
        return x[:max_chars] if len(x) > max_chars else x

    return {
        "name": rec["name"],
        "website": rec["website"],
        "tagline": trunc(rec["tagline"]),
        "current_category": rec["current_category"],
        "title": trunc(rec["title"]),
        "h1": trunc(rec["h1"]),
        "meta_description": trunc(rec["meta_description"]),
        "og_description": trunc(rec["og_description"]),
        "first_paragraph": trunc(rec["first_paragraph"]),
        "h2_list": rec["h2_list"][:5],
        "manual_note": trunc(rec["manual_note"]),
    }


def _classify_batch(client, model: str, records: list[dict]) -> list[dict]:
    """Send one batch of companies to the API, return list of classifications."""
    payload = [_company_payload(r) for r in records]
    user_msg = (
        "Classify each of the following companies on Sector + Function. "
        "Respond with a JSON array in the same order.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    # Robust to occasional code-fence wrap
    if text.startswith("```"):
        text = text.strip("`")
        first_newline = text.find("\n")
        if first_newline > 0:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Model returned non-JSON output: {e}\nFirst 400 chars:\n{text[:400]}"
        )
    if not isinstance(parsed, list):
        raise RuntimeError(f"Expected JSON array, got: {type(parsed).__name__}")
    if len(parsed) != len(records):
        # Tolerate mismatches gracefully — match by name
        by_name = {(c.get("name") or "").strip().lower(): c for c in parsed if isinstance(c, dict)}
        parsed = []
        for r in records:
            key = r["name"].strip().lower()
            parsed.append(by_name.get(key) or {"name": r["name"], "sector": "Cross-industry",
                                               "function": "Copilot / Assistant",
                                               "reasoning": "missing from model output"})
    return parsed


def main() -> None:
    p = argparse.ArgumentParser(description="Classify companies on Sector + Function via Anthropic API.")
    p.add_argument("--root", default=".", help="Project root (default: cwd)")
    p.add_argument("--out", default="data/classifications.json")
    p.add_argument("--batch-size", type=int, default=15)
    p.add_argument("--model", default="claude-haiku-4-5-20251001")
    p.add_argument("--only", default="",
                   help="Comma-separated company names to classify (re-classify these specifically).")
    p.add_argument("--force", action="store_true",
                   help="Re-classify all — ignore existing classifications.json.")
    p.add_argument("--sleep", type=float, default=0.5, help="Seconds between batches.")
    args = p.parse_args()

    try:
        import anthropic
    except ImportError:
        raise SystemExit(
            "anthropic package not installed. Run: pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY in the environment first.")

    root = Path(args.root)
    out_path = root / args.out

    records = _load_inputs(root)
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}
        records = [r for r in records if r["name"].strip().lower() in wanted]

    # Load existing classifications to enable resume
    existing: dict[str, dict] = {}
    if out_path.exists() and not args.force:
        with out_path.open(encoding="utf-8") as f:
            existing = json.load(f).get("classifications", {})
        # Only classify rows not already done
        records = [r for r in records if r["name"] not in existing]

    if not records:
        print("Nothing to classify — all companies already have classifications. "
              "Pass --force to redo.")
        return

    client = anthropic.Anthropic(api_key=api_key)
    total = len(records)
    print(f"Classifying {total} companies with {args.model}, batch size {args.batch_size}...")

    results: dict[str, dict] = dict(existing)
    start = time.perf_counter()
    for i in range(0, total, args.batch_size):
        batch = records[i : i + args.batch_size]
        t0 = time.perf_counter()
        try:
            parsed = _classify_batch(client, args.model, batch)
        except Exception as e:
            print(f"  batch {i // args.batch_size + 1} failed: {e}")
            # Save what we have and abort
            _save(out_path, results, args.model)
            raise
        for rec, cls in zip(batch, parsed):
            results[rec["name"]] = {
                "sector": cls.get("sector", "Cross-industry"),
                "function": cls.get("function", "Copilot / Assistant"),
                "reasoning": cls.get("reasoning", ""),
            }
        _save(out_path, results, args.model)
        batch_time = time.perf_counter() - t0
        done = min(i + args.batch_size, total)
        print(f"  batch {i // args.batch_size + 1}: {done}/{total} in {batch_time:.1f}s", flush=True)
        if args.sleep > 0 and done < total:
            time.sleep(args.sleep)

    elapsed = time.perf_counter() - start
    print(f"\nDone in {elapsed:.1f}s. Wrote {out_path} ({len(results)} companies).")


def _save(path: Path, classifications: dict, model: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({
            "version": 1,
            "model": model,
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "classifications": classifications,
        }, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
