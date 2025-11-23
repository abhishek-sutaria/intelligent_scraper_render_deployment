import asyncio
import json
import os
import subprocess
import sys
import traceback
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from extractor import PaperExtractor
from html_generator import HTMLGenerator
from semantic_scholar_scraper import SemanticScholarScraper

BASE_DIR = Path(__file__).parent
WEB_DIR = BASE_DIR / "web"
ARTIFACT_DIR = BASE_DIR / "artifacts"
HTML_DIR = ARTIFACT_DIR / "html"
DEBUG_DIR = ARTIFACT_DIR / "debug"

for folder in (HTML_DIR, DEBUG_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Scholar Scraper UI")

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/artifacts", StaticFiles(directory=ARTIFACT_DIR), name="artifacts")


async def _ensure_playwright_browsers():
    """Ensure Playwright browsers are installed, install if missing."""
    try:
        # First, try to get the executable path to check if browsers actually exist
        browser_exists = False
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser_path = p.chromium.executable_path
                if browser_path and Path(browser_path).exists():
                    print(f"[Startup] ✅ Playwright browsers already installed at: {browser_path}")
                    browser_exists = True
                else:
                    print(f"[Startup] ⚠️  Browser executable not found at: {browser_path}")
        except Exception as check_exc:
            print(f"[Startup] ⚠️  Could not check browser path: {check_exc}")
        
        if not browser_exists:
            # Browsers don't exist, install them
            print("[Startup] Installing Playwright browsers...")
            install_result = subprocess.run(
                ["playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            if install_result.returncode == 0:
                print("[Startup] ✅ Playwright browsers installed successfully")
                if install_result.stdout:
                    print(f"[Startup] Installation output: {install_result.stdout[:500]}")
            else:
                print(f"[Startup] ⚠️  Browser installation failed (exit code: {install_result.returncode})")
                if install_result.stderr:
                    print(f"[Startup] Error: {install_result.stderr[:500]}")
                if install_result.stdout:
                    print(f"[Startup] Output: {install_result.stdout[:500]}")
    except Exception as exc:
        print(f"[Startup] ⚠️  Could not check/install browsers: {exc}")
        import traceback
        print(f"[Startup] Traceback: {traceback.format_exc()}")


@app.on_event("startup")
async def startup_event():
    """Ensure Playwright browsers are installed on startup."""
    await _ensure_playwright_browsers()


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


class ScrapeRequest(BaseModel):
    profile_url: HttpUrl
    max_papers: int = Field(50, ge=1, le=1000)


jobs: Dict[str, Dict[str, Any]] = {}


def extract_author_id(profile_url: str) -> str:
    parsed = urllib.parse.urlparse(profile_url)
    path_parts = parsed.path.rstrip("/").split("/")
    if len(path_parts) >= 2 and path_parts[-1].isdigit():
        return path_parts[-1]
    raise ValueError(
        "Semantic Scholar profile URL must look like "
        "'https://www.semanticscholar.org/author/Name/ID'."
    )


@app.post("/api/scrape")
async def start_scrape(request: ScrapeRequest) -> Dict[str, str]:
    try:
        author_id = extract_author_id(str(request.profile_url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "status": "queued",
        "message": "Request accepted",
        "stage": "",
        "percentage": 0,
        "result": None,
        "error": None,
    }

    asyncio.create_task(
        run_scrape_job(
            job_id=job_id,
            author_id=author_id,
            profile_url=str(request.profile_url),
            max_papers=request.max_papers,
        )
    )

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def scrape_status(job_id: str) -> Dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/diagnose/playwright")
async def diagnose_playwright() -> Dict[str, Any]:
    """Diagnostic endpoint to test Playwright installation and browser availability."""
    diagnostics = {
        "timestamp": datetime.utcnow().isoformat(),
        "python_version": sys.version,
        "playwright_package": {},
        "browser_installation": {},
        "browser_launch_test": {},
        "environment": {},
        "file_system_checks": {},
    }
    
    # 1. Check Playwright Python package
    try:
        from playwright.async_api import async_playwright
        diagnostics["playwright_package"]["imported"] = True
        diagnostics["playwright_package"]["version"] = "unknown"  # Playwright doesn't expose version easily
    except ImportError as exc:
        diagnostics["playwright_package"]["imported"] = False
        diagnostics["playwright_package"]["error"] = str(exc)
        return diagnostics
    
    # 2. Check browser installation via CLI
    try:
        result = subprocess.run(
            ["playwright", "install", "--dry-run", "chromium"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        diagnostics["browser_installation"]["dry_run_exit_code"] = result.returncode
        diagnostics["browser_installation"]["dry_run_stdout"] = result.stdout
        diagnostics["browser_installation"]["dry_run_stderr"] = result.stderr
        diagnostics["browser_installation"]["browsers_installed"] = result.returncode == 0
    except FileNotFoundError:
        diagnostics["browser_installation"]["playwright_cli_not_found"] = True
    except subprocess.TimeoutExpired:
        diagnostics["browser_installation"]["timeout"] = True
    except Exception as exc:
        diagnostics["browser_installation"]["error"] = str(exc)
    
    # 3. Check browser executable paths
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser_path = p.chromium.executable_path
            diagnostics["browser_installation"]["executable_path"] = browser_path
            diagnostics["browser_installation"]["executable_exists"] = Path(browser_path).exists() if browser_path else False
    except Exception as exc:
        diagnostics["browser_installation"]["executable_check_error"] = str(exc)
    
    # 4. Try to actually launch a browser
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ],
                timeout=10000,
            )
            diagnostics["browser_launch_test"]["success"] = True
            diagnostics["browser_launch_test"]["browser_version"] = browser.version
            await browser.close()
    except Exception as exc:
        diagnostics["browser_launch_test"]["success"] = False
        diagnostics["browser_launch_test"]["error_type"] = type(exc).__name__
        diagnostics["browser_launch_test"]["error_message"] = str(exc)
        diagnostics["browser_launch_test"]["traceback"] = traceback.format_exc()
    
    # 5. Check environment variables
    diagnostics["environment"]["PLAYWRIGHT_BROWSERS_PATH"] = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "not set")
    diagnostics["environment"]["PATH"] = os.getenv("PATH", "not set")
    diagnostics["environment"]["HOME"] = os.getenv("HOME", "not set")
    diagnostics["environment"]["USER"] = os.getenv("USER", "not set")
    
    # 6. Check common browser cache locations
    cache_paths = [
        "/opt/render/.cache/ms-playwright",
        os.path.expanduser("~/.cache/ms-playwright"),
        "/tmp/.cache/ms-playwright",
    ]
    for cache_path in cache_paths:
        path_obj = Path(cache_path)
        diagnostics["file_system_checks"][cache_path] = {
            "exists": path_obj.exists(),
            "is_dir": path_obj.is_dir() if path_obj.exists() else False,
        }
        if path_obj.exists() and path_obj.is_dir():
            try:
                chromium_dirs = list(path_obj.glob("chromium*"))
                diagnostics["file_system_checks"][cache_path]["chromium_dirs"] = [
                    str(d) for d in chromium_dirs
                ]
            except Exception as exc:
                diagnostics["file_system_checks"][cache_path]["list_error"] = str(exc)
    
    return diagnostics


async def run_scrape_job(job_id: str, author_id: str, profile_url: str, max_papers: int) -> None:
    job = jobs[job_id]

    def progress_handler(stage: str, current: int, total: int, percentage: float) -> None:
        job["stage"] = stage
        percent_value = round(min(100.0, max(0.0, percentage)))
        job["percentage"] = percent_value
        job["message"] = f"{stage}… {percent_value}% complete"

    job["status"] = "running"
    job["message"] = "Fetching data…"
    job["percentage"] = 5

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    html_path = HTML_DIR / f"semantic_scholar_{author_id}_{timestamp}.html"
    debug_path = DEBUG_DIR / f"debug_{author_id}_{timestamp}.json"

    scraper = SemanticScholarScraper(
        api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
        max_papers=max_papers,
        verbose=False,
        collect_debug=True,
        progress_handler=progress_handler,
    )

    try:
        papers = await scraper.scrape_profile(author_id)
        if not papers:
            job["status"] = "failed"
            job["message"] = "No papers found for this author."
            job["percentage"] = 100
            return

        validated_papers = [PaperExtractor.validate_paper_data(paper) for paper in papers]
        html_content = HTMLGenerator.generate_html(validated_papers, author_id)
        html_path.write_text(html_content, encoding="utf-8")

        debug_report = scraper.build_debug_report(user_id=author_id)
        debug_path.write_text(json.dumps(debug_report, indent=2), encoding="utf-8")

        job["status"] = "completed"
        job["message"] = f"Scrape complete. Collected {len(validated_papers)} papers."
        job["percentage"] = 100
        job["stage"] = "Completed"
        job["result"] = {
            "author_id": author_id,
            "profile_url": profile_url,
            "total_papers": len(validated_papers),
            "html_url": f"/artifacts/html/{html_path.name}",
            "debug_url": f"/artifacts/debug/{debug_path.name}",
        }
    except Exception as exc:  # pylint: disable=broad-except
        traceback.print_exc()
        job["status"] = "failed"
        job["error"] = str(exc)
        job["message"] = "Scrape failed. Check server logs for details."
        job["percentage"] = 100

