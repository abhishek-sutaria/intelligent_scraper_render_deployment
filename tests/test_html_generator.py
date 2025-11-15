from html_generator import HTMLGenerator


def test_generate_html_escapes_content_and_includes_stats():
    papers = [
        {
            "title": "<Test & Title>",
            "authors": "Alice & Bob",
            "year": "2023",
            "publication": "Journal <X>",
            "doi": "10.1234/example",
            "download_link": "https://example.org/paper.pdf",
        }
    ]

    html = HTMLGenerator.generate_html(papers, "abc123")

    assert "<Test & Title>" not in html
    assert "&lt;Test &amp; Title&gt;" in html
    assert "Total Papers" in html
    assert "abc123" in html
    assert "Download PDF" in html


def test_generate_html_handles_missing_fields():
    papers = [
        {
            "title": "No DOI",
            "authors": "",
            "year": "",
            "publication": "",
            "doi": "",
            "download_link": "",
        }
    ]

    html = HTMLGenerator.generate_html(papers, "user42")

    assert "Not found" in html
    assert "user42" in html


