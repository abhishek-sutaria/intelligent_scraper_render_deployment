from extractor import PaperExtractor


def test_validate_paper_data_extracts_and_removes_year():
    raw = {
        "title": "Sample Title",
        "authors": "Alice; Bob",
        "publication": "Proceedings of Testing 2022",
        "download_link": "https://example.org/paper.pdf",
    }

    cleaned = PaperExtractor.validate_paper_data(raw)
    assert cleaned["year"] == "2022"
    assert cleaned["publication"] == "Proceedings of Testing"


def test_extract_doi_and_year_helpers():
    text_with_doi = "Available at DOI: 10.1234/example.2024 and year 2024"
    text_without = "No identifiers present here"

    assert PaperExtractor.extract_doi(text_with_doi) == "10.1234/example.2024"
    assert PaperExtractor.extract_doi(text_without) == ""
    assert PaperExtractor.extract_year(text_with_doi) == "2024"
    assert PaperExtractor.extract_year(text_without) == ""


def test_clean_text_compacts_whitespace():
    assert PaperExtractor.clean_text("  A   B  ") == "A B"
    assert PaperExtractor.clean_text("") == ""


