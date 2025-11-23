"""
HTML Generator for creating interactive checklist table
"""
from typing import List, Dict


class HTMLGenerator:
    """Generates interactive HTML checklist table for papers"""
    
    @staticmethod
    def generate_html(papers: List[Dict], author_id: str) -> str:
        """
        Generate HTML file with interactive checklist table
        
        Args:
            papers: List of paper dictionaries
            author_id: Semantic Scholar author identifier
            
        Returns:
            HTML string
        """
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Semantic Scholar Papers - {author_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #1e3a8a 0%, #0ea5e9 50%, #06b6d4 100%);
            background-attachment: fixed;
            padding: 30px 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 16px;
            box-shadow: 0 25px 80px rgba(30, 58, 138, 0.4), 0 0 0 1px rgba(14, 165, 233, 0.1);
            overflow: hidden;
            animation: fadeInUp 0.6s ease-out;
        }}
        
        @keyframes fadeInUp {{
            from {{
                opacity: 0;
                transform: translateY(20px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .header {{
            background: linear-gradient(135deg, #1e3a8a 0%, #0ea5e9 100%);
            color: #ffffff;
            padding: 50px 40px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }}
        
        .header::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(135deg, rgba(6, 182, 212, 0.15) 0%, rgba(14, 165, 233, 0.1) 100%);
            pointer-events: none;
        }}
        
        .header::after {{
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, transparent, #06b6d4, transparent);
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 12px;
            font-weight: 700;
            letter-spacing: -0.5px;
            color: #ffffff;
            text-shadow: 0 2px 10px rgba(6, 182, 212, 0.4);
            position: relative;
            z-index: 1;
        }}
        
        .header p {{
            font-size: 1.15em;
            color: #06b6d4;
            font-weight: 500;
            letter-spacing: 0.5px;
            position: relative;
            z-index: 1;
        }}
        
        .controls {{
            padding: 25px 40px;
            background: linear-gradient(to bottom, #f8f8f8, #ffffff);
            border-bottom: 2px solid #e8e8e8;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }}
        
        .stats {{
            font-size: 1em;
            color: #2d2d2d;
            font-weight: 600;
        }}
        
        .stats strong {{
            color: #1a1a1a;
        }}
        
        .stats span#checked-count {{
            color: #0ea5e9;
            font-weight: 700;
        }}
        
        .button-group {{
            display: flex;
            gap: 12px;
        }}
        
        button {{
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.95em;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-weight: 600;
            letter-spacing: 0.3px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            position: relative;
            overflow: hidden;
        }}
        
        button::before {{
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.2);
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }}
        
        button:hover::before {{
            width: 300px;
            height: 300px;
        }}
        
        button:active {{
            transform: scale(0.98);
        }}
        
        .btn-select-all {{
            background: linear-gradient(135deg, #0ea5e9 0%, #06b6d4 100%);
            color: #ffffff;
        }}
        
        .btn-select-all:hover {{
            background: linear-gradient(135deg, #06b6d4 0%, #0ea5e9 100%);
            box-shadow: 0 4px 16px rgba(14, 165, 233, 0.4);
            transform: translateY(-2px);
        }}
        
        .btn-deselect-all {{
            background: linear-gradient(135deg, #475569 0%, #334155 100%);
            color: #ffffff;
        }}
        
        .btn-deselect-all:hover {{
            background: linear-gradient(135deg, #334155 0%, #1e293b 100%);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            transform: translateY(-2px);
        }}
        
        .btn-export {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: #ffffff;
        }}
        
        .btn-export:hover {{
            background: linear-gradient(135deg, #059669 0%, #047857 100%);
            box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
            transform: translateY(-2px);
        }}
        
        .btn-clear-history {{
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            color: #ffffff;
        }}
        
        .btn-clear-history:hover {{
            background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
            box-shadow: 0 4px 16px rgba(239, 68, 68, 0.4);
            transform: translateY(-2px);
        }}
        
        .table-wrapper {{
            overflow-x: auto;
            padding: 30px 40px;
            background: #ffffff;
        }}
        
        table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 0.95em;
        }}
        
        thead {{
            background: linear-gradient(to bottom, #1e3a8a, #0ea5e9);
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        
        th {{
            padding: 18px 15px;
            text-align: left;
            font-weight: 700;
            color: #ffffff;
            border-bottom: 3px solid #06b6d4;
            white-space: nowrap;
            font-size: 0.9em;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        
        th:first-child {{
            width: 50px;
            text-align: center;
            border-top-left-radius: 8px;
        }}
        
        th:last-child {{
            border-top-right-radius: 8px;
        }}
        
        th:nth-child(2) {{
            width: 70px;
            text-align: center;
        }}
        
        th:nth-child(9) {{
            width: 150px;
            min-width: 150px;
            max-width: 150px;
            text-align: center;
            white-space: normal;
            word-break: break-word;
            line-height: 1.2;
            padding: 12px 8px;
        }}
        
        td:nth-child(9) {{
            text-align: center;
            padding: 8px;
            width: 150px;
            min-width: 150px;
            max-width: 150px;
            overflow: hidden;
        }}
        
        tbody tr {{
            border-bottom: 1px solid #e8e8e8;
            transition: all 0.2s ease;
            background: #ffffff;
        }}
        
        tbody tr:nth-child(even) {{
            background: #fafafa;
        }}
        
        tbody tr:hover {{
            background: linear-gradient(to right, #f0f9ff, #ffffff) !important;
            box-shadow: 0 2px 8px rgba(14, 165, 233, 0.15);
            transform: scale(1.001);
        }}
        
        tbody tr.checked {{
            background: linear-gradient(to right, #e0f2fe, #f0f9ff) !important;
            border-left: 4px solid #0ea5e9;
        }}
        
        tbody tr.checked:hover {{
            background: linear-gradient(to right, #e0f2fe, #f0f9ff) !important;
        }}
        
        td {{
            padding: 18px 15px;
            vertical-align: top;
        }}
        
        td:first-child,
        td:nth-child(2) {{
            text-align: center;
        }}
        
        input[type="checkbox"] {{
            width: 22px;
            height: 22px;
            cursor: pointer;
            accent-color: #0ea5e9;
            border-radius: 4px;
            border: 2px solid #0ea5e9;
        }}
        
        input[type="checkbox"]:checked {{
            background-color: #0ea5e9;
        }}
        
        .sr-no {{
            font-weight: 700;
            color: #0ea5e9;
            font-size: 1.05em;
            background: linear-gradient(135deg, #e0f2fe, #f0f9ff);
            padding: 4px 10px;
            border-radius: 6px;
            display: inline-block;
        }}
        
        .title {{
            font-weight: 600;
            color: #1a1a1a;
            line-height: 1.5;
            font-size: 1.02em;
        }}
        
        .authors {{
            color: #4a4a4a;
            line-height: 1.6;
            font-size: 0.95em;
        }}
        
        .year {{
            color: #2d2d2d;
            font-weight: 600;
            background: #f5f5f5;
            padding: 4px 10px;
            border-radius: 6px;
            display: inline-block;
        }}
        
        .publication {{
            color: #555555;
            font-style: italic;
            font-size: 0.93em;
        }}
        
        .citations {{
            color: #1e3a8a;
            font-weight: 600;
            background: linear-gradient(135deg, #e0f2fe, #f0f9ff);
            padding: 4px 10px;
            border-radius: 6px;
            display: inline-block;
            font-size: 0.95em;
        }}
        
        .doi {{
            color: #1a1a1a;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            word-break: break-all;
            background: #f5f5f5;
            padding: 4px 8px;
            border-radius: 4px;
            border: 1px solid #e8e8e8;
        }}
        
        .download-link {{
            color: #10b981;
            text-decoration: none;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 6px;
            background: linear-gradient(135deg, #ecfdf5, #d1fae5);
            border: 1px solid #10b981;
            display: inline-block;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}
        
        .download-link:hover {{
            background: linear-gradient(135deg, #d1fae5, #a7f3d0);
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.2);
        }}
        
        .download-link.downloaded {{
            color: #2563eb;
            background: linear-gradient(135deg, #dbeafe, #bfdbfe);
            border: 1px solid #3b82f6;
            white-space: nowrap;
        }}
        
        .download-link.downloaded:hover {{
            background: linear-gradient(135deg, #bfdbfe, #93c5fd);
            box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
        }}
        
        .no-link {{
            color: #999999;
            font-style: italic;
            font-size: 0.9em;
        }}
        
        
        .footer {{
            padding: 25px 40px;
            text-align: center;
            color: #666666;
            font-size: 0.9em;
            background: linear-gradient(to bottom, #f8f8f8, #f0f0f0);
            border-top: 2px solid #e8e8e8;
        }}
        
        .footer::before {{
            content: '';
            display: block;
            width: 60px;
            height: 2px;
            background: linear-gradient(90deg, transparent, #06b6d4, transparent);
            margin: 0 auto 15px;
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 15px 10px;
            }}
            
            .container {{
                border-radius: 12px;
            }}
            
            .header {{
                padding: 35px 25px;
            }}
            
            .header h1 {{
                font-size: 1.8em;
            }}
            
            .controls {{
                flex-direction: column;
                align-items: stretch;
                padding: 20px 25px;
            }}
            
            .stats {{
                text-align: center;
                margin-bottom: 5px;
            }}
            
            .button-group {{
                width: 100%;
                flex-direction: column;
            }}
            
            button {{
                width: 100%;
            }}
            
            .table-wrapper {{
                padding: 15px 10px;
            }}
            
            table {{
                font-size: 0.85em;
            }}
            
            th {{
                padding: 12px 8px;
                font-size: 0.8em;
            }}
            
            td {{
                padding: 12px 8px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 Research Papers Checklist</h1>
            <p>Semantic Scholar Profile: {author_id}</p>
        </div>
        
        <div class="controls">
            <div class="stats">
                <strong>Total Papers:</strong> {len(papers)} | 
                <strong>Checked:</strong> <span id="checked-count">0</span>
            </div>
            <div class="button-group">
                <button class="btn-select-all" onclick="selectAll()">✓ Select All</button>
                <button class="btn-deselect-all" onclick="deselectAll()">✗ Deselect All</button>
                <button class="btn-export" onclick="exportChecked()">📥 Export Checked</button>
                <button class="btn-clear-history" onclick="clearDownloadHistory()">🗑️ Clear Download History</button>
            </div>
        </div>
        
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>✓</th>
                        <th>Sr. No</th>
                        <th>Title</th>
                        <th>Authors</th>
                        <th>Year</th>
                        <th>Publication</th>
                        <th>Citations</th>
                        <th>DOI</th>
                        <th>Download Link</th>
                    </tr>
                </thead>
                <tbody>
{HTMLGenerator._generate_table_rows(papers)}
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            Generated by Semantic Scholar Scraper | {HTMLGenerator._get_current_date()}
        </div>
    </div>
    
    <script>
        // Update checked count
        function updateCheckedCount() {{
            const checkboxes = document.querySelectorAll('tbody input[type="checkbox"]');
            const checked = Array.from(checkboxes).filter(cb => cb.checked).length;
            document.getElementById('checked-count').textContent = checked;
            
            // Add/remove checked class from rows
            checkboxes.forEach(checkbox => {{
                const row = checkbox.closest('tr');
                if (checkbox.checked) {{
                    row.classList.add('checked');
                }} else {{
                    row.classList.remove('checked');
                }}
            }});
        }}
        
        // Select all checkboxes
        function selectAll() {{
            const checkboxes = document.querySelectorAll('tbody input[type="checkbox"]');
            checkboxes.forEach(cb => cb.checked = true);
            updateCheckedCount();
        }}
        
        // Deselect all checkboxes
        function deselectAll() {{
            const checkboxes = document.querySelectorAll('tbody input[type="checkbox"]');
            checkboxes.forEach(cb => cb.checked = false);
            updateCheckedCount();
        }}
        
        // Export checked papers to CSV
        function exportChecked() {{
            const checkboxes = document.querySelectorAll('tbody input[type="checkbox"]');
            const checkedPapers = [];
            
            checkboxes.forEach((checkbox, index) => {{
                if (checkbox.checked) {{
                    const row = checkbox.closest('tr');
                    const cells = row.querySelectorAll('td');
                    
                    checkedPapers.push({{
                        srNo: cells[1].textContent.trim(),
                        title: cells[2].textContent.trim(),
                        authors: cells[3].textContent.trim(),
                        year: cells[4].textContent.trim(),
                        publication: cells[5].textContent.trim(),
                        citations: cells[6].textContent.trim(),
                        doi: cells[7].textContent.trim(),
                        downloadLink: cells[8].querySelector('a') ? cells[8].querySelector('a').href : ''
                    }});
                }}
            }});
            
            if (checkedPapers.length === 0) {{
                alert('No papers selected. Please select at least one paper.');
                return;
            }}
            
            // Convert to CSV
            const headers = ['Sr. No', 'Title', 'Authors', 'Year', 'Publication', 'Citations', 'DOI', 'Download Link'];
            const csvRows = [
                headers.join(','),
                ...checkedPapers.map(p => [
                    `"${{p.srNo}}"`,
                    `"${{p.title.replace(/"/g, '""')}}"`,
                    `"${{p.authors.replace(/"/g, '""')}}"`,
                    `"${{p.year}}"`,
                    `"${{p.publication.replace(/"/g, '""')}}"`,
                    `"${{p.citations}}"`,
                    `"${{p.doi}}"`,
                    `"${{p.downloadLink}}"`
                ].join(','))
            ];
            
            const csvContent = csvRows.join('\\n');
            const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', 'checked_papers.csv');
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }}
        
        // Add event listeners to all checkboxes and restore download state
        document.addEventListener('DOMContentLoaded', function() {{
            const checkboxes = document.querySelectorAll('tbody input[type="checkbox"]');
            checkboxes.forEach(checkbox => {{
                checkbox.addEventListener('change', updateCheckedCount);
            }});
            updateCheckedCount();
            restoreDownloadedState();
        }});
        
        // Download Tracking Functions
        function getStorageKey() {{
            // Extract author_id from the page
            const profileText = document.querySelector('.header p');
            if (profileText) {{
                const match = profileText.textContent.match(/Semantic Scholar Profile: (.+)/);
                if (match && match[1]) {{
                    return 'downloaded_papers_' + match[1].trim();
                }}
            }}
            // Fallback to a default key if author_id not found
            return 'downloaded_papers_default';
        }}
        
        function markAsDownloaded(paperId) {{
            try {{
                const storageKey = getStorageKey();
                let downloadedPapers = {{}};
                
                // Get existing downloaded papers from localStorage
                const stored = localStorage.getItem(storageKey);
                if (stored) {{
                    try {{
                        downloadedPapers = JSON.parse(stored);
                    }} catch(e) {{
                        console.error('Error parsing stored download data:', e);
                    }}
                }}
                
                // Mark this paper as downloaded
                downloadedPapers[paperId] = true;
                
                // Save back to localStorage
                localStorage.setItem(storageKey, JSON.stringify(downloadedPapers));
                
                // Update the link appearance
                const link = document.querySelector('.download-link[data-paper-id="' + paperId + '"]');
                if (link) {{
                    link.classList.add('downloaded');
                    link.textContent = 'Downloaded ✓';
                }}
            }} catch(e) {{
                console.error('Error marking paper as downloaded:', e);
                // Handle localStorage quota exceeded or other errors gracefully
            }}
        }}
        
        function restoreDownloadedState() {{
            try {{
                const storageKey = getStorageKey();
                const stored = localStorage.getItem(storageKey);
                
                if (!stored) {{
                    return;
                }}
                
                const downloadedPapers = JSON.parse(stored);
                
                // Restore state for each downloaded paper
                for (const paperId in downloadedPapers) {{
                    if (downloadedPapers[paperId]) {{
                        const link = document.querySelector('.download-link[data-paper-id="' + paperId + '"]');
                        if (link) {{
                            link.classList.add('downloaded');
                            link.textContent = 'Downloaded ✓';
                        }}
                    }}
                }}
            }} catch(e) {{
                console.error('Error restoring downloaded state:', e);
            }}
        }}
        
        function clearDownloadHistory() {{
            if (!confirm('Are you sure you want to clear all download history? This action cannot be undone.')) {{
                return;
            }}
            
            try {{
                const storageKey = getStorageKey();
                localStorage.removeItem(storageKey);
                
                // Remove downloaded class and reset text for all download links
                const downloadedLinks = document.querySelectorAll('.download-link.downloaded');
                downloadedLinks.forEach(link => {{
                    link.classList.remove('downloaded');
                    link.textContent = 'Download PDF';
                }});
                
                // Show feedback
                alert('Download history cleared successfully!');
            }} catch(e) {{
                console.error('Error clearing download history:', e);
                alert('Error clearing download history. Please try again.');
            }}
        }}
        
        // Add event listener for download link clicks
        document.addEventListener('click', function(event) {{
            const downloadLink = event.target.closest('.download-link');
            if (downloadLink && downloadLink.hasAttribute('data-paper-id')) {{
                const paperId = downloadLink.getAttribute('data-paper-id');
                markAsDownloaded(paperId);
            }}
        }});
    </script>
</body>
</html>"""
        return html_content
    
    @staticmethod
    def _format_citations(citations: str) -> str:
        """Format citation count with commas or return as-is if it's 'Missing citations'"""
        if citations == "Missing citations" or not citations:
            return "Missing citations"
        try:
            # Remove any existing commas and convert to int, then format with commas
            num = int(citations.replace(',', ''))
            return f"{num:,}"
        except (ValueError, AttributeError):
            return citations
    
    @staticmethod
    def _generate_table_rows(papers: List[Dict]) -> str:
        """Generate HTML table rows for papers"""
        rows = []
        
        for idx, paper in enumerate(papers, 1):
            title = HTMLGenerator._escape_html(paper.get('title', ''))
            authors = HTMLGenerator._escape_html(paper.get('authors', ''))
            year = HTMLGenerator._escape_html(paper.get('year', ''))
            publication = HTMLGenerator._escape_html(paper.get('publication', ''))
            citations = paper.get('citations', 'Missing citations')
            citations_formatted = HTMLGenerator._format_citations(citations)
            doi = HTMLGenerator._escape_html(paper.get('doi', ''))
            download_link = paper.get('download_link', '')
            
            # Format download link
            # Note: URLs in href attributes should NOT be HTML-escaped
            # HTML escaping is for text content, not URLs
            if download_link:
                # Only escape quotes in the URL to prevent breaking the HTML attribute
                safe_url = download_link.replace('"', '&quot;').replace("'", '&#39;')
                download_html = f'<a href="{safe_url}" target="_blank" class="download-link" data-paper-id="{idx}">Download PDF</a>'
            else:
                download_html = '<span class="no-link">Not found</span>'
            
            # Format DOI
            if doi:
                doi_html = f'<span class="doi">{doi}</span>'
            else:
                doi_html = '<span class="no-link">-</span>'
            
            # Format citations
            if citations_formatted == "Missing citations":
                citations_html = '<span class="no-link">Missing citations</span>'
            else:
                citations_html = f'<span class="citations">{HTMLGenerator._escape_html(citations_formatted)}</span>'
            
            row = f"""                    <tr>
                        <td><input type="checkbox" id="paper-{idx}"></td>
                        <td><span class="sr-no">{idx}</span></td>
                        <td><span class="title">{title}</span></td>
                        <td><span class="authors">{authors}</span></td>
                        <td><span class="year">{year}</span></td>
                        <td><span class="publication">{publication}</span></td>
                        <td>{citations_html}</td>
                        <td>{doi_html}</td>
                        <td>{download_html}</td>
                    </tr>"""
            rows.append(row)
        
        return '\n'.join(rows)
    
    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters"""
        if not text:
            return ""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
    
    @staticmethod
    def _get_current_date() -> str:
        """Get current date string"""
        from datetime import datetime
        return datetime.now().strftime("%B %d, %Y")

