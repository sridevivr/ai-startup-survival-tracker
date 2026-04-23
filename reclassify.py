"""
Reclassify AI-tagged companies into more specific categories using keyword
rules against their taglines.

The bulk of the 577-company dataset (about 350 rows) comes out of YC and
Product Hunt with nothing more specific than the generic "AI" tag. That's
too coarse to build a sector-level view on, so this script reads each
row's tagline and assigns a more specific category when a keyword pattern
matches.

Rules are checked in priority order: domain-specific categories first
(Healthcare, Legal, Finance, Real Estate, etc.) then function-specific
(Code, Voice, Image, AI Agents, etc.). First match wins. Anything that
doesn't match lands in "General AI" — an honest label for genuinely
unspecific companies.

The script also normalises duplicate tags (Image Gen / Image Generation
→ Image AI, AI Health → Healthcare AI, etc.) and writes back:
    * data/startups.csv with updated `category` (original preserved as
      `original_category`)
    * output/signals.json with updated `category` so the dashboard and
      scoring don't need a full tracker re-run.

Usage:
    python reclassify.py                       # apply and write back
    python reclassify.py --dry-run             # print before/after, write nothing
    python reclassify.py --sample 50           # print a random sample of changes
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter
from pathlib import Path


# Rules are ordered. First match wins, with domain-specific categories
# checked before function-specific ones. Patterns are regex fragments
# applied case-insensitively to the tagline.
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    # ---- Tier 1: domain-specific ----
    ("Healthcare AI", [
        r"\bhealth\b", r"\bmedical\b", r"\bclinic", r"\bpatient", r"\bhospital",
        r"\btherapy\b", r"\btherapist", r"\bdiagnos", r"\bdental", r"\bdentist",
        r"\bveterinar", r"\bnurse\b", r"\bnursing\b", r"\bpharma", r"\bbiotech",
        r"\bgenomic", r"\bradiolog", r"\boncolog", r"\bemr\b", r"\behr\b",
        r"\bmedicaid\b", r"\bmedicare\b", r"\bphysician", r"\bdoctor",
        r"\bhealthcare\b", r"\bdrug discovery", r"\bmental health",
        r"\btelemedicine\b", r"\btelehealth\b",
        # Expanded: life sciences, antimicrobial terms, wellness / fitness
        r"\blife scienc", r"\bantibiotic", r"\bbacterial\b", r"\bvaccine",
        r"\bimmun", r"\bmicrobio", r"\bclinical trial", r"\bwellness\b",
        r"\bnutrition\b", r"\bfitness\b",
        # Second-pass additions
        r"\bcancer\b", r"\bmolecul", r"\bwetlab\b", r"\bhome care\b",
        r"\bhome health\b", r"\bpt/ot\b", r"\bslp\b",
        r"\brehabilitat", r"\bfda\b",
    ]),
    ("ClimateTech AI", [
        r"\bclimate\b", r"\bcarbon\b", r"\brenewable\b", r"\bclean tech\b",
        r"\bcleantech\b", r"\bsolar\b", r"\bwind power\b",
        r"\bemissions?\b", r"\bsustainabilit", r"\bgreenhouse\b",
        r"\besg\b", r"\bgreentech\b", r"\bsustainable\b",
        r"\butility bill", r"\benergy efficient", r"\batmosphere\b",
    ]),
    ("Gaming AI", [
        r"\bgames?\b", r"\bgaming\b", r"\bminecraft\b", r"\broblox\b",
        r"\bgame platform\b", r"\bgame studio\b",
    ]),
    ("Consumer AI", [
        r"\bfriends?\b", r"\bcouples?\b", r"\bsocial\b",
        r"\bromance\b", r"\bimessage\b", r"\bgroup chat\b",
        r"\brelationship\b", r"\bdating\b", r"\bentertainment\b",
        r"\bpersonal ai\b", r"\bcomfort\b",
    ]),
    ("Legal AI", [
        r"\blegal\b", r"law firm", r"law firms", r"lawfirm",
        r"\blawyer", r"\battorney",
        r"\bpatent\b", r"\btrademark\b", r"\blitigation\b",
        r"\bparalegal\b", r"\bcontract\b", r"\bcontracts\b",
        r"\bcompliance\b",
    ]),
    ("Finance AI", [
        r"\bbank\b", r"\bbanks\b", r"\bfinanc", r"\binvest",
        r"\bfintech\b", r"\bpayment", r"\bfraud\b", r"\binsurance\b",
        r"\baccount(?!s\b)", r"\baudit", r"\bhedge fund",
        r"\bprivate equity", r"\bventure capital", r"\btrading\b",
        r"\bwealth", r"\btax\b", r"\btaxes\b", r"\bbookkeep",
        r"\btreasury\b", r"\bloan\b", r"\blending\b", r"\bcredit\b",
        r"\bcapital markets", r"\bdue diligence", r"\bcfo\b",
        r"\bbilling\b",
        # Expanded: accounts payable/receivable and revenue cycle
        r"\baccounts payable\b", r"\baccounts receivable\b",
        r"\bap automation\b", r"\bar automation\b",
        r"\brevenue cycle\b",
        # Second pass: debt, derivatives, exchanges, stocks
        r"\bdebt collect", r"\bderivatives\b", r"\bexchange\b",
        r"\bstock research\b", r"\bstocks\b",
    ]),
    ("Real Estate AI", [
        r"\breal estate\b", r"\bproperty manag", r"\blandlord",
        r"\btenant", r"\bmortgage\b", r"\bcommercial real",
        r"\brental", r"\brealtor", r"\blease\b", r"\bleasing\b",
        r"\bhoa\b", r"\bdigital twin",
    ]),
    ("Education AI", [
        r"\bteach", r"\bstudent", r"\bschool", r"\beducat",
        r"\bcurriculum\b", r"\btutor", r"\bgrading\b", r"\bexam\b",
        r"\buniversit", r"\bedtech\b", r"\bclassroom\b", r"\blearner",
    ]),
    ("E-commerce AI", [
        r"\be-commerce\b", r"\becommerce\b", r"\bretail\b",
        r"\bshopify\b", r"\bproduct catalog", r"\bmerchant",
        r"\bd2c\b", r"\bdtc\b", r"\bshopping\b", r"\bcheckout\b",
        r"\bdrop ship", r"\bgrocery\b", r"\bsell online\b",
    ]),
    ("Engineering AI", [
        r"\bconstruction\b", r"\barchitect", r"\bcivil engineer",
        r"\bmechanical engineer", r"\bchip design", r"\bsemiconductor\b",
        r"\baircraft\b", r"\bmanufactur", r"\bindustrial\b",
        r"\bhardware\b", r"\bengineering workflow",
    ]),
    ("HR AI", [
        r"\brecruit", r"\bhiring\b", r"\bworkforce\b", r"\bpeople ops\b",
        r"\btalent\b", r"\bpayroll\b", r"\bonboard",
        r"\bhuman resource", r"\bemployee\b",
        r"\bbackground check", r"\bseasonal worker", r"\bhire engineers\b",
        r"\bhire amazing\b",
    ]),
    ("Customer Support AI", [
        r"\bsupport agent", r"\bcustomer support\b",
        r"\bsupport ticket", r"\bhelpdesk\b", r"\bhelp desk\b",
        r"\bcustomer service\b", r"\btickets?\b",
        r"\bcall center", r"\bsupport rep", r"\bit support\b",
    ]),
    ("Logistics AI", [
        r"\bfreight\b", r"\bshipping\b", r"\bsupply chain\b",
        r"\bwarehous", r"\bfleet\b", r"\bcarrier\b", r"\blogistic",
        r"\btrucking\b", r"\btruck\b", r"\baviation\b", r"\bcourier",
        r"\btransit\b",
    ]),
    ("Robotics", [
        r"\brobot\b", r"\brobots\b", r"\brobotic", r"\bautonomous vehicle",
        r"\bself-driving\b", r"\bself driving\b", r"\bphysical ai\b",
        r"\bdrone",
    ]),

    # ---- Tier 2: function-specific ----
    ("Code AI", [
        r"\bcoding\b", r"\bdeveloper", r"\bdevtool", r"\bdev tool",
        r"\bcodebase\b", r"\bprogramming\b", r"\bsoftware engineer",
        r"\bcode review", r"\bcoding agent", r"\bcopilot\b",
        r"\bcli\b", r"\bide\b", r"\bgithub\b", r"\bgit\b",
        r"\bapi\b", r"\bapis\b",
        # Second-pass additions
        r"\bcursor for\b", r"\bcursor alternative\b",
        r"\breplit\b", r"\blovable\b", r"\bjetbrains\b",
        r"\bsoftware\b", r"\bfull-stack\b", r"\bfull stack\b",
        r"\bdevops\b", r"\bruntime\b", r"\bruntime\b",
        r"\binternal tool", r"\bbuild app", r"\bbuild internal",
        r"\bcoding assistant\b", r"\bcode assistant\b",
        r"\bvisual editor\b", r"\bchrome plugin", r"\bswe\b",
        r"\bfull-stack apps\b", r"\bon-call\b", r"\bruntime\b",
        r"\bfrontend\b", r"\bbackend\b", r"\bmcp\b",
        r"\btest and debug\b", r"\bmobile testing\b",
        r"\bquality assurance\b", r"\btest prep automation\b",
        r"\bengineering work\b",
    ]),
    ("Voice AI", [
        r"\bvoice\b", r"\bspeech\b", r"\bphone call", r"\btranscri",
        r"\bcall center\b", r"\bspoken\b", r"\bconversational\b",
    ]),
    ("Image AI", [
        r"\bimage gen", r"\bimage ai\b", r"\bphoto\b", r"\bpicture\b",
        r"\bimagery\b",
    ]),
    ("Video AI", [
        r"\bvideo\b", r"\bfilm\b", r"\bfootage\b", r"\banimation\b",
    ]),
    ("Security AI", [
        r"\bsecurity\b", r"\bvulnerab", r"\bcyber", r"\bthreat\b",
        r"\bmalware\b", r"\bphishing\b", r"\bsoc ?2",
        r"\bdependency attack",
    ]),
    ("Foundation Models", [
        r"\bfoundation model", r"\blarge language model",
        r"\bfrontier model", r"\bllm\b",
    ]),
    ("Data Infrastructure", [
        r"\bdata pipeline", r"\bdata warehouse", r"\bdata lake\b",
        r"\betl\b", r"\bdatabase\b", r"\bdata platform\b",
        r"\bknowledge graph\b",
    ]),
    ("ML Infrastructure", [
        r"\bmlops\b", r"\bml ops\b", r"\bml platform\b",
        r"\bllm infra", r"\bmodel training\b", r"\binference\b",
        r"\bml services\b", r"\bevaluation engine\b",
        r"\bdataset\b", r"\btraining data\b", r"\bdata labeling\b",
        r"\bai trainer",
        # Second-pass additions
        r"\bllm\b", r"\bllms\b", r"\bgpu\b", r"\bgpus\b",
        r"\bfine-tun", r"\bfine tun", r"\bgenerative ai\b",
        r"\bgen ai\b", r"\bgenai\b", r"\bfrontier\b",
        r"\bembedding", r"\bvector database\b", r"\bvector db\b",
        r"\bmemory layer\b", r"\bdeploy (?:machine learning|ml) model",
        r"\bfrontier model", r"\bmodel serving\b", r"\btransformer model",
        r"\bprompt", r"\bedge devices?\b",
        r"\breliability platform\b",
    ]),
    ("AI Search", [
        r"\bsearch\b", r"\bsemantic search\b", r"\bretrieval\b",
        r"\bdeepresearch\b", r"\bdeep research\b",
    ]),
    ("Design AI", [
        r"\bdesigner", r"\bui\/ux", r"\bux\b", r"\bdesign\b",
        r"\bcreative strateg",
    ]),
    ("AI Writing", [
        r"\bwriting\b", r"\bcontent generation\b", r"\bcopywriting\b",
        r"\bblog post", r"\bnewsletter\b", r"\bauthor\b",
    ]),
    ("Analytics", [
        r"\banalytic", r"\bdashboard\b", r"\bbusiness intelligence\b",
        r"\bkpi", r"\breport",
        r"\brevenue intelligence\b", r"\bgen bi\b", r"\bbi\b",
        r"\bdeal collaboration\b",
    ]),
    ("Go-to-Market AI", [
        r"\bmarketing\b", r"\bsales\b", r"\bgtm\b", r"\bgo-to-market\b",
        r"\blead gen", r"\boutbound\b", r"\bcrm\b", r"\bgrowth\b",
        r"\bleads?\b", r"\badvertising\b", r"\bad\b", r"\bseo\b",
    ]),
    ("AI Agents", [
        r"\bagent\b", r"\bagents\b", r"\bai employee", r"\bai worker",
        r"\bai coworker", r"\bai teammate\b", r"\bautonomous ",
        r"\brpa\b", r"\brobotic process automation\b",
    ]),
    ("Productivity AI", [
        r"\bnotes\b", r"\bnote-taking\b", r"\bpersonal assistant\b",
        r"\bproductivity\b", r"\bpersonal context", r"\bcloud desktop\b",
        r"\bdesktop os\b",
        # Everyday-work apps with AI layered on
        r"\bspreadsheet", r"\bemail\b", r"\binbox\b", r"\bcalendar\b",
        r"\bmeeting note", r"\bpresentation editor\b",
    ]),
]

# Direct rename map for existing tags that already mean the same thing
# as a canonical bucket. Applied to rows whose current category is NOT
# just "AI" — reclassification by keyword only touches generic-AI rows.
RENAMES: dict[str, str] = {
    "AI Health": "Healthcare AI",
    "Image Gen": "Image AI",
    "Image Generation": "Image AI",
    "Video Generation": "Video AI",
    "Enterprise Search": "AI Search",
    "Enterprise Writing": "AI Writing",
    "Personal AI": "Productivity AI",
    "Enterprise Gen AI": "Foundation Models",
    "Music Generation": "Music AI",
    "AI Hardware": "Engineering AI",
    "Autonomous Driving": "Robotics",
    "Consumer AI": "Consumer AI",  # preserved as-is
    "AI Research": "AI Research",  # preserved as-is
    "Analytics": "Analytics",
}


def _normalise_tagline(tagline: str) -> str:
    """Clean up YC / Product Hunt tagline artifacts before keyword matching.

    Scraped taglines arrive with three common quirks that break naive
    keyword matching:

    1. CamelCase joins: "iPhone" stays glued as one word. We split
       lowercase-followed-by-uppercase transitions.
    2. Acronym-word joins: "AIcoding", "AIsupport", "GenBI" — an acronym
       immediately followed by a lowercase word. We split those at the
       acronym/word boundary using a lookbehind.
    3. Collapsed whitespace and punctuation.
    """
    if not tagline:
        return ""
    # 1. CamelCase split: "iPhone" -> "i Phone"
    fixed = re.sub(r"([a-z])([A-Z])", r"\1 \2", tagline)
    # 2. Acronym-word split: "AIcoding" -> "AI coding"
    # Zero-width boundary match: sitting between two uppercases and a
    # following lowercase. The lowercase marks the start of a word; the
    # preceding two uppercases mark the tail of an acronym. Insert a
    # space there.
    fixed = re.sub(r"(?<=[A-Z][A-Z])(?=[a-z])", " ", fixed)
    # 3. Collapse whitespace
    fixed = re.sub(r"\s+", " ", fixed).strip()
    return fixed


def classify(tagline: str | None) -> str | None:
    """Return the first matching category name, or None."""
    if not tagline:
        return None
    t = _normalise_tagline(tagline).lower()
    for category, patterns in CATEGORY_RULES:
        for pat in patterns:
            if re.search(pat, t, flags=re.IGNORECASE):
                return category
    return None


def decide_new_category(current: str, tagline: str | None) -> str:
    """Given a row's current category and tagline, return the new category."""
    current = (current or "").strip()
    if current and current.lower() != "ai":
        # Row already has a specific tag. Normalise duplicates, otherwise leave alone.
        return RENAMES.get(current, current)
    # Generic "AI" or empty. Try to reclassify via tagline.
    new = classify(tagline)
    return new or "General AI"


def main() -> None:
    p = argparse.ArgumentParser(description="Reclassify AI-only companies into sector-specific categories.")
    p.add_argument("--csv", default="data/startups.csv")
    p.add_argument("--signals", default="output/signals.json")
    p.add_argument("--dry-run", action="store_true",
                   help="Print changes but do not write files.")
    p.add_argument("--sample", type=int, default=0,
                   help="Print N random before→after reclassifications for spot-check.")
    args = p.parse_args()

    csv_path = Path(args.csv)
    signals_path = Path(args.signals)

    if not csv_path.exists():
        raise SystemExit(f"Missing {csv_path}")
    if not signals_path.exists():
        raise SystemExit(f"Missing {signals_path}")

    # ---- Pass 1: reclassify the CSV ----
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    if "original_category" not in fieldnames:
        fieldnames.insert(fieldnames.index("category") + 1, "original_category")

    changes: list[dict] = []
    for row in rows:
        current = (row.get("category") or "").strip()
        tagline = (row.get("tagline") or "").strip()
        new = decide_new_category(current, tagline)
        if new != current:
            changes.append({
                "name": row.get("name", ""),
                "tagline": tagline,
                "from": current or "(empty)",
                "to": new,
            })
            if not row.get("original_category"):
                row["original_category"] = current
            row["category"] = new
        elif "original_category" not in row:
            row["original_category"] = ""

    # ---- Build distribution before / after ----
    before = Counter()
    after = Counter()
    for row in rows:
        before[(row.get("original_category") or row.get("category") or "").strip() or "(empty)"] += 1
        after[(row.get("category") or "").strip() or "(empty)"] += 1

    # ---- Print summary ----
    total = len(rows)
    print(f"Reclassified {len(changes)} / {total} rows.\n")
    print(f"{'Category':25s} {'Before':>7s}  {'After':>7s}  {'Δ':>5s}")
    print("-" * 52)
    all_cats = sorted(set(before) | set(after), key=lambda c: -after.get(c, 0))
    for c in all_cats:
        b = before.get(c, 0)
        a = after.get(c, 0)
        diff = a - b
        sign = "+" if diff > 0 else ""
        print(f"{c[:25]:25s} {b:>7d}  {a:>7d}  {sign}{diff:>4d}")

    # ---- Optional sample spot-check ----
    if args.sample > 0 and changes:
        print(f"\nRandom sample of {min(args.sample, len(changes))} reclassifications:\n")
        random.seed(42)
        sample = random.sample(changes, min(args.sample, len(changes)))
        for c in sample:
            print(f"  [{c['from']:12s} → {c['to']:22s}] {c['name'][:20]:20s}  {c['tagline'][:70]}")

    if args.dry_run:
        print("\n--dry-run: no files written.")
        return

    # ---- Pass 2: write CSV back ----
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})
    print(f"\nWrote {csv_path} ({total} rows).")

    # ---- Pass 3: apply the same logic to signals.json ----
    # Build a name → new_category map from the CSV pass, then apply to signals.json.
    # Keyed on normalised name to be robust to small differences.
    def norm(s: str) -> str:
        return (s or "").strip().lower()

    name_to_category = {norm(r.get("name", "")): r.get("category", "") for r in rows}

    with signals_path.open(encoding="utf-8") as f:
        signals = json.load(f)
    updated = 0
    for s in signals:
        key = norm(s.get("name", ""))
        new_cat = name_to_category.get(key)
        if new_cat and s.get("category") != new_cat:
            s["category"] = new_cat
            updated += 1
    with signals_path.open("w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2, default=str)
    print(f"Wrote {signals_path} (updated {updated} rows).")


if __name__ == "__main__":
    main()
