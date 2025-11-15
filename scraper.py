"""
Google Scholar Profile Scraper using Playwright
"""
import asyncio
import copy
import html
import json
import random
import platform
import re
import sys
import urllib.parse
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple
from playwright.async_api import Page, async_playwright


class GoogleScholarScraper:
    """Scrapes Google Scholar profile pages for research papers"""
    
    def __init__(
        self,
        headless: bool = True,
        max_papers: int = 50,
        verbose: bool = False,
        collect_debug: bool = False,
        progress_handler: Optional[Callable[[str, int, int, float], None]] = None,
    ):
        self.headless = headless
        self.max_papers = max_papers
        self.verbose = verbose
        self.collect_debug = collect_debug
        self.progress_handler = progress_handler
        self.base_url = "https://scholar.google.com"
        # Statistics tracking
        self.stats = {
            'doi_found': 0,
            'doi_strategies': {1: 0, 2: 0, 3: 0, 4: 0, 'meta': 0, 'jsonld': 0, 'citation': 0, 'url': 0},
            'download_gs': 0,  # From Google Scholar
            'download_scihub': 0,  # From Sci-Hub
            'download_none': 0,  # No download link found
            'scihub_attempts': 0,
            'scihub_success': 0,
            'scihub_failed': 0,
        }
        self.debug_records: List[Dict] = []
    
    def _log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            prefix = {
                "INFO": "ℹ️",
                "DEBUG": "🔍",
                "WARN": "⚠️",
                "ERROR": "❌",
                "SUCCESS": "✓"
            }.get(level, "•")
            print(f"{prefix} {message}")
    
    def _print_progress(self, current: int, total: int, prefix: str = "Progress"):
        """Print a progress bar and emit progress callbacks"""
        if total == 0:
            return
        
        percentage = (current / total) * 100
        bar_length = 40
        filled_length = int(bar_length * current // total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        # Use carriage return to overwrite the line
        sys.stdout.write(f'\r{prefix}: [{bar}] {current}/{total} ({percentage:.1f}%)')
        sys.stdout.flush()
        
        if current >= total:
            print()  # New line when complete
        
        if self.progress_handler:
            try:
                stage_label = self._normalize_stage_label(prefix)
                self.progress_handler(stage_label, current, total, percentage)
            except Exception:
                # Avoid breaking scraping due to progress UI failures
                pass

    @staticmethod
    def _normalize_stage_label(prefix: str) -> str:
        """Return a human-friendly stage label without emoji/count context."""
        label = (prefix or "").strip()
        if not label:
            return "Processing"
        
        if label and not label[0].isalnum():
            parts = label.split(" ", 1)
            if len(parts) == 2:
                label = parts[1].strip()
        
        mapping = {
            "extracting doi & download links": "Enriching papers",
            "extracting papers": "Extracting papers",
        }
        key = label.lower()
        return mapping.get(key, label)
        
    async def scrape_profile(self, user_id: str) -> List[Dict]:
        """
        Scrape all papers from a Google Scholar profile
        
        Args:
            user_id: Google Scholar user ID (e.g., 'x8xNLZQAAAAJ')
            
        Returns:
            List of dictionaries containing paper metadata
        """
        profile_url = f"{self.base_url}/citations?user={user_id}&hl=en&oi=ao"
        papers = []
        if self.collect_debug:
            self.debug_records = []
        
        async with async_playwright() as p:
            # Launch browser with realistic settings
            # Try with different launch options for macOS compatibility
            launch_options = {
                'headless': self.headless,
                'slow_mo': 100  # Add small delay between actions
            }
            
            # On macOS, sometimes need to disable sandbox
            if platform.system() == 'Darwin':
                launch_options['args'] = ['--no-sandbox', '--disable-setuid-sandbox']
            
            browser = await p.chromium.launch(**launch_options)
            
            # Create context with realistic user agent
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            
            try:
                print(f"Navigating to profile: {profile_url}")
                await page.goto(profile_url, wait_until='networkidle', timeout=30000)
                
                # Wait for page to load
                await asyncio.sleep(2)
                
                # Check if profile exists
                if await self._check_profile_exists(page):
                    print("Profile found. Starting to scrape papers...")
                    papers = await self._scrape_papers(page)
                else:
                    print("Error: Profile not found or inaccessible")
                    
            except Exception as e:
                print(f"Error during scraping: {str(e)}")
                import traceback
                traceback.print_exc()
                # Return partial results if available
                if papers:
                    print(f"Returning {len(papers)} papers collected so far...")
                    
            finally:
                await browser.close()
                
        return papers
    
    async def _check_profile_exists(self, page: Page) -> bool:
        """Check if the profile page loaded successfully"""
        try:
            # Look for common elements that indicate a valid profile
            profile_selector = 'div#gsc_prf'
            await page.wait_for_selector(profile_selector, timeout=5000)
            return True
        except:
            return False
    
    async def _scrape_papers(self, page: Page) -> List[Dict]:
        """Extract papers from the current page and handle pagination"""
        papers = []
        page_num = 0
        profile_url = page.url  # Store profile URL to return to after paper visits
        seen_titles = set()  # Track papers we've already seen to avoid duplicates
        
        print(f"\n📊 Starting to scrape papers (target: {self.max_papers})...\n")
        
        while len(papers) < self.max_papers:
            # Calculate how many more papers we need BEFORE extracting
            remaining = self.max_papers - len(papers)
            
            # Extract papers from current page, but limit to what we need (+ buffer for duplicates)
            # Add a small buffer (10-20) to account for potential duplicates
            buffer = min(20, remaining)  # Don't add more buffer than we need
            max_to_extract = remaining + buffer
            
            page_papers = await self._extract_papers_from_page(page, profile_url, max_to_process=max_to_extract)
            
            if not page_papers:
                print("\n⚠️  No more papers found.")
                break
            
            # Filter out papers we've already seen (avoid duplicates after "Show more")
            new_papers = []
            for paper in page_papers:
                if paper and paper.get('title'):
                    title_key = paper['title'].lower().strip()
                    if title_key not in seen_titles:
                        seen_titles.add(title_key)
                        new_papers.append(paper)
            
            if not new_papers:
                print("\n⚠️  No new papers found (possibly duplicates or end of list).")
                break
            
            # Add new papers up to max limit
            papers.extend(new_papers[:remaining])
            
            # Show progress
            self._print_progress(len(papers), self.max_papers, "📄 Extracting papers")
            
            # Check if we've reached the limit
            if len(papers) >= self.max_papers:
                break
            
            # Count papers on page before loading more
            try:
                papers_on_page_before_load = await page.query_selector_all('tr.gsc_a_tr')
                count_before_load = len(papers_on_page_before_load)
            except:
                count_before_load = len(page_papers) if page_papers else 0
            
            # Try to load more papers
            load_success = await self._load_more_papers(page)
            
            if not load_success:
                # Verify we actually have papers - might have reached the end
                await asyncio.sleep(2)  # Wait a bit longer
                try:
                    # Check if there are more papers on page than we've collected
                    remaining_on_page = await page.query_selector_all('tr.gsc_a_tr')
                    papers_on_page_count = len(remaining_on_page)
                    
                    # If there are more papers on page than we've collected, extract them
                    if papers_on_page_count > len(papers):
                        print(f"\n📄 Found {papers_on_page_count} papers on page, but only collected {len(papers)}. Extracting remaining papers...")
                        # Extract remaining papers from current page (this will continue the loop)
                        # But first, check if we need to click "Show more" to get more papers
                        # If papers_on_page_count is exactly what we need and we haven't reached target, try loading more
                        if papers_on_page_count < self.max_papers:
                            # Try to load more papers before extracting
                            await self._load_more_papers(page)
                            await asyncio.sleep(2)
                        continue
                    
                    # Try scrolling to bottom to trigger lazy loading or reveal button
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await asyncio.sleep(2)
                    
                    # Check again after scrolling
                    remaining_after_scroll = await page.query_selector_all('tr.gsc_a_tr')
                    if len(remaining_after_scroll) > papers_on_page_count:
                        # New papers appeared after scrolling
                        print(f"\n📄 Scrolling revealed {len(remaining_after_scroll)} papers. Extracting...")
                        continue
                    
                    # Try clicking "Show more" button again after scrolling (might be visible now)
                    retry_load = await self._load_more_papers(page)
                    if retry_load:
                        print(f"\n📄 Successfully clicked 'Show more' after scrolling. Continuing...")
                        continue
                except Exception as e:
                    print(f"\n⚠️  Error checking for more papers: {str(e)}")
                
                # Final check: if we haven't reached our target, try one more time
                if len(papers) < self.max_papers:
                    try:
                        final_check = await page.query_selector_all('tr.gsc_a_tr')
                        if len(final_check) > len(papers):
                            print(f"\n📄 Final check: Found {len(final_check)} papers on page. Extracting remaining...")
                            continue
                    except:
                        pass
                
                print(f"\n⚠️  No more pages available. Collected {len(papers)} papers (target was {self.max_papers}).")
                break
            
            # Verify new papers were actually loaded by checking the page
            await asyncio.sleep(1)  # Brief wait for page to stabilize
            try:
                papers_on_page_after = await page.query_selector_all('tr.gsc_a_tr')
                count_after_load = len(papers_on_page_after)
                
                # If no new papers appeared on page, we might have reached the end
                if count_after_load <= count_before_load:
                    # Check one more time after a longer wait
                    await asyncio.sleep(2)
                    papers_on_page_final = await page.query_selector_all('tr.gsc_a_tr')
                    if len(papers_on_page_final) <= count_before_load:
                        print(f"\n⚠️  No new papers loaded. Collected {len(papers)} papers.")
                        break
            except:
                # If we can't verify, continue anyway
                pass
            
            # Random delay to avoid rate limiting
            delay = random.uniform(2, 5)
            await asyncio.sleep(delay)
            page_num += 1
        
        print()  # New line after progress bar
        return papers[:self.max_papers]
    
    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize relative scholar URLs to absolute ones"""
        if not url:
            return ""
        url = url.strip()
        if not url:
            return ""
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("/"):
            return f"https://scholar.google.com{url}"
        return url

    @staticmethod
    def _extract_urls_from_encoded_string(raw_value: Optional[str]) -> List[str]:
        """Extract embedded URLs from data attributes such as data-clk or onclick strings"""
        if not raw_value:
            return []
        decoded = html.unescape(raw_value)
        matches = re.findall(r'(?:^|[?&;])(url|u|href|q)=([^&;]+)', decoded)
        urls: List[str] = []
        for _, value in matches:
            try:
                candidate = urllib.parse.unquote(value)
            except Exception:
                candidate = value
            if candidate:
                urls.append(candidate)
        return urls

    @staticmethod
    def _is_scholar_profile_link(url: str) -> bool:
        """Return True if the URL points to a Google Scholar profile/citation page"""
        if not url:
            return False
        lower = url.lower()
        if "scholar.googleusercontent.com" in lower or "scholar.google.com/scholar_url" in lower:
            return False
        if "scholar.google.com" not in lower:
            return False
        scholar_patterns = [
            "citations?",
            "view_op=view_citation",
            "scholar?oi=",
        ]
        return any(pattern in lower for pattern in scholar_patterns)

    @staticmethod
    def _score_candidate(url: str, source: str) -> int:
        """Assign a priority score (lower is better) to a candidate download URL"""
        lower_url = url.lower()
        if lower_url.endswith(".pdf"):
            return 0
        if "scholar.googleusercontent.com" in lower_url:
            return 0
        if "pdf" in lower_url:
            return 1
        repository_indicators = [
            "arxiv.org",
            "researchgate.net",
            "academia.edu",
            "ieeexplore.ieee.org",
            "acm.org",
            "springer.com",
            "link.springer.com",
            "sciencedirect.com",
            "frontiersin.org",
            "nature.com",
            "science.org",
            "mdpi.com",
            "hindawi.com",
            "biorxiv.org",
            "medrxiv.org",
            "pmc.ncbi.nlm.nih.gov",
            "ncbi.nlm.nih.gov/pmc",
        ]
        if any(indicator in lower_url for indicator in repository_indicators):
            return 1
        if GoogleScholarScraper._is_scholar_profile_link(url):
            return 9
        if source in {"row_data", "data_clk"}:
            return 2
        return 3

    def _select_preferred_candidate(self, candidates: List[Dict]) -> Optional[Dict]:
        """
        Choose the best download candidate, prioritizing non-Scholar direct links.
        """
        if not candidates:
            return None
        sorted_candidates = sorted(
            (candidate for candidate in candidates if candidate.get("url")),
            key=lambda candidate: (candidate.get("score", 99), candidate.get("url", "")),
        )

        for candidate in sorted_candidates:
            if not self._is_scholar_profile_link(candidate["url"]):
                return candidate
        return sorted_candidates[0] if sorted_candidates else None

    def _apply_download_selection(self, paper_data: Dict) -> Optional[Dict]:
        """Update paper_data['download_link'] based on best available candidate."""
        candidates = paper_data.get('download_candidates', [])
        best_candidate = self._select_preferred_candidate(candidates)
        if best_candidate:
            paper_data['download_link'] = best_candidate['url']
        else:
            paper_data['download_link'] = paper_data.get('download_link', '')
        return best_candidate

    async def _collect_inline_download_candidates(self, row) -> Tuple[Optional[Dict], List[Dict]]:
        """
        Inspect the profile table row for any inline download links or embedded URLs.
        Returns (best_candidate, all_candidates)
        """
        candidates: List[Dict] = []
        seen: set = set()

        def register_candidate(url: str, source: str, meta: Dict) -> None:
            normalized = self._normalize_url(url)
            if not normalized or normalized in seen:
                return
            if not normalized.lower().startswith(("http://", "https://")):
                return
            seen.add(normalized)
            candidates.append({
                "url": normalized,
                "source": source,
                "score": self._score_candidate(normalized, source),
                "meta": meta,
            })

        anchors = await row.query_selector_all('a[href]')
        for anchor in anchors:
            try:
                anchor_data = await anchor.evaluate("""(el) => ({
                    href: el.getAttribute('href') || '',
                    text: el.innerText || '',
                    className: el.className || '',
                    dataClk: el.getAttribute('data-clk') || '',
                    dataUrl: el.getAttribute('data-url') || '',
                    dataHref: el.getAttribute('data-href') || '',
                    onClick: el.getAttribute('onclick') || '',
                    rel: el.getAttribute('rel') || '',
                })""")
            except Exception:
                continue

            href = anchor_data.get("href", "")
            if href:
                register_candidate(
                    href,
                    "row_anchor",
                    {
                        "text": anchor_data.get("text", ""),
                        "class": anchor_data.get("className", ""),
                    }
                )

            for attr_name in ("dataClk", "dataUrl", "dataHref", "onClick"):
                for extracted_url in self._extract_urls_from_encoded_string(anchor_data.get(attr_name)):
                    register_candidate(
                        extracted_url,
                        "data_attr",
                        {
                            "attribute": attr_name,
                            "text": anchor_data.get("text", ""),
                        }
                    )

        # Inspect row-level attributes for encoded URLs
        try:
            row_data = await row.evaluate("""(el) => ({
                dataClk: el.getAttribute('data-clk') || '',
                dataUrl: el.getAttribute('data-url') || '',
                dataHref: el.getAttribute('data-href') || '',
            })""")
        except Exception:
            row_data = {}

        for attr_name in ("dataClk", "dataUrl", "dataHref"):
            for extracted_url in self._extract_urls_from_encoded_string(row_data.get(attr_name)):
                register_candidate(
                    extracted_url,
                    "row_data",
                    {
                        "attribute": attr_name,
                    }
                )

        # Sort by score, then by URL for determinism
        candidates.sort(key=lambda candidate: (candidate["score"], candidate["url"]))
        best_candidate = self._select_preferred_candidate(candidates)
        return best_candidate, candidates

    async def _collect_page_download_candidates(self, page: Page) -> List[Dict]:
        """Collect potential download links from the currently open paper detail page."""
        candidates: List[Dict] = []
        seen: set = set()

        def register_candidate(url: str, source: str, meta: Dict) -> None:
            normalized = self._normalize_url(url)
            if not normalized or normalized in seen:
                return
            if not normalized.lower().startswith(("http://", "https://")):
                return
            seen.add(normalized)
            candidates.append({
                "url": normalized,
                "source": source,
                "score": self._score_candidate(normalized, source),
                "meta": meta,
            })

        try:
            anchor_nodes = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'), el => ({
                    href: el.getAttribute('href') || '',
                    text: el.innerText || '',
                    className: el.className || '',
                    rel: el.getAttribute('rel') || '',
                    dataClk: el.getAttribute('data-clk') || '',
                    dataUrl: el.getAttribute('data-url') || '',
                    dataHref: el.getAttribute('data-href') || '',
                    onclick: el.getAttribute('onclick') || '',
                    ariaLabel: el.getAttribute('aria-label') || ''
                }))
            """)
        except Exception:
            anchor_nodes = []

        for node in anchor_nodes:
            href = node.get("href", "")
            if not href:
                continue
            text = node.get("text", "") or ""
            class_name = node.get("className", "") or ""
            rel_value = (node.get("rel") or "").lower()
            lower_href = href.lower()
            lower_text = text.lower()

            should_register = False
            if lower_href.endswith(".pdf"):
                should_register = True
            if "scholar.googleusercontent.com" in lower_href or "scholar.google.com/scholar_url" in lower_href:
                should_register = True
            if "pdf" in lower_href or "pdf" in lower_text or "download" in lower_text:
                should_register = True
            if "full text" in lower_text or "full-text" in lower_text:
                should_register = True
            if "alternat" in rel_value and "pdf" in rel_value:
                should_register = True
            if class_name and any(token in class_name for token in ["gsc_ggs", "gsc_a_at", "gs_or_ggsm"]):
                should_register = True

            if should_register:
                register_candidate(
                    href,
                    "page_anchor",
                    {
                        "text": text,
                        "class": class_name,
                        "rel": node.get("rel", ""),
                    }
                )

            for attr_name in ("dataClk", "dataUrl", "dataHref", "onclick"):
                for extracted_url in self._extract_urls_from_encoded_string(node.get(attr_name)):
                    register_candidate(
                        extracted_url,
                        "page_anchor_attr",
                        {
                            "attribute": attr_name,
                            "text": text,
                            "class": class_name,
                        }
                    )

        # Parse link tags for alternate PDF resources
        try:
            link_nodes = await page.evaluate("""
                () => Array.from(document.querySelectorAll('link[rel][href]'), el => ({
                    href: el.getAttribute('href') || '',
                    rel: el.getAttribute('rel') || '',
                    type: el.getAttribute('type') || ''
                }))
            """)
        except Exception:
            link_nodes = []

        for node in link_nodes:
            href = node.get("href", "")
            rel_value = (node.get("rel") or "").lower()
            type_value = (node.get("type") or "").lower()
            if not href:
                continue
            if ("alternate" in rel_value and "pdf" in type_value) or "alternate" in rel_value and href.lower().endswith(".pdf"):
                register_candidate(
                    href,
                    "link_rel",
                    {
                        "rel": node.get("rel", ""),
                        "type": node.get("type", ""),
                    }
                )

        # Parse meta tags for citation PDF URLs
        try:
            meta_nodes = await page.evaluate("""
                () => Array.from(document.querySelectorAll('meta[name], meta[property]'), el => ({
                    name: el.getAttribute('name') || '',
                    property: el.getAttribute('property') || '',
                    content: el.getAttribute('content') || ''
                }))
            """)
        except Exception:
            meta_nodes = []

        for node in meta_nodes:
            key = (node.get("name") or node.get("property") or "").lower()
            content = node.get("content", "")
            if not content:
                continue
            if any(marker in key for marker in ["citation_pdf_url", "pdf_url", "fulltext_url_pdf", "pdf"]):
                register_candidate(
                    content,
                    "meta",
                    {
                        "key": key,
                    }
                )

        candidates.sort(key=lambda candidate: (candidate["score"], candidate["url"]))
        return candidates

    @staticmethod
    def _merge_candidate_lists(existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """Merge two candidate lists while preserving score ordering and metadata."""
        merged: Dict[str, Dict] = {}
        for candidate in existing + new:
            url = candidate.get("url")
            if not url:
                continue
            if url not in merged:
                merged[url] = candidate
            else:
                # Merge meta dictionaries conservatively
                existing_meta = merged[url].setdefault("meta", {})
                new_meta = candidate.get("meta", {})
                for key, value in new_meta.items():
                    existing_meta.setdefault(key, value)
                # Prefer lower score if new candidate has better priority
                existing_score = merged[url].get("score", 99)
                new_score = candidate.get("score", 99)
                if new_score < existing_score:
                    merged[url]["score"] = new_score
                # Aggregate sources
                existing_sources = set(
                    merged[url].get("source", "").split("|")
                    if isinstance(merged[url].get("source"), str) else []
                )
                new_source = candidate.get("source")
                if isinstance(new_source, str) and new_source not in existing_sources:
                    combined = existing_sources | {new_source}
                    merged[url]["source"] = "|".join(sorted(s for s in combined if s))
        merged_list = list(merged.values())
        merged_list.sort(key=lambda candidate: (candidate.get("score", 99), candidate.get("url", "")))
        return merged_list

    def build_debug_report(self, user_id: Optional[str] = None) -> Dict:
        """Return a structured debug summary of the most recent scrape run."""
        report = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "stats": copy.deepcopy(self.stats),
            "papers": copy.deepcopy(self.debug_records) if self.collect_debug else [],
            "max_papers": self.max_papers,
            "headless": self.headless,
        }
        return report
    
    async def _extract_papers_from_page(self, page: Page, profile_url: str, max_to_process: Optional[int] = None) -> List[Dict]:
        """Extract paper data from the current page view"""
        papers = []
        
        try:
            # Wait for paper entries to load
            await page.wait_for_selector('tr.gsc_a_tr', timeout=10000)
            
            # Get all paper rows
            paper_rows = await page.query_selector_all('tr.gsc_a_tr')
            
            # Limit rows to process if specified (for performance when we already have enough)
            if max_to_process and len(paper_rows) > max_to_process:
                paper_rows = paper_rows[:max_to_process]
            
            # First pass: Extract all basic data from rows (before navigating away)
            paper_links = []
            for idx, row in enumerate(paper_rows):
                try:
                    # Extract basic data immediately while row is still valid
                    title_elem = await row.query_selector('a.gsc_a_at')
                    title = await title_elem.inner_text() if title_elem else ""
                    title = title.strip()
                    
                    authors_elem = await row.query_selector('div.gs_gray')
                    authors = await authors_elem.inner_text() if authors_elem else ""
                    authors = authors.strip()
                    
                    pub_elems = await row.query_selector_all('div.gs_gray')
                    publication = ""
                    year = ""
                    
                    if len(pub_elems) > 1:
                        pub_text = await pub_elems[1].inner_text()
                        pub_text = pub_text.strip()
                        
                        import re
                        year_match = re.search(r'\b(19|20)\d{2}\b', pub_text)
                        if year_match:
                            year = year_match.group()
                            publication = pub_text.replace(year, "").strip()
                        else:
                            publication = pub_text
                    
                    # Try to extract year from other row elements if not found
                    if not year:
                        try:
                            # Check all text in the row for year
                            row_text = await row.inner_text()
                            year_match = re.search(r'\b(19|20)\d{2}\b', row_text)
                            if year_match:
                                year = year_match.group()
                        except:
                            pass
                    
                    # Extract citation count
                    citations = "Missing citations"
                    try:
                        # Try multiple selectors for citation count
                        citation_selectors = [
                            'a.gsc_a_c',
                            'span.gsc_a_c',
                            'td.gsc_a_c',
                            'a[href*="cites"]',
                        ]
                        
                        for selector in citation_selectors:
                            try:
                                citation_elem = await row.query_selector(selector)
                                if citation_elem:
                                    citation_text = await citation_elem.inner_text()
                                    citation_text = citation_text.strip()
                                    if citation_text:
                                        # Extract number from text like "Cited by 5,754" or just "5754"
                                        # Remove commas and spaces, then extract digits
                                        citation_text_clean = citation_text.replace(',', '').replace(' ', '')
                                        citation_match = re.search(r'(\d+)', citation_text_clean)
                                        if citation_match:
                                            citations = citation_match.group(1)
                                            break
                            except:
                                continue
                        
                        # Fallback: search all links in the row for citation patterns
                        if citations == "Missing citations":
                            try:
                                all_links = await row.query_selector_all('a')
                                for link in all_links:
                                    try:
                                        link_text = await link.inner_text()
                                        href = await link.get_attribute('href')
                                        # Check if this looks like a citation link
                                        if href and ('cites' in href.lower() or 'citation' in href.lower()):
                                            if link_text:
                                                link_text_clean = link_text.replace(',', '').replace(' ', '')
                                                citation_match = re.search(r'(\d+)', link_text_clean)
                                                if citation_match:
                                                    citations = citation_match.group(1)
                                                    break
                                    except:
                                        continue
                            except:
                                pass
                        
                        # Final fallback: search entire row text for citation patterns
                        if citations == "Missing citations":
                            try:
                                row_text = await row.inner_text()
                                # Look for patterns like "Cited by 5,754" or "5754 citations"
                                citation_patterns = [
                                    r'cited\s+by\s+(\d{1,3}(?:,\d{3})*)',
                                    r'(\d{1,3}(?:,\d{3})*)\s+citations?',
                                    r'citations?[:\s]+(\d{1,3}(?:,\d{3})*)',
                                ]
                                for pattern in citation_patterns:
                                    match = re.search(pattern, row_text, re.IGNORECASE)
                                    if match:
                                        citations = match.group(1).replace(',', '')
                                break
                            except:
                                pass
                    except Exception as e:
                        self._log(f"Error extracting citations: {str(e)}", "DEBUG")
                        pass
                    
                    # Get paper link
                    paper_link = None
                    if title_elem:
                        href = await title_elem.get_attribute('href')
                        if href:
                            paper_link = self._normalize_url(href)
                    
                    # Try to extract PDF link(s) directly from profile page row (faster!)
                    pdf_link = ""
                    inline_best, inline_candidates = await self._collect_inline_download_candidates(row)
                    if inline_best:
                        pdf_link = inline_best["url"]
                    
                    # Try to extract DOI from PDF link URL if available
                    doi_from_url = ""
                    if pdf_link:
                        doi_from_url = self._extract_doi_from_url(pdf_link)
                        if doi_from_url:
                            self.stats['doi_strategies']['url'] = self.stats['doi_strategies'].get('url', 0) + 1
                            self._log(f"DOI found from profile PDF URL: {doi_from_url}", "SUCCESS")
                    
                    debug_record = None
                    if self.collect_debug:
                        debug_record = {
                            'title': title,
                            'paper_link': paper_link,
                            'inline_candidates': inline_candidates.copy(),
                            'detail_candidates': [],
                            'final_download_link': "",
                            'doi_sources': {
                                'from_profile_url': bool(doi_from_url),
                            },
                            'scihub_attempted': False,
                            'scihub_success': False,
                            'errors': [],
                        }
                        self.debug_records.append(debug_record)
                    
                    # Store basic data and link for DOI/download extraction
                    paper_entry = {
                        'title': title,
                        'authors': authors,
                        'year': year,
                        'publication': publication,
                        'citations': citations,
                        'citation_trend': [],  # Initialize as empty list, will be populated when visiting detail page
                        'doi': doi_from_url,  # Use DOI from URL if found
                        'download_link': "",  # Will be determined from candidates
                        'download_candidates': inline_candidates,
                        'debug_record': debug_record
                    }
                    selected_candidate = self._apply_download_selection(paper_entry)
                    if debug_record is not None:
                        debug_record['final_download_link'] = selected_candidate['url'] if selected_candidate else ""
                    papers.append(paper_entry)
                    paper_links.append(paper_link)
                    
                except Exception as e:
                    print(f"\n⚠️  Error extracting basic paper data: {str(e)}")
                    papers.append(None)
                    paper_links.append(None)
                    continue
            
            # Second pass: Extract DOI and download links (navigate to each paper page)
            valid_papers = [p for p in papers if p is not None]
            total_papers = len(valid_papers)
            
            if total_papers > 0:
                print(f"\n🔍 Extracting DOI & download links for {total_papers} papers...")
            
            processed_count = 0
            for idx, (paper_data, paper_link) in enumerate(zip(papers, paper_links)):
                if paper_data and paper_link:
                    try:
                        processed_count += 1
                        # Show progress for DOI/download extraction
                        self._print_progress(processed_count, total_papers, "🔍 Extracting DOI & download links")
                        
                        # Only visit paper page if we don't already have a download link from profile
                        if not paper_data.get('download_link'):
                            doi, download_link, detail_candidates, year_from_detail, citation_trend = await self._extract_doi_and_download(page, paper_link, profile_url)
                            paper_data['doi'] = doi
                            # Update year if missing and found on detail page
                            if not paper_data.get('year') and year_from_detail:
                                paper_data['year'] = year_from_detail
                            # Store citation trend data (always store, even if empty, for debugging)
                            paper_data['citation_trend'] = citation_trend
                            if citation_trend:
                                self._log(f"Stored {len(citation_trend)} trend data points for paper: {paper_data.get('title', 'Unknown')[:50]}", "SUCCESS")
                                if self.verbose:
                                    # Log sample of stored data
                                    sample = citation_trend[:2] if len(citation_trend) >= 2 else citation_trend
                                    self._log(f"Sample stored data: {sample}", "DEBUG")
                            else:
                                self._log(f"No trend data found for paper: {paper_data.get('title', 'Unknown')[:50]}", "WARN")
                            paper_data['download_candidates'] = self._merge_candidate_lists(
                                paper_data.get('download_candidates', []),
                                detail_candidates
                            )
                            debug_record = paper_data.get('debug_record')
                            if detail_candidates and debug_record is not None:
                                debug_record['detail_candidates'] = detail_candidates
                            if doi and debug_record is not None:
                                debug_record.setdefault('doi_sources', {})['from_detail_page'] = True
                            
                            if download_link:
                                self.stats['download_gs'] += 1
                                self._log(f"Download link from Google Scholar for: {paper_data.get('title', 'Unknown')[:50]}...", "SUCCESS")
                            else:
                                # No download link found on Google Scholar, try Sci-Hub
                                # Try Sci-Hub for ALL papers without download links (even without DOI)
                                if paper_data.get('title'):
                                    self.stats['scihub_attempts'] += 1
                                    self._log(f"Trying Sci-Hub for: {paper_data.get('title', 'Unknown')[:50]}...", "DEBUG")
                                    if debug_record is not None:
                                        debug_record['scihub_attempted'] = True
                                    scihub_link = await self._find_scihub_link(
                                        page,
                                        doi=doi,  # Will be empty if not found, but that's okay
                                        title=paper_data.get('title', ''),
                                        authors=paper_data.get('authors', ''),
                                        profile_url=profile_url
                                    )
                                    if scihub_link:
                                        self.stats['download_scihub'] += 1
                                        self.stats['scihub_success'] += 1
                                        self._log(f"Download link from Sci-Hub found!", "SUCCESS")
                                        if debug_record is not None:
                                            debug_record['scihub_success'] = True
                                        paper_data['download_candidates'] = self._merge_candidate_lists(
                                            paper_data.get('download_candidates', []),
                                            [{
                                                "url": scihub_link,
                                                "source": "scihub",
                                                "meta": {
                                                    "domain": urllib.parse.urlparse(scihub_link).netloc
                                                },
                                                "score": self._score_candidate(scihub_link, "scihub"),
                                            }]
                                        )
                                    else:
                                        self.stats['download_none'] += 1
                                        self.stats['scihub_failed'] += 1
                                        self._log(f"No download link found from Sci-Hub", "WARN")
                                        if debug_record is not None:
                                            debug_record.setdefault('errors', []).append("Sci-Hub download not found")
                                    # Add delay between Sci-Hub requests to avoid overloading servers
                                    await asyncio.sleep(2.5)
                                else:
                                    self.stats['download_none'] += 1
                        else:
                            # We already have download link from profile, just try to get DOI
                            # Skip visiting paper page if we have both, to save time
                            # Note: download_gs already counted when extracted from profile page (line 406)
                            if not paper_data.get('doi') or not paper_data.get('year') or not paper_data.get('citation_trend'):
                                doi, _, detail_candidates, year_from_detail, citation_trend = await self._extract_doi_and_download(page, paper_link, profile_url)
                            if not paper_data.get('doi'):
                                paper_data['doi'] = doi
                                # Update year if missing and found on detail page
                                if not paper_data.get('year') and year_from_detail:
                                    paper_data['year'] = year_from_detail
                                # Store citation trend data (always store if not already present)
                                if not paper_data.get('citation_trend'):
                                    paper_data['citation_trend'] = citation_trend
                                    if citation_trend:
                                        self._log(f"Stored {len(citation_trend)} trend data points for paper", "SUCCESS")
                                    else:
                                        self._log(f"No trend data found for paper: {paper_data.get('title', 'Unknown')[:50]}", "WARN")
                                paper_data['download_candidates'] = self._merge_candidate_lists(
                                    paper_data.get('download_candidates', []),
                                    detail_candidates
                                )
                                debug_record = paper_data.get('debug_record')
                                if debug_record is not None:
                                    if detail_candidates:
                                        debug_record['detail_candidates'] = detail_candidates
                                    if doi:
                                        debug_record.setdefault('doi_sources', {})['from_detail_page'] = True

                        selected_candidate = self._apply_download_selection(paper_data)
                        debug_record = paper_data.get('debug_record')
                        if debug_record is not None:
                            debug_record['final_download_link'] = selected_candidate['url'] if selected_candidate else ""
                    except Exception as e:
                        print(f"\n⚠️  Error extracting DOI/download for paper {idx+1}: {str(e)}")
                        continue
            
            if total_papers > 0:
                print()  # New line after progress bar
                    
        except Exception as e:
            print(f"\n⚠️  Error extracting papers from page: {str(e)}")
        
        # Filter out None entries
        papers = [p for p in papers if p is not None]
        return papers
    
    def _extract_doi_from_url(self, url: str) -> str:
        """
        Extract DOI from a URL (e.g., repository URLs often contain DOIs)
        
        Args:
            url: URL string that may contain a DOI
            
        Returns:
            Extracted DOI string, or empty string if not found
        """
        if not url:
            return ""
        
        # Common URL patterns that contain DOIs
        doi_patterns_in_url = [
            r'/doi/(?:pdf|pdfdirect|abs|full)/(10\.\d+/[^\s?&#]+)',  # Wiley, PNAS, etc. (e.g., pnas.org/doi/pdf/10.1073/...)
            r'doi\.org/(10\.\d+/[^\s?&#]+)',  # Direct DOI links
            r'doi[=:](10\.\d+/[^\s?&#]+)',  # DOI in query params
            r'/doi/(10\.\d+/[^\s?&#]+)',  # Generic /doi/ pattern
        ]
        
        for pattern in doi_patterns_in_url:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                doi = match.group(1)
                # Clean up DOI (remove trailing punctuation)
                doi = re.sub(r'[.,;:)\]]+$', '', doi)
                if doi.startswith('10.'):
                    return doi
        
        return ""
    
    async def _diagnose_chart_structure(self, page: Page) -> Dict:
        """Diagnostic method to capture actual DOM structure of Google Scholar chart"""
        diagnostic_info = {
            'bars_container_exists': False,
            'bars_container_html': '',
            'bars_found': 0,
            'bar_elements': [],
            'year_labels': [],
            'script_tags_with_chart': [],
            'window_variables': {},
            'total_citations': None
        }
        
        try:
            # Check if bars container exists
            bars_container = await page.query_selector('#gsc_oci_graph_bars')
            if bars_container:
                diagnostic_info['bars_container_exists'] = True
                diagnostic_info['bars_container_html'] = await bars_container.inner_html()
                
                # Count bars
                bars = await bars_container.query_selector_all('div, span, rect, g')
                diagnostic_info['bars_found'] = len(bars)
                
                # Get info about first few bars
                for i, bar in enumerate(bars[:10]):  # Limit to first 10
                    try:
                        tag_name = await page.evaluate('el => el.tagName', bar)
                        bar_info = {
                            'index': i,
                            'tag': tag_name,
                            'class': await bar.get_attribute('class') or '',
                            'style': await bar.get_attribute('style') or '',
                            'title': await bar.get_attribute('title') or '',
                            'text': (await bar.inner_text())[:50] if await bar.inner_text() else ''
                        }
                        diagnostic_info['bar_elements'].append(bar_info)
                    except:
                        pass
            
            # Get year labels
            if bars_container:
                container_text = await bars_container.inner_text()
                year_matches = re.findall(r'\b(19|20)\d{2}\b', container_text)
                diagnostic_info['year_labels'] = sorted(list(set(year_matches)))
            
            # Check window variables
            window_vars = await page.evaluate("""
                () => {
                    const vars = {};
                    if (window.gsc_graph_data) vars.gsc_graph_data = 'exists';
                    if (window.gsc_graph) vars.gsc_graph = 'exists';
                    return vars;
                }
            """)
            diagnostic_info['window_variables'] = window_vars
                    
        except Exception as e:
            diagnostic_info['error'] = str(e)
        
        return diagnostic_info
    
    async def _extract_citation_trend(self, page: Page) -> List[Dict]:
        """Extract citation trend data (year-citation pairs) from Google Scholar detail page"""
        trend_data = []
        try:
            # Wait for chart to load - give it more time
            await asyncio.sleep(3)
            
            # Run diagnostic first to understand structure
            diagnostic_info = await self._diagnose_chart_structure(page)
            self._log(f"Chart diagnostic: container exists={diagnostic_info.get('bars_container_exists')}, bars found={diagnostic_info.get('bars_found', 0)}, years={len(diagnostic_info.get('year_labels', []))}", "DEBUG")
            
            # Method 1: Try to find chart data in JavaScript variables and script tags
            try:
                chart_data = await page.evaluate("""
                    () => {
                        // Strategy 1: Check window variables
                        if (window.gsc_graph_data && Array.isArray(window.gsc_graph_data)) {
                            return window.gsc_graph_data;
                        }
                        if (window.gsc_graph && window.gsc_graph.data) {
                            return window.gsc_graph.data;
                        }
                        
                        // Strategy 2: Search all script tags for chart data
                        const scripts = document.querySelectorAll('script');
                        for (let script of scripts) {
                            const text = script.textContent || script.innerText || '';
                            
                            // Only search scripts that might contain chart data
                            if (!text.includes('gsc') && !text.includes('graph') && !text.includes('citation')) {
                                continue;
                            }
                            
                            // Try multiple patterns - be more specific to avoid false matches
                            const patterns = [
                                /gsc_graph_data\\s*[:=]\\s*(\\[\\[(?:19|20)\\d{2}[,\\s]+\\d+.*?\\]\\])/,
                                /var\\s+gsc_graph_data\\s*=\\s*(\\[\\[(?:19|20)\\d{2}[,\\s]+\\d+.*?\\]\\])/,
                                /gsc_graph_data\\s*=\\s*(\\[\\[(?:19|20)\\d{2}[,\\s]+\\d+.*?\\]\\])/,
                                // More specific pattern: must have years starting with 19 or 20
                                /(\\[\\[(?:19|20)\\d{2}[,\\s]+\\d+[,\\s]*(?:19|20)?\\d{0,2}.*?\\]\\])/,
                            ];
                            
                            for (let pattern of patterns) {
                                const match = text.match(pattern);
                                if (match && match[1]) {
                                    try {
                                        // Try eval first (works for array literals)
                                        const data = eval('(' + match[1] + ')');
                                        if (Array.isArray(data) && data.length > 0) {
                                            // Validate: first item should be a year (4 digits starting with 19 or 20)
                                            const firstItem = data[0];
                                            if (Array.isArray(firstItem) && firstItem.length >= 2) {
                                                const firstYear = String(firstItem[0]);
                                                if (firstYear.length === 4 && (firstYear.startsWith('19') || firstYear.startsWith('20'))) {
                                                    return data;
                                                }
                                            }
                                        }
                                    } catch(e) {
                                        // Try JSON.parse
                                        try {
                                            const data = JSON.parse(match[1]);
                                            if (Array.isArray(data) && data.length > 0) {
                                                const firstItem = data[0];
                                                if (Array.isArray(firstItem) && firstItem.length >= 2) {
                                                    const firstYear = String(firstItem[0]);
                                                    if (firstYear.length === 4 && (firstYear.startsWith('19') || firstYear.startsWith('20'))) {
                                                        return data;
                                                    }
                                                }
                                            }
                                        } catch(e2) {
                                            // Skip manual parsing - too error-prone
                                        }
                                    }
                                }
                            }
                        }
                        return null;
                    }
                """)
                
                if chart_data and isinstance(chart_data, list):
                    if self.verbose:
                        self._log(f"Method 1 raw data received: {chart_data[:5] if len(chart_data) > 5 else chart_data}", "DEBUG")
                    for item in chart_data:
                        if isinstance(item, list) and len(item) >= 2:
                            try:
                                year = str(int(item[0]))  # Ensure year is a valid integer string
                                citations = int(item[1]) if isinstance(item[1], (int, float)) else 0
                                if self.verbose:
                                    self._log(f"Method 1 processing item: {item} -> year={year}, citations={citations}", "DEBUG")
                                # ADD VALIDATION: Only accept 4-digit years
                                if year and len(year) == 4 and citations >= 0:
                                    trend_data.append({'year': year, 'citations': citations})
                                elif self.verbose:
                                    self._log(f"Method 1 rejected item (invalid year length or citations): {item}", "DEBUG")
                            except (ValueError, TypeError) as e:
                                if self.verbose:
                                    self._log(f"Method 1 error processing item {item}: {str(e)}", "DEBUG")
                                continue
                                
                if trend_data:
                    self._log(f"Extracted {len(trend_data)} trend data points from JavaScript", "SUCCESS")
                    if self.verbose and trend_data:
                        sample = trend_data[:3]
                        self._log(f"Sample trend data (Method 1): {sample}", "DEBUG")
                        self._log(f"Full trend data (Method 1): {trend_data}", "DEBUG")
            except Exception as e:
                self._log(f"Error in JavaScript extraction: {str(e)}", "DEBUG")
            
            # Method 2: Try to get data from Google Scholar's chart data structure (before DOM extraction)
            if not trend_data:
                try:
                    chart_data_structure = await page.evaluate("""
                        () => {
                            // Google Scholar might store chart data in various places
                            // Try to find it in the page's JavaScript context
                            
                            // Check for Google Charts or similar chart library data
                            if (window.google && window.google.visualization) {
                                // Google Charts might be used
                                const charts = document.querySelectorAll('[id^="chart_"]');
                                for (let chart of charts) {
                                    // Try to get data from chart instance
                                    try {
                                        const chartId = chart.id;
                                        if (window[chartId] && window[chartId].getDataTable) {
                                            const dataTable = window[chartId].getDataTable();
                                            if (dataTable) {
                                                const rows = [];
                                                for (let i = 0; i < dataTable.getNumberOfRows(); i++) {
                                                    const year = dataTable.getValue(i, 0);
                                                    const citations = dataTable.getValue(i, 1);
                                                    rows.push([year, citations]);
                                                }
                                                if (rows.length > 0) return rows;
                                            }
                                        }
                                    } catch(e) {}
                                }
                            }
                            
                            // Look for data in script tags that might contain the chart configuration
                            const scripts = document.querySelectorAll('script');
                            for (let script of scripts) {
                                const text = script.textContent || script.innerText || '';
                                // Look for patterns that indicate chart data
                                if (text.includes('gsc_oci_graph') || text.includes('graph_bars') || text.includes('citation')) {
                                    // Try multiple patterns to extract the data array
                                    const patterns = [
                                        /gsc_oci_graph_data\\s*[:=]\\s*(\\[\\[.*?\\]\\])/,
                                        /graphData\\s*[:=]\\s*(\\[\\[.*?\\]\\])/,
                                        /data\\s*[:=]\\s*(\\[\\[.*?\\]\\])/,
                                        /(\\[\\[\\d+,\\s*\\d+.*?\\]\\])/
                                    ];
                                    
                                    for (let pattern of patterns) {
                                        const match = text.match(pattern);
                                        if (match && match[1]) {
                                            try {
                                                const data = eval('(' + match[1] + ')');
                                                if (Array.isArray(data) && data.length > 0) {
                                                    return data;
                                                }
                                            } catch(e) {
                                                try {
                                                    const data = JSON.parse(match[1]);
                                                    if (Array.isArray(data) && data.length > 0) {
                                                        return data;
                                                    }
                                                } catch(e2) {}
                                            }
                                        }
                                    }
                                }
                            }
                            
                            return null;
                        }
                    """)
                    
                    if chart_data_structure and isinstance(chart_data_structure, list):
                        if self.verbose:
                            self._log(f"Method 2 raw data received: {chart_data_structure[:5] if len(chart_data_structure) > 5 else chart_data_structure}", "DEBUG")
                        for item in chart_data_structure:
                            if isinstance(item, list) and len(item) >= 2:
                                try:
                                    year = str(int(item[0]))
                                    citations = int(item[1]) if isinstance(item[1], (int, float)) else 0
                                    if self.verbose:
                                        self._log(f"Method 2 processing item: {item} -> year={year}, citations={citations}", "DEBUG")
                                    # ADD VALIDATION: Only accept 4-digit years
                                    if year and len(year) == 4 and citations >= 0:
                                        trend_data.append({'year': year, 'citations': citations})
                                    elif self.verbose:
                                        self._log(f"Method 2 rejected item (invalid year length or citations): {item}", "DEBUG")
                                except (ValueError, TypeError) as e:
                                    if self.verbose:
                                        self._log(f"Method 2 error processing item {item}: {str(e)}", "DEBUG")
                                    continue
                                    
                        if trend_data:
                            self._log(f"Extracted {len(trend_data)} trend data points from chart structure", "SUCCESS")
                            if self.verbose and trend_data:
                                sample = trend_data[:3]
                                self._log(f"Sample trend data (Method 2): {sample}", "DEBUG")
                                self._log(f"Full trend data (Method 2): {trend_data}", "DEBUG")
                except Exception as e:
                    self._log(f"Error in chart structure extraction: {str(e)}", "DEBUG")
            
            # Method 3: Extract from Google Charts DataTable - PRIMARY METHOD
            if not trend_data:
                try:
                    # Wait for chart container and ensure it has content
                    await page.wait_for_selector('#gsc_oci_graph_bars', timeout=5000)
                    # Additional wait to ensure chart is fully rendered
                    await asyncio.sleep(1)
                    
                    chart_data = await page.evaluate("""
                        () => {
                            const debugInfo = { methods_tried: [], data_found: false };
                            
                            // Method 1: Try to get from Google Charts DataTable
                            debugInfo.methods_tried.push('DataTable');
                            if (window.google && window.google.visualization) {
                                const chartContainer = document.querySelector('#gsc_oci_graph_bars');
                                if (chartContainer) {
                                    // Try multiple ways to access chart instance
                                    const chartElements = chartContainer.querySelectorAll('*');
                                    for (let el of chartElements) {
                                        // Try different chart instance properties
                                        const chart = el.__chart__ || el.chart || el._chart || 
                                                     (el.parentElement && (el.parentElement.__chart__ || el.parentElement.chart));
                                        if (chart && chart.dataTable) {
                                            try {
                                                const dataTable = chart.dataTable;
                                                const rows = dataTable.getNumberOfRows();
                                                const trendData = [];
                                                for (let i = 0; i < rows; i++) {
                                                    const year = String(dataTable.getValue(i, 0));
                                                    const citations = dataTable.getValue(i, 1);
                                                    trendData.push([year, citations]);
                                                }
                                                if (trendData.length > 0) {
                                                    debugInfo.data_found = true;
                                                    return { method: 'DataTable', data: trendData, debug: debugInfo };
                                                }
                                            } catch(e) {
                                                // Continue to next method
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Method 2: Extract from gsc_graph_data variable (most reliable)
                            debugInfo.methods_tried.push('window.gsc_graph_data');
                            if (window.gsc_graph_data && Array.isArray(window.gsc_graph_data)) {
                                debugInfo.data_found = true;
                                return { method: 'window.gsc_graph_data', data: window.gsc_graph_data, debug: debugInfo };
                            }
                            
                            // Method 3: Find data in script tags - look for the actual data array
                            debugInfo.methods_tried.push('script_tag');
                            const scripts = document.querySelectorAll('script');
                            debugInfo.script_count = scripts.length;
                            for (let script of scripts) {
                                const text = script.textContent || script.innerText || '';
                                
                                // Only search scripts that might contain chart data
                                if (!text.includes('gsc') && !text.includes('graph') && !text.includes('chart')) {
                                    continue;
                                }
                                
                                // Look for patterns like: gsc_graph_data = [[2011, 5], [2012, 10], ...]
                                const patterns = [
                                    /gsc_graph_data\\s*[=:]\\s*(\\[\\[[\\d\\s,\\.]+\\]\\])/,
                                    /gsc_oci_graph_data\\s*[=:]\\s*(\\[\\[[\\d\\s,\\.]+\\]\\])/,
                                    /var\\s+graphData\\s*=\\s*(\\[\\[[\\d\\s,\\.]+\\]\\])/,
                                    /(\\[\\[\\d+,\\s*\\d+[\\]\\[\\d,\\s]*\\]\\])/,
                                ];
                                
                                for (let pattern of patterns) {
                                    const match = text.match(pattern);
                                    if (match && match[1]) {
                                        try {
                                            // Try to parse the array
                                            const data = eval('(' + match[1] + ')');
                                            if (Array.isArray(data) && data.length > 0 && Array.isArray(data[0])) {
                                                // Validate: first item should be a valid year (4 digits starting with 19 or 20)
                                                const firstItem = data[0];
                                                if (Array.isArray(firstItem) && firstItem.length >= 2) {
                                                    const firstYear = String(firstItem[0]);
                                                    if (firstYear.length === 4 && (firstYear.startsWith('19') || firstYear.startsWith('20'))) {
                                                        debugInfo.data_found = true;
                                                        return { method: 'script_tag', data: data, debug: debugInfo };
                                                    }
                                                }
                                            }
                                        } catch(e) {
                                            // Try JSON.parse if eval fails
                                            try {
                                                const data = JSON.parse(match[1]);
                                                if (Array.isArray(data) && data.length > 0) {
                                                    const firstItem = data[0];
                                                    if (Array.isArray(firstItem) && firstItem.length >= 2) {
                                                        const firstYear = String(firstItem[0]);
                                                        if (firstYear.length === 4 && (firstYear.startsWith('19') || firstYear.startsWith('20'))) {
                                                            debugInfo.data_found = true;
                                                            return { method: 'script_tag_json', data: data, debug: debugInfo };
                                                        }
                                                    }
                                                }
                                            } catch(e2) {
                                                // Continue to next pattern
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Method 4: Extract from actual Google Scholar chart structure (a tags with spans)
                            debugInfo.methods_tried.push('gsc_oci_g_a');
                            const barsContainer = document.querySelector('#gsc_oci_graph_bars');
                            if (!barsContainer) {
                                debugInfo.container_found = false;
                                return { method: 'none', data: null, debug: debugInfo };
                            }
                            debugInfo.container_found = true;
                            
                            // Extract years from span.gsc_oci_g_t elements
                            const yearSpans = barsContainer.querySelectorAll('span.gsc_oci_g_t');
                            const yearLabels = [];
                            yearSpans.forEach(span => {
                                const yearText = span.textContent.trim();
                                if (yearText && /^(19|20)\\d{2}$/.test(yearText)) {
                                    yearLabels.push(yearText);
                                }
                            });
                            yearLabels.sort();
                            debugInfo.years_found = yearLabels.length;
                            debugInfo.year_labels = yearLabels.slice(0, 5); // First 5 for debugging
                            
                            // Extract bars (a.gsc_oci_g_a elements) with citation counts
                            const barLinks = barsContainer.querySelectorAll('a.gsc_oci_g_a');
                            debugInfo.bar_count = barLinks.length;
                            const trendData = [];
                            
                            barLinks.forEach((barLink, index) => {
                                // Get citation count from span.gsc_oci_g_al inside the link
                                const citationSpan = barLink.querySelector('span.gsc_oci_g_al');
                                let citations = 0;
                                
                                if (citationSpan) {
                                    const citationText = citationSpan.textContent.trim();
                                    citations = parseInt(citationText.replace(/,/g, '')) || 0;
                                }
                                
                                // Extract year from href if available, otherwise match by index
                                let year = null;
                                const href = barLink.getAttribute('href') || '';
                                const yearMatch = href.match(/as_ylo=(\\d{4})/);
                                if (yearMatch) {
                                    year = yearMatch[1];
                                } else if (index < yearLabels.length) {
                                    // Match by index if href doesn't have year
                                    year = yearLabels[index];
                                }
                                
                                if (year && citations >= 0) {
                                    trendData.push([year, citations]);
                                }
                            });
                            
                            debugInfo.trend_data_count = trendData.length;
                            if (trendData.length > 0) {
                                debugInfo.data_found = true;
                                debugInfo.sample_data = trendData.slice(0, 3); // First 3 for debugging
                                return { method: 'gsc_oci_g_a', data: trendData, debug: debugInfo };
                            }
                            
                            debugInfo.data_found = false;
                            return { method: 'none', data: null, debug: debugInfo };
                        }
                    """)
                    
                    if chart_data:
                        extraction_method = chart_data.get('method', 'unknown')
                        chart_data_list = chart_data.get('data', [])
                        debug_info = chart_data.get('debug', {})
                        
                        # Log diagnostic information
                        if debug_info:
                            methods_tried = debug_info.get('methods_tried', [])
                            self._log(f"Extraction methods tried: {', '.join(methods_tried)}", "DEBUG")
                            if 'script_count' in debug_info:
                                self._log(f"Scripts searched: {debug_info.get('script_count', 0)}", "DEBUG")
                            if 'bar_count' in debug_info:
                                self._log(f"Bar links (a.gsc_oci_g_a) found: {debug_info.get('bar_count', 0)}", "DEBUG")
                            if 'years_found' in debug_info:
                                self._log(f"Years found in container: {debug_info.get('years_found', 0)}", "DEBUG")
                                if 'year_labels' in debug_info:
                                    self._log(f"Year labels: {debug_info.get('year_labels', [])}", "DEBUG")
                            if 'trend_data_count' in debug_info:
                                self._log(f"Trend data points extracted: {debug_info.get('trend_data_count', 0)}", "DEBUG")
                                if 'sample_data' in debug_info:
                                    self._log(f"Sample extracted data: {debug_info.get('sample_data', [])}", "DEBUG")
                        
                        if chart_data_list and isinstance(chart_data_list, list):
                            valid_items = 0
                            invalid_items = 0
                            for item in chart_data_list:
                                if isinstance(item, list) and len(item) >= 2:
                                    try:
                                        # Validate year
                                        year_raw = item[0]
                                        if year_raw is None:
                                            invalid_items += 1
                                            continue
                                        year = str(int(year_raw))
                                        
                                        # Validate citations
                                        citations_raw = item[1]
                                        if citations_raw is None:
                                            citations = 0
                                        elif isinstance(citations_raw, (int, float)):
                                            citations = int(citations_raw)
                                        else:
                                            # Try to parse string numbers
                                            try:
                                                citations = int(float(str(citations_raw).replace(',', '')))
                                            except (ValueError, TypeError):
                                                citations = 0
                                        
                                        # Final validation
                                        if year and len(year) == 4 and citations >= 0:
                                            trend_data.append({'year': year, 'citations': citations})
                                            valid_items += 1
                                        else:
                                            invalid_items += 1
                                    except (ValueError, TypeError) as e:
                                        invalid_items += 1
                                        if self.verbose:
                                            self._log(f"Invalid trend data item: {item}, error: {str(e)}", "DEBUG")
                                        continue
                            
                            if self.verbose:
                                self._log(f"Data validation: {valid_items} valid, {invalid_items} invalid items", "DEBUG")
                                        
                            if trend_data:
                                self._log(f"Extracted {len(trend_data)} trend data points using method: {extraction_method}", "SUCCESS")
                                if self.verbose and trend_data:
                                    sample = trend_data[:3]
                                    self._log(f"Sample trend data: {sample}", "DEBUG")
                        else:
                            self._log(f"Method {extraction_method} found but returned invalid data format", "DEBUG")
                    else:
                        self._log("All extraction methods failed - no chart data found", "DEBUG")
                except Exception as e:
                    self._log(f"Error in Google Charts extraction: {str(e)}", "DEBUG")
            
            # Method 3: Try to extract from chart container if previous methods failed
            if not trend_data:
                try:
                    chart_data_dom = await page.evaluate("""
                        () => {
                            const container = document.querySelector('#gsc_graph_target, .gsc_graph_target');
                            if (container) {
                                const dataAttr = container.getAttribute('data-graph-data');
                                if (dataAttr) {
                                    try {
                                        return JSON.parse(dataAttr);
                                    } catch(e) {}
                                }
                                
                                const script = container.querySelector('script');
                                if (script) {
                                    const text = script.textContent || script.innerText || '';
                                    const match = text.match(/\\[\\[.*?\\]\\]/);
                                    if (match) {
                                        try {
                                            return eval('(' + match[0] + ')');
                                        } catch(e) {}
                                    }
                                }
                            }
                            return null;
                        }
                    """)
                    
                    if chart_data_dom and isinstance(chart_data_dom, list):
                        for item in chart_data_dom:
                            if isinstance(item, list) and len(item) >= 2:
                                try:
                                    year = str(int(item[0]))
                                    citations = int(item[1]) if isinstance(item[1], (int, float)) else 0
                                    if year and citations >= 0:
                                        trend_data.append({'year': year, 'citations': citations})
                                except (ValueError, TypeError):
                                    continue
                                    
                        if trend_data:
                            self._log(f"Extracted {len(trend_data)} trend data points from DOM", "SUCCESS")
                except Exception as e:
                    self._log(f"Error in DOM extraction: {str(e)}", "DEBUG")
            
            # Sort by year if we got data
            if trend_data:
                try:
                    trend_data.sort(key=lambda x: int(x['year']))
                    self._log(f"Citation trend extraction successful: {len(trend_data)} data points", "SUCCESS")
                except:
                    pass
            else:
                self._log("No citation trend data found - buttons will be disabled", "WARN")
                    
        except Exception as e:
            self._log(f"Error extracting citation trend: {str(e)}", "DEBUG")
        
        return trend_data
    
    async def _extract_doi_and_download(self, page: Page, paper_url: str, profile_url: str) -> Tuple[str, str, List[Dict], str, List[Dict]]:
        """Extract DOI, download link candidates, year, and citation trend from a paper detail page"""
        doi = ""
        download_link = ""
        year = ""
        citation_trend = []
        detail_candidates: List[Dict] = []
        seen_candidates: set = set()

        def register_download_candidate(url: str, source: str, meta: Dict) -> None:
            normalized = self._normalize_url(url)
            if not normalized or normalized in seen_candidates:
                return
            seen_candidates.add(normalized)
            detail_candidates.append({
                "url": normalized,
                "source": source,
                "meta": meta,
                "score": self._score_candidate(normalized, source),
            })
        
        try:
            # Navigate to paper page with better waiting
            await page.goto(paper_url, wait_until='networkidle', timeout=20000)
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Increased wait time for dynamic content
            
            self._log(f"Extracting DOI from: {paper_url}", "DEBUG")
            
            # Collect any immediate download candidates present on the page
            page_level_candidates = await self._collect_page_download_candidates(page)
            for candidate in page_level_candidates:
                register_download_candidate(
                    candidate.get("url", ""),
                    candidate.get("source", "page"),
                    candidate.get("meta", {})
                )
            if not download_link and detail_candidates:
                download_link = detail_candidates[0]["url"]
            
            # Comprehensive DOI extraction - multiple strategies
            
            # Strategy 1: Look for DOI links (href containing doi.org)
            if not doi:
                doi_link_selectors = [
                    'a[href*="doi.org"]',
                    'a[href*="dx.doi.org"]',
                ]
                
                for selector in doi_link_selectors:
                    try:
                        doi_links = await page.query_selector_all(selector)
                        self._log(f"Found {len(doi_links)} DOI links with selector {selector}", "DEBUG")
                        for link in doi_links:
                            href = await link.get_attribute('href')
                            if href and 'doi.org' in href:
                                # Extract DOI from URL (format: https://doi.org/10.1234/example)
                                doi_match = re.search(r'doi\.org/(10\.\d+/[^\s?&#]+)', href)
                                if doi_match:
                                    doi = doi_match.group(1)
                                    self.stats['doi_strategies'][1] += 1
                                    self._log(f"DOI found via Strategy 1 (links): {doi}", "SUCCESS")
                                    break
                                # Fallback: extract everything after doi.org/
                                else:
                                    potential_doi = href.split('doi.org/')[-1].split('?')[0].split('#')[0]
                                    if potential_doi.startswith('10.'):
                                        doi = potential_doi
                                        self.stats['doi_strategies'][1] += 1
                                        self._log(f"DOI found via Strategy 1 (links, fallback): {doi}", "SUCCESS")
                                        break
                        if doi:
                            break
                    except Exception as e:
                        self._log(f"Error in Strategy 1: {str(e)}", "WARN")
                        continue
            
            # Strategy Meta: Check meta tags
            if not doi:
                try:
                    meta_tags = await page.query_selector_all('meta[name*="doi"], meta[property*="doi"], meta[name*="citation_doi"]')
                    for meta in meta_tags:
                        content = await meta.get_attribute('content')
                        if content:
                            doi_match = re.search(r'(10\.\d+/[^\s]+)', content)
                            if doi_match:
                                doi = doi_match.group(1)
                                self.stats['doi_strategies']['meta'] += 1
                                self._log(f"DOI found via Meta tags: {doi}", "SUCCESS")
                                break
                except Exception as e:
                    self._log(f"Error in Meta strategy: {str(e)}", "WARN")
            
            # Strategy JSON-LD: Check JSON-LD structured data
            if not doi:
                try:
                    json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
                    for script in json_ld_scripts:
                        try:
                            content = await script.inner_text()
                            data = json.loads(content)
                            # Recursively search for DOI in JSON
                            def find_doi_in_dict(obj):
                                if isinstance(obj, dict):
                                    for key, value in obj.items():
                                        if 'doi' in key.lower() and isinstance(value, str):
                                            doi_match = re.search(r'(10\.\d+/[^\s]+)', value)
                                            if doi_match:
                                                return doi_match.group(1)
                                        elif isinstance(value, (dict, list)):
                                            result = find_doi_in_dict(value)
                                            if result:
                                                return result
                                elif isinstance(obj, list):
                                    for item in obj:
                                        result = find_doi_in_dict(item)
                                        if result:
                                            return result
                                return None
                            
                            found_doi = find_doi_in_dict(data)
                            if found_doi:
                                doi = found_doi
                                self.stats['doi_strategies']['jsonld'] += 1
                                self._log(f"DOI found via JSON-LD: {doi}", "SUCCESS")
                                break
                        except:
                            continue
                except Exception as e:
                    self._log(f"Error in JSON-LD strategy: {str(e)}", "WARN")
            
            # Strategy 2: Search entire page text for DOI patterns
            if not doi:
                try:
                    # Get all text content from the page
                    page_text = await page.evaluate('document.body.innerText')
                    
                    # Look for DOI patterns in text (10.xxxx/xxxxx)
                    doi_patterns = [
                        r'DOI[:\s]+(10\.\d+/[^\s\n\r]+)',  # "DOI: 10.1234/example"
                        r'doi[:\s]+(10\.\d+/[^\s\n\r]+)',  # "doi: 10.1234/example"
                        r'(10\.\d{4,}/[^\s\n\r<>"]+)',      # Standalone DOI pattern
                    ]
                    
                    for pattern in doi_patterns:
                        match = re.search(pattern, page_text, re.IGNORECASE)
                        if match:
                            potential_doi = match.group(1) if match.groups() else match.group(0)
                            # Clean up DOI (remove trailing punctuation, etc.)
                            potential_doi = re.sub(r'[.,;:)\]]+$', '', potential_doi)
                            if potential_doi.startswith('10.'):
                                doi = potential_doi
                                self.stats['doi_strategies'][2] += 1
                                self._log(f"DOI found via Strategy 2 (page text): {doi}", "SUCCESS")
                                break
                except Exception as e:
                    self._log(f"Error in Strategy 2: {str(e)}", "WARN")
            
            # Strategy 3: Check specific Google Scholar sections
            if not doi:
                try:
                    metadata_selectors = [
                        'div.gs_ri',
                        'div.gs_rs',
                        'div.gs_a',
                        'div#gsc_oci',
                        'div.gsc_oci_value',
                        'div.gs_scl',
                        'div.gs_ggs',
                    ]
                    
                    for selector in metadata_selectors:
                        try:
                            elements = await page.query_selector_all(selector)
                            for elem in elements:
                                text = await elem.inner_text()
                                if text:
                                    # Look for DOI in this element's text
                                    doi_match = re.search(r'(?:DOI|doi)[:\s]+(10\.\d+/[^\s\n\r]+)', text, re.IGNORECASE)
                                    if not doi_match:
                                        doi_match = re.search(r'(10\.\d{4,}/[^\s\n\r<>"]+)', text)
                                    
                                    if doi_match:
                                        potential_doi = doi_match.group(1) if doi_match.groups() else doi_match.group(0)
                                        potential_doi = re.sub(r'[.,;:)\]]+$', '', potential_doi)
                                        if potential_doi.startswith('10.'):
                                            doi = potential_doi
                                            self.stats['doi_strategies'][3] += 1
                                            self._log(f"DOI found via Strategy 3 (metadata sections): {doi}", "SUCCESS")
                                            break
                            if doi:
                                break
                        except:
                            continue
                except Exception as e:
                    self._log(f"Error in Strategy 3: {str(e)}", "WARN")
            
            # Strategy 4: Check all links for DOI in their text content
            if not doi:
                try:
                    all_links = await page.query_selector_all('a')
                    for link in all_links:
                        try:
                            text = await link.inner_text()
                            if text:
                                doi_match = re.search(r'(10\.\d+/[^\s]+)', text)
                                if doi_match:
                                    potential_doi = doi_match.group(1)
                                    # Also check href in case it's a DOI link
                                    href = await link.get_attribute('href')
                                    if href and 'doi.org' in href:
                                        doi_from_href = re.search(r'doi\.org/(10\.\d+/[^\s?&#]+)', href)
                                        if doi_from_href:
                                            potential_doi = doi_from_href.group(1)
                                    if potential_doi.startswith('10.'):
                                        doi = potential_doi
                                        self.stats['doi_strategies'][4] += 1
                                        self._log(f"DOI found via Strategy 4 (link text): {doi}", "SUCCESS")
                                        break
                        except:
                            continue
                except Exception as e:
                    self._log(f"Error in Strategy 4: {str(e)}", "WARN")
            
            # Strategy Citation: Try citation export (BibTeX/RIS)
            if not doi:
                try:
                    # Look for citation export links
                    citation_links = await page.query_selector_all('a[href*="citation"], a[href*="bibtex"], a[href*="ris"]')
                    for link in citation_links[:3]:  # Limit to first 3 to avoid too many requests
                        try:
                            href = await link.get_attribute('href')
                            if href and ('citation' in href.lower() or 'bibtex' in href.lower() or 'ris' in href.lower()):
                                # Try to get citation export page
                                export_url = href if href.startswith('http') else f"{self.base_url}{href}"
                                await page.goto(export_url, wait_until='networkidle', timeout=10000)
                                await asyncio.sleep(1)
                                
                                # Check page content for DOI
                                content = await page.content()
                                doi_match = re.search(r'doi[:\s=]+(10\.\d+/[^\s\n\r<>"]+)', content, re.IGNORECASE)
                                if not doi_match:
                                    doi_match = re.search(r'(10\.\d{4,}/[^\s\n\r<>"]+)', content)
                                
                                if doi_match:
                                    potential_doi = doi_match.group(1) if doi_match.groups() else doi_match.group(0)
                                    potential_doi = re.sub(r'[.,;:)\]]+$', '', potential_doi)
                                    if potential_doi.startswith('10.'):
                                        doi = potential_doi
                                        self.stats['doi_strategies']['citation'] += 1
                                        self._log(f"DOI found via Citation export: {doi}", "SUCCESS")
                                        # Return to paper page
                                        await page.goto(paper_url, wait_until='networkidle', timeout=15000)
                                        await asyncio.sleep(1)
                                        break
                                
                                # Return to paper page
                                await page.goto(paper_url, wait_until='networkidle', timeout=15000)
                                await asyncio.sleep(1)
                        except:
                            # Return to paper page on error
                            try:
                                await page.goto(paper_url, wait_until='networkidle', timeout=15000)
                                await asyncio.sleep(1)
                            except:
                                pass
                            continue
                except Exception as e:
                    self._log(f"Error in Citation export strategy: {str(e)}", "WARN")
            
            # Try to find download link - comprehensive approach
            self._log("Searching for download link...", "DEBUG")
            fallback_link = await self._find_pdf_link(page)
            if fallback_link:
                register_download_candidate(
                    fallback_link,
                    "detail_fallback",
                    {"strategy": "find_pdf_link"}
                )
                if not download_link:
                    download_link = fallback_link
            
            # If no direct PDF found, try "All versions" page
            if not download_link:
                all_versions_link = await self._find_pdf_in_all_versions(page)
                if all_versions_link:
                    register_download_candidate(
                        all_versions_link,
                        "detail_all_versions",
                        {}
                    )
                    download_link = all_versions_link
            
            # Strategy 0: Extract DOI from download link URL (if we found one and don't have DOI yet)
            if not doi and download_link:
                doi_from_url = self._extract_doi_from_url(download_link)
                if doi_from_url:
                    doi = doi_from_url
                    self.stats['doi_strategies']['url'] = self.stats['doi_strategies'].get('url', 0) + 1
                    self._log(f"DOI found from download URL: {doi}", "SUCCESS")
            
            # Track DOI found
            if doi:
                self.stats['doi_found'] += 1
            else:
                self._log("No DOI found after all strategies", "WARN")
            
            if download_link:
                self._log(f"Download link found: {download_link[:80]}...", "SUCCESS")
            else:
                self._log("No download link found", "WARN")
            
            # Extract year from detail page if not already found
            if not year:
                try:
                    # Try to find year in common metadata locations
                    # Check publication info sections
                    pub_selectors = [
                        'div.gs_ri',
                        'div.gs_rs',
                        'div.gs_a',
                        'div#gsc_oci',
                        'div.gsc_oci_value',
                    ]
                    for selector in pub_selectors:
                        try:
                            elements = await page.query_selector_all(selector)
                            for elem in elements:
                                text = await elem.inner_text()
                                if text:
                                    year_match = re.search(r'\b(19|20)\d{2}\b', text)
                                    if year_match:
                                        year = year_match.group()
                                        self._log(f"Year found from detail page: {year}", "DEBUG")
                                        break
                            if year:
                                break
                        except:
                            continue
                    
                    # Fallback: search entire page text
                    if not year:
                        try:
                            page_text = await page.evaluate('document.body.innerText')
                            year_match = re.search(r'\b(19|20)\d{2}\b', page_text)
                            if year_match:
                                year = year_match.group()
                                self._log(f"Year found from page text: {year}", "DEBUG")
                        except:
                            pass
                except Exception as e:
                    self._log(f"Error extracting year from detail page: {str(e)}", "DEBUG")
            
            # Extract citation trend data
            citation_trend = await self._extract_citation_trend(page)
            if citation_trend:
                self._log(f"Citation trend data extracted: {len(citation_trend)} data points", "DEBUG")
            
        except Exception as e:
            self._log(f"Error extracting DOI/download from {paper_url}: {str(e)}", "ERROR")
        finally:
            # Always return to profile page
            try:
                await page.goto(profile_url, wait_until='networkidle', timeout=15000)
                await asyncio.sleep(1)
            except Exception as e:
                self._log(f"Warning: Could not return to profile page: {str(e)}", "WARN")
        
        detail_candidates.sort(key=lambda candidate: (candidate.get("score", 99), candidate.get("url", "")))
        return doi, download_link, detail_candidates, year, citation_trend
    
    async def _find_pdf_link(self, page: Page) -> str:
        """Comprehensive PDF link detection on paper page"""
        download_link = ""
        
        # Wait a bit for dynamic content to load
        await asyncio.sleep(0.5)
        
        # Get ALL links on the page and check each one
        try:
            all_links = await page.query_selector_all('a[href]')
            for link in all_links:
                href = await link.get_attribute('href')
                if not href:
                    continue
                
                # Get link text
                try:
                    text = await link.inner_text()
                except:
                    text = ""
                
                href_lower = href.lower()
                text_lower = text.lower() if text else ""
                
                # Direct PDF file - highest priority
                if href.endswith('.pdf'):
                    download_link = href if href.startswith('http') else f"{self.base_url}{href}"
                    return download_link
                
                # Google Scholar PDF hosting - high priority
                if 'scholar.googleusercontent.com' in href or 'scholar.google.com/scholar_url' in href:
                    download_link = href if href.startswith('http') else f"{self.base_url}{href}"
                    return download_link
                
                # PDF in URL path
                if '/pdf' in href_lower or '/pdf?' in href_lower:
                    # Exclude citation/profile pages
                    if 'citations' not in href_lower and 'user=' not in href_lower:
                        download_link = href if href.startswith('http') else f"{self.base_url}{href}"
                        if not download_link.startswith('http'):
                            continue
                        return download_link
                
                # Repository PDF links
                repo_patterns = [
                    'arxiv.org/pdf',
                    'arxiv.org/abs',  # arXiv abstracts often have PDF links
                    'researchgate.net/publication',
                    'academia.edu',
                    'semanticscholar.org',
                    'biorxiv.org/content',
                    'medrxiv.org/content',
                    'ieee.org',  # IEEE Xplore
                    'ieeexplore.ieee.org',
                    'acm.org',  # ACM Digital Library
                    'dl.acm.org',
                    'springer.com',  # SpringerLink
                    'link.springer.com',
                    'sciencedirect.com',  # ScienceDirect
                    'pmc.ncbi.nlm.nih.gov',  # PubMed Central
                    'ncbi.nlm.nih.gov/pmc',
                    'nature.com',
                    'science.org',
                    'plos.org',
                    'hindawi.com',
                    'mdpi.com',
                    'frontiersin.org',
                ]
                if any(pattern in href for pattern in repo_patterns):
                    download_link = href if href.startswith('http') else f"{self.base_url}{href}"
                    self._log(f"Found repository link: {download_link[:80]}...", "DEBUG")
                    return download_link
                
                # PDF in link text (but verify it's not just a citation link)
                if 'pdf' in text_lower and 'citation' not in href_lower and 'user=' not in href_lower:
                    # Make sure it looks like a real PDF link
                    if any(indicator in href_lower for indicator in ['http', 'www', 'doi', 'arxiv', 'researchgate']):
                        download_link = href if href.startswith('http') else f"{self.base_url}{href}"
                        return download_link
        except Exception as e:
            pass
        
        # Also check specific Google Scholar sections with more targeted approach
        try:
            # Check for PDF in right sidebar or main content area
            content_areas = await page.query_selector_all('div.gs_ri, div.gs_ggs, div.gs_or_ggsm, div#gs_ocd, div.gs_oci')
            for area in content_areas:
                links = await area.query_selector_all('a[href]')
                for link in links:
                    href = await link.get_attribute('href')
                    if not href:
                        continue
                    
                    try:
                        text = await link.inner_text()
                    except:
                        text = ""
                    
                    href_lower = href.lower()
                    text_lower = text.lower() if text else ""
                    
                    # Check for PDF indicators
                    if (href.endswith('.pdf') or 
                        'scholar.googleusercontent.com' in href or
                        ('pdf' in href_lower and 'citation' not in href_lower) or
                        ('pdf' in text_lower and href.startswith('http'))):
                        download_link = href if href.startswith('http') else f"{self.base_url}{href}"
                        if download_link:
                            return download_link
        except:
            pass
        
        return download_link
    
    async def _find_pdf_in_all_versions(self, page: Page) -> str:
        """Follow 'All versions' link to find PDF download"""
        download_link = ""
        original_url = page.url  # Store current URL to return to
        
        try:
            # Look for "All versions" link
            all_versions_link = await page.query_selector('a:has-text("All versions")')
            
            if all_versions_link:
                href = await all_versions_link.get_attribute('href')
                if href:
                    versions_url = f"{self.base_url}{href}" if not href.startswith('http') else href
                    await page.goto(versions_url, wait_until='networkidle', timeout=15000)
                    await asyncio.sleep(1)
                    
                    # Comprehensive PDF link search in versions page
                    # Use the same comprehensive method as paper pages
                    download_link = await self._find_pdf_link(page)
                    
                    # If still not found, check each version row individually
                    if not download_link:
                        version_rows = await page.query_selector_all('tr.gs_ri, div.gs_ri, tr.gs_or, div.gs_or')
                        
                        for row in version_rows:
                            try:
                                # Get all links in this version row
                                links = await row.query_selector_all('a[href]')
                                for link in links:
                                    href = await link.get_attribute('href')
                                    if not href:
                                        continue
                                    
                                    try:
                                        text = await link.inner_text()
                                    except:
                                        text = ""
                                    
                                    href_lower = href.lower()
                                    text_lower = text.lower() if text else ""
                                    
                                    # Direct PDF or Google Scholar PDF
                                    if (href.endswith('.pdf') or 
                                        'scholar.googleusercontent.com' in href or
                                        ('pdf' in href_lower and 'citation' not in href_lower) or
                                        ('pdf' in text_lower and href.startswith('http'))):
                                        download_link = href if href.startswith('http') else f"{self.base_url}{href}"
                                        if download_link:
                                            break
                            except:
                                continue
                            
                            if download_link:
                                break
                    
                    # Return to original paper page
                    await page.goto(original_url, wait_until='networkidle', timeout=15000)
                    await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Error finding PDF in all versions: {str(e)}")
        
        return download_link
    
    async def _find_scihub_link(self, page: Page, doi: str = "", title: str = "", authors: str = "", profile_url: str = "") -> str:
        """
        Try to find PDF link from Sci-Hub
        
        Args:
            page: Playwright page object
            doi: DOI of the paper (preferred method)
            title: Title of the paper (fallback)
            authors: Authors of the paper (fallback, optional)
            profile_url: Profile URL to return to after Sci-Hub check
            
        Returns:
            PDF download link from Sci-Hub if found, empty string otherwise
        """
        if not doi and not title:
            self._log("Sci-Hub: No DOI or title provided", "WARN")
            return ""
        
        # Sci-Hub domains (try multiple as they change frequently)
        scihub_domains = [
            'https://sci-hub.se',
            'https://sci-hub.st',
            'https://sci-hub.ru',
        ]
        
        for domain_idx, domain in enumerate(scihub_domains):
            try:
                # Construct Sci-Hub URL
                if doi:
                    scihub_url = f"{domain}/{doi}"
                    self._log(f"Sci-Hub: Trying {domain} with DOI: {doi[:50]}...", "DEBUG")
                else:
                    # Use title (and optionally authors) as search query
                    search_query = title
                    if authors:
                        # Use first author's last name + title for better results
                        first_author = authors.split(',')[0].strip() if ',' in authors else authors.split(' ')[0]
                        search_query = f"{first_author} {title}"
                    # URL encode the search query
                    encoded_query = urllib.parse.quote(search_query)
                    scihub_url = f"{domain}/{encoded_query}"
                    self._log(f"Sci-Hub: Trying {domain} with query: {search_query[:50]}...", "DEBUG")
                
                # Navigate to Sci-Hub
                try:
                    await page.goto(scihub_url, wait_until='networkidle', timeout=20000)
                    await page.wait_for_load_state('networkidle')
                    await asyncio.sleep(3)  # Increased wait time for Sci-Hub to load
                except Exception as e:
                    self._log(f"Sci-Hub: Navigation error for {domain}: {str(e)}", "WARN")
                    continue
                
                # Check if we got redirected or if there's an error
                current_url = page.url
                if 'sci-hub' not in current_url.lower():
                    self._log(f"Sci-Hub: Redirected away from {domain} to {current_url[:50]}...", "WARN")
                    continue
                
                # Check for error messages or CAPTCHA
                try:
                    page_text = await page.evaluate('document.body.innerText')
                    if any(keyword in page_text.lower() for keyword in ['captcha', 'error', 'not found', 'unavailable']):
                        self._log(f"Sci-Hub: Error message detected on {domain}", "WARN")
                        if domain_idx < len(scihub_domains) - 1:
                            continue  # Try next domain
                except:
                    pass
                
                # Look for PDF download link on Sci-Hub page - comprehensive approach
                pdf_link = ""
                
                # Strategy 1: Check for embed#plugin with original-url (PRIMARY - Most common Sci-Hub pattern)
                try:
                    # Primary: Check for embed#plugin (Chrome PDF viewer - most common)
                    embed_plugin = await page.query_selector('embed#plugin')
                    if embed_plugin:
                        original_url = await embed_plugin.get_attribute('original-url')
                        if original_url:
                            # Clean URL: remove anchors, HTML entities, Chrome extension params
                            pdf_link = original_url.split('#')[0].split('&amp;')[0].split('&')[0]
                            # Validate it's a real PDF URL (not Chrome extension)
                            if pdf_link.startswith('http') and ('.pdf' in pdf_link.lower() or 'sci-hub' in pdf_link.lower()):
                                self._log(f"Sci-Hub: Found PDF via embed#plugin original-url: {pdf_link[:80]}...", "SUCCESS")
                                if profile_url:
                                    try:
                                        await page.goto(profile_url, wait_until='networkidle', timeout=15000)
                                        await asyncio.sleep(1)
                                    except:
                                        pass
                                return pdf_link
                    
                    # Fallback: Check all embeds for original-url attribute
                    all_embeds = await page.query_selector_all('embed[original-url]')
                    for embed in all_embeds:
                        original_url = await embed.get_attribute('original-url')
                        if original_url:
                            pdf_link = original_url.split('#')[0].split('&amp;')[0].split('&')[0]
                            if pdf_link.startswith('http') and ('.pdf' in pdf_link.lower() or 'sci-hub' in pdf_link.lower()):
                                self._log(f"Sci-Hub: Found PDF via embed original-url: {pdf_link[:80]}...", "SUCCESS")
                                if profile_url:
                                    try:
                                        await page.goto(profile_url, wait_until='networkidle', timeout=15000)
                                        await asyncio.sleep(1)
                                    except:
                                        pass
                                return pdf_link
                except Exception as e:
                    self._log(f"Sci-Hub: Error checking embed#plugin: {str(e)}", "DEBUG")
                
                # Strategy 1B: Check page source for original-url pattern (fallback if DOM query fails)
                if not pdf_link:
                    try:
                        page_content = await page.content()
                        # Look for original-url="..." pattern in embed tags
                        original_url_patterns = [
                            r'original-url=["\']([^"\']+\.pdf[^"\']*)["\']',  # original-url="...pdf..."
                            r'original-url=["\']([^"\']*sci-hub[^"\']*\.pdf[^"\']*)["\']',  # Sci-Hub specific
                        ]
                        for pattern in original_url_patterns:
                            matches = re.findall(pattern, page_content, re.IGNORECASE)
                            for match in matches:
                                if match:
                                    pdf_link = match.split('#')[0].split('&amp;')[0].split('&')[0]
                                    if pdf_link.startswith('http') and ('.pdf' in pdf_link.lower() or 'sci-hub' in pdf_link.lower()):
                                        self._log(f"Sci-Hub: Found PDF via page source original-url: {pdf_link[:80]}...", "SUCCESS")
                                        if profile_url:
                                            try:
                                                await page.goto(profile_url, wait_until='networkidle', timeout=15000)
                                                await asyncio.sleep(1)
                                            except:
                                                pass
                                        return pdf_link
                    except Exception as e:
                        self._log(f"Sci-Hub: Error checking page source for original-url: {str(e)}", "DEBUG")
                
                # Strategy 2: Check for iframe with PDF
                if not pdf_link:
                    try:
                        iframe_selectors = [
                            'iframe#pdf',
                            'iframe[src*=".pdf"]',
                            'iframe[src*="/downloads/"]',
                            'iframe[src*="/pdf/"]',
                        ]
                        for selector in iframe_selectors:
                            iframe = await page.query_selector(selector)
                            if iframe:
                                src = await iframe.get_attribute('src')
                                if src:
                                    pdf_link = src if src.startswith('http') else f"{domain}{src}"
                                    self._log(f"Sci-Hub: Found PDF via iframe: {pdf_link[:80]}...", "SUCCESS")
                                    break
                    except Exception as e:
                        self._log(f"Sci-Hub: Error checking iframes: {str(e)}", "DEBUG")
                
                # Strategy 3: Check for download button/link
                if not pdf_link:
                    try:
                        button_selectors = [
                            'button#save',
                            'a#save',
                            'button:has-text("save")',
                            'a:has-text("save")',
                            'a:has-text("download")',
                            'a[onclick*="save"]',
                        ]
                        for selector in button_selectors:
                            button = await page.query_selector(selector)
                            if button:
                                # Check if button has href or onclick that leads to PDF
                                href = await button.get_attribute('href')
                                onclick = await button.get_attribute('onclick')
                                if href and '.pdf' in href.lower():
                                    pdf_link = href if href.startswith('http') else f"{domain}{href}"
                                    self._log(f"Sci-Hub: Found PDF via button/link: {pdf_link[:80]}...", "SUCCESS")
                                    break
                                elif onclick:
                                    # Extract URL from onclick handler
                                    url_match = re.search(r'https?://[^\s"\'<>]+\.pdf', onclick)
                                    if url_match:
                                        pdf_link = url_match.group(0)
                                        self._log(f"Sci-Hub: Found PDF via onclick: {pdf_link[:80]}...", "SUCCESS")
                                        break
                    except Exception as e:
                        self._log(f"Sci-Hub: Error checking buttons: {str(e)}", "DEBUG")
                
                # Strategy 4: Check all links for PDF
                if not pdf_link:
                    try:
                        all_links = await page.query_selector_all('a[href]')
                        for link in all_links:
                            try:
                                href = await link.get_attribute('href')
                                if href and ('.pdf' in href.lower() or '/downloads/' in href.lower() or '/pdf/' in href.lower()):
                                    # Make sure it's not a navigation link
                                    if not any(nav in href.lower() for nav in ['home', 'about', 'contact', 'search']):
                                        pdf_link = href if href.startswith('http') else f"{domain}{href}"
                                        self._log(f"Sci-Hub: Found PDF via link: {pdf_link[:80]}...", "SUCCESS")
                                        break
                            except:
                                continue
                    except Exception as e:
                        self._log(f"Sci-Hub: Error checking links: {str(e)}", "DEBUG")
                
                # Strategy 5: Check page source for PDF URLs
                if not pdf_link:
                    try:
                        page_content = await page.content()
                        # Look for PDF URLs in various formats
                        pdf_patterns = [
                            r'https?://[^\s"\'<>]+\.pdf',
                            r'https?://[^\s"\'<>]+/downloads/[^\s"\'<>]+',
                            r'https?://[^\s"\'<>]+/pdf/[^\s"\'<>]+',
                            r'src=["\']([^"\']+\.pdf)',
                            r'href=["\']([^"\']+\.pdf)',
                        ]
                        for pattern in pdf_patterns:
                            matches = re.findall(pattern, page_content, re.IGNORECASE)
                            for match in matches:
                                if isinstance(match, tuple):
                                    match = match[0] if match else ""
                                if match and '.pdf' in match.lower():
                                    pdf_link = match if match.startswith('http') else f"{domain}{match}"
                                    # Validate it's a real PDF URL
                                    if 'sci-hub' in pdf_link.lower() or pdf_link.startswith('http'):
                                        self._log(f"Sci-Hub: Found PDF via page source: {pdf_link[:80]}...", "SUCCESS")
                                        break
                            if pdf_link:
                                break
                    except Exception as e:
                        self._log(f"Sci-Hub: Error checking page source: {str(e)}", "DEBUG")
                
                # Strategy 6: Check for embedded PDF viewer
                if not pdf_link:
                    try:
                        # Sci-Hub sometimes uses PDF.js or similar viewers
                        viewer_elements = await page.query_selector_all('canvas, embed[type="application/pdf"], object[type="application/pdf"]')
                        if viewer_elements:
                            # Try to find the source URL
                            for elem in viewer_elements:
                                src = await elem.get_attribute('src') or await elem.get_attribute('data')
                                if src and '.pdf' in src.lower():
                                    pdf_link = src if src.startswith('http') else f"{domain}{src}"
                                    self._log(f"Sci-Hub: Found PDF via viewer: {pdf_link[:80]}...", "SUCCESS")
                                    break
                    except Exception as e:
                        self._log(f"Sci-Hub: Error checking PDF viewer: {str(e)}", "DEBUG")
                
                if pdf_link:
                    # Return to profile page before returning the link
                    if profile_url:
                        try:
                            await page.goto(profile_url, wait_until='networkidle', timeout=15000)
                            await asyncio.sleep(1)
                        except Exception as e:
                            self._log(f"Sci-Hub: Error returning to profile: {str(e)}", "WARN")
                    return pdf_link
                else:
                    self._log(f"Sci-Hub: No PDF found on {domain}", "DEBUG")
                    
            except Exception as e:
                self._log(f"Sci-Hub: Exception on {domain}: {str(e)}", "ERROR")
                # If this domain fails, try next one
                continue
        
        # Return to profile page if we didn't find a link
        if profile_url:
            try:
                await page.goto(profile_url, wait_until='networkidle', timeout=15000)
                await asyncio.sleep(1)
            except Exception as e:
                self._log(f"Sci-Hub: Error returning to profile after failure: {str(e)}", "WARN")
        
        return ""
    
    async def _load_more_papers(self, page: Page) -> bool:
        """Click 'Show more' button to load additional papers"""
        # Define button selectors (used in multiple places)
        button_selectors = [
            'button#gsc_bpf_more',
            'button:has-text("Show more")',
            'button:has-text("show more")',
            'button.gsc_bpf_more',
            'a:has-text("Show more")',
        ]
        
        # Count current papers before clicking
        try:
            current_papers = await page.query_selector_all('tr.gsc_a_tr')
            initial_count = len(current_papers)
        except:
            initial_count = 0
        
        # Try multiple selectors for "Show more" button
        show_more_button = None
        for selector in button_selectors:
            try:
                button = await page.query_selector(selector)
                if button:
                    show_more_button = button
                    break
            except:
                continue
        
        if not show_more_button:
            # Debug: Check if button exists but wasn't found with our selectors
            try:
                all_buttons = await page.query_selector_all('button')
                for btn in all_buttons:
                    try:
                        text = await btn.inner_text()
                        if text and ('show more' in text.lower() or 'more' in text.lower()):
                            # Found a button with "more" text, try using it
                            show_more_button = btn
                            break
                    except:
                        continue
            except:
                pass
            
            if not show_more_button:
                return False
        
        # Try to make button visible by scrolling to it
        try:
            await show_more_button.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
        except:
            pass
        
        # Check if button is clickable
        try:
            is_visible = await show_more_button.is_visible()
            is_enabled = await show_more_button.is_enabled()
            
            if not (is_visible and is_enabled):
                # Try to click anyway (might be hidden but clickable)
                try:
                    await show_more_button.click(force=True)
                except:
                    return False
            else:
                await show_more_button.click()
        except Exception as e:
            return False
        
        # Wait for new content to load and verify papers were added
        max_wait = 10  # Maximum wait time in seconds
        wait_interval = 0.5
        waited = 0
        max_retries = 3  # Try clicking button multiple times if needed
        retry_count = 0
        
        while waited < max_wait:
            await asyncio.sleep(wait_interval)
            waited += wait_interval
            
            try:
                new_papers = await page.query_selector_all('tr.gsc_a_tr')
                new_count = len(new_papers)
                
                # If we got more papers, loading is complete
                if new_count > initial_count:
                    return True
                
                # If count is same but we've waited a bit, try clicking again
                if waited >= 3 and new_count == initial_count and retry_count < max_retries:
                    # Check if button still exists and try clicking again
                    try:
                        # Try to find button again (it might have moved)
                        for selector in button_selectors:
                            retry_button = await page.query_selector(selector)
                            if retry_button:
                                try:
                                    await retry_button.scroll_into_view_if_needed()
                                    await asyncio.sleep(0.5)
                                    if await retry_button.is_visible():
                                        await retry_button.click()
                                        retry_count += 1
                                        waited = 0  # Reset wait timer
                                        break
                                except:
                                    continue
                    except:
                        pass
                
                # If count is same and we've waited enough, might be done loading
                if waited >= 5 and new_count == initial_count:
                    # Check if button still exists (if not, we're done)
                    try:
                        button_still_exists = False
                        for selector in button_selectors:
                            btn = await page.query_selector(selector)
                            if btn and await btn.is_visible():
                                button_still_exists = True
                                break
                        if not button_still_exists:
                            return False  # No more papers
                    except:
                        pass
            except:
                pass
        
        # Verify papers were actually added
        try:
            final_papers = await page.query_selector_all('tr.gsc_a_tr')
            final_count = len(final_papers)
            if final_count > initial_count:
                return True
        except:
            pass
        
        return False

