"""QueryUnderstandingAgent (CLAUDE.md §11A.1) — intent, topic, language, risk detection.

Reuses ACIF Gate 1's own risk detector (RiskSignals/TextNormalizer) for the risk_level output
field instead of building a second, parallel injection-detection mechanism.
"""
from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.services.acif.risk_signals import RiskSignals
from app.services.acif.text_normalizer import TextNormalizer

# Topic keywords mirror CLAUDE.md §13's entity/intent vocabulary and §11A's adaptive filtering
# rule (jadwal/biaya/persyaratan/hasil seleksi/regulasi -> strict filtering). Ordered from most
# specific to least specific: "pendaftaran" is checked last because its keywords ("daftar",
# "jalur", "spmb") appear in almost every SPMB-related message regardless of the actual specific
# intent, and would otherwise shadow more specific topics like jadwal/biaya.
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "jadwal": ["jadwal", "tanggal", "kalender", "gelombang", "tahap"],
    "biaya": ["biaya", "bayar", "pembayaran", "tarif", "ukt"],
    "persyaratan": ["syarat", "persyaratan", "dokumen", "berkas"],
    "hasil_seleksi": ["hasil seleksi", "hasil", "kelulusan", "lulus", "pengumuman"],
    "form": ["form", "formulir", "unduh form"],
    "kontak": ["kontak", "hubungi", "telepon", "email", "alamat"],
    "regulasi": ["pedoman", "tata tertib", "regulasi", "peraturan", "sop", "ketentuan"],
    "pendaftaran": ["daftar", "pendaftaran", "jalur", "spmb", "pmb"],
}

# Topics that require precise official data — drives ACIFAgent's strict filtering_mode.
STRICT_TOPICS = {"jadwal", "biaya", "persyaratan", "hasil_seleksi", "regulasi"}

_INDONESIAN_STOPWORDS = {"yang", "dan", "untuk", "dengan", "adalah", "apa", "bagaimana", "saya", "ini", "itu"}
_ENGLISH_STOPWORDS = {"the", "is", "are", "what", "how", "when", "where", "please", "you", "can"}


class QueryUnderstandingAgent(BaseAgent):
    name = "QueryUnderstandingAgent"

    async def _run(self, input_data: dict) -> dict:
        message: str = input_data["message"]
        normalized = TextNormalizer.normalize(message)
        risk_score, risk_signals = RiskSignals.get_risk_score(normalized)

        topic = self._detect_topic(normalized)
        language = self._detect_language(normalized)

        # Shared Query Understanding Layer (same service /chat uses — §11A parity).
        # Risk detection above stays authoritative for risk_level; the analysis only
        # shapes retrieval (rewritten queries, expansions, clarification).
        from app.services.query_understanding import QueryUnderstandingService

        analysis = await QueryUnderstandingService.analyze(
            message,
            history=input_data.get("history"),
            history_allowed=bool(input_data.get("history_allowed")),
        )

        return {
            "intent": topic or "general_campus_information",
            "bahasa": language,
            "topik": topic,
            "normalized_query": normalized,
            "requires_retrieval": True,
            "risk_level": self._risk_level(risk_score),
            "risk_score": risk_score,
            "risk_signals": risk_signals,
            "analysis": analysis.model_dump(),
            "rewritten_queries": analysis.rewritten_queries,
            "intent_label": analysis.intent,
            "intent_confidence": analysis.intent_confidence,
            "needs_clarification": analysis.needs_clarification,
            "clarification_question": analysis.clarification_question,
        }

    @staticmethod
    def _detect_topic(normalized_text: str) -> str | None:
        for topic, keywords in _TOPIC_KEYWORDS.items():
            if any(keyword in normalized_text for keyword in keywords):
                return topic
        return None

    @staticmethod
    def _detect_language(normalized_text: str) -> str:
        """Cheap stopword-count heuristic. Defaults to Indonesian (this is an ID-first assistant),
        switches to English only when English signal clearly outweighs Indonesian signal."""
        words = normalized_text.split()
        id_count = sum(1 for w in words if w in _INDONESIAN_STOPWORDS)
        en_count = sum(1 for w in words if w in _ENGLISH_STOPWORDS)
        if en_count > id_count:
            return "en"
        return "id"

    @staticmethod
    def _risk_level(score: float) -> str:
        """Mirrors ACIF Gate 1's own deployed thresholds (settings.acif_input_reject_threshold/
        acif_input_caution_threshold) rather than an arbitrary separate scale, so risk_level
        meaningfully reflects what Gate 1 will actually do with this input."""
        if score >= settings.acif_input_reject_threshold:
            return "high"
        if score >= settings.acif_input_caution_threshold:
            return "medium"
        return "low"
