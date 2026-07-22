"""Reason-specific fallback messages (Indonesian, user-facing).

One place for every controlled-refusal copy so the assistant can explain *why* it cannot
answer instead of returning one generic message for every failure mode. Reasons map to
the fallback taxonomy: no_context, ambiguous_question, out_of_domain, prompt_injection,
insufficient_context, conflicting_context, unapproved_only, retrieval_error, llm_error.
"""

FALLBACK_MESSAGES: dict[str, str] = {
    "no_context": (
        "Saya belum menemukan informasi tersebut pada dokumen resmi yang telah diverifikasi. "
        "Silakan merujuk ke kanal resmi Poltekkes Kemenkes Yogyakarta atau hubungi unit terkait."
    ),
    "insufficient_context": (
        "Saya tidak menemukan informasi ini dalam sumber resmi yang dimuat. "
        "Silakan merujuk ke saluran informasi resmi Poltekkes Kemenkes Yogyakarta atau hubungi unit terkait."
    ),
    "ambiguous_question": (
        "Pertanyaan tersebut masih terlalu umum. Apakah yang dimaksud pendaftaran SPMB, "
        "pendaftaran ulang, atau layanan akademik?"
    ),
    "out_of_domain": (
        "Asisten virtual ini terbatas pada layanan informasi resmi kampus Poltekkes Kemenkes "
        "Yogyakarta. Saya tidak dapat menjawab pertanyaan di luar cakupan tersebut."
    ),
    "prompt_injection": (
        "Saya tidak dapat mengikuti instruksi tersebut. Saya hanya dapat menjawab "
        "berdasarkan dokumen resmi yang tersedia."
    ),
    "conflicting_context": (
        "Sumber resmi yang tersedia memuat informasi yang belum konsisten mengenai hal tersebut. "
        "Untuk kepastian, silakan hubungi unit terkait di Poltekkes Kemenkes Yogyakarta."
    ),
    "unapproved_only": (
        "Informasi terkait topik tersebut ditemukan, tetapi sumbernya belum diverifikasi admin "
        "sehingga belum dapat digunakan sebagai dasar jawaban."
    ),
    "retrieval_error": (
        "Terjadi kendala saat mencari sumber informasi. Silakan coba lagi beberapa saat."
    ),
    "llm_error": (
        "Terjadi kendala saat menyusun jawaban. Silakan coba lagi beberapa saat."
    ),
}

_DEFAULT_REASON = "insufficient_context"


def get_fallback_message(reason: str | None = None) -> str:
    """Return the user-facing message for a fallback reason (defaults to insufficient_context)."""
    return FALLBACK_MESSAGES.get(reason or _DEFAULT_REASON, FALLBACK_MESSAGES[_DEFAULT_REASON])
