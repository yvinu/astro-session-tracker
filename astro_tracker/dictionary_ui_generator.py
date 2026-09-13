"""FITS Dictionary Interactive Web UI Generator.

Generates a standalone, searchable JavaScript-powered web application
(fits_dictionary_explorer.html) with instant indexing, publisher filtering,
card synonym maps, and responsive dark-mode styling.
"""

import os
import json


def generate_dictionary_ui_html(output_file="fits_dictionary_explorer.html"):
    """Generate an interactive HTML/JS web dictionary explorer."""
    dict_path = os.path.join(os.path.dirname(__file__), "fits_dictionary.json")
    with open(dict_path, 'r', encoding='utf-8') as f:
        dict_data = json.load(f)

    # Invert mapping by publisher
    publisher_index = {}
    for concept, info in dict_data.items():
        for syn in info.get("synonyms", []):
            card = syn.get("card", "")
            for pub in syn.get("publishers", []):
                pub_clean = pub.strip()
                if pub_clean not in publisher_index:
                    publisher_index[pub_clean] = []
                publisher_index[pub_clean].append({
                    "card": card,
                    "concept": concept,
                    "display_name": info.get("display_name", concept),
                    "notes": syn.get("notes", "")
                })

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FITS Header Metadata Dictionary</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 27, 38, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent-primary: #7c3aed;
            --accent-secondary: #06b6d4;
            --accent-green: #10b981;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}

        header {{
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--card-border);
            padding: 20px 40px;
            position: sticky;
            top: 0;
            z-index: 50;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .logo-area {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .logo-badge {{
            background: linear-gradient(135deg, #7c3aed, #06b6d4);
            color: white;
            font-weight: 700;
            font-size: 14px;
            padding: 6px 12px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(124, 58, 237, 0.3);
        }}

        h1 {{
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.02em;
        }}

        .search-bar {{
            position: relative;
            width: 380px;
        }}

        .search-bar input {{
            width: 100%;
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 10px 16px 10px 40px;
            border-radius: 10px;
            color: white;
            font-size: 14px;
            outline: none;
            transition: all 0.2s ease;
        }}

        .search-bar input:focus {{
            border-color: var(--accent-secondary);
            box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.2);
        }}

        .search-icon {{
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 14px;
        }}

        .container {{
            max-width: 1400px;
            margin: 30px auto;
            padding: 0 40px;
            width: 100%;
            display: grid;
            grid-template-columns: 280px 1fr;
            gap: 30px;
            flex: 1;
        }}

        .sidebar {{
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 20px;
            height: fit-content;
        }}

        .sidebar h3 {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
            margin-bottom: 12px;
        }}

        .nav-tabs {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin-bottom: 24px;
        }}

        .nav-item {{
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            color: var(--text-muted);
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .nav-item:hover {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
        }}

        .nav-item.active {{
            background: rgba(124, 58, 237, 0.15);
            color: #a78bfa;
            border: 1px solid rgba(124, 58, 237, 0.3);
        }}

        .publisher-list {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            max-height: 400px;
            overflow-y: auto;
        }}

        .pub-badge {{
            font-size: 13px;
            padding: 6px 10px;
            border-radius: 6px;
            cursor: pointer;
            color: var(--text-muted);
            transition: all 0.2s;
        }}

        .pub-badge:hover, .pub-badge.active {{
            background: rgba(6, 182, 212, 0.15);
            color: var(--accent-secondary);
        }}

        .main-content {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}

        .stats-bar {{
            display: flex;
            gap: 16px;
            margin-bottom: 10px;
        }}

        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            padding: 14px 20px;
            border-radius: 12px;
            flex: 1;
        }}

        .stat-card .val {{
            font-size: 22px;
            font-weight: 700;
            color: var(--text-main);
        }}

        .stat-card .lbl {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 2px;
        }}

        .concept-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            transition: transform 0.2s, border-color 0.2s;
        }}

        .concept-card:hover {{
            border-color: rgba(255, 255, 255, 0.18);
        }}

        .concept-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}

        .concept-title {{
            font-size: 18px;
            font-weight: 700;
            color: #f3f4f6;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .concept-key {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            background: rgba(124, 58, 237, 0.2);
            color: #c4b5fd;
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid rgba(124, 58, 237, 0.3);
        }}

        .type-tag {{
            font-size: 12px;
            color: var(--text-muted);
            background: rgba(255, 255, 255, 0.05);
            padding: 4px 8px;
            border-radius: 6px;
        }}

        .synonyms-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 14px;
        }}

        .synonym-item {{
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 14px;
        }}

        .synonym-card-name {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 15px;
            font-weight: 600;
            color: var(--accent-secondary);
            margin-bottom: 6px;
        }}

        .synonym-notes {{
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 10px;
        }}

        .publishers-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}

        .publisher-chip {{
            font-size: 11px;
            font-weight: 500;
            background: rgba(16, 185, 129, 0.15);
            color: #6ee7b7;
            border: 1px solid rgba(16, 185, 129, 0.3);
            padding: 3px 8px;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <header>
        <div class="logo-area">
            <span class="logo-badge">FITS DICTIONARY</span>
            <h1>Header Metadata & Publisher Index</h1>
        </div>
        <div class="search-bar">
            <span class="search-icon">🔍</span>
            <input type="text" id="searchInput" placeholder="Search card (DET-TEMP), concept, software..." oninput="filterData()">
        </div>
    </header>

    <div class="container">
        <div class="sidebar">
            <h3>View Mode</h3>
            <div class="nav-tabs">
                <div class="nav-item active" id="tabConcepts" onclick="switchTab('concepts')">
                    Canonical Concepts
                    <span>{len(dict_data)}</span>
                </div>
                <div class="nav-item" id="tabPublishers" onclick="switchTab('publishers')">
                    Publishers / Software
                    <span>{len(publisher_index)}</span>
                </div>
            </div>

            <h3>Filter Publisher</h3>
            <div class="publisher-list" id="publisherList">
                <div class="pub-badge active" onclick="filterByPublisher('ALL')">All Publishers</div>
                {"".join([f'<div class="pub-badge" onclick="filterByPublisher(\'{pub}\')">{pub}</div>' for pub in sorted(publisher_index.keys())])}
            </div>
        </div>

        <div class="main-content">
            <div class="stats-bar">
                <div class="stat-card">
                    <div class="val">{len(dict_data)}</div>
                    <div class="lbl">Canonical Concepts</div>
                </div>
                <div class="stat-card">
                    <div class="val">{sum(len(info.get('synonyms', [])) for info in dict_data.values())}</div>
                    <div class="lbl">FITS Card Variations</div>
                </div>
                <div class="stat-card">
                    <div class="val">{len(publisher_index)}</div>
                    <div class="lbl">Associated Publishers</div>
                </div>
            </div>

            <div id="resultsContainer"></div>
        </div>
    </div>

    <script>
        const dictionaryData = {json.dumps(dict_data)};
        const publisherData = {json.dumps(publisher_index)};

        let currentTab = 'concepts';
        let currentPublisherFilter = 'ALL';

        function renderConcepts(filterText = '') {{
            const container = document.getElementById('resultsContainer');
            container.innerHTML = '';

            let count = 0;
            for (const [key, info] of Object.entries(dictionaryData)) {{
                const dispName = info.display_name || key;
                const synonyms = info.synonyms || [];

                // Publisher filter
                if (currentPublisherFilter !== 'ALL') {{
                    const hasPub = synonyms.some(s => (s.publishers || []).includes(currentPublisherFilter));
                    if (!hasPub) continue;
                }}

                // Text filter
                if (filterText) {{
                    const matchesKey = key.toLowerCase().includes(filterText);
                    const matchesDisp = dispName.toLowerCase().includes(filterText);
                    const matchesCard = synonyms.some(s => s.card.toLowerCase().includes(filterText));
                    const matchesNotes = synonyms.some(s => (s.notes || '').toLowerCase().includes(filterText));
                    if (!matchesKey && !matchesDisp && !matchesCard && !matchesNotes) continue;
                }}

                count++;
                const cardEl = document.createElement('div');
                cardEl.className = 'concept-card';

                let synHtml = '';
                synonyms.forEach(syn => {{
                    const pubsHtml = (syn.publishers || []).map(p => `<span class="publisher-chip">${{p}}</span>`).join('');
                    synHtml += `
                        <div class="synonym-item">
                            <div class="synonym-card-name">${{syn.card}}</div>
                            <div class="synonym-notes">${{syn.notes || 'Standard header card'}}</div>
                            <div class="publishers-tags">${{pubsHtml}}</div>
                        </div>
                    `;
                }});

                cardEl.innerHTML = `
                    <div class="concept-header">
                        <div class="concept-title">
                            ${{dispName}}
                            <span class="concept-key">${{key}}</span>
                        </div>
                        <span class="type-tag">Type: ${{info.data_type || 'str'}} | Default: ${{info.default || 'N/A'}}</span>
                    </div>
                    <div class="synonyms-grid">${{synHtml}}</div>
                `;
                container.appendChild(cardEl);
            }}

            if (count === 0) {{
                container.innerHTML = '<div style="text-align:center; padding: 40px; color: var(--text-muted);">No matching concepts or header cards found.</div>';
            }}
        }}

        function renderPublishers(filterText = '') {{
            const container = document.getElementById('resultsContainer');
            container.innerHTML = '';

            let count = 0;
            for (const [pubName, cards] of Object.entries(publisherData)) {{
                if (currentPublisherFilter !== 'ALL' && pubName !== currentPublisherFilter) continue;

                if (filterText) {{
                    const matchesPub = pubName.toLowerCase().includes(filterText);
                    const matchesCard = cards.some(c => c.card.toLowerCase().includes(filterText) || c.display_name.toLowerCase().includes(filterText));
                    if (!matchesPub && !matchesCard) continue;
                }}

                count++;
                const cardEl = document.createElement('div');
                cardEl.className = 'concept-card';

                let cardsHtml = '';
                cards.forEach(c => {{
                    cardsHtml += `
                        <div class="synonym-item">
                            <div class="synonym-card-name">${{c.card}}</div>
                            <div style="font-size: 13px; color: #f3f4f6; margin-bottom: 4px;">${{c.display_name}} (<code>${{c.concept}}</code>)</div>
                            <div class="synonym-notes">${{c.notes || ''}}</div>
                        </div>
                    `;
                }});

                cardEl.innerHTML = `
                    <div class="concept-header">
                        <div class="concept-title">
                            🏢 ${{pubName}}
                        </div>
                        <span class="type-tag">${{cards.length}} Header Cards</span>
                    </div>
                    <div class="synonyms-grid">${{cardsHtml}}</div>
                `;
                container.appendChild(cardEl);
            }}

            if (count === 0) {{
                container.innerHTML = '<div style="text-align:center; padding: 40px; color: var(--text-muted);">No matching software publishers found.</div>';
            }}
        }}

        function switchTab(tab) {{
            currentTab = tab;
            document.getElementById('tabConcepts').classList.toggle('active', tab === 'concepts');
            document.getElementById('tabPublishers').classList.toggle('active', tab === 'publishers');
            filterData();
        }}

        function filterByPublisher(pub) {{
            currentPublisherFilter = pub;
            document.querySelectorAll('.pub-badge').forEach(el => {{
                el.classList.toggle('active', el.innerText.trim() === pub || (pub === 'ALL' && el.innerText.includes('All')));
            }});
            filterData();
        }}

        function filterData() {{
            const query = document.getElementById('searchInput').value.toLowerCase().trim();
            if (currentTab === 'concepts') {{
                renderConcepts(query);
            }} else {{
                renderPublishers(query);
            }}
        }}

        // Initial render
        renderConcepts();
    </script>
</body>
</html>
"""

    abs_output = os.path.abspath(output_file)
    with open(abs_output, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return abs_output
