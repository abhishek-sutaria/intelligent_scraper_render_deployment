# Semantic Scholar Profile Scraper

A Python tool that uses the official Semantic Scholar API to fetch an author's most-cited papers and generate an interactive HTML checklist.

## Features

- Pulls data directly from Semantic Scholar's API (no browser automation required)
- Always returns the **top cited** papers for each author (server-side citation sorting)
- Extracts title, authors, publication venue, publication year, citations, DOI, and open-access PDF links
- Generates a responsive HTML checklist with CSV export and download tracking
- Optional debug report with detailed scrape statistics

## Requirements

- Python 3.8+
- Internet access (for API calls)
- *(Optional)* Semantic Scholar API key for higher rate limits

## Installation

```bash
git clone <repo>
cd Information_Scraper_v2
pip install -r requirements.txt
```

## Usage

### CLI (top-cited by default)

```bash
python main.py <author_id_or_name_or_url> [options]
```

Examples:

```bash
# Fetch by author ID
python main.py 40066064

# Search by author name
python main.py "Jonah A. Berger"

# Provide API key and custom max papers
python main.py https://www.semanticscholar.org/author/Jonah-A.-Berger/40066064 --max-papers 75 --api-key YOUR_KEY
```

#### Command-line options

- `author_input` (required): Semantic Scholar author ID, profile URL, or name
- `--max-papers`: How many **top cited** papers to return (default 50)
- `--output`: Custom HTML filename
- `--api-key`: Semantic Scholar API key (optional)
- `--verbose`: Enable verbose logging
- `--debug-report`: Path to save a JSON debug report

### How to find an author ID

1. Open the Semantic Scholar profile page.
2. Look at the URL: `https://www.semanticscholar.org/author/Name/40066064`
3. The numeric portion at the end (`40066064`) is the author ID.

## Output

- **Interactive checklist** sorted by citation count (highest first)
- **Columns**: Checkbox, Sr. No, Title, Authors, Year, Publication, Citations, DOI, Download Link
- **CSV export**: Export selected papers with one click
- **Download tracking**: Remembers which PDF links you've already clicked

## Web interface

```bash
uvicorn server:app --reload
```

Then open [http://localhost:8000](http://localhost:8000), paste a Semantic Scholar author URL, and watch the progress indicator. Completed jobs provide links to the generated HTML checklist and debug report.

## Troubleshooting

- **Author not found**: Double-check the ID/URL or try searching by name.
- **No papers returned**: The author might not have indexed papers yet *or* the API temporarily rejected the request. Wait 60 seconds and try again.
- **Rate limit exceeded / Unknown failure**:
  - Without an API key the Graph API only allows a handful of requests per minute.
  - The scraper now retries with exponential backoff and serves cached data when available, but you may still need to pause between runs.
  - For uninterrupted usage, request a free API key and set `SEMANTIC_SCHOLAR_API_KEY=YOUR_KEY` (or pass `--api-key`).
- **Missing download links**: Not all papers have open-access PDFs on Semantic Scholar.

## Environment variables

- `SEMANTIC_SCHOLAR_API_KEY` (optional) – set once to avoid passing `--api-key` every run.

## License & Disclaimer

This project is provided as-is for educational and research purposes. Always respect Semantic Scholar's [API terms of service](https://www.semanticscholar.org/product/api) and rate limits when using their data.

