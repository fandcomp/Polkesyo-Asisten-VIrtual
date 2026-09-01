"""Unit tests for GraphReasoningAgent, including surfacing the 2-hop ProgramStudi->
JalurPendaftaran->target chain (2026-07-23) in `relations`/`path_reasoning`.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.graph_reasoning_agent import GraphReasoningAgent


@pytest.mark.asyncio
class TestGraphReasoningAgent:
    async def test_two_hop_result_included_in_relations_with_program_studi(self):
        graph_results = [
            {
                "entity_type": "Jadwal",
                "entity_name": "17 Juni 2026",
                "relation": "MEMILIKI_JADWAL",
                "related_to": "Jalur Mandiri",
                "program_studi": "D3 Keperawatan",
            },
        ]
        with patch(
            "app.agents.graph_reasoning_agent.GraphRetrieverService.retrieve_by_intent",
            AsyncMock(return_value=graph_results),
        ):
            agent = GraphReasoningAgent()
            result = await agent._run({"intent": "jadwal"})

        assert result["graph_available"] is True
        assert result["relations"] == [
            {
                "from": "Jalur Mandiri",
                "relation": "MEMILIKI_JADWAL",
                "to": "17 Juni 2026",
                "program_studi": "D3 Keperawatan",
            }
        ]
        assert "D3 Keperawatan -TERSEDIA_PADA-> Jalur Mandiri -MEMILIKI_JADWAL-> 17 Juni 2026" in result["path_reasoning"]

    async def test_one_hop_result_without_program_studi_still_formats_correctly(self):
        graph_results = [
            {
                "entity_type": "Jadwal",
                "entity_name": "17 Juni 2026",
                "relation": "MEMILIKI_JADWAL",
                "related_to": "Jalur Mandiri",
            },
        ]
        with patch(
            "app.agents.graph_reasoning_agent.GraphRetrieverService.retrieve_by_intent",
            AsyncMock(return_value=graph_results),
        ):
            agent = GraphReasoningAgent()
            result = await agent._run({"intent": "jadwal"})

        assert result["relations"][0]["program_studi"] is None
        assert result["path_reasoning"] == "Jalur Mandiri -MEMILIKI_JADWAL-> 17 Juni 2026"

    async def test_neo4j_unavailable_degrades_gracefully(self):
        with patch(
            "app.agents.graph_reasoning_agent.GraphRetrieverService.retrieve_by_intent",
            AsyncMock(side_effect=RuntimeError("connection refused")),
        ):
            agent = GraphReasoningAgent()
            result = await agent._run({"intent": "jadwal"})

        assert result["graph_available"] is False
        assert result["graph_results"] == []
        assert result["confidence_score"] == 0.0
