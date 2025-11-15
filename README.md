# Google Scholar Profile Scraper

A Python tool to scrape research papers from Google Scholar profiles and generate an interactive HTML checklist table.

## Features

- Scrapes up to 50 papers from a Google Scholar profile
- Extracts comprehensive metadata: Title, Authors, Publication Year, Publication Venue, DOI, Download Links
- Generates a beautiful, interactive HTML checklist with checkboxes
- Follows "All versions" links to find PDF download links
- Handles missing data gracefully
- Progress logging during scraping
- Export checked papers to CSV

## Requirements

- Python 3.8 or higher
- Playwright browser automation library

## Installation

1. Clone or download this repository

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

## Usage

### Basic Usage (CLI)

```bash
python main.py <user_id>
```

Example:
```bash
python main.py x8xNLZQAAAAJ
```

This will create an HTML file named `scholar_x8xNLZQAAAAJ.html` in the current directory.

### Advanced Options

```bash
# Run browser in visible mode (for debugging)
python main.py x8xNLZQAAAAJ --visible

# Specify custom output filename
python main.py x8xNLZQAAAAJ --output my_papers.html

# Limit number of papers (default: 50)
python main.py x8xNLZQAAAAJ --max-papers 25
```

### Command Line Arguments

- `user_id` (required): Google Scholar user ID (e.g., `x8xNLZQAAAAJ`)
- `--visible`: Run browser in visible mode instead of headless
- `--output`: Custom output HTML filename
- `--max-papers`: Maximum number of papers to scrape (default: 50)

## How to Find Google Scholar User ID

1. Go to the Google Scholar profile page
2. Look at the URL: `https://scholar.google.com/citations?user=USER_ID&hl=en`
3. The `USER_ID` is the part after `user=` (e.g., `x8xNLZQAAAAJ`)

## Output

The CLI generates an HTML file with:

- **Interactive Checklist**: Checkboxes to mark papers you've reviewed
- **Clean Table Layout**: All paper details in an organized table
- **Export Functionality**: Export checked papers to CSV
- **Responsive Design**: Works on desktop and mobile devices
- **Modern UI**: Beautiful gradient design with hover effects

### Table Columns

1. **Checkbox**: Select papers you've reviewed
2. **Sr. No**: Serial number
3. **Title**: Paper title
4. **Authors**: Author names
5. **Year**: Publication year
6. **Publication**: Publication venue/journal
7. **DOI**: Digital Object Identifier (if available)
8. **Download Link**: PDF download link (if found)

## Notes

- The scraper includes delays between requests to avoid rate limiting
- Some papers may not have DOI or download links available
- Large profiles may take several minutes to scrape
- The tool saves partial results if scraping is interrupted

## Troubleshooting

### "Profile not found" error
- Verify the user ID is correct
- Check if the profile is public and accessible
- Try accessing the profile URL directly in your browser

### No papers found
- The profile might be private or empty
- Check your internet connection
- Google Scholar might be blocking automated access (try again later)

### Browser installation issues
- Make sure Playwright browsers are installed: `playwright install chromium`
- On Linux, you may need additional dependencies

### Playwright "Target closed" error on macOS
If you encounter "Target page, context or browser has been closed" error on macOS:
1. Try reinstalling Playwright: `pip uninstall playwright && pip install playwright && playwright install chromium`
2. Make sure you have the latest version: `pip install --upgrade playwright`
3. On macOS, you may need to grant Terminal/IDE permissions in System Preferences > Security & Privacy
4. Try running with `--visible` flag to see if browser launches: `python main.py USER_ID --visible`
5. If issues persist, check Playwright GitHub issues for macOS-specific fixes

## Web Interface

You can also drive the scraper via a lightweight web UI.

1. Install the extra dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Start the FastAPI server:
   ```bash
   uvicorn server:app --reload
   ```
3. Open [http://localhost:8000](http://localhost:8000) in your browser.
4. Paste a Scholar profile link, select the number of papers, and watch the progress indicator.
5. When the scrape finishes, download the generated HTML checklist or the debug report from the result panel.

> **Note:** The server exposes artifacts under `/artifacts/…`. Ensure Playwright browsers are installed on the host that runs the API.

## License

This tool is provided as-is for educational and research purposes.

## Disclaimer

This tool is for personal use only. Please respect Google Scholar's terms of service and use responsibly. Consider rate limiting and don't overload their servers.

