"""ACIF Gate 5: Output Claim Verifier — verify LLM claims against official context."""
import json
import re
import logging
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.fallback_messages import get_fallback_message
from app.services.openrouter_client import OpenRouterClient, OpenRouterError


logger = logging.getLogger(__name__)


class Claim(BaseModel):
    """Extracted claim from LLM output."""
    text: str
    claim_type: str
    confidence: float = 0.5


class ClaimVerificationResult(BaseModel):
    """Result of claim verification."""
    claim: Claim
    is_supported: bool
    support_evidence: str = ""
    confidence_score: float = 0.0


class OutputVerificationResult(BaseModel):
    """Overall output verification result."""
    answer: str
    total_claims: int = 0
    supported_claims: int = 0
    unsupported_claims: int = 0
    claim_details: list[ClaimVerificationResult] = []
    overall_confidence: float = 1.0
    should_enforce_fallback: bool = False
    fallback_reason: str = ""


class OutputClaimVerifier:
    """Verify LLM-generated claims against approved context."""

    # A bare 4-digit year only counts as a date claim when date context surrounds it
    # (tanggal/tahun/periode/gelombang, a full dd-mm-yyyy figure, a "dd MonthName yyyy"
    # form, or an academic-year range) — otherwise document titles like
    # "Panduan SPMB 2026" turn every sentence citing them into a critical date claim.
    _MONTH_NAMES = (
        r"jan(?:uari)?|feb(?:ruari)?|mar(?:et)?|apr(?:il)?|mei|jun(?:i)?|jul(?:i)?|"
        r"agu(?:stus)?|sep(?:tember)?|okt(?:ober)?|nov(?:ember)?|des(?:ember)?"
    )
    CLAIM_PATTERNS = {
        "requirement": r"(?:harus|must|require|syarat|persyaratan)",
        "date": (
            r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"
            rf"|\b\d{{1,2}}\s+(?:{_MONTH_NAMES})\s+\d{{4}}\b"
            r"|\b(?:tahun|tanggal|periode|gelombang)\s+\d{4}\b"
            r"|\b\d{4}[-/]\d{4}\b"
        ),
        "fee": r"(?:biaya|fee|cost|harga|price|rp\.?)",
        "procedure": r"(?:prosedur|langkah|tahap|step|proses)",
        "contact": r"(?:hubungi|contact|kontak|telepon|phone)",
        "regulation": r"(?:peraturan|regulasi|tata tertib|policy)",
    }

    CRITICAL_TYPES = {"requirement", "fee", "date", "procedure", "regulation"}

    LLM_VERIFICATION_PROMPT = """You are a fact-checker for an assistant's answer, checked against OFFICIAL SOURCE TEXT.
For EACH numbered claim below, decide whether it is supported.

Apply two different strictness levels depending on the claim:

1. Claims containing a SPECIFIC FIGURE (a date, fee/amount, article/regulation number, or
   location/address) must be STRICT: the exact figure must appear in the source. If the
   source states a different number, or the figure doesn't appear at all, mark unsupported.
   Treat the SAME date written in different notations as the same figure: "10 Juni 2026",
   "10/06/2026", and "10-6-2026" all match each other. A DIFFERENT date is still unsupported.

2. Claims that are general/introductory/connective statements (e.g. "the process has several
   stages", restating a heading, summarizing that requirements exist) — WITHOUT a specific
   figure — should be LENIENT: mark supported if the source discusses the same topic or
   process, even when the assistant's wording differs from the source's wording. Only mark
   these unsupported if the source doesn't discuss the topic at all.

OFFICIAL SOURCE TEXT:
{sources}

CLAIMS:
{claims}

Respond with ONLY a JSON array, exactly {claim_count} items, one per claim in the same order.
Each item: {{"supported": true or false, "evidence": "quote from the source, 10 words or fewer, or empty string"}}
Keep every evidence quote short (under 10 words) so the JSON stays well-formed. No other text
before or after the JSON array."""

    @staticmethod
    async def verify(
        answer: str,
        approved_chunks: list[dict],
        graph_evidence: list[dict],
        strict_mode: bool = True,
        db: AsyncSession | None = None,
        use_llm: bool = False,
    ) -> OutputVerificationResult:
        """Verify LLM answer claims against approved context.

        When `use_llm=True` (the real chat pipeline's default — see chat_core.py /
        answer_composer_agent.py), tries an LLM-based verification call first: more
        accurate than word-overlap since it catches paraphrased errors and
        wrong-but-plausible-looking figures. On any failure (API error, malformed JSON,
        unexpected shape), falls back to the regex/word-overlap heuristic automatically —
        Gate 5 must fail closed to its previous behavior, never skip verification entirely.
        Defaults to the heuristic-only path (`use_llm=False`) so existing callers/tests that
        don't pass a real OpenRouter key keep working deterministically without network calls.
        """

        claims = OutputClaimVerifier._extract_claims(answer)

        if not claims:
            return OutputVerificationResult(
                answer=answer,
                total_claims=0,
                supported_claims=0,
                unsupported_claims=0,
                overall_confidence=0.95,
                should_enforce_fallback=False,
            )

        if use_llm:
            try:
                verified_claims = await OutputClaimVerifier._verify_claims_with_llm(
                    claims, approved_chunks, db
                )
                return OutputClaimVerifier._build_result(answer, claims, verified_claims, strict_mode)
            except Exception as e:
                logger.warning(f"LLM-based Gate 5 verification failed, falling back to heuristic: {e}")

        context_text = OutputClaimVerifier._build_context(approved_chunks, graph_evidence)
        verified_claims = [
            OutputClaimVerifier._verify_single_claim(claim, context_text, approved_chunks, graph_evidence)
            for claim in claims
        ]
        return OutputClaimVerifier._build_result(answer, claims, verified_claims, strict_mode)

    @staticmethod
    def _build_result(
        answer: str,
        claims: list[Claim],
        verified_claims: list["ClaimVerificationResult"],
        strict_mode: bool,
    ) -> OutputVerificationResult:
        """Aggregate per-claim verification results into the overall decision — shared by
        both the LLM path and the heuristic fallback so the fallback-threshold logic exists
        in exactly one place."""
        unsupported_critical = [
            claim
            for claim, verification in zip(claims, verified_claims)
            if not verification.is_supported and claim.claim_type in OutputClaimVerifier.CRITICAL_TYPES
        ]

        supported = sum(1 for v in verified_claims if v.is_supported)
        total = len(verified_claims)
        unsupported = total - supported
        overall_confidence = (supported / total) if total > 0 else 1.0

        should_fallback = False
        fallback_reason = ""

        if strict_mode and unsupported_critical:
            should_fallback = True
            fallback_reason = f"Found {len(unsupported_critical)} unsupported critical claim(s)"

        # Deployed value 0.60 — reading from config is a behavioral no-op, it just stops
        # the threshold silently diverging from ACIF_GROUNDING_FALLBACK_THRESHOLD in .env.
        if overall_confidence < settings.acif_grounding_fallback_threshold and strict_mode:
            should_fallback = True
            fallback_reason = f"Low confidence: {overall_confidence:.1%}"

        return OutputVerificationResult(
            answer=answer,
            total_claims=total,
            supported_claims=supported,
            unsupported_claims=unsupported,
            claim_details=verified_claims,
            overall_confidence=overall_confidence,
            should_enforce_fallback=should_fallback,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def unsupported_critical_texts(result: OutputVerificationResult) -> list[str]:
        """Texts of critical claims that failed verification, for the corrective prompt."""
        return [
            detail.claim.text
            for detail in result.claim_details
            if not detail.is_supported
            and detail.claim.claim_type in OutputClaimVerifier.CRITICAL_TYPES
        ]

    @staticmethod
    def should_attempt_regeneration(result: OutputVerificationResult) -> bool:
        """Whether the CLAUDE.md §11.6 regenerate-with-stricter-prompt path applies.

        Only for answers that are otherwise strongly grounded (confidence at or above the
        verified threshold) but tripped on a few unsupported critical claims — typical for
        broad questions whose long multi-document answers contain one or two side remarks
        the verifier can't confirm. Low-confidence answers never regenerate: they fall back
        immediately, exactly as before.
        """
        return (
            settings.acif_regenerate_on_unsupported
            and result.should_enforce_fallback
            and result.overall_confidence >= settings.acif_grounding_verified_threshold
            and bool(OutputClaimVerifier.unsupported_critical_texts(result))
        )

    @staticmethod
    def build_regeneration_prompt(original_prompt: str, unsupported_texts: list[str]) -> str:
        """Append a strict correction block to the original bounded prompt.

        The bounded prompt (policy/context/user question separation) is reused verbatim —
        this only adds an instruction to omit the specific claims verification could not
        confirm, so the regenerated answer stays inside the same ACIF prompt boundary.
        """
        failing = "\n".join(f"- {text}" for text in unsupported_texts)
        return (
            f"{original_prompt}\n\n"
            "=== KOREKSI WAJIB ===\n"
            "Jawaban sebelumnya memuat pernyataan berikut yang TIDAK dapat diverifikasi "
            "terhadap konteks resmi di atas:\n"
            f"{failing}\n"
            "Tulis ulang jawaban TANPA pernyataan-pernyataan tersebut dan tanpa "
            "menggantinya dengan klaim baru. Hanya sampaikan fakta yang tertulis secara "
            "eksplisit dalam konteks resmi di atas. Jika bagian tertentu tidak tercakup "
            "konteks, nyatakan bahwa informasi tersebut tidak tersedia dalam sumber resmi "
            "yang dimuat."
        )

    @staticmethod
    async def _verify_claims_with_llm(
        claims: list[Claim],
        approved_chunks: list[dict],
        db: AsyncSession | None,
    ) -> list["ClaimVerificationResult"]:
        """Ask OpenRouter to verify each claim against the verbatim source text.

        Raises on any failure so the caller falls back to the heuristic — never returns a
        partial or best-effort result silently.
        """
        # Prefer the immutable original_text over the (possibly paraphrased) summary —
        # verification against the true source is the whole point of this upgrade.
        source_texts = [
            (chunk.get("original_text") or chunk.get("content") or "").strip()
            for chunk in approved_chunks
            if chunk.get("approval_status") == "approved"
        ]
        source_texts = [t for t in source_texts if t]
        if not source_texts:
            raise ValueError("No approved source text available for LLM verification")

        sources_block = "\n\n".join(f"[Source {i+1}]\n{t}" for i, t in enumerate(source_texts))
        claims_block = "\n".join(f"{i+1}. {c.text}" for i, c in enumerate(claims))

        prompt = OutputClaimVerifier.LLM_VERIFICATION_PROMPT.format(
            sources=sources_block, claims=claims_block, claim_count=len(claims)
        )

        try:
            result = await OpenRouterClient.generate(
                prompt,
                db=db,
                model=settings.openrouter_verification_model,
                # Generous headroom per claim — a too-tight budget was truncating the JSON
                # mid-string on longer "evidence" quotes, which then failed to parse and
                # silently fell back to the heuristic on every such response.
                max_tokens=max(300, 120 * len(claims)),
                temperature=0.0,
                timeout=20,
            )
        except OpenRouterError as e:
            raise RuntimeError(f"Verification LLM call failed: {e}") from e

        decisions = OutputClaimVerifier._parse_llm_verification(result.text, expected_count=len(claims))

        return [
            ClaimVerificationResult(
                claim=claim,
                is_supported=bool(decision.get("supported")),
                support_evidence=str(decision.get("evidence") or ""),
                confidence_score=0.9 if decision.get("supported") else 0.1,
            )
            for claim, decision in zip(claims, decisions)
        ]

    @staticmethod
    def _parse_llm_verification(raw: str, expected_count: int) -> list[dict]:
        """Parse the verification LLM's JSON array, tolerating a markdown code fence."""
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)

        decisions = json.loads(text)
        if not isinstance(decisions, list) or len(decisions) != expected_count:
            raise ValueError(
                f"Expected a JSON array of {expected_count} items, got: {type(decisions)} "
                f"len={len(decisions) if isinstance(decisions, list) else 'n/a'}"
            )
        return decisions

    @staticmethod
    def _extract_claims(answer: str) -> list[Claim]:
        """Extract claims from answer text.

        Strips the trailing "(Source: ...)" citation first (same pattern
        `is_content_relevant_to_answer` already uses) — otherwise a citation like
        "(Source: Panduan SPMB Jalur Mandiri 2026 (Uji))" gets mis-detected as a "date"
        claim (the `\\d{4}` year in "2026") and then correctly judged unsupported by any
        verifier, since a citation label isn't itself a fact stated in the source text.
        The old word-overlap heuristic missed this by accident (shared vocabulary with the
        real chunk inflated its match ratio); the stricter LLM-based check exposed it.
        """
        claims = []
        seen = set()
        cleaned_answer = OutputClaimVerifier._INLINE_SOURCE_RE.sub("", answer)
        # "Rp. 500.000" must not split after "Rp." — that severs the amount from its
        # claim, leaving an unverifiable "Biaya Pendaftaran: Rp" fragment that Gate 5
        # then correctly-but-uselessly rejects as an unsupported fee claim.
        sentences = re.split(r'(?<!\bRp)(?<!\brp)(?<!\bRP)[.!?]\s+', cleaned_answer)

        for sentence in sentences:
            sentence = sentence.strip()
            # Numbered/bulleted markdown lists (CLAUDE.md's own recommended output format)
            # can split into a dangling heading fragment like "**Tahapan Seleksi:**\n1" —
            # not a real claim, just a list header plus a stray list-marker digit. Requiring
            # at least 4 real words filters these out without excluding genuine short
            # claims (existing claims in this file all have 5+ words).
            word_count = len(re.findall(r"\w+", sentence))
            if not sentence or len(sentence) < 10 or word_count < 4:
                continue
            # Same list-splitting artifact, caught differently: the fragment's last line is
            # nothing but a bare list marker ("1", "2.", "-") with no real content of its
            # own — e.g. "...tahapan, yaitu:\n1". A verifier can never confirm this against
            # source text since it doesn't actually assert anything; the real facts are the
            # list items that got split away from it.
            last_line_content = re.sub(r"[\d.\)\-\*\s]", "", sentence.split("\n")[-1])
            if len(last_line_content) < 2:
                continue
            # List-intro fragments ("Persyaratan yang harus diunggah adalah:") assert no
            # fact of their own — the facts are the bullet items that follow, which are
            # extracted and verified as separate claims. Same artifact family as the
            # dangling list-marker filters above.
            if sentence.rstrip().rstrip("*").endswith(":"):
                continue
            claim_type = OutputClaimVerifier._detect_claim_type(sentence)
            if claim_type and sentence.lower() not in seen:
                claims.append(Claim(text=sentence, claim_type=claim_type, confidence=0.7))
                seen.add(sentence.lower())

        return claims

    _MONTH_NUMBERS = {
        "januari": 1, "jan": 1, "februari": 2, "feb": 2, "maret": 3, "mar": 3,
        "april": 4, "apr": 4, "mei": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
        "agustus": 8, "agu": 8, "september": 9, "sep": 9, "oktober": 10, "okt": 10,
        "november": 11, "nov": 11, "desember": 12, "des": 12,
    }

    @classmethod
    def _normalize_dates(cls, text: str) -> str:
        """Canonicalize date notations to one \\w+-stable token (e.g. "10_6_2026").

        "10 Juni 2026", "10/06/2026", and "10-6-2026" all become "10_6_2026"; a different
        date becomes a different token, so notation differences stop failing verification
        while genuinely different dates still fail. Expects lowercased input.
        """
        def _numeric(match: re.Match) -> str:
            day, month, year = match.groups()
            return f"{int(day)}_{int(month)}_{year}"

        def _named(match: re.Match) -> str:
            day, month_name, year = match.groups()
            month = cls._MONTH_NUMBERS.get(month_name[:3] if month_name not in cls._MONTH_NUMBERS else month_name)
            if month is None:
                return match.group(0)
            return f"{int(day)}_{month}_{year}"

        text = re.sub(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", _numeric, text)
        text = re.sub(rf"\b(\d{{1,2}})\s+({cls._MONTH_NAMES})\s+(\d{{4}})\b", _named, text)
        return text

    @staticmethod
    def _detect_claim_type(text: str) -> str | None:
        """Detect claim type."""
        text_lower = text.lower()
        for claim_type, pattern in OutputClaimVerifier.CLAIM_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                return claim_type
        return None

    @staticmethod
    def _verify_single_claim(claim: Claim, context_text: str, approved_chunks: list[dict], graph_evidence: list[dict]) -> ClaimVerificationResult:
        """Verify single claim against context.

        Words are extracted with \\w+ rather than a plain whitespace split so Markdown
        formatting in the answer (e.g. "**ijazah**", table "| cells |") doesn't attach
        punctuation to words and spuriously fail to match the same word in plain-text context.

        Date notations are canonicalized on both sides first so "10 Juni 2026" in the
        answer matches "10/06/2026" in the source — same date, different notation. A
        different date still produces different canonical tokens and fails to match.
        """
        claim_text = OutputClaimVerifier._normalize_dates(claim.text.lower())
        normalized_context = OutputClaimVerifier._normalize_dates(context_text.lower())
        claim_words = set(re.findall(r"\w+", claim_text))
        context_words = set(re.findall(r"\w+", normalized_context))
        matching_words = claim_words & context_words
        match_ratio = len(matching_words) / len(claim_words) if claim_words else 0

        best_evidence = ""
        for chunk in approved_chunks:
            if any(word in chunk.get("content", "").lower() for word in claim_words):
                best_evidence = chunk.get("content", "")[:200]
                break

        is_supported = match_ratio >= 0.4
        confidence = min(match_ratio, 0.95) if is_supported else max(0, match_ratio - 0.1)
        if best_evidence:
            confidence = min(confidence + 0.2, 0.95)

        return ClaimVerificationResult(
            claim=claim,
            is_supported=is_supported,
            support_evidence=best_evidence,
            confidence_score=confidence,
        )

    # Strips LLM-appended inline citations like "(Sumber: Some Document Title)" before
    # claim extraction and word-overlap comparison -- otherwise their words (shared
    # boilerplate like "sumber"/"source", or words from a *different* correct citation)
    # pollute the comparison. Matches both "Sumber" (the Indonesian-by-default prompt
    # format, see prompt_boundary_builder.py) and "Source" (English fallback).
    # Global, NOT end-anchored: multi-section answers to broad questions cite per section
    # ("(Sumber: Pedoman X)" mid-answer, several times). With only the trailing citation
    # stripped, sentence-splitting turned each mid-answer citation into a pseudo-claim
    # ("(Sumber: PEDOMAN ... 2026)" → detected as a date/regulation claim) that no source
    # text can ever support — systematically forcing fallback on otherwise-verified
    # answers. A citation label is not a factual claim; Gate 5 verifies facts, and
    # citation validity is enforced separately by the citation-relevance check.
    # Tolerates one level of nested parentheses — real document titles contain them
    # ("PEDOMAN SELEKSI PENERIMAAN MAHASISWA BARU (SPMB) PRESTASI ..."), and stopping at
    # the first ")" left a dangling "... TA 2026/2027)" fragment that became a pseudo-claim.
    _INLINE_SOURCE_RE = re.compile(
        r"\(\s*(?:sumber|source)\s*:(?:[^()]|\([^()]*\))*\)", re.IGNORECASE
    )

    @staticmethod
    def is_source_cited_in_answer(answer: str, document_title: str | None) -> bool:
        """Whether the answer's own inline "(Sumber: ...)" citations name this document.

        Long multi-section answers (broad questions spanning several documents) dilute the
        per-chunk word-overlap ratio below its threshold even though every section is
        genuinely grounded — but those answers explicitly attribute each section to its
        document by title, which is direct evidence the chunk was drawn on. Complements
        (never replaces) the overlap check.
        """
        if not document_title:
            return False
        return document_title.strip().lower() in answer.lower()

    @staticmethod
    def is_content_relevant_to_answer(
        answer: str,
        content: str,
        min_overlap_ratio: float = 0.45,
    ) -> bool:
        """Whether a chunk's content is actually reflected in the final answer.

        Citations should only ever list sources the answer genuinely drew on — not every chunk
        that merely survived retrieval + ACIF Gates 2/3 upstream, some of which can be
        topically adjacent (or, if the answer became a fallback message, entirely unrelated)
        without ever contributing anything to what was actually said. The threshold is
        calibrated well above the shared-domain-vocabulary floor: documents in this corpus
        almost all mention generic terms like "SPMB"/"mandiri"/"jalur"/the current year, which
        alone produces ~0.25 overlap even between genuinely unrelated chunks — a real answer
        actually grounded in a chunk measures closer to 0.7-0.8.
        """
        cleaned_answer = OutputClaimVerifier._INLINE_SOURCE_RE.sub("", answer)
        answer_words = {w for w in re.findall(r"\w+", cleaned_answer.lower()) if len(w) > 3}
        if not answer_words:
            return False
        content_words = {w for w in re.findall(r"\w+", content.lower()) if len(w) > 3}
        overlap = answer_words & content_words
        return (len(overlap) / len(answer_words)) >= min_overlap_ratio

    @staticmethod
    def _build_context(approved_chunks: list[dict], graph_evidence: list[dict]) -> str:
        """Build searchable context."""
        parts = []
        for chunk in approved_chunks:
            if chunk.get("approval_status") == "approved":
                parts.append(chunk.get("content", ""))
        for item in graph_evidence:
            if isinstance(item, dict):
                parts.append(item.get("entity_name", ""))
        return " ".join(parts)


class FallbackResponse:
    """Generate fallback response (reason-specific copy lives in fallback_messages.py)."""

    FALLBACK_MESSAGE = get_fallback_message("insufficient_context")

    @staticmethod
    def get_fallback(reason: str = "") -> str:
        """Get fallback message for a reason.

        Accepts either a taxonomy key ("no_context", "llm_error", ...) or a free-text
        Gate 5 reason ("Found 2 unsupported critical claim(s)") — free text maps to the
        default insufficient-context copy.
        """
        if reason:
            logger.info(f"Fallback enforced: {reason}")
        return get_fallback_message(reason)
