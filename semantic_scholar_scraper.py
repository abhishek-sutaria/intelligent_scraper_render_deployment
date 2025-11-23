"""
Semantic Scholar Profile Scraper using the official API.
"""
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import quote, unquote, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from semanticscholar import SemanticScholar
from semanticscholar.SemanticScholarException import SemanticScholarException

# Suppress SSL warnings when we intentionally disable verification
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Optional Playwright import for advanced scraping
try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = None
    Page = None


class SemanticScholarScraper:
    """Scrapes Semantic Scholar author profiles for research papers via API."""

    CACHE_TTL_SECONDS = 12 * 60 * 60  # 12 hours
    CACHE_PATH = Path(__file__).parent / ".cache" / "author_cache.json"
    RATE_LIMIT_BACKOFF = (10, 30, 60)  # seconds

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_papers: int = 50,
        verbose: bool = False,
        collect_debug: bool = False,
        progress_handler: Optional[Callable[[str, int, int, float], None]] = None,
        search_buffer: int = 100,
        min_top_results: int = 50,
    ):
        self.api_key = api_key
        self.max_papers = max_papers
        self.verbose = verbose
        self.collect_debug = collect_debug
        self.progress_handler = progress_handler
        self.sch = SemanticScholar(api_key=api_key) if api_key else SemanticScholar()
        self.search_buffer = max(10, search_buffer)
        self.min_top_results = max(10, min_top_results)
        self.stats = {
            "doi_found": 0,
            "papers_found": 0,
            "download_links_found": 0,
            "api_calls": 0,
            "sorted_by_citations": True,
        }
        self.debug_records: List[Dict] = []
        self._browser: Optional[Browser] = None
        self._playwright_context = None
        self._validation_cache: Dict[str, bool] = {}  # Cache for PDF link validation

    async def _get_browser(self) -> Optional[Browser]:
        """Lazy initialization of Playwright browser."""
        if not PLAYWRIGHT_AVAILABLE:
            return None
        if self._browser is None:
            playwright = await async_playwright().start()
            self._playwright_context = playwright
            # Launch with stealth settings to avoid detection
            self._browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
        return self._browser

    async def _close_browser(self):
        """Close browser and cleanup Playwright."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright_context:
            await self._playwright_context.stop()
            self._playwright_context = None

    @staticmethod
    def extract_author_id_from_url(author_input: str) -> Optional[str]:
        """Extract author ID from Semantic Scholar profile URL or return the input."""
        if not author_input:
            return None

        candidate = author_input.strip()
        if candidate.isdigit():
            return candidate

        if "semanticscholar.org/author/" in candidate:
            try:
                parsed = urlparse(candidate)
                segments = [seg for seg in parsed.path.strip("/").split("/") if seg]
                if len(segments) >= 2:
                    slug = unquote(segments[-2])
                    slug = slug.replace("-", " ").replace("_", " ").replace(".", " ")
                    slug = slug.strip()
                    if slug:
                        return slug
                if segments and segments[-1].isdigit():
                    return segments[-1]
            except Exception:
                pass

        return candidate

    def _log(self, message: str, level: str = "INFO"):
        if not self.verbose:
            return
        prefix = {
            "INFO": "ℹ️",
            "DEBUG": "🔍",
            "WARN": "⚠️",
            "ERROR": "❌",
            "SUCCESS": "✓",
        }.get(level, "•")
        print(f"{prefix} {message}")

    def _print_progress(self, current: int, total: int, prefix: str):
        if not total:
            return
        percentage = (current / total) * 100
        bar_length = 40
        filled_length = int(bar_length * current // total)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        print(f"\r{prefix}: [{bar}] {current}/{total} ({percentage:.1f}%)", end="", flush=True)
        if current >= total:
            print()
        if self.progress_handler:
            try:
                self.progress_handler(self._normalize_stage_label(prefix), current, total, percentage)
            except Exception:
                pass

    @staticmethod
    def _normalize_stage_label(prefix: str) -> str:
        label = prefix.strip() if prefix else "Processing"
        mapping = {
            "🔍 Fetching author data": "Fetching author data",
            "📄 Fetching papers": "Fetching papers",
            "📊 Sorting papers": "Sorting papers",
            "📝 Processing papers": "Processing papers",
        }
        return mapping.get(label, label.lstrip("🔍📄📊📝 ").strip() or "Processing")

    async def scrape_profile(self, author_input: str) -> List[Dict]:
        """Scrape papers for an author (sorted by citation count descending)."""
        papers: List[Dict] = []
        if self.collect_debug:
            self.debug_records = []

        print(f"\n📊 Starting Semantic Scholar scrape (target: {self.max_papers})\n")

        try:
            author, author_id = await self._resolve_author(author_input)
        except Exception as exc:
            print(f"\n❌ Error resolving author: {exc}")
            return papers

        self._print_progress(0, 100, "📄 Fetching papers")
        all_papers = await self._fetch_author_papers(author_id)

        if not all_papers:
            print("\n⚠️  No papers found for this author.")
            return papers

        self._print_progress(20, 100, "📊 Sorting papers")
        all_papers.sort(
            key=lambda paper: getattr(paper, "citationCount", 0) or 0,
            reverse=True,
        )
        selected = all_papers[: self.max_papers]
        self._log(f"Selected top {len(selected)} papers by citations", "SUCCESS")

        self._print_progress(30, 100, "📝 Processing papers")
        for idx, paper in enumerate(selected, start=1):
            try:
                paper_dict = await self._extract_paper_metadata(paper)
                if not paper_dict:
                    continue
                papers.append(paper_dict)
                if self.collect_debug:
                    self.debug_records.append(
                        {
                            "title": paper_dict.get("title", ""),
                            "paper_id": getattr(paper, "paperId", ""),
                            "citations": paper_dict.get("citations", "0"),
                            "doi": paper_dict.get("doi", ""),
                            "download_link": paper_dict.get("download_link", ""),
                            "errors": [],
                        }
                    )
            except Exception as exc:  # pylint: disable=broad-except
                self._log(f"Error processing paper {idx}: {exc}", "WARN")
                if self.collect_debug:
                    self.debug_records.append(
                        {
                            "title": getattr(paper, "title", "") or "",
                            "paper_id": getattr(paper, "paperId", ""),
                            "citations": getattr(paper, "citationCount", "") or "",
                            "doi": "",
                            "download_link": "",
                            "errors": [str(exc)],
                        }
                    )
            finally:
                self._print_progress(30 + int((idx / len(selected)) * 60), 100, "📝 Processing papers")

        self.stats["papers_found"] = len(papers)
        print(f"\n✓ Successfully processed {len(papers)} papers (sorted by citations).\n")
        self._print_progress(100, 100, "Completed")
        return papers

    async def _resolve_author(self, author_input: str):
        """Resolve input to an author object and numeric ID."""
        self._print_progress(0, 100, "🔍 Fetching author data")
        candidate = self.extract_author_id_from_url(author_input)
        try:
            if candidate and candidate.isdigit():
                author = await asyncio.to_thread(self.sch.get_author, candidate)
                self.stats["api_calls"] += 1
                self._log(f"Author found by ID: {author.name}", "SUCCESS")
                return author, candidate

            search_query = candidate if candidate else author_input
            self._log(f"Searching for author by name: {search_query}", "INFO")
            search_results = await asyncio.to_thread(
                lambda: self.sch.search_author(search_query, limit=5)
            )
            self.stats["api_calls"] += 1
            if not search_results:
                raise ValueError("Author not found.")
            author = search_results[0]
            self._log(f"Using author: {author.name}", "SUCCESS")
            return author, str(author.authorId)
        except Exception as exc:
            raise ValueError(f"Unable to fetch author information: {exc}") from exc

    async def _fetch_author_papers(self, author_id: str) -> List:
        """Retrieve author papers and sort by citations to get top-cited papers."""
        # Fetch a large pool to ensure we get top-cited papers
        # get_author_papers doesn't support sorting, so we fetch many and sort ourselves
        target_count = max(self.max_papers, self.search_buffer, self.min_top_results)
        # Fetch up to 500 papers to ensure we capture top-cited ones
        fetch_limit = min(500, max(100, target_count * 10))
        fields = [
            "paperId",
            "title",
            "year",
            "venue",
            "citationCount",
            "authors",
            "externalIds",
            "openAccessPdf",
        ]

        def collect() -> List:
            # Use get_author_papers - it doesn't support sorting but returns all papers
            # We'll sort by citations after fetching
            results = self.sch.get_author_papers(
                author_id,
                fields=fields,
                limit=fetch_limit,
            )
            papers: List = []
            # PaginatedResults has .items attribute
            if hasattr(results, 'items'):
                papers = list(results.items)
            elif hasattr(results, '__iter__'):
                papers = list(results)
            return papers

        attempts = len(self.RATE_LIMIT_BACKOFF) + 1
        for attempt in range(attempts):
            try:
                papers = await asyncio.to_thread(collect)
                self.stats["api_calls"] += 1
                
                # Sort by citation count descending to get top-cited papers
                papers.sort(
                    key=lambda paper: getattr(paper, "citationCount", 0) or 0,
                    reverse=True,
                )
                
                # Return the top papers up to target_count
                return papers[:target_count]
            except SemanticScholarException as exc:
                status = getattr(exc, "status", None)
                if status == 429 and attempt < len(self.RATE_LIMIT_BACKOFF):
                    wait = self.RATE_LIMIT_BACKOFF[attempt]
                    self._log(f"Rate limit reached. Retrying in {wait}s…", "WARN")
                    time.sleep(wait)
                    continue
                raise
            except Exception as exc:
                self._log(f"Error fetching papers: {exc}", "ERROR")
                break

        return []

    def _load_cached_results(self, author_id: str, allow_stale: bool = False) -> Optional[List[Dict]]:
        try:
            cache_raw = self.CACHE_PATH.read_text()
            cache = json.loads(cache_raw)
        except FileNotFoundError:
            return None
        except Exception as exc:
            self._log(f"Failed to read cache: {exc}", "WARN")
            return None

        entry = cache.get(author_id)
        if not entry:
            return None

        timestamp = entry.get("timestamp", 0)
        age = time.time() - timestamp
        if age > self.CACHE_TTL_SECONDS and not allow_stale:
            return None

        return entry.get("papers", [])

    def _save_cached_results(self, author_id: str, papers: List[Dict]) -> None:
        try:
            cache = json.loads(self.CACHE_PATH.read_text())
        except FileNotFoundError:
            cache = {}
        except Exception:
            cache = {}

        self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cache[author_id] = {
            "timestamp": time.time(),
            "papers": papers,
        }
        self.CACHE_PATH.write_text(json.dumps(cache, indent=2))

    def _create_semantic_scholar_url(self, paper_id: str, title: str = "") -> str:
        """
        Create a proper Semantic Scholar URL with title slug.
        
        Format: https://www.semanticscholar.org/paper/{title-slug}/{paper_id}
        
        Args:
            paper_id: Semantic Scholar paper ID
            title: Paper title (optional, for creating URL-friendly slug)
            
        Returns:
            Properly formatted Semantic Scholar URL
        """
        if title:
            # Create URL-friendly slug from title
            # Convert to lowercase
            slug = title.lower()
            # Replace spaces and underscores with hyphens
            slug = re.sub(r'[\s_]+', '-', slug)
            # Keep common punctuation that Semantic Scholar uses (colons, etc.)
            # Remove only truly problematic characters, keep hyphens and common punctuation
            slug = re.sub(r'[^a-z0-9\-\:\.]', '', slug)
            # Replace multiple consecutive hyphens with single hyphen
            slug = re.sub(r'-+', '-', slug)
            # Remove leading/trailing hyphens
            slug = slug.strip('-')
            # Limit length (Semantic Scholar typically uses ~50-60 chars)
            if len(slug) > 60:
                slug = slug[:60].rstrip('-')
            # URL-encode the slug (handles special characters like colons as %3A)
            slug = quote(slug, safe='-')
            return f"https://www.semanticscholar.org/paper/{slug}/{paper_id}"
        else:
            # Fallback to ID-only format if no title
            return f"https://www.semanticscholar.org/paper/{paper_id}"

    async def _scroll_and_reveal_content(self, page, paper_id: str) -> None:
        """Scroll to trigger lazy loading of PDF buttons."""
        try:
            # Scroll to PDF button sections
            pdf_sections = await page.query_selector_all(
                '[class*="pdf"], [class*="download"], [class*="alternate"], [id*="pdf"], [id*="download"]'
            )
            if pdf_sections:
                for section in pdf_sections[:3]:  # Limit to first 3 sections
                    try:
                        await section.scroll_into_view_if_needed(timeout=1000)
                        await page.wait_for_timeout(300)  # Wait for lazy loading
                    except Exception:
                        continue
            # Scroll back to top
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(200)
        except Exception as exc:
            if self.verbose:
                self._log(f"Error scrolling for {paper_id}: {exc}", "DEBUG")

    async def _click_dropdowns_and_extract(self, page, paper_id: str) -> None:
        """Click dropdown menus to reveal hidden PDF links."""
        try:
            # Find dropdown buttons (limit to first 3 to avoid too many clicks)
            dropdown_selectors = [
                'button[aria-expanded="false"]',
                '.dropdown-toggle',
                '[data-toggle="dropdown"]',
                'button.alternate-sources__dropdown-button',
                '.alternate-sources button'
            ]
            
            clicked_count = 0
            for selector in dropdown_selectors:
                if clicked_count >= 3:  # Limit to 3 dropdowns
                    break
                try:
                    dropdowns = await page.query_selector_all(selector)
                    for dropdown in dropdowns[:2]:  # Max 2 per selector type
                        if clicked_count >= 3:
                            break
                        try:
                            # Check if dropdown is visible and clickable
                            is_visible = await dropdown.is_visible()
                            if is_visible:
                                await dropdown.click(timeout=2000)
                                await page.wait_for_timeout(500)  # Wait for dropdown to open
                                clicked_count += 1
                                if self.verbose:
                                    self._log(f"Clicked dropdown for {paper_id}", "DEBUG")
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as exc:
            if self.verbose:
                self._log(f"Error clicking dropdowns for {paper_id}: {exc}", "DEBUG")
    
    async def _extract_from_modals(self, page, paper_id: str) -> List[str]:
        """Extract PDF links from modals/popups."""
        found_links = []
        try:
            # Look for modal triggers
            modal_triggers = await page.query_selector_all(
                'button[data-target*="modal"], button[data-toggle="modal"], '
                'a[data-target*="modal"], [class*="modal-trigger"]'
            )
            
            for trigger in modal_triggers[:2]:  # Limit to 2 modals
                try:
                    if await trigger.is_visible():
                        await trigger.click(timeout=3000)
                        await page.wait_for_timeout(1000)  # Wait for modal to open
                        
                        # Extract PDF links from modal
                        modal_pdf_links = await page.query_selector_all(
                            '.modal a[href*=".pdf"], [role="dialog"] a[href*=".pdf"]'
                        )
                        for link in modal_pdf_links:
                            href = await link.get_attribute('href')
                            if href and href.startswith('http') and 'semanticscholar.org' not in href:
                                found_links.append(href)
                        
                        # Close modal
                        close_buttons = await page.query_selector_all(
                            '.modal [data-dismiss="modal"], .modal .close, button[aria-label="Close"]'
                        )
                        if close_buttons:
                            await close_buttons[0].click(timeout=1000)
                            await page.wait_for_timeout(300)
                except Exception:
                    continue
        except Exception as exc:
            if self.verbose:
                self._log(f"Error extracting from modals for {paper_id}: {exc}", "DEBUG")
        return found_links

    async def _validate_pdf_link(self, pdf_url: str) -> bool:
        """Validate that a PDF link is accessible (not 404/dead) with caching and Content-Type checking."""
        if not pdf_url or not pdf_url.startswith('http'):
            return False
        
        # Check cache first
        if pdf_url in self._validation_cache:
            return self._validation_cache[pdf_url]
        
        try:
            # Use HEAD request to check if link is accessible (faster than GET)
            # First try with SSL verification
            try:
                response = await asyncio.to_thread(
                    requests.head,
                    pdf_url,
                    allow_redirects=True,
                    timeout=5,
                    verify=True,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (compatible; ScholarScraper/1.0)'
                    }
                )
            except requests.exceptions.SSLError:
                # If SSL verification fails, try without verification (some sites have self-signed certs)
                response = await asyncio.to_thread(
                    requests.head,
                    pdf_url,
                    allow_redirects=True,
                    timeout=5,
                    verify=False,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (compatible; ScholarScraper/1.0)'
                    }
                )
            
            # Check status code (200-399 is valid)
            is_valid_status = 200 <= response.status_code < 400
            
            # Check Content-Type header for PDF (if available)
            content_type = response.headers.get('Content-Type', '').lower()
            is_pdf_content = 'application/pdf' in content_type or 'pdf' in content_type
            
            # Consider valid if status is good AND (Content-Type indicates PDF OR URL ends with .pdf)
            is_valid = is_valid_status and (is_pdf_content or pdf_url.lower().endswith('.pdf'))
            
            # Cache the result
            self._validation_cache[pdf_url] = is_valid
            
            if self.verbose:
                self._log(f"PDF link validation: {pdf_url[:50]}... -> {response.status_code} (Content-Type: {content_type[:30]}) ({'valid' if is_valid else 'invalid'})", "DEBUG")
            return is_valid
        except requests.exceptions.Timeout:
            if self.verbose:
                self._log(f"PDF link validation timeout: {pdf_url[:50]}...", "DEBUG")
            self._validation_cache[pdf_url] = False
            return False
        except requests.exceptions.RequestException as exc:
            if self.verbose:
                self._log(f"PDF link validation error: {pdf_url[:50]}... -> {exc}", "DEBUG")
            self._validation_cache[pdf_url] = False
            return False
        except Exception as exc:
            if self.verbose:
                self._log(f"PDF link validation unexpected error: {pdf_url[:50]}... -> {exc}", "DEBUG")
            self._validation_cache[pdf_url] = False
            return False

    async def _extract_pdf_from_paper_page(self, paper_id: str, title: str = "") -> str:
        """Scrape Semantic Scholar paper page using Playwright to find alternate PDF sources."""
        paper_url = self._create_semantic_scholar_url(paper_id, title)
        
        # Diagnostic logging
        print(f"[PDF Extraction] 🔍 Attempting PDF extraction for paper: {paper_id}")
        print(f"[PDF Extraction] 📄 Paper URL: {paper_url}")
        print(f"[PDF Extraction] 🤖 Playwright available: {PLAYWRIGHT_AVAILABLE}")
        
        # Try Playwright first if available
        if PLAYWRIGHT_AVAILABLE:
            print(f"[PDF Extraction] 🚀 Starting Playwright browser for {paper_id}")
            try:
                # Use context manager approach (recommended by Playwright)
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(
                        headless=True,
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--disable-dev-shm-usage',
                            '--no-sandbox',
                        ]
                    )
                    
                    context = await browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    page = await context.new_page()
                    
                    # Remove webdriver detection
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                    """)
                    
                    # Navigate to the page with better error handling
                    try:
                        # Use 'load' which is less strict than networkidle
                        response = await page.goto(paper_url, wait_until="load", timeout=30000)
                        if not response or response.status >= 400:
                            if self.verbose:
                                self._log(f"Page returned status {response.status if response else 'None'} for {paper_id}", "DEBUG")
                            return ""
                    except Exception as nav_exc:
                        if self.verbose:
                            self._log(f"Navigation error for {paper_id}: {nav_exc}", "DEBUG")
                        return ""
                    
                    # Wait for page to fully load and check if we're on a challenge page
                    try:
                        # Wait for page to settle and check for PDF-related elements
                        await asyncio.sleep(1)
                        
                        # Try to wait for PDF-related elements to appear (better than fixed sleep)
                        try:
                            await asyncio.wait_for(
                                page.wait_for_selector(
                                    'a[data-heap-direct-pdf-link="true"], .alternate-sources__dropdown-button, a[href*=".pdf"]',
                                    timeout=3000
                                ),
                                timeout=3.5
                            )
                        except (asyncio.TimeoutError, Exception):
                            # Elements might not be present, continue anyway
                            pass
                        
                        # Try to get title - this will fail if page is closed
                        try:
                            title = await asyncio.wait_for(page.title(), timeout=5.0)
                        except asyncio.TimeoutError:
                            if self.verbose:
                                self._log(f"Timeout getting page title for {paper_id}", "DEBUG")
                            return ""
                        except Exception as title_err:
                            if self.verbose:
                                self._log(f"Error getting page title for {paper_id}: {title_err}", "DEBUG")
                            return ""
                        
                        if 'verification' in title.lower() or 'challenge' in title.lower():
                            if self.verbose:
                                self._log(f"Challenge page detected for {paper_id}, waiting longer...", "DEBUG")
                            # Wait longer for challenge to complete
                            await page.wait_for_timeout(5000)
                            try:
                                title = await page.title()
                                if 'verification' in title.lower():
                                    if self.verbose:
                                        self._log(f"Still on challenge page for {paper_id}, skipping", "DEBUG")
                                    return ""
                            except Exception:
                                return ""
                    except Exception as title_exc:
                        if self.verbose:
                            self._log(f"Error checking page title for {paper_id}: {title_exc}", "DEBUG")
                        return ""
                    
                    # Extract PDF links from multiple page states
                    found_links = []
                    
                    print(f"[PDF Extraction] 📋 Extracting PDF links from page states...")
                    
                    # State 1: Initial load (before interactions)
                    initial_links = await self._extract_pdf_links_from_page(page, paper_id, "initial")
                    print(f"[PDF Extraction] 📌 Initial state found {len(initial_links)} links")
                    found_links.extend(initial_links)
                    
                    # State 2: After scrolling (reveal lazy-loaded content)
                    await self._scroll_and_reveal_content(page, paper_id)
                    scroll_links = await self._extract_pdf_links_from_page(page, paper_id, "after_scroll")
                    print(f"[PDF Extraction] 📜 After scroll found {len(scroll_links)} links")
                    found_links.extend(scroll_links)
                    
                    # State 3: After clicking dropdowns
                    await self._click_dropdowns_and_extract(page, paper_id)
                    dropdown_links = await self._extract_pdf_links_from_page(page, paper_id, "after_dropdowns")
                    print(f"[PDF Extraction] 📂 After dropdowns found {len(dropdown_links)} links")
                    found_links.extend(dropdown_links)
                    
                    # Remove duplicates while preserving order
                    seen = set()
                    unique_links = []
                    for link in found_links:
                        if link not in seen:
                            seen.add(link)
                            unique_links.append(link)
                    found_links = unique_links
                    
                    # Extract from modals (Phase 2)
                    modal_links = await self._extract_from_modals(page, paper_id)
                    print(f"[PDF Extraction] 🪟 Modals found {len(modal_links)} links")
                    found_links.extend(modal_links)
                    
                    # Remove duplicates again
                    seen = set(unique_links)
                    for link in modal_links:
                        if link not in seen:
                            seen.add(link)
                            found_links.append(link)
                    
                    # Extract external sources from page HTML (arXiv, DOI)
                    external_links = await self._extract_external_sources_from_page(page, paper_id)
                    print(f"[PDF Extraction] 🔗 External sources found {len(external_links)} links")
                    found_links.extend(external_links)
                    
                    # Final deduplication
                    seen = set()
                    final_links = []
                    for link in found_links:
                        if link not in seen:
                            seen.add(link)
                            final_links.append(link)
                    found_links = final_links
                    print(f"[PDF Extraction] ✅ Total unique links found: {len(found_links)}")
                    
                    # Validate and return first working PDF link found (parallel validation with early exit)
                    if found_links:
                        print(f"[PDF Extraction] 🔍 Validating {len(found_links)} links...")
                        # Validate up to 3 links in parallel for performance
                        validation_tasks = []
                        for pdf_link in found_links[:3]:  # Limit to first 3 for parallel validation
                            validation_tasks.append(self._validate_pdf_link(pdf_link))
                        
                        # Run validations in parallel
                        validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
                        
                        # Check results and return first valid link
                        for idx, is_valid in enumerate(validation_results):
                            pdf_link = found_links[idx]
                            print(f"[PDF Extraction] ✓ Link {idx+1}: {pdf_link[:70]}... -> {'VALID' if is_valid is True else 'INVALID'}")
                            if is_valid is True:  # Explicitly check for True (not just truthy)
                                if self.verbose:
                                    self._log(f"Found valid PDF from paper page: {pdf_link[:60]}...", "SUCCESS")
                                print(f"[PDF Extraction] ✅ Returning valid PDF link for {paper_id}")
                                return pdf_link
                        
                        # If parallel validation didn't find valid link, try remaining links sequentially
                        for pdf_link in found_links[3:]:
                            is_valid = await self._validate_pdf_link(pdf_link)
                            print(f"[PDF Extraction] ✓ Link: {pdf_link[:70]}... -> {'VALID' if is_valid else 'INVALID'}")
                            if is_valid:
                                if self.verbose:
                                    self._log(f"Found valid PDF from paper page: {pdf_link[:60]}...", "SUCCESS")
                                print(f"[PDF Extraction] ✅ Returning valid PDF link for {paper_id}")
                                return pdf_link
                            elif self.verbose:
                                self._log(f"PDF link failed validation (404/dead): {pdf_link[:60]}...", "DEBUG")
                        
                        # If all links failed validation, return empty to use Semantic Scholar page
                        print(f"[PDF Extraction] ❌ All {len(found_links)} links failed validation for {paper_id}")
                        if self.verbose:
                            self._log(f"All PDF links failed validation for {paper_id}, using fallback", "DEBUG")
                        return ""
                    
                    print(f"[PDF Extraction] ❌ No PDF links found when scraping {paper_id}")
                    if self.verbose:
                        self._log(f"No PDF links found when scraping {paper_id}", "DEBUG")
                    
            except Exception as exc:
                import traceback
                error_details = traceback.format_exc()
                error_type = type(exc).__name__
                
                # Always log errors for debugging
                print(f"\n[PDF Extraction] ❌ Playwright scraping failed for {paper_id}")
                print(f"[PDF Extraction] Error type: {error_type}")
                print(f"[PDF Extraction] Error message: {exc}")
                if self.verbose:
                    print(f"[PDF Extraction] Full traceback:\n{error_details}")
                    self._log(f"Error scraping paper page {paper_id}: {exc}", "DEBUG")
                    self._log(f"Error details: {error_details}", "DEBUG")
                elif "TargetClosedError" in error_type:
                    # This is a known compatibility issue - log it
                    print(f"⚠️  Playwright compatibility issue detected. Consider upgrading Playwright: pip install --upgrade playwright")
                
                # Context manager will cleanup automatically
        
            # Fallback: return empty string (will use Semantic Scholar page link)
            print(f"[PDF Extraction] ⚠️  Playwright not available or failed, returning empty for {paper_id}")
            return ""
    
    async def _extract_pdf_links_from_page(self, page, paper_id: str, state: str) -> List[str]:
        """Extract PDF links from page using all strategies."""
        found_links = []
        try:
            # Strategy 1: Look for data-heap-direct-pdf-link="true"
            heap_links = await page.query_selector_all('a[data-heap-direct-pdf-link="true"]')
            for link in heap_links:
                try:
                    href = await link.get_attribute('href')
                    if href and href.startswith('http') and '.pdf' in href.lower():
                        if 'semanticscholar.org' not in href:
                            found_links.append(href)
                except Exception:
                    continue
            
            # Strategy 2: Look for alternate-sources buttons
            alt_links = await page.query_selector_all('a.alternate-sources__dropdown-button')
            for link in alt_links:
                try:
                    href = await link.get_attribute('href')
                    if href and href.startswith('http') and '.pdf' in href.lower():
                        if 'semanticscholar.org' not in href:
                            found_links.append(href)
                except Exception:
                    continue
            
            # Strategy 3: Look for any links with .pdf extension
            all_links = await page.query_selector_all('a[href*=".pdf"]')
            for link in all_links:
                try:
                    href = await link.get_attribute('href')
                    if href and href.startswith('http') and 'semanticscholar.org' not in href:
                        found_links.append(href)
                except Exception:
                    continue
            
            # Strategy 4: Look for PDF buttons by aria-label/title attributes
            pdf_buttons = await page.query_selector_all(
                'button[aria-label*="PDF"], button[aria-label*="pdf"], '
                'button[title*="PDF"], button[title*="pdf"], '
                'a[aria-label*="PDF"], a[aria-label*="pdf"]'
            )
            for button in pdf_buttons:
                try:
                    href = await button.get_attribute('href')
                    if href and href.startswith('http') and '.pdf' in href.lower():
                        if 'semanticscholar.org' not in href:
                            found_links.append(href)
                    # Check data attributes
                    for attr in ['data-href', 'data-url', 'data-pdf-url', 'data-download-url']:
                        data_url = await button.get_attribute(attr)
                        if data_url and data_url.startswith('http') and '.pdf' in data_url.lower():
                            if 'semanticscholar.org' not in data_url:
                                found_links.append(data_url)
                except Exception:
                    continue
            
            # Strategy 5: Extract PDF URLs from onclick handlers
            onclick_elements = await page.query_selector_all(
                'button[onclick*="pdf"], button[onclick*="PDF"], '
                'a[onclick*="pdf"], a[onclick*="PDF"]'
            )
            for element in onclick_elements:
                try:
                    onclick = await element.get_attribute('onclick') or ''
                    # Extract URLs from onclick JavaScript
                    import re
                    urls = re.findall(r'https?://[^\s"\'<>\)]+\.pdf', onclick, re.IGNORECASE)
                    for url in urls:
                        if 'semanticscholar.org' not in url:
                            found_links.append(url)
                except Exception:
                    continue
            
            # Strategy 6: Look for links/buttons with PDF-related text content
            try:
                # Get all links and buttons, then filter by text content
                all_elements = await page.query_selector_all('a, button')
                for element in all_elements:
                    try:
                        text = await element.inner_text()
                        if text and ('pdf' in text.lower() or 'download' in text.lower()):
                            href = await element.get_attribute('href')
                            if href and href.startswith('http') and '.pdf' in href.lower():
                                if 'semanticscholar.org' not in href:
                                    found_links.append(href)
                    except Exception:
                        continue
            except Exception:
                pass
                
        except Exception as extract_exc:
            if self.verbose:
                self._log(f"Error extracting links for {paper_id} (state: {state}): {extract_exc}", "DEBUG")
        
        return found_links
    
    async def _extract_external_sources_from_page(self, page, paper_id: str) -> List[str]:
        """Extract arXiv and DOI links from page HTML."""
        found_links = []
        try:
            # Extract arXiv links
            arxiv_links = await page.query_selector_all('a[href*="arxiv.org"]')
            for link in arxiv_links:
                try:
                    href = await link.get_attribute('href')
                    if href and 'arxiv.org' in href:
                        # Convert to PDF URL if it's an abstract page
                        if '/abs/' in href:
                            arxiv_id = href.split('/abs/')[-1].split('/')[0]
                            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                            found_links.append(pdf_url)
                        elif '/pdf/' in href:
                            found_links.append(href)
                except Exception:
                    continue
            
            # Extract DOI links (might lead to PDFs)
            doi_links = await page.query_selector_all('a[href*="doi.org"], a[href*="dx.doi.org"]')
            for link in doi_links[:5]:  # Limit to first 5 DOI links
                try:
                    href = await link.get_attribute('href')
                    if href and ('doi.org' in href or 'dx.doi.org' in href):
                        # DOI links might redirect to PDFs, but we'll validate them
                        found_links.append(href)
                except Exception:
                    continue
        except Exception as exc:
            if self.verbose:
                self._log(f"Error extracting external sources for {paper_id}: {exc}", "DEBUG")
        return found_links
    
    async def _extract_arxiv_pdf(self, paper) -> Optional[str]:
        """Convert arXiv ID to PDF URL."""
        try:
            external_ids = getattr(paper, "externalIds", {}) or {}
            if isinstance(external_ids, dict):
                arxiv_id = external_ids.get("ArXiv", "") or external_ids.get("arXiv", "") or ""
                if arxiv_id:
                    # Clean arXiv ID (remove version number if present)
                    arxiv_id = arxiv_id.split('v')[0]
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    # Validate the arXiv PDF link
                    if await self._validate_pdf_link(pdf_url):
                        if self.verbose:
                            self._log(f"Found valid arXiv PDF: {pdf_url[:60]}...", "SUCCESS")
                        return pdf_url
            return None
        except Exception as exc:
            if self.verbose:
                self._log(f"Error extracting arXiv PDF: {exc}", "DEBUG")
            return None
    
    async def _extract_doi_pdf(self, paper) -> Optional[str]:
        """Find PDF via DOI using Unpaywall API (legitimate open-access only)."""
        try:
            external_ids = getattr(paper, "externalIds", {}) or {}
            if isinstance(external_ids, dict):
                doi = external_ids.get("DOI", "") or ""
                if doi:
                    print(f"[Unpaywall] 🔍 Checking DOI: {doi}")
                    # Clean DOI - ensure it starts with 10.
                    if not doi.startswith("10."):
                        doi = f"10.{doi}" if not doi.startswith("10.") else doi
                    
                    # Try Unpaywall API (free, legitimate, open-access only)
                    # Email is required by Unpaywall for their records (not verified)
                    unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=scraper@scholar-scraper.local"
                    try:
                        response = await asyncio.to_thread(
                            requests.get,
                            unpaywall_url,
                            timeout=5,
                            headers={
                                'User-Agent': 'Mozilla/5.0 (compatible; ScholarScraper/1.0)',
                                'Accept': 'application/json'
                            }
                        )
                        if response.status_code == 200:
                            print(f"[Unpaywall] ✅ API response OK for DOI {doi}")
                            data = response.json()
                            # Check for open-access PDF location
                            best_oa = data.get('best_oa_location')
                            is_oa = data.get('is_oa', False)
                            print(f"[Unpaywall] 📊 Paper is_oa={is_oa}, best_oa_location={'present' if best_oa else 'missing'}")
                            if best_oa and best_oa.get('url_for_pdf'):
                                pdf_url = best_oa['url_for_pdf']
                                print(f"[Unpaywall] 🔗 Found PDF URL: {pdf_url[:70]}...")
                                # Validate the PDF link
                                is_valid = await self._validate_pdf_link(pdf_url)
                                print(f"[Unpaywall] ✓ Validation result: {'VALID' if is_valid else 'INVALID'}")
                                if is_valid:
                                    if self.verbose:
                                        self._log(f"Found open-access PDF via Unpaywall: {pdf_url[:60]}...", "SUCCESS")
                                    print(f"[Unpaywall] ✅ Returning valid PDF link")
                                    return pdf_url
                                elif self.verbose:
                                    self._log(f"Unpaywall PDF link failed validation: {pdf_url[:60]}...", "DEBUG")
                            elif self.verbose:
                                if not is_oa:
                                    print(f"[Unpaywall] ⚠️  Paper with DOI {doi} is not open-access")
                                    self._log(f"Paper with DOI {doi} is not open-access", "DEBUG")
                    except requests.exceptions.Timeout:
                        if self.verbose:
                            self._log(f"Unpaywall API timeout for DOI {doi}", "DEBUG")
                    except requests.exceptions.RequestException as exc:
                        if self.verbose:
                            self._log(f"Unpaywall API error for {doi}: {exc}", "DEBUG")
                    except Exception as exc:
                        if self.verbose:
                            self._log(f"Error parsing Unpaywall response for {doi}: {exc}", "DEBUG")
                    
                    # Fallback: Try DOI.org redirect (may lead to publisher PDF)
                    # Note: Most DOIs redirect to publisher pages, not direct PDFs
                    # But we can check if the redirect leads to a PDF
                    doi_url = f"https://doi.org/{doi}"
                    try:
                        response = await asyncio.to_thread(
                            requests.head,
                            doi_url,
                            allow_redirects=True,
                            timeout=3,
                            headers={'User-Agent': 'Mozilla/5.0 (compatible; ScholarScraper/1.0)'}
                        )
                        final_url = response.url
                        content_type = response.headers.get('Content-Type', '').lower()
                        # Check if redirect leads to PDF
                        if 'application/pdf' in content_type or final_url.lower().endswith('.pdf'):
                            if await self._validate_pdf_link(final_url):
                                if self.verbose:
                                    self._log(f"Found PDF via DOI.org redirect: {final_url[:60]}...", "SUCCESS")
                                return final_url
                    except Exception:
                        # DOI.org redirect check is optional, fail silently
                        pass
                    
            return None
        except Exception as exc:
            if self.verbose:
                self._log(f"Error extracting DOI PDF: {exc}", "DEBUG")
            return None

    async def _extract_paper_metadata(self, paper) -> Optional[Dict]:
        """Convert an API paper object into the structure used by the HTML generator."""
        try:
            paper_id = getattr(paper, "paperId", "") or ""
            title = getattr(paper, "title", "") or ""
            
            print(f"\n[Paper Processing] 📄 Processing paper: {title[:60]}...")
            print(f"[Paper Processing] 🆔 Paper ID: {paper_id}")
            
            authors = ", ".join(
                author.name if hasattr(author, "name") else str(author)
                for author in getattr(paper, "authors", []) or []
            )
            year = str(getattr(paper, "year", "") or "")
            publication = getattr(paper, "venue", "") or ""
            citations = str(getattr(paper, "citationCount", "") or "0")

            doi = ""
            external_ids = getattr(paper, "externalIds", {}) or {}
            if isinstance(external_ids, dict):
                doi = external_ids.get("DOI", "") or ""
                if doi and not doi.startswith("10."):
                    doi = f"10.{doi}" if not doi.startswith("10.") else doi
            if doi:
                print(f"[Paper Processing] 🔖 DOI found: {doi}")
                self.stats["doi_found"] += 1

            download_link = ""
            open_access_pdf = getattr(paper, "openAccessPdf", None)
            
            print(f"[Paper Processing] 📥 Checking openAccessPdf from API...")
            # Debug: log what we're getting
            if open_access_pdf:
                print(f"[Paper Processing] ✅ openAccessPdf present: {type(open_access_pdf)}")
                if self.verbose:
                    self._log(f"openAccessPdf type: {type(open_access_pdf)}, value: {open_access_pdf}", "DEBUG")
            else:
                print(f"[Paper Processing] ❌ No openAccessPdf in API response")
            
            if open_access_pdf:
                # Handle both dict and object cases
                if isinstance(open_access_pdf, dict):
                    download_link = open_access_pdf.get("url", "") or ""
                elif hasattr(open_access_pdf, "url"):
                    download_link = getattr(open_access_pdf, "url", "") or ""
                elif isinstance(open_access_pdf, str):
                    # Sometimes it might be a direct URL string
                    download_link = open_access_pdf
                
                # Only count if we have a non-empty URL
                if download_link and download_link.strip():
                    print(f"[Paper Processing] 🔗 openAccessPdf URL: {download_link[:70]}...")
                    # Validate the link before counting it
                    is_valid = await self._validate_pdf_link(download_link)
                    print(f"[Paper Processing] ✓ Validation result: {'VALID' if is_valid else 'INVALID'}")
                    if is_valid:
                        print(f"[Paper Processing] ✅ Using openAccessPdf URL")
                        self.stats["download_links_found"] += 1
                    else:
                        # Link is dead/invalid, reset to empty
                        print(f"[Paper Processing] ❌ openAccessPdf URL failed validation, trying alternatives...")
                        if self.verbose:
                            self._log(f"openAccessPdf URL failed validation: {download_link[:60]}...", "DEBUG")
                        download_link = ""
                else:
                    # Reset to empty string if URL is empty/missing
                    download_link = ""
                    print(f"[Paper Processing] ⚠️  openAccessPdf present but URL is empty, trying alternatives...")
                    if self.verbose:
                        self._log(f"openAccessPdf present but URL is empty. Status: {open_access_pdf.get('status', 'N/A') if isinstance(open_access_pdf, dict) else 'N/A'}", "DEBUG")
            
            # If no PDF link found, try fetching full paper details for alternate sources
            paper_id = getattr(paper, "paperId", "")
            if not download_link and paper_id:
                try:
                    # Fetch full paper details which may include alternate PDF sources
                    full_paper = await asyncio.to_thread(
                        self.sch.get_paper,
                        paper_id,
                        fields=["openAccessPdf", "externalIds"]
                    )
                    self.stats["api_calls"] += 1
                    
                    # Check if full paper has openAccessPdf
                    full_oa_pdf = getattr(full_paper, "openAccessPdf", None)
                    if full_oa_pdf:
                        if isinstance(full_oa_pdf, dict):
                            full_url = full_oa_pdf.get("url", "") or ""
                        elif hasattr(full_oa_pdf, "url"):
                            full_url = getattr(full_oa_pdf, "url", "") or ""
                        else:
                            full_url = ""
                        
                        if full_url and full_url.strip():
                            # Validate the link before using it
                            if await self._validate_pdf_link(full_url):
                                download_link = full_url
                                self.stats["download_links_found"] += 1
                                if self.verbose:
                                    self._log(f"Found valid PDF link from full paper details: {full_url[:60]}...", "SUCCESS")
                            else:
                                if self.verbose:
                                    self._log(f"PDF link from full paper details failed validation: {full_url[:60]}...", "DEBUG")
                except Exception as exc:
                    # Silently fail - alternate source fetch is optional
                    if self.verbose:
                        self._log(f"Could not fetch full paper details for alternate sources: {exc}", "DEBUG")
            
            # Phase 3: Try arXiv PDF conversion (fast, no API calls)
            if not download_link:
                print(f"[PDF Extraction] 🔬 Trying arXiv extraction for {paper_id}")
                arxiv_pdf = await self._extract_arxiv_pdf(paper)
                if arxiv_pdf:
                    print(f"[PDF Extraction] ✅ Found arXiv PDF: {arxiv_pdf[:60]}...")
                    download_link = arxiv_pdf
                    self.stats["download_links_found"] += 1
                else:
                    print(f"[PDF Extraction] ❌ No arXiv PDF found for {paper_id}")
            
            # Phase 3: Try DOI-based PDF (skip if arXiv found)
            if not download_link:
                print(f"[PDF Extraction] 🔍 Trying Unpaywall/DOI extraction for {paper_id}")
                doi_pdf = await self._extract_doi_pdf(paper)
                if doi_pdf:
                    print(f"[PDF Extraction] ✅ Found PDF via DOI: {doi_pdf[:60]}...")
                    download_link = doi_pdf
                    self.stats["download_links_found"] += 1
                else:
                    print(f"[PDF Extraction] ❌ No PDF found via DOI for {paper_id}")
            
            # Fallback: If still no PDF link, scrape Semantic Scholar page for alternate sources
            if not download_link and paper_id:
                print(f"[PDF Extraction] 🌐 Trying Playwright scraping for {paper_id}")
                pdf_from_page = await self._extract_pdf_from_paper_page(paper_id, title)
                if pdf_from_page:
                    print(f"[PDF Extraction] ✅ Found PDF via Playwright: {pdf_from_page[:60]}...")
                    download_link = pdf_from_page
                    self.stats["download_links_found"] += 1
                    if self.verbose:
                        self._log(f"Found PDF from paper page scraping: {pdf_from_page[:60]}...", "SUCCESS")
                else:
                    print(f"[PDF Extraction] ❌ Playwright found no PDF for {paper_id}, using Semantic Scholar page link")
                    # Final fallback: link to Semantic Scholar paper page with proper title slug
                    download_link = self._create_semantic_scholar_url(paper_id, title)
                    if self.verbose:
                        self._log(f"Using fallback link to Semantic Scholar paper page for {paper_id}", "DEBUG")

            return {
                "title": title.strip(),
                "authors": authors.strip(),
                "year": year.strip(),
                "publication": publication.strip(),
                "citations": citations,
                "citation_trend": [],
                "doi": doi,
                "download_link": download_link,
            }
        except Exception as exc:
            self._log(f"Error extracting paper metadata: {exc}", "ERROR")
            return None

    def build_debug_report(self, user_id: Optional[str] = None) -> Dict:
        """Return a structured debug summary of the most recent scrape run."""
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "author_id": user_id,
            "stats": self.stats.copy(),
            "papers": self.debug_records.copy() if self.collect_debug else [],
            "max_papers": self.max_papers,
            "api_key_used": bool(self.api_key),
            "sorted_by_citations": True,
        }

