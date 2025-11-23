"""
Main entry point for Semantic Scholar Profile Scraper
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from semantic_scholar_scraper import SemanticScholarScraper
from extractor import PaperExtractor
from html_generator import HTMLGenerator


async def main():
    """Main function to orchestrate scraping and HTML generation"""
    parser = argparse.ArgumentParser(
        description='Scrape Semantic Scholar author profile and generate HTML checklist',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python main.py 40066064
  python main.py "Jonah A. Berger"
  python main.py https://www.semanticscholar.org/author/Jonah-A.-Berger/40066064 --api-key YOUR_API_KEY
        """
    )
    
    parser.add_argument(
        'author_input',
        type=str,
        help='Semantic Scholar author ID, name, or profile URL'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output HTML filename (default: semantic_scholar_{author_id}.html)'
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
        '--api-key',
        type=str,
        default=None,
        help='Semantic Scholar API key (optional, for higher rate limits)'
    )
    
    parser.add_argument(
        '--debug-report',
        type=str,
        default=None,
        help='Optional path to save a JSON debug report with candidate and source information'
    )
    
    args = parser.parse_args()
    
    if not args.author_input or len(args.author_input.strip()) == 0:
        print("Error: Invalid author input. Provide an author ID, name, or Semantic Scholar URL.")
        sys.exit(1)
    author_identifier = SemanticScholarScraper.extract_author_id_from_url(args.author_input)
    if not author_identifier:
        print("Error: Unable to parse author identifier. Please double-check the input.")
        sys.exit(1)
    
    # Determine output filename
    if args.output:
        output_file = args.output
        if not output_file.endswith('.html'):
            output_file += '.html'
    else:
        safe_id = author_identifier.replace('/', '_').replace(' ', '_')
        output_file = f"semantic_scholar_{safe_id}.html"
    
    print("=" * 60)
    print("Semantic Scholar Profile Scraper")
    print("=" * 60)
    print(f"Author Input: {args.author_input}")
    print(f"Resolved Author ID/Name: {author_identifier}")
    print(f"Max Papers: {args.max_papers}")
    print(f"API Key Provided: {'Yes' if args.api_key else 'No'}")
    print(f"Output File: {output_file}")
    print("=" * 60)
    print()
    
    collect_debug = bool(args.debug_report)
    
    # Initialize scraper
    scraper = SemanticScholarScraper(
        api_key=args.api_key,
        max_papers=args.max_papers,
        verbose=args.verbose,
        collect_debug=collect_debug
    )
    
    # Scrape profile
    print("Starting scraping process...")
    try:
        papers = await scraper.scrape_profile(args.author_input)
        
        if not papers:
            print("\nError: No papers found. Please check:")
            print("  1. The author ID/name/URL is correct")
            print("  2. The author has public papers on Semantic Scholar")
            print("  3. Your internet connection is working")
            print("  4. (Optional) Provide an API key if you hit rate limits")
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
        print(f"API Calls Made: {scraper.stats.get('api_calls', 0)}")
        
        print("=" * 60)
        
        if args.debug_report:
            debug_report_path = Path(args.debug_report)
            if not debug_report_path.parent.exists():
                debug_report_path.parent.mkdir(parents=True, exist_ok=True)
            report_payload = scraper.build_debug_report(author_identifier)
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



