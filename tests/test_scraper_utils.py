import sys
import types

import pytest

# Provide a lightweight Playwright stub so the scraper module can be imported in test environments
async def _stub_async_playwright():
    raise RuntimeError("Playwright is not available in the unit test environment")


playwright_async_api = types.ModuleType("playwright.async_api")
playwright_async_api.Page = object  # Placeholder, not used in these tests
playwright_async_api.async_playwright = _stub_async_playwright

playwright_module = types.ModuleType("playwright")
playwright_module.async_api = playwright_async_api

sys.modules.setdefault("playwright", playwright_module)
sys.modules.setdefault("playwright.async_api", playwright_async_api)

from scraper import GoogleScholarScraper

SCRAPER = GoogleScholarScraper()


def test_normalize_url_handles_relative_and_absolute():
    assert SCRAPER._normalize_url("/citations") == "https://scholar.google.com/citations"
    assert SCRAPER._normalize_url("https://example.org/paper.pdf") == "https://example.org/paper.pdf"
    assert SCRAPER._normalize_url("//example.org/doc.pdf") == "https://example.org/doc.pdf"


@pytest.mark.parametrize(
    "encoded,expected",
    [
        ("hl=en&url=https%3A%2F%2Fexample.com%2Ffile.pdf", {"https://example.com/file.pdf"}),
        ("u=%2Fscholar%3Fq%3Dtest", {"/scholar?q=test"}),
        ("url=https%3A%2F%2Ffoo.com%2Fpaper.pdf&href=https%3A%2F%2Fbar.com%2Fdata", {"https://foo.com/paper.pdf", "https://bar.com/data"}),
        ("", set()),
    ],
)
def test_extract_urls_from_encoded_string(encoded, expected):
    urls = set(SCRAPER._extract_urls_from_encoded_string(encoded))
    for item in expected:
        assert item in urls


def test_score_candidate_prioritises_pdf_sources():
    direct_pdf = SCRAPER._score_candidate("https://example.org/paper.pdf", "page_anchor")
    google_pdf = SCRAPER._score_candidate("https://scholar.googleusercontent.com/abc", "page_anchor")
    repository = SCRAPER._score_candidate("https://arxiv.org/abs/1234.5678", "page_anchor")
    generic = SCRAPER._score_candidate("https://example.org/index", "page_anchor")
    scholar_profile = SCRAPER._score_candidate("https://scholar.google.com/citations?view_op=view_citation&hl=en&user=abc", "row_anchor")

    assert direct_pdf == 0
    assert google_pdf == 0
    assert repository == 1
    assert generic > repository
    assert scholar_profile > generic


def test_is_scholar_profile_link_detection():
    assert SCRAPER._is_scholar_profile_link("https://scholar.google.com/citations?view_op=view_citation&hl=en&user=abc")
    assert not SCRAPER._is_scholar_profile_link("https://scholar.googleusercontent.com/some.pdf")
    assert not SCRAPER._is_scholar_profile_link("https://example.org/file.pdf")


def test_select_preferred_candidate_skips_scholar_when_alt_exists():
    candidates = [
        {"url": "https://scholar.google.com/citations?view_op=view_citation&user=abc", "score": 9},
        {"url": "https://example.org/paper.pdf", "score": 0},
    ]
    chosen = SCRAPER._select_preferred_candidate(candidates)
    assert chosen["url"] == "https://example.org/paper.pdf"


def test_select_preferred_candidate_returns_scholar_when_only_option():
    candidates = [
        {"url": "https://scholar.google.com/citations?view_op=view_citation&user=abc", "score": 9},
    ]
    chosen = SCRAPER._select_preferred_candidate(candidates)
    assert chosen["url"].startswith("https://scholar.google.com/citations?")


def test_merge_candidate_lists_deduplicates_and_merges_meta():
    existing = [
        {
            "url": "https://example.org/paper.pdf",
            "source": "row_anchor",
            "score": 0,
            "meta": {"text": "PDF"},
        }
    ]
    new = [
        {
            "url": "https://example.org/paper.pdf",
            "source": "detail_fallback",
            "score": 1,
            "meta": {"attribute": "dataClk"},
        },
        {
            "url": "https://alt.org/paper",
            "source": "meta",
            "score": 2,
            "meta": {"key": "citation_pdf_url"},
        },
    ]

    merged = SCRAPER._merge_candidate_lists(existing, new)
    assert len(merged) == 2
    merged_urls = {candidate["url"] for candidate in merged}
    assert "https://example.org/paper.pdf" in merged_urls
    assert "https://alt.org/paper" in merged_urls

    merged_pdf = next(candidate for candidate in merged if candidate["url"] == "https://example.org/paper.pdf")
    assert merged_pdf["source"] == "detail_fallback|row_anchor"
    assert merged_pdf["meta"]["text"] == "PDF"
    assert merged_pdf["meta"]["attribute"] == "dataClk"


def test_extract_doi_from_url_handles_multiple_patterns():
    doi_url = "https://doi.org/10.1234/example.5678"
    query_url = "https://example.org/download?doi=10.9876/foo.bar"
    trailing_url = "https://publisher.org/doi/pdf/10.1122/abcd.efgh?download=1"
    invalid_url = "https://example.org/articles/2023"

    assert SCRAPER._extract_doi_from_url(doi_url) == "10.1234/example.5678"
    assert SCRAPER._extract_doi_from_url(query_url) == "10.9876/foo.bar"
    assert SCRAPER._extract_doi_from_url(trailing_url) == "10.1122/abcd.efgh"
    assert SCRAPER._extract_doi_from_url(invalid_url) == ""

