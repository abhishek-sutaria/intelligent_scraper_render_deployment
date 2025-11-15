"""
Data extraction utilities for parsing paper metadata
"""
import re
from typing import Dict, Optional
from bs4 import BeautifulSoup


class PaperExtractor:
    """Utility class for extracting and cleaning paper metadata"""
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return ""
        return " ".join(text.split())
    
    @staticmethod
    def extract_year(text: str) -> str:
        """Extract publication year from text"""
        if not text:
            return ""
        
        # Look for 4-digit year (1900-2099)
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            return year_match.group()
        return ""
    
    @staticmethod
    def extract_doi(text: str) -> str:
        """Extract DOI from text"""
        if not text:
            return ""
        
        # DOI pattern: 10.xxxx/xxxxx
        doi_match = re.search(r'10\.\d+/[^\s\)]+', text)
        if doi_match:
            return doi_match.group().rstrip('.,;')
        return ""
    
    @staticmethod
    def normalize_authors(authors: str) -> str:
        """Normalize author names"""
        if not authors:
            return ""
        
        # Remove extra whitespace and normalize
        authors = PaperExtractor.clean_text(authors)
        return authors
    
    @staticmethod
    def validate_paper_data(paper: Dict) -> Dict:
        """Validate and clean paper data"""
        validated = {
            'title': PaperExtractor.clean_text(paper.get('title', '')),
            'authors': PaperExtractor.normalize_authors(paper.get('authors', '')),
            'year': paper.get('year', ''),
            'publication': PaperExtractor.clean_text(paper.get('publication', '')),
            'citations': paper.get('citations', 'Missing citations'),
            'citation_trend': paper.get('citation_trend', []),
            'doi': paper.get('doi', ''),
            'download_link': paper.get('download_link', '')
        }
        
        # Ensure year is extracted if not already present
        if not validated['year'] and validated['publication']:
            validated['year'] = PaperExtractor.extract_year(validated['publication'])
            if validated['year']:
                # Remove year from publication string
                validated['publication'] = validated['publication'].replace(validated['year'], '').strip()
        
        return validated




