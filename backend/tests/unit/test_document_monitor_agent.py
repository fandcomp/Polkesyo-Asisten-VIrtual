"""Unit tests for DocumentMonitorAgent's parser (CLAUDE.md §11A.3).

Uses a fixture that mirrors the real official site's markup (confirmed via a live fetch during
implementation, 2026-07-02) so this test stays deterministic and doesn't depend on the live site
being unchanged when tests run.
"""
from app.agents.document_monitor_agent import DocumentMonitorAgent

_FIXTURE_HTML = """
<div class="columns is-multiline">
  <div class="column is-one-quarter">
    <a href="/index.php?mod=login_default&sub=streamData&act=view&typ=html&dataId=147"
       target="_blank" title="HASIL SELEKSI TAHAP III (AKHIR) SPMB JALUR MANDIRI">
      <div class="bt bt-download-4">
        <div class="card-content download-panduan">
          <strong class="title-panduan">HASIL SELEKSI TAHAP III (AKHIR) SPMB JALUR MANDIRI</strong>
        </div>
      </div>
    </a>
  </div>
  <div class="column is-one-quarter">
    <a href="/index.php?mod=login_default&sub=streamData&act=view&typ=html&dataId=118"
       target="_blank" title="Pedoman SPMB Mandiri Reguler SMA Poltekkes Kemenkes Yogyakarta TA 2026-2027">
      <div class="bt bt-download-4">
        <div class="card-content download-panduan">
          <strong class="title-panduan">Pedoman SPMB Mandiri Reguler SMA</strong>
        </div>
      </div>
    </a>
  </div>
  <div class="column is-one-quarter">
    <a class="nav-item xhr dest_subcontent-element" href="/index.php?mod=login_default&sub=agenda&act=view&typ=html">
      Not a document link, must be ignored
    </a>
  </div>
</div>
"""


class TestDocumentMonitorAgentParser:
    def test_parses_real_site_markup_shape(self):
        links = DocumentMonitorAgent._parse_listing(
            _FIXTURE_HTML, base_url="https://sipenmaru.poltekkesjogja.ac.id/index.php"
        )
        assert len(links) == 2

    def test_extracts_data_id(self):
        links = DocumentMonitorAgent._parse_listing(
            _FIXTURE_HTML, base_url="https://sipenmaru.poltekkesjogja.ac.id/index.php"
        )
        data_ids = {link["data_id"] for link in links}
        assert data_ids == {"147", "118"}

    def test_extracts_title_from_title_attribute(self):
        links = DocumentMonitorAgent._parse_listing(
            _FIXTURE_HTML, base_url="https://sipenmaru.poltekkesjogja.ac.id/index.php"
        )
        titles = {link["title"] for link in links}
        assert "HASIL SELEKSI TAHAP III (AKHIR) SPMB JALUR MANDIRI" in titles

    def test_resolves_relative_url_to_absolute(self):
        links = DocumentMonitorAgent._parse_listing(
            _FIXTURE_HTML, base_url="https://sipenmaru.poltekkesjogja.ac.id/index.php"
        )
        assert all(link["url"].startswith("https://sipenmaru.poltekkesjogja.ac.id/") for link in links)

    def test_non_streamdata_links_are_excluded(self):
        links = DocumentMonitorAgent._parse_listing(
            _FIXTURE_HTML, base_url="https://sipenmaru.poltekkesjogja.ac.id/index.php"
        )
        assert not any("sub=agenda" in link["url"] for link in links)

    def test_empty_html_returns_no_links(self):
        links = DocumentMonitorAgent._parse_listing(
            "<html><body>No documents here</body></html>",
            base_url="https://sipenmaru.poltekkesjogja.ac.id/index.php",
        )
        assert links == []


class TestDocumentMonitorAgentSafeFilename:
    def test_sanitizes_title_into_filename(self):
        filename = DocumentMonitorAgent._safe_filename(
            {"title": "Pedoman SPMB Mandiri (2026/2027)!"}, checksum="abcdef1234567890"
        )
        assert filename.endswith("_abcdef12.pdf")
        assert "/" not in filename and "(" not in filename

    def test_empty_title_falls_back_to_document(self):
        filename = DocumentMonitorAgent._safe_filename({"title": "!!!"}, checksum="abcdef1234567890")
        assert filename.startswith("document_")
