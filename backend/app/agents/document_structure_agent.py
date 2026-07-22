"""DocumentStructureAgent (structure-aware document extraction plan, CLAUDE.md §11A pattern).

Reads a document's page-indexed extraction first and produces an ordered zone list instead of
letting every page flow into the same flat chunking path. Only ever produces zones for
`document_type == "Pedoman"` (see `zone_patterns.SUPPORTED_DOCUMENT_TYPES`) — every other
document type, and any Pedoman document that doesn't match the verified divider-page template,
gets zero zones back, which the caller (`ingestion_service.py`) treats as "fall through to
today's exact flat-ingestion behavior." That's what makes this rollout safe without first
auditing every document on the VPS.
"""
from app.agents.base_agent import BaseAgent
from app.services.ingestion import zone_patterns

# A near-blank page (page number/footer remnant only) can't independently signal whether it's
# a vision-form continuation or a text-form continuation — below this character count, it
# inherits the zone type of the run it's extending rather than opening a spurious new zone.
_BLANK_PAGE_CHAR_THRESHOLD = 20


class DocumentStructureAgent(BaseAgent):
    name = "DocumentStructureAgent"

    async def _run(self, input_data: dict) -> dict:
        document_type: str = input_data.get("document_type") or ""
        pages: list[dict] = input_data.get("pages") or []

        if document_type not in zone_patterns.SUPPORTED_DOCUMENT_TYPES or not pages:
            return {"zones": []}

        dividers = self._find_dividers(pages)
        if not dividers:
            # Template doesn't match this document instance -> zero zones. The caller falls
            # through to today's single flat body-ingestion path — no regression risk.
            return {"zones": []}

        zones: list[dict] = []

        sk_pages = [p["page"] for p in pages if zone_patterns.is_decision_letter_page(p.get("text") or "")]
        if sk_pages:
            zones.append({
                "zone_type": "decision_letter",
                "start_page": min(sk_pages),
                "end_page": max(sk_pages),
                "title": "SK Direktur",
            })

        first_divider_page = dividers[0][0]
        body_start = 1
        body_end = first_divider_page - 1
        if body_end >= body_start:
            zones.append({
                "zone_type": "body",
                "start_page": body_start,
                "end_page": body_end,
                "title": None,
            })

        page_by_num = {p["page"]: p for p in pages}
        last_page = max(p["page"] for p in pages)
        for idx, (start, title) in enumerate(dividers):
            region_start = start + 1
            region_end = dividers[idx + 1][0] - 1 if idx + 1 < len(dividers) else last_page
            if region_end < region_start:
                continue
            zones.extend(
                self._split_region_by_page_type(page_by_num, region_start, region_end, title)
            )

        return {"zones": zones}

    @staticmethod
    def _find_dividers(pages: list[dict]) -> list[tuple[int, str | None]]:
        dividers: list[tuple[int, str | None]] = []
        for p in pages:
            stripped = (p.get("text") or "").strip()
            if zone_patterns.is_divider_page(stripped):
                dividers.append((p["page"], zone_patterns.divider_title(stripped)))
        return dividers

    @staticmethod
    def _split_region_by_page_type(
        page_by_num: dict[int, dict],
        start: int,
        end: int,
        title: str | None,
    ) -> list[dict]:
        """Split a divider-opened page region into contiguous same-type runs (form_text vs.
        form_vision). One divider region is not always one zone_type — the verified ground
        truth's "DOKUMEN UJI KESEHATAN" region mixes a vision-only sub-form (raster pages)
        with a text-native sub-form (a real PDF table) under the same divider, so the split
        has to happen per page-type run, not just per divider."""
        runs: list[dict] = []
        current_type: str | None = None
        current_start: int | None = None

        for page_num in range(start, end + 1):
            page = page_by_num.get(page_num, {})
            page_type = DocumentStructureAgent._page_zone_type(page, current_type)
            if page_type != current_type:
                if current_type is not None:
                    runs.append({
                        "zone_type": current_type,
                        "start_page": current_start,
                        "end_page": page_num - 1,
                        "title": title,
                    })
                current_type = page_type
                current_start = page_num

        if current_type is not None:
            runs.append({
                "zone_type": current_type,
                "start_page": current_start,
                "end_page": end,
                "title": title,
            })
        return runs

    @staticmethod
    def _page_zone_type(page: dict, previous_type: str | None) -> str:
        """A page with near-zero extracted text and at least one embedded image is a raster/
        scanned form (verified: page 26's FORMULIR PEMERIKSAAN KESEHATAN — 2 embedded images,
        near-empty get_text()). A near-blank page with no images (e.g. a signature-only
        continuation, verified: page 27) can't independently prove which type it is, so it
        inherits the previous run's type instead of opening a spurious new zone. Everything
        else is a text-native form."""
        text = (page.get("text") or "").strip()
        image_count = page.get("image_count", 0) or 0

        if image_count > 0 and len(text) < _BLANK_PAGE_CHAR_THRESHOLD:
            return "form_vision"
        if len(text) < _BLANK_PAGE_CHAR_THRESHOLD and previous_type is not None:
            return previous_type
        return "form_text"
