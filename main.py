"""
Main entry point for Google Scholar Profile Scraper
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from scraper import GoogleScholarScraper
from extractor import PaperExtractor
from html_generator import HTMLGenerator


async def main():
    """Main function to orchestrate scraping and HTML generation"""
    parser = argparse.ArgumentParser(
        description='Scrape Google Scholar profile and generate HTML checklist',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python main.py x8xNLZQAAAAJ
  python main.py x8xNLZQAAAAJ --visible
  python main.py x8xNLZQAAAAJ --output custom_name.html
        """
    )
    
    parser.add_argument(
        'user_id',
        type=str,
        help='Google Scholar user ID (e.g., x8xNLZQAAAAJ)'
    )
    
    parser.add_argument(
        '--visible',
        action='store_true',
        help='Run browser in visible mode (default: headless)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output HTML filename (default: scholar_{user_id}.html)'
    )
    
    parser.add_argument(
        '--max-papers',
        type=int,
        default=50,
        help='Maximum number of papers to scrape (default: 50)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug logging (default: off)'
    )
    
    parser.add_argument(
        '--debug-report',
        type=str,
        default=None,
        help='Optional path to save a JSON debug report with candidate and source information'
    )
    
    args = parser.parse_args()
    
    # Validate user ID
    if not args.user_id or len(args.user_id) < 5:
        print("Error: Invalid user ID. Please provide a valid Google Scholar user ID.")
        sys.exit(1)
    
    # Determine output filename
    if args.output:
        output_file = args.output
        if not output_file.endswith('.html'):
            output_file += '.html'
    else:
        output_file = f"scholar_{args.user_id}.html"
    
    print("=" * 60)
    print("Google Scholar Profile Scraper")
    print("=" * 60)
    print(f"User ID: {args.user_id}")
    print(f"Max Papers: {args.max_papers}")
    print(f"Browser Mode: {'Visible' if args.visible else 'Headless'}")
    print(f"Output File: {output_file}")
    print("=" * 60)
    print()
    
    collect_debug = bool(args.debug_report)
    
    # Initialize scraper
    scraper = GoogleScholarScraper(
        headless=not args.visible,
        max_papers=args.max_papers,
        verbose=args.verbose,
        collect_debug=collect_debug
    )
    
    # Scrape profile
    print("Starting scraping process...")
    try:
        papers = await scraper.scrape_profile(args.user_id)
        
        if not papers:
            print("\nError: No papers found. Please check:")
            print("  1. The user ID is correct")
            print("  2. The profile is public and accessible")
            print("  3. Your internet connection is working")
            sys.exit(1)
        
        print(f"\nSuccessfully scraped {len(papers)} papers!")
        print("\nValidating and cleaning data...")
        
        # Validate and clean paper data
        validated_papers = []
        for paper in papers:
            validated = PaperExtractor.validate_paper_data(paper)
            validated_papers.append(validated)
        
        # Generate HTML
        print("Generating HTML file...")
        html_content = HTMLGenerator.generate_html(validated_papers, args.user_id)
        
        # Save to file
        output_path = Path(output_file)
        output_path.write_text(html_content, encoding='utf-8')
        
        print(f"\n✓ Success! HTML file saved as: {output_file}")
        print(f"  Location: {output_path.absolute()}")
        print("\nYou can now open the HTML file in your browser to view the checklist.")
        
        # Print summary
        print("\n" + "=" * 60)
        print("Summary:")
        print("=" * 60)
        print(f"Total Papers: {len(validated_papers)}")
        
        papers_with_doi = sum(1 for p in validated_papers if p.get('doi'))
        papers_with_download = sum(1 for p in validated_papers if p.get('download_link'))
        
        print(f"Papers with DOI: {papers_with_doi}")
        print(f"Papers with Download Link: {papers_with_download}")
        
        # Print detailed statistics if available
        if hasattr(scraper, 'stats') and scraper.stats:
            stats = scraper.stats
            if stats.get('download_gs', 0) > 0 or stats.get('download_scihub', 0) > 0:
                print(f"\nDownload Link Sources:")
                print(f"  - Google Scholar: {stats.get('download_gs', 0)}")
                print(f"  - Sci-Hub: {stats.get('download_scihub', 0)}")
                print(f"  - Not Found: {stats.get('download_none', 0)}")
            
            if stats.get('scihub_attempts', 0) > 0:
                print(f"\nSci-Hub Statistics:")
                print(f"  - Attempts: {stats.get('scihub_attempts', 0)}")
                print(f"  - Success: {stats.get('scihub_success', 0)}")
                print(f"  - Failed: {stats.get('scihub_failed', 0)}")
            
            if stats.get('doi_found', 0) > 0 and args.verbose:
                print(f"\nDOI Extraction Strategies:")
                for strategy, count in stats.get('doi_strategies', {}).items():
                    if count > 0:
                        print(f"  - Strategy {strategy}: {count}")
        
        print("=" * 60)
        
        if args.debug_report:
            debug_report_path = Path(args.debug_report)
            if not debug_report_path.parent.exists():
                debug_report_path.parent.mkdir(parents=True, exist_ok=True)
            report_payload = scraper.build_debug_report(args.user_id)
            debug_report_path.write_text(json.dumps(report_payload, indent=2), encoding='utf-8')
            print(f"\nDebug report saved to: {debug_report_path.absolute()}")
        
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())



