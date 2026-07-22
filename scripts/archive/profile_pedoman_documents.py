"""Phase 0 diagnostic for the structure-aware document extraction plan.

Report-only: runs just the divider-page detection step (zone_patterns.is_divider_page) and
the decision-letter marker detection (zone_patterns.is_decision_letter_page) across every PDF
in a given directory, and prints what it found. Makes no database writes, no ingestion calls,
no pipeline changes — it exists purely to confirm (or refute) that the divider-page template
verified by hand on one production Pedoman PDF also holds for the other Pedoman documents
before DocumentStructureAgent is relied on for them specifically.

Usage (run manually, from the repository root or campus-va/backend):
    python scripts/profile_pedoman_documents.py [--dir data/raw] [--filter Pedoman]

`--dir` defaults to `data/raw` relative to the repository root (campus-va/data/raw per
CLAUDE.md's repository structure). Point it at a local copy of the VPS's data/raw to run this
against the real production corpus.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Standalone script, not part of the `app` package — add backend/ to sys.path so
# `app.services.text_extractor`/`app.services.ingestion.zone_patterns` can be imported without
# installing the backend package or running this from inside backend/.
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.ingestion import zone_patterns  # noqa: E402
from app.services.text_extractor import TextExtractor  # noqa: E402


async def profile_document(pdf_path: Path) -> dict:
    pages = await TextExtractor.extract_pages_from_pdf(str(pdf_path))
    if not pages:
        return {"file": pdf_path.name, "pages": 0, "dividers": [], "decision_letter_pages": [], "error": "no pages extracted"}

    dividers = []
    decision_letter_pages = []
    for page in pages:
        stripped = (page.get("text") or "").strip()
        if zone_patterns.is_divider_page(stripped):
            dividers.append({"page": page["page"], "title": zone_patterns.divider_title(stripped)})
        if zone_patterns.is_decision_letter_page(stripped):
            decision_letter_pages.append(page["page"])

    return {
        "file": pdf_path.name,
        "pages": len(pages),
        "dividers": dividers,
        "decision_letter_pages": decision_letter_pages,
    }


def _print_report(report: dict) -> None:
    print(f"\n=== {report['file']} ===")
    if report.get("error"):
        print(f"  ERROR: {report['error']}")
        return
    print(f"  Total pages: {report['pages']}")
    print(f"  Decision-letter (SK) pages: {report['decision_letter_pages'] or 'none found'}")
    if report["dividers"]:
        print(f"  Divider pages found ({len(report['dividers'])}):")
        for d in report["dividers"]:
            print(f"    - page {d['page']}: {d['title']}")
    else:
        print("  Divider pages found: none — this document falls through to a single body "
              "zone (no behavior change) if ingested today.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        default=str(Path(__file__).resolve().parent.parent / "data" / "raw"),
        help="Directory of PDFs to scan (default: data/raw)",
    )
    parser.add_argument(
        "--filter",
        default="Pedoman",
        help="Case-insensitive filename substring filter (default: 'Pedoman'; pass '' for all PDFs)",
    )
    args = parser.parse_args()

    scan_dir = Path(args.dir)
    if not scan_dir.is_dir():
        print(f"Directory not found: {scan_dir}")
        return

    pdf_files = sorted(
        p for p in scan_dir.glob("*.pdf")
        if not args.filter or args.filter.lower() in p.name.lower()
    )
    if not pdf_files:
        print(f"No matching PDFs found in {scan_dir} (filter={args.filter!r})")
        return

    print(f"Profiling {len(pdf_files)} document(s) in {scan_dir} (filter={args.filter!r})")
    for pdf_path in pdf_files:
        report = await profile_document(pdf_path)
        _print_report(report)


if __name__ == "__main__":
    asyncio.run(main())
