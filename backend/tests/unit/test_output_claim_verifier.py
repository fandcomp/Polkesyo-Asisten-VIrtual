"""Unit tests for ACIF Gate 5 — Output Claim Verification."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.acif.output_claim_verifier import (
    FallbackResponse,
    OutputClaimVerifier,
)
from app.services.openrouter_client import GenerationResult, OpenRouterError


def _generation(text: str) -> GenerationResult:
    """Build a GenerationResult for mocking OpenRouterClient.generate — the real client
    returns this (not a bare string) so chat_core.py/answer_composer_agent.py can read
    model/token usage for Evaluation Layer logging."""
    return GenerationResult(text=text, model="test-model", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)


APPROVED_CHUNK = {
    "content": "Syarat pendaftaran jalur mandiri: calon mahasiswa harus melampirkan ijazah SMA.",
    "approval_status": "approved",
}


@pytest.mark.asyncio
class TestOutputClaimVerifierHappyPath:
    async def test_answer_with_no_claim_like_sentences_skips_verification(self):
        result = await OutputClaimVerifier.verify(
            "Terima kasih atas pertanyaan Anda, semoga membantu.",
            [APPROVED_CHUNK],
            [],
            strict_mode=True,
        )
        assert result.total_claims == 0
        assert result.overall_confidence == pytest.approx(0.95)
        assert result.should_enforce_fallback is False

    async def test_requirement_claim_supported_by_approved_chunk_passes(self):
        answer = "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri."
        result = await OutputClaimVerifier.verify(answer, [APPROVED_CHUNK], [], strict_mode=True)

        assert result.total_claims == 1
        assert result.supported_claims == 1
        assert result.overall_confidence == pytest.approx(1.0)
        assert result.should_enforce_fallback is False
        assert result.claim_details[0].claim.claim_type == "requirement"


@pytest.mark.asyncio
class TestOutputClaimVerifierFallbackEnforcement:
    async def test_unsupported_critical_claim_enforces_fallback(self):
        """Fee is a CRITICAL_TYPE. With only this one unsupported claim,
        overall_confidence drops to 0.0, which independently also crosses the
        low-confidence branch (<0.6) — that branch runs *after* the critical-
        claim branch and overwrites fallback_reason, so the final reason is
        the low-confidence message even though the critical-claim check is
        what conceptually flagged it. Both branches are non-exclusive `if`s,
        not `elif`, so whichever runs last wins the message."""
        answer = "Biaya pendaftaran adalah Rp 500000 untuk semua jalur."
        result = await OutputClaimVerifier.verify(answer, [APPROVED_CHUNK], [], strict_mode=True)

        assert result.claim_details[0].claim.claim_type == "fee"
        assert result.claim_details[0].is_supported is False
        assert result.should_enforce_fallback is True
        assert result.fallback_reason == "Low confidence: 0.0%"

    async def test_non_strict_mode_does_not_enforce_fallback(self):
        answer = "Biaya pendaftaran adalah Rp 500000 untuk semua jalur."
        result = await OutputClaimVerifier.verify(answer, [APPROVED_CHUNK], [], strict_mode=False)
        assert result.should_enforce_fallback is False

    async def test_unsupported_non_critical_contact_claim_still_lowers_confidence_enough_to_fallback(self):
        """"contact" is not in CRITICAL_TYPES, so it can never trigger the
        unsupported-critical-claim branch on its own — but it still counts
        toward overall_confidence, which can independently trip the
        low-confidence fallback branch."""
        answer = (
            "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri. "
            "Hubungi kontak admisi di nomor lain untuk info tambahan sekarang."
        )
        result = await OutputClaimVerifier.verify(answer, [APPROVED_CHUNK], [], strict_mode=True)

        assert result.total_claims == 2
        assert result.supported_claims == 1
        assert result.overall_confidence == pytest.approx(0.5)
        assert result.should_enforce_fallback is True
        assert result.fallback_reason == "Low confidence: 50.0%"


@pytest.mark.asyncio
class TestExtractClaimsIgnoresSourceCitation:
    """Regression test: a trailing "(Source: ... 2026 ...)" citation used to get
    mis-detected as a "date" claim (the year number), then correctly judged unsupported
    since a citation label isn't a fact stated in the source — silently enforcing a
    fallback on an otherwise fully-grounded answer. The old word-overlap heuristic hid
    this by accident (shared vocabulary inflated its match ratio); the stricter
    LLM-based path (test above) is what actually surfaced it."""

    async def test_citation_line_not_extracted_as_a_claim(self):
        answer = (
            "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri. "
            "(Source: Panduan SPMB Jalur Mandiri 2026 (Uji))"
        )
        claims = OutputClaimVerifier._extract_claims(answer)

        assert len(claims) == 1
        assert "Source" not in claims[0].text

    async def test_fully_grounded_answer_with_citation_does_not_fallback(self):
        answer = (
            "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri. "
            "(Source: Panduan SPMB Jalur Mandiri 2026 (Uji))"
        )
        result = await OutputClaimVerifier.verify(answer, [APPROVED_CHUNK], [], strict_mode=True)

        assert result.should_enforce_fallback is False

    async def test_indonesian_sumber_citation_not_extracted_as_a_claim(self):
        """Same regression as above, but for the "(Sumber: ...)" citation format the prompt
        now uses by default (prompt_boundary_builder.py's Indonesian-first output rules)."""
        answer = (
            "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri. "
            "(Sumber: Panduan SPMB Jalur Mandiri 2026 (Uji))"
        )
        claims = OutputClaimVerifier._extract_claims(answer)

        assert len(claims) == 1
        assert "Sumber" not in claims[0].text


class TestExtractClaimsIgnoresDanglingListFragments:
    """Regression test: numbered-list answers (the recommended output format) can produce
    a dangling heading + stray digit fragment like "**Tahapan Seleksi:**\\n1" when split on
    sentence punctuation — not a real claim, just a header plus a list-marker artifact."""

    def test_short_heading_plus_list_marker_fragment_is_not_a_claim(self):
        answer = "**Tahapan Seleksi:**\n1. Administrasi\n2. Ujian tulis CBT\n3. Tes kesehatan"
        claims = OutputClaimVerifier._extract_claims(answer)

        assert not any(c.text.strip() == "**Tahapan Seleksi:**\n1" for c in claims)

    def test_genuine_short_claim_with_enough_words_still_extracted(self):
        answer = "Biaya pendaftaran adalah Rp 500000 untuk semua jalur."
        claims = OutputClaimVerifier._extract_claims(answer)

        assert len(claims) == 1

    def test_longer_intro_sentence_ending_in_bare_list_marker_is_not_a_claim(self):
        """Same failure mode with more words padding it past the word-count filter —
        the tell is the dangling bare "1" on its own line, not the sentence length."""
        answer = (
            "**Tahapan Seleksi:**\nProses seleksi terdiri dari beberapa tahapan, yaitu:\n"
            "1. Seleksi administrasi\n2. Ujian tulis CBT\n3. Tes kesehatan"
        )
        claims = OutputClaimVerifier._extract_claims(answer)

        assert not any(c.text.endswith("\n1") for c in claims)


class TestClaimTypeDetection:
    def test_detects_contact_claim(self):
        assert OutputClaimVerifier._detect_claim_type("Hubungi kontak kami di kantor") == "contact"

    def test_detects_date_claim(self):
        assert OutputClaimVerifier._detect_claim_type("Pendaftaran dibuka pada tahun 2026") == "date"

    def test_plain_sentence_has_no_claim_type(self):
        assert OutputClaimVerifier._detect_claim_type("Ini kalimat biasa tanpa klaim apapun") is None


class TestGraphEvidenceShapeMatchesRetriever:
    """GraphRetrieverService.retrieve_by_intent (app/services/graph_retriever.py)
    returns dicts shaped {"entity_type": ..., "entity_name": ...}, matching
    what _build_context reads via item.get("entity_name", ""). (Previously the
    retriever used {"type", "name"}, which silently contributed nothing here
    — fixed by standardizing the retriever's dict keys.)"""

    def test_real_shaped_graph_dicts_contribute_to_context(self):
        graph_results_from_retriever = [{"entity_type": "ProgramStudi", "entity_name": "D3 Keperawatan"}]
        context = OutputClaimVerifier._build_context([], graph_results_from_retriever)
        assert context == "D3 Keperawatan"

    def test_old_type_name_shape_no_longer_used_would_contribute_nothing(self):
        legacy_shape = [{"type": "ProgramStudi", "name": "D3 Keperawatan"}]
        context = OutputClaimVerifier._build_context([], legacy_shape)
        assert context == ""


@pytest.mark.asyncio
class TestOutputClaimVerifierLlmPath:
    """use_llm=True is what chat_core.py / answer_composer_agent.py actually pass in
    production — these tests mock OpenRouterClient.generate so the LLM call itself is
    never real network traffic."""

    APPROVED_CHUNK_WITH_ORIGINAL = {
        "content": "Biaya pendaftaran sekitar Rp 350 ribu.",
        "original_text": "Biaya pendaftaran jalur mandiri sebesar Rp 350.000, tidak dapat dikembalikan.",
        "approval_status": "approved",
    }

    async def test_llm_marks_claim_supported_from_json_response(self):
        answer = "Biaya pendaftaran jalur mandiri adalah Rp 350.000."
        with patch(
            "app.services.acif.output_claim_verifier.OpenRouterClient.generate",
            AsyncMock(return_value=_generation('[{"supported": true, "evidence": "Rp 350.000"}]')),
        ) as mock_generate:
            result = await OutputClaimVerifier.verify(
                answer, [self.APPROVED_CHUNK_WITH_ORIGINAL], [], strict_mode=True, use_llm=True
            )

        mock_generate.assert_awaited_once()
        assert result.total_claims == 1
        assert result.supported_claims == 1
        assert result.should_enforce_fallback is False
        assert result.claim_details[0].support_evidence == "Rp 350.000"

    async def test_llm_verification_uses_original_text_not_paraphrased_summary(self):
        """The LLM prompt must be built from original_text (the verbatim source) rather
        than the possibly-paraphrased `content` summary — this is the whole point of the
        upgrade (a wrong-but-plausible number in the summary should still get caught)."""
        answer = "Biaya pendaftaran jalur mandiri adalah Rp 350.000."
        with patch(
            "app.services.acif.output_claim_verifier.OpenRouterClient.generate",
            AsyncMock(return_value=_generation('[{"supported": true, "evidence": ""}]')),
        ) as mock_generate:
            await OutputClaimVerifier.verify(
                answer, [self.APPROVED_CHUNK_WITH_ORIGINAL], [], strict_mode=True, use_llm=True
            )

        prompt_sent = mock_generate.await_args.args[0]
        assert "Rp 350.000, tidak dapat dikembalikan" in prompt_sent
        assert "Rp 350 ribu" not in prompt_sent

    async def test_llm_marks_claim_unsupported_enforces_fallback(self):
        answer = "Biaya pendaftaran jalur mandiri adalah Rp 999.999."
        with patch(
            "app.services.acif.output_claim_verifier.OpenRouterClient.generate",
            AsyncMock(return_value=_generation('[{"supported": false, "evidence": ""}]')),
        ):
            result = await OutputClaimVerifier.verify(
                answer, [self.APPROVED_CHUNK_WITH_ORIGINAL], [], strict_mode=True, use_llm=True
            )

        assert result.supported_claims == 0
        assert result.should_enforce_fallback is True

    async def test_llm_error_falls_back_to_heuristic(self):
        """API failure must not skip verification — it should silently fall back to the
        same heuristic path used when use_llm=False, not raise or return an empty result."""
        answer = "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri."
        with patch(
            "app.services.acif.output_claim_verifier.OpenRouterClient.generate",
            AsyncMock(side_effect=OpenRouterError("service unavailable")),
        ):
            result = await OutputClaimVerifier.verify(
                answer, [APPROVED_CHUNK], [], strict_mode=True, use_llm=True
            )

        # Same outcome as the pure-heuristic happy-path test above.
        assert result.total_claims == 1
        assert result.supported_claims == 1
        assert result.should_enforce_fallback is False

    async def test_malformed_json_falls_back_to_heuristic(self):
        answer = "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri."
        with patch(
            "app.services.acif.output_claim_verifier.OpenRouterClient.generate",
            AsyncMock(return_value=_generation("not valid json at all")),
        ):
            result = await OutputClaimVerifier.verify(
                answer, [APPROVED_CHUNK], [], strict_mode=True, use_llm=True
            )

        assert result.total_claims == 1
        assert result.supported_claims == 1

    async def test_wrong_length_json_array_falls_back_to_heuristic(self):
        answer = (
            "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri. "
            "Hubungi kontak admisi di nomor lain untuk info tambahan sekarang."
        )
        with patch(
            "app.services.acif.output_claim_verifier.OpenRouterClient.generate",
            # Only 1 item returned for 2 claims — a shape mismatch that must be rejected.
            AsyncMock(return_value=_generation('[{"supported": true, "evidence": ""}]')),
        ):
            result = await OutputClaimVerifier.verify(
                answer, [APPROVED_CHUNK], [], strict_mode=True, use_llm=True
            )

        assert result.total_claims == 2

    async def test_no_approved_source_text_falls_back_to_heuristic(self):
        answer = "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri."
        unapproved = {"content": "some content", "approval_status": "rejected"}
        with patch(
            "app.services.acif.output_claim_verifier.OpenRouterClient.generate",
            AsyncMock(return_value=_generation('[{"supported": true, "evidence": ""}]')),
        ) as mock_generate:
            result = await OutputClaimVerifier.verify(
                answer, [unapproved], [], strict_mode=True, use_llm=True
            )

        mock_generate.assert_not_awaited()
        assert result.total_claims == 1

    async def test_use_llm_false_never_calls_openrouter(self):
        answer = "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar jalur mandiri."
        with patch(
            "app.services.acif.output_claim_verifier.OpenRouterClient.generate",
            AsyncMock(return_value=_generation('[{"supported": true, "evidence": ""}]')),
        ) as mock_generate:
            await OutputClaimVerifier.verify(answer, [APPROVED_CHUNK], [], strict_mode=True)

        mock_generate.assert_not_awaited()


class TestFallbackResponse:
    def test_returns_indonesian_fallback_message(self):
        message = FallbackResponse.get_fallback("some reason")
        assert "tidak menemukan informasi" in message.lower()

    def test_free_text_reasons_map_to_same_default_copy(self):
        assert FallbackResponse.get_fallback("reason A") == FallbackResponse.get_fallback("reason B")

    def test_taxonomy_reason_returns_specific_copy(self):
        assert FallbackResponse.get_fallback("llm_error") != FallbackResponse.get_fallback("no_context")


@pytest.mark.asyncio
class TestDateClaimTuning:
    """Gate 5 date-claim tuning: notation-equivalent dates match; different dates fail;
    bare title years are no longer critical date claims. Strictness-preserving."""

    async def test_same_date_different_notation_is_supported(self):
        chunk = {
            "content": "Pendaftaran jalur mandiri dibuka pada tanggal 10/06/2026 secara online.",
            "approval_status": "approved",
        }
        answer = "Pendaftaran jalur mandiri dibuka pada 10 Juni 2026 secara online."
        result = await OutputClaimVerifier.verify(answer, [chunk], [], strict_mode=True)

        assert result.total_claims >= 1
        assert result.should_enforce_fallback is False

    async def test_bare_title_year_is_not_a_date_claim(self):
        """'Panduan SPMB 2026' inside a sentence must not classify the sentence as a
        critical date claim (it may still be another claim type or none)."""
        claim_type = OutputClaimVerifier._detect_claim_type(
            "informasi ini tercantum dalam panduan spmb 2026 bagi calon mahasiswa"
        )
        assert claim_type != "date"

    async def test_contextual_year_is_still_a_date_claim(self):
        assert OutputClaimVerifier._detect_claim_type("Pendaftaran dibuka pada tahun 2026") == "date"
        assert OutputClaimVerifier._detect_claim_type("gelombang 2026 akan diumumkan") == "date"
        assert OutputClaimVerifier._detect_claim_type("dibuka 10 juni 2026") == "date"
        assert OutputClaimVerifier._detect_claim_type("dibuka 10/06/2026") == "date"

    async def test_normalize_dates_canonical_forms(self):
        normalize = OutputClaimVerifier._normalize_dates
        assert "10_6_2026" in normalize("dibuka 10 juni 2026")
        assert "10_6_2026" in normalize("dibuka 10/06/2026")
        assert "10_6_2026" in normalize("dibuka 10-6-2026")
        # Different date -> different canonical token
        assert "15_7_2026" in normalize("ditutup 15 juli 2026")

    async def test_unsupported_fee_claim_still_forces_fallback(self):
        """Strictness regression guard: date tuning must not loosen fee verification."""
        answer = "Biaya pendaftaran adalah Rp 750000 untuk jalur mandiri."
        result = await OutputClaimVerifier.verify(answer, [APPROVED_CHUNK], [], strict_mode=True)
        assert result.should_enforce_fallback is True


@pytest.mark.asyncio
class TestGate5CorrectiveRegeneration:
    """CLAUDE.md §11.6 'Regenerate with stricter prompt if allowed by configuration'."""

    @staticmethod
    def _result(confidence: float, unsupported_critical: int, fallback: bool):
        from app.services.acif.output_claim_verifier import (
            Claim,
            ClaimVerificationResult,
            OutputVerificationResult,
        )

        details = [
            ClaimVerificationResult(
                claim=Claim(text=f"klaim gagal {i}", claim_type="requirement"),
                is_supported=False,
            )
            for i in range(unsupported_critical)
        ]
        details += [
            ClaimVerificationResult(
                claim=Claim(text="klaim didukung", claim_type="requirement"),
                is_supported=True,
            )
        ]
        return OutputVerificationResult(
            answer="jawaban",
            total_claims=len(details),
            supported_claims=sum(1 for d in details if d.is_supported),
            unsupported_claims=sum(1 for d in details if not d.is_supported),
            claim_details=details,
            overall_confidence=confidence,
            should_enforce_fallback=fallback,
            fallback_reason="Found unsupported critical claim(s)" if fallback else "",
        )

    async def test_regenerates_when_strongly_grounded_but_critical_claims_fail(self):
        result = self._result(confidence=0.92, unsupported_critical=2, fallback=True)
        assert OutputClaimVerifier.should_attempt_regeneration(result) is True

    async def test_no_regeneration_below_verified_threshold(self):
        result = self._result(confidence=0.50, unsupported_critical=2, fallback=True)
        assert OutputClaimVerifier.should_attempt_regeneration(result) is False

    async def test_no_regeneration_when_verification_passed(self):
        result = self._result(confidence=0.95, unsupported_critical=0, fallback=False)
        assert OutputClaimVerifier.should_attempt_regeneration(result) is False

    async def test_no_regeneration_when_config_disabled(self):
        from app.core.config import settings

        result = self._result(confidence=0.92, unsupported_critical=1, fallback=True)
        original = settings.acif_regenerate_on_unsupported
        settings.acif_regenerate_on_unsupported = False
        try:
            assert OutputClaimVerifier.should_attempt_regeneration(result) is False
        finally:
            settings.acif_regenerate_on_unsupported = original

    async def test_unsupported_critical_texts_lists_only_failing_critical_claims(self):
        result = self._result(confidence=0.92, unsupported_critical=2, fallback=True)
        texts = OutputClaimVerifier.unsupported_critical_texts(result)
        assert texts == ["klaim gagal 0", "klaim gagal 1"]

    async def test_regeneration_prompt_contains_original_and_failing_claims(self):
        prompt = OutputClaimVerifier.build_regeneration_prompt(
            "PROMPT ASLI", ["Biaya pendaftaran Rp 999.999"]
        )
        assert prompt.startswith("PROMPT ASLI")
        assert "KOREKSI WAJIB" in prompt
        assert "Biaya pendaftaran Rp 999.999" in prompt
        assert "TANPA pernyataan-pernyataan tersebut" in prompt


@pytest.mark.asyncio
class TestInlineCitationStripping:
    """Mid-answer '(Sumber: ...)' citations must never become verifiable pseudo-claims.

    Regression for the prod finding where multi-section answers to broad questions cite
    per section; the old end-anchored regex only stripped the trailing citation, so each
    mid-answer citation fragment was extracted as a critical date/regulation claim that
    no source could support — systematically forcing fallback on verified answers.
    """

    async def test_mid_answer_citations_produce_no_claims(self):
        answer = (
            "**1. Jalur Mandiri**\n\n"
            "(Sumber: PEDOMAN SPMB JALUR MANDIRI STR RPL 2026)\n\n"
            "**2. Jalur Prestasi**\n\n"
            "(Sumber: Pedoman SPMB Prestasi TA 2026/2027)\n"
        )
        claims = OutputClaimVerifier._extract_claims(answer)
        assert claims == []

    async def test_real_claims_survive_citation_stripping(self):
        answer = (
            "Calon mahasiswa harus melampirkan ijazah SMA untuk mendaftar. "
            "(Sumber: Pedoman SPMB Mandiri 2026) "
            "Biaya pendaftaran adalah Rp 300.000 untuk WNI."
        )
        claims = OutputClaimVerifier._extract_claims(answer)
        texts = " ".join(c.text for c in claims)
        assert "ijazah" in texts
        assert "300.000" in texts
        assert "Sumber" not in texts

    async def test_citation_only_answer_with_trailing_citation_still_stripped(self):
        # The previous (end-anchored) behavior must keep working.
        answer = "Persyaratan lengkap tersedia. (Sumber: Panduan SPMB Jalur Mandiri 2026 (Uji))"
        cleaned = OutputClaimVerifier._INLINE_SOURCE_RE.sub("", answer)
        assert "2026" not in cleaned

    async def test_citation_with_nested_parentheses_fully_stripped(self):
        answer = (
            "Persyaratan tersedia.\n"
            "(Sumber: PEDOMAN SELEKSI PENERIMAAN MAHASISWA BARU (SPMB) PRESTASI TA 2026/2027)\n"
            "Lanjutan teks."
        )
        cleaned = OutputClaimVerifier._INLINE_SOURCE_RE.sub("", answer)
        assert "2026/2027" not in cleaned
        assert "SPMB) PRESTASI" not in cleaned


@pytest.mark.asyncio
class TestSourceCitedInAnswer:
    async def test_title_named_in_answer_counts_as_cited(self):
        answer = "**1. Jalur Prestasi** ... (Sumber: Pedoman SPMB Prestasi 2026)"
        assert OutputClaimVerifier.is_source_cited_in_answer(answer, "Pedoman SPMB Prestasi 2026")

    async def test_unnamed_title_is_not_cited(self):
        answer = "Jawaban tanpa menyebut dokumen itu."
        assert not OutputClaimVerifier.is_source_cited_in_answer(answer, "Pedoman SPMB Prestasi 2026")
        assert not OutputClaimVerifier.is_source_cited_in_answer(answer, None)


@pytest.mark.asyncio
class TestSentenceSplitKeepsRpAmounts:
    async def test_rp_abbreviation_does_not_sever_amount_from_claim(self):
        answer = "Biaya Pendaftaran: Rp. 500.000,- untuk WNI dibayarkan saat mendaftar."
        claims = OutputClaimVerifier._extract_claims(answer)
        assert len(claims) == 1
        assert "500.000" in claims[0].text

    async def test_list_intro_ending_with_colon_is_not_a_claim(self):
        answer = (
            "Persyaratan pendaftaran dan kelengkapan berkas yang harus diunggah adalah:\n"
            "*   Scan ijazah SMA yang telah dilegalisir\n"
        )
        claims = OutputClaimVerifier._extract_claims(answer)
        texts = [c.text for c in claims]
        assert not any(t.rstrip().endswith(":") for t in texts)
        assert any("ijazah" in t for t in texts)
