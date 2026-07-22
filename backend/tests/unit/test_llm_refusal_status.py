"""Unit tests for ChatCoreService._detect_llm_refusal_status — mapping the LLM's own
policy refusals (which Gate 5 passes as "verified" since they contain no claims) to the
CLAUDE.md §8.3 statuses out_of_domain / insufficient_context."""
from app.services.chat_core import ChatCoreService


OOD_REFUSAL = (
    "Asisten virtual ini hanya melayani informasi resmi kampus Poltekkes Kemenkes "
    "Yogyakarta. Saya tidak dapat menjawab pertanyaan di luar cakupan tersebut."
)
NOT_IN_SOURCES = "Informasi ini tidak tersedia dalam sumber resmi yang kami muat saat ini."


class TestDetectLlmRefusalStatus:
    def test_out_of_domain_refusal_detected(self):
        assert ChatCoreService._detect_llm_refusal_status(OOD_REFUSAL) == "out_of_domain"

    def test_out_of_domain_detected_even_with_surrounding_text(self):
        answer = f"Mohon maaf. {OOD_REFUSAL} Terima kasih atas pengertian Anda."
        assert ChatCoreService._detect_llm_refusal_status(answer) == "out_of_domain"

    def test_not_in_sources_refusal_detected(self):
        assert ChatCoreService._detect_llm_refusal_status(NOT_IN_SOURCES) == "insufficient_context"

    def test_not_in_sources_phrase_inside_long_partial_answer_is_not_a_refusal(self):
        # A real answer that covers X but notes Y is unavailable must stay a normal answer —
        # the phrase only counts as a refusal when the whole answer is a short lead-in refusal.
        answer = (
            "Syarat pendaftaran jalur mandiri adalah ijazah SMA/sederajat, kartu keluarga, "
            "pas foto terbaru, dan surat keterangan sehat dari fasilitas kesehatan. "
            "Pendaftaran dilakukan melalui portal SPMB pada periode yang ditentukan panitia. "
            "Adapun rincian biaya seragam untuk tahun ini tidak tersedia dalam sumber resmi "
            "yang kami muat saat ini, silakan hubungi bagian akademik untuk konfirmasi."
        )
        assert ChatCoreService._detect_llm_refusal_status(answer) is None

    def test_normal_answer_returns_none(self):
        answer = "Syarat pendaftaran jalur mandiri adalah ijazah SMA, kartu keluarga, dan pas foto."
        assert ChatCoreService._detect_llm_refusal_status(answer) is None

    def test_detection_is_case_insensitive(self):
        assert ChatCoreService._detect_llm_refusal_status(OOD_REFUSAL.upper()) == "out_of_domain"
