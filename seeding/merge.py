"""Merge per-source seed CSVs into a single deduplicated startups.csv.

Inputs: any number of CSVs under seeding/sources/ plus (optionally) the
previously hand-curated data/startups.csv. Output: a single CSV matching
the shape the tracker expects.

## Dedup strategy

Each row is assigned a dedup key in this priority order:
    1. Normalized website (strip protocol, www., trailing slash,
       lowercase host). This is the strongest signal since two sources
       describing the same company almost always have the same domain.
    2. Fallback: normalized name (lowercase, non-alphanumeric stripped)
       — used when a row has no website.

When two rows collide on the same key, we merge them:
    - `sources` becomes pipe-joined union (e.g. "ycombinator|producthunt")
    - Scalar fields prefer the first non-empty value, with source priority
      curated > ycombinator > producthunt (see `SOURCE_PRIORITY`).
    - `notes` is concatenated (semicolon-separated) from all rows.

## Why keep the hand-curated list

The original `data/startups.csv` has human-verified rows (e.g. the Humane
HP acquisition, the Codeium/Windsurf acquihire chain) that no public
directory captures correctly. The merger treats this file as the
highest-priority source so that manual corrections survive refresh.

Run:
    python seeding/merge.py \\
        --inputs seeding/sources/yc.csv seeding/sources/producthunt.csv \\
        --curated data/startups.csv \\
        --out data/startups.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import OrderedDict

# Output schema — matches what tracker.py / scoring.py expect, plus
# seeding-specific provenance columns.
OUT_FIELDS = [
    "name", "website", "category", "founded", "github_org",
    "twitter_handle", "notes", "batch", "yc_status", "ph_slug",
    "tagline", "sources",
]

# Higher = higher priority for field-level preference when merging
SOURCE_PRIORITY = {
    "curated": 3,
    "ycombinator": 2,
    "producthunt": 1,
}


def norm_website(url: str) -> str:
    """Produce a normalized dedup key from a website URL."""
    if not url:
        return ""
    s = url.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0]
    return s.rstrip(".")


def norm_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def dedup_key(row: dict) -> str:
    """Return the dedup key for a row — website first, name fallback."""
    ws = norm_website(row.get("website", ""))
    if ws:
        return f"w:{ws}"
    nm = norm_name(row.get("name", ""))
    return f"n:{nm}" if nm else ""


def categorize_from_yc(row: dict) -> str:
    """Map YC one-liner + tagline into a coarse category.

    YC doesn't ship a clean category column, so we do keyword matching.
    This is rough — the goal is just a reasonable bucket for the UI
    filter, not a definitive taxonomy.
    """
    text = " ".join([
        row.get("one_liner", ""),
        row.get("tagline", ""),
        row.get("name", ""),
    ]).lower()
    rules = [
        (r"\b(legal|contract|litigation|law)\b", "Legal AI"),
        (r"\b(health|medical|radiolog|clinical|patient|carepod)\b", "Healthcare AI"),
        (r"\b(voice|speech|audio|podcast)\b", "Voice AI"),
        (r"\b(video|animation|film)\b", "Video AI"),
        (r"\b(image|photo|diffusion|stable)\b", "Image Gen"),
        (r"\b(music|song|sonic)\b", "Music Gen"),
        (r"\b(code|developer|engineer|ide|repo|compiler)\b", "Code AI"),
        (r"\b(agent|autonomous|auto\s?gpt)\b", "AI Agents"),
        (r"\b(search|retrieval)\b", "AI Search"),
        (r"\b(llm|foundation|model|fine[- ]?tun)\b", "ML Infrastructure"),
        (r"\b(analytics|dashboard|reporting|bi)\b", "Analytics"),
        (r"\b(sales|marketing|crm)\b", "Go-to-Market AI"),
        (r"\b(design|ui|figma|canvas)\b", "Design AI"),
        (r"\b(data|etl|warehouse|pipeline)\b", "Data Infrastructure"),
        (r"\b(security|compliance|vulnerability)\b", "Security AI"),
    ]
    for pattern, cat in rules:
        if re.search(pattern, text):
            return cat
    return "AI"


def normalize_row(row: dict, source: str) -> dict:
    """Map a source-specific row into the unified output shape."""
    out = {k: "" for k in OUT_FIELDS}
    out["name"] = (row.get("name") or "").strip()
    out["website"] = (row.get("website") or "").strip()
    out["sources"] = source
    if source == "ycombinator":
        out["founded"] = row.get("founded_year") or ""
        out["batch"] = row.get("batch") or ""
        out["yc_status"] = row.get("status") or ""
        out["tagline"] = row.get("one_liner") or ""
        out["category"] = categorize_from_yc({
            "one_liner": row.get("one_liner", ""),
            "name": row.get("name", ""),
        })
        # Translate YC status into tracker-compatible notes for override
        status = (row.get("status") or "").lower()
        if status == "inactive":
            out["notes"] = f"YC marked Inactive (batch: {out['batch']}); presumed shut down"
        elif status == "acquired":
            out["notes"] = f"YC marked Acquired (batch: {out['batch']})"
    elif source == "producthunt":
        out["ph_slug"] = row.get("ph_slug") or ""
        out["tagline"] = row.get("tagline") or ""
        out["category"] = categorize_from_yc({
            "one_liner": row.get("tagline", ""),
            "name": row.get("name", ""),
        })
        # PH public mode often has no website — that's fine, merge logic
        # can still dedup by name.
    elif source == "curated":
        # Already in output shape; copy over.
        for k in OUT_FIELDS:
            if row.get(k):
                out[k] = row[k]
        out["sources"] = "curated"
    return out


def merge_two(a: dict, b: dict) -> dict:
    """Merge b into a. a has equal-or-higher source priority."""
    merged = dict(a)
    # Union the sources list
    a_srcs = set((a.get("sources") or "").split("|"))
    b_srcs = set((b.get("sources") or "").split("|"))
    merged["sources"] = "|".join(sorted(s for s in a_srcs | b_srcs if s))
    # Field-wise: prefer a, fall back to b
    for k in OUT_FIELDS:
        if k == "sources":
            continue
        if not merged.get(k) and b.get(k):
            merged[k] = b[k]
    # notes is accumulative
    notes = [n for n in [a.get("notes"), b.get("notes")] if n and n not in (merged.get("notes") or "")]
    merged["notes"] = "; ".join(sorted(set(filter(None, (a.get("notes"), b.get("notes"))))))
    # If either row has a better website (actual URL vs empty), take it
    if not merged.get("website") and b.get("website"):
        merged["website"] = b["website"]
    return merged


def load_source(path: str, source: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [normalize_row(r, source) for r in reader]


def detect_source_from_path(path: str) -> str:
    p = path.lower()
    if "yc" in p or "ycombinator" in p:
        return "ycombinator"
    if "producthunt" in p or "ph" in p.split("/")[-1]:
        return "producthunt"
    return "curated"


def merge_all(inputs: list[tuple[str, str]], curated: str | None) -> list[dict]:
    """Merge all inputs into a dedup'd ordered list, highest-priority first.

    Two-stage dedup: first by website (the strong key), then a second pass
    that tries to collapse name-only entries into website-keyed entries
    when the normalized name matches. This matters because our Product
    Hunt public-mode rows have no website — without the second pass, a
    Langfuse-in-PH row would never merge with Langfuse-in-YC.
    """
    bucket: OrderedDict[str, dict] = OrderedDict()
    name_index: dict[str, str] = {}  # normalized name -> bucket key

    sources: list[tuple[str, str]] = []
    if curated:
        sources.append((curated, "curated"))
    sources.extend(inputs)
    # Process by descending priority so earlier entries "win"
    sources.sort(key=lambda t: -SOURCE_PRIORITY.get(t[1], 0))

    for path, source in sources:
        rows = load_source(path, source)
        print(f"  loaded {len(rows)} rows from {path} (source={source})",
              file=sys.stderr)
        for row in rows:
            key = dedup_key(row)
            if not key:
                continue
            nm_norm = norm_name(row.get("name", ""))

            # Stage 2 lookup: if this row has no website, check if a prior
            # row with the same normalized name already exists.
            if key.startswith("n:") and nm_norm in name_index:
                existing_key = name_index[nm_norm]
                bucket[existing_key] = merge_two(bucket[existing_key], row)
                continue

            # If this row DOES have a website but a prior name-only row
            # exists for the same name, collapse the name-only row into
            # this new website-keyed row.
            if key.startswith("w:") and nm_norm in name_index:
                prev_key = name_index[nm_norm]
                if prev_key != key and prev_key.startswith("n:"):
                    existing = bucket.pop(prev_key)
                    if key in bucket:
                        bucket[key] = merge_two(bucket[key], row)
                        bucket[key] = merge_two(bucket[key], existing)
                    else:
                        bucket[key] = merge_two(row, existing)
                    name_index[nm_norm] = key
                    continue

            if key in bucket:
                bucket[key] = merge_two(bucket[key], row)
            else:
                bucket[key] = row
            if nm_norm:
                name_index.setdefault(nm_norm, key)
    return list(bucket.values())


def write_output(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inputs", nargs="+", required=True,
                    help="Source CSVs (YC, Product Hunt, etc.)")
    ap.add_argument("--curated", default=None,
                    help="Existing hand-curated startups.csv (preserves manual corrections)")
    ap.add_argument("--out", required=True,
                    help="Output CSV path")
    args = ap.parse_args()

    inputs = [(p, detect_source_from_path(p)) for p in args.inputs]
    print(f"Merging {len(inputs)} sources" +
          (f" + curated '{args.curated}'" if args.curated else ""),
          file=sys.stderr)
    merged = merge_all(inputs, args.curated)
    write_output(merged, args.out)

    # Summary
    from collections import Counter
    source_combos = Counter(r.get("sources", "") for r in merged)
    with_website = sum(1 for r in merged if r.get("website"))
    print(f"Wrote {len(merged)} unique rows to {args.out}", file=sys.stderr)
    print(f"  with website: {with_website}", file=sys.stderr)
    print(f"  source combos: {dict(source_combos)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
