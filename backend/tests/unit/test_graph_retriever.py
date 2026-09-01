"""Unit tests for GraphRetrieverService.retrieve_by_intent, including the 2-hop
ProgramStudi->JalurPendaftaran->{Jadwal,Biaya,Persyaratan} chain added 2026-07-23.
Mocks the Neo4j async driver/session so these run without a real database, following the same
pattern as test_graph_service_read.py.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.graph_retriever import GraphRetrieverService


def make_async_result(records: list[dict]):
    result = MagicMock()

    async def _aiter():
        for r in records:
            yield r

    result.__aiter__ = lambda self=result: _aiter()
    return result


def make_mock_session(run_results: list):
    """`run_results` is consumed in call order — one entry per `session.run(...)` call."""
    session = AsyncMock()
    session.run = AsyncMock(side_effect=run_results)
    return session


def patch_driver(session):
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session_ctx)
    driver.close = AsyncMock()
    return patch.object(GraphRetrieverService, "get_driver", AsyncMock(return_value=driver))


@pytest.mark.asyncio
class TestRetrieveByIntentTwoHopChain:
    async def test_schedule_intent_returns_1hop_and_2hop_results(self):
        # Order of session.run() calls for intent="jadwal": program scan is skipped (no
        # "program"/"jurusan" keyword), jalur scan skipped, persyaratan scan skipped, then the
        # 1-hop MEMILIKI_JADWAL query, then the new 2-hop chain query.
        one_hop = make_async_result([{"jalur_name": "Jalur Mandiri", "target_name": "17 Juni 2026"}])
        two_hop = make_async_result([
            {"program_name": "D3 Keperawatan", "jalur_name": "Jalur Mandiri", "target_name": "17 Juni 2026"},
        ])
        session = make_mock_session([one_hop, two_hop])

        with patch_driver(session):
            results = await GraphRetrieverService.retrieve_by_intent("jadwal")

        assert len(results) == 2
        one_hop_result = next(r for r in results if r.get("program_studi") is None)
        two_hop_result = next(r for r in results if r.get("program_studi") is not None)

        assert one_hop_result["entity_type"] == "Jadwal"
        assert one_hop_result["related_to"] == "Jalur Mandiri"

        assert two_hop_result["entity_type"] == "Jadwal"
        assert two_hop_result["program_studi"] == "D3 Keperawatan"
        assert two_hop_result["related_to"] == "Jalur Mandiri"
        assert two_hop_result["entity_name"] == "17 Juni 2026"

    async def test_two_hop_query_targets_correct_relation_for_fee_intent(self):
        one_hop = make_async_result([])
        two_hop = make_async_result([])
        session = make_mock_session([one_hop, two_hop])

        with patch_driver(session):
            await GraphRetrieverService.retrieve_by_intent("biaya")

        chain_call_query = session.run.call_args_list[1].args[0]
        assert "ProgramStudi" in chain_call_query
        assert "TERSEDIA_PADA" in chain_call_query
        assert "MEMILIKI_BIAYA" in chain_call_query
        assert "Biaya" in chain_call_query

    async def test_no_matching_intent_keywords_issues_no_relation_queries(self):
        session = make_mock_session([])

        with patch_driver(session):
            results = await GraphRetrieverService.retrieve_by_intent("unknown")

        assert results == []
        session.run.assert_not_called()

    async def test_neo4j_error_propagates_to_caller(self):
        """GraphReasoningAgent (not this service) is responsible for the try/except fallback
        per CLAUDE.md §22.5 — this service itself should not silently swallow errors."""
        driver = MagicMock()
        driver.session = MagicMock(side_effect=RuntimeError("connection refused"))
        driver.close = AsyncMock()

        with patch.object(GraphRetrieverService, "get_driver", AsyncMock(return_value=driver)):
            with pytest.raises(RuntimeError):
                await GraphRetrieverService.retrieve_by_intent("jadwal")


@pytest.mark.asyncio
class TestRetrieveByIntentEntityAwareScoping:
    """A question naming a specific jalur/program should scope the 1-hop/2-hop Cypher to
    that entity, not scan every jalur in the graph (2026-07-27 — see graph_retriever.py's
    module comment for the eval evidence this fixes).

    All test intents below deliberately avoid the "program"/"jurusan"/"daftar"/"jalur"
    substrings so only the "syarat" flat Persyaratan scan (call index 0, inherent to the
    pre-existing code — MENGHARUSKAN's own trigger keywords are the same "syarat"/
    "persyaratan" pair) plus the 1-hop (index 1) and 2-hop (index 2) MENGHARUSKAN queries
    run — three session.run calls per case, not the two in the older schedule/fee tests
    above which don't share a keyword with any flat scan.
    """

    async def test_named_jalur_scopes_1hop_query_with_where_clause(self):
        flat = make_async_result([])
        one_hop = make_async_result([
            {"jalur_name": "SPMB Mandiri Profesi", "target_name": "buta warna"},
        ])
        two_hop = make_async_result([])
        session = make_mock_session([flat, one_hop, two_hop])

        with patch_driver(session):
            results = await GraphRetrieverService.retrieve_by_intent(
                "informasi mengenai syarat SPMB Mandiri Profesi tes buta warna"
            )

        one_hop_call = session.run.call_args_list[1]
        assert "WHERE j.name IN $jalur_names" in one_hop_call.args[0]
        assert one_hop_call.kwargs["jalur_names"] == ["SPMB Mandiri Profesi"]
        assert results[0]["related_to"] == "SPMB Mandiri Profesi"

    async def test_named_jalur_scopes_2hop_chain_query(self):
        flat = make_async_result([])
        one_hop = make_async_result([])
        two_hop = make_async_result([])
        session = make_mock_session([flat, one_hop, two_hop])

        with patch_driver(session):
            await GraphRetrieverService.retrieve_by_intent(
                "informasi mengenai syarat SPMB Mandiri Profesi"
            )

        chain_call = session.run.call_args_list[2]
        assert "WHERE j.name IN $jalur_names" in chain_call.args[0]
        assert chain_call.kwargs["jalur_names"] == ["SPMB Mandiri Profesi"]
        assert "program_names" not in chain_call.kwargs

    async def test_named_program_and_jalur_scopes_2hop_chain_with_both(self):
        flat = make_async_result([])
        one_hop = make_async_result([])
        two_hop = make_async_result([])
        session = make_mock_session([flat, one_hop, two_hop])

        with patch_driver(session):
            await GraphRetrieverService.retrieve_by_intent(
                "informasi mengenai syarat D-III Keperawatan SPMB Mandiri Profesi"
            )

        chain_call = session.run.call_args_list[2]
        query = chain_call.args[0]
        assert "j.name IN $jalur_names" in query
        assert "p.name IN $program_names" in query
        assert " AND " in query
        assert chain_call.kwargs["jalur_names"] == ["SPMB Mandiri Profesi"]
        assert chain_call.kwargs["program_names"] == ["D-III Keperawatan"]

    async def test_no_named_entity_falls_back_to_unscoped_query(self):
        """Preserves pre-upgrade behavior exactly when the question doesn't name a
        specific jalur/program."""
        flat = make_async_result([])
        one_hop = make_async_result([])
        two_hop = make_async_result([])
        session = make_mock_session([flat, one_hop, two_hop])

        with patch_driver(session):
            await GraphRetrieverService.retrieve_by_intent("informasi mengenai syarat umum yang berlaku")

        one_hop_call = session.run.call_args_list[1]
        assert "WHERE" not in one_hop_call.args[0]
        assert one_hop_call.kwargs == {}
