"""FITS Metadata Graph Visualizer Generator.

Generates a standalone, interactive HTML visualization file (graph_explorer.html)
using vis-network.js to allow users to visually explore nodes (Concepts, Cards,
Publishers), edges, and relationships in any web browser.
"""

import os
import json
from astro_tracker.fits_graph_db import FITSGraphDB


def generate_graph_html(output_file="graph_explorer.html"):
    """Export property graph data to an interactive vis-network HTML visualizer."""
    db = FITSGraphDB()

    # Retrieve all canonical concepts, cards, and publishers
    nodes = []
    edges = []
    node_ids = set()

    with open(os.path.join(os.path.dirname(__file__), "fits_dictionary.json"), 'r', encoding='utf-8') as f:
        dict_data = json.load(f)

    # 1. Concept Nodes
    for concept, info in dict_data.items():
        c_id = f"concept:{concept}"
        if c_id not in node_ids:
            nodes.append({
                "id": c_id,
                "label": f"{concept}\n({info.get('display_name', concept)})",
                "group": "Concept",
                "color": {"background": "#9d4edd", "border": "#c77dff", "highlight": {"background": "#e0aaff", "border": "#ffffff"}},
                "shape": "ellipse",
                "font": {"color": "#ffffff", "face": "Inter, sans-serif", "size": 14}
            })
            node_ids.add(c_id)

        # 2. Card and Publisher Nodes & Edges
        for syn in info.get("synonyms", []):
            card_name = syn.get("card", "").upper().strip()
            if not card_name:
                continue

            card_id = f"card:{card_name}"
            if card_id not in node_ids:
                nodes.append({
                    "id": card_id,
                    "label": card_name,
                    "group": "HeaderCard",
                    "color": {"background": "#00b4d8", "border": "#90e0ef", "highlight": {"background": "#caf0f8", "border": "#ffffff"}},
                    "shape": "box",
                    "font": {"color": "#03045e", "face": "Inter, sans-serif", "size": 13, "bold": True}
                })
                node_ids.add(card_id)

            # Edge: Card -> Concept
            edges.append({
                "from": card_id,
                "to": c_id,
                "label": "MAPS_TO",
                "arrows": "to",
                "color": {"color": "rgba(144, 224, 239, 0.6)", "highlight": "#caf0f8"},
                "font": {"color": "#90e0ef", "size": 10, "align": "middle"}
            })

            # Publisher Nodes & Edges
            for pub in syn.get("publishers", []):
                pub_clean = pub.strip()
                if not pub_clean:
                    continue

                pub_id = f"pub:{pub_clean}"
                if pub_id not in node_ids:
                    nodes.append({
                        "id": pub_id,
                        "label": pub_clean,
                        "group": "Publisher",
                        "color": {"background": "#38b000", "border": "#70e000", "highlight": {"background": "#9ef01a", "border": "#ffffff"}},
                        "shape": "diamond",
                        "font": {"color": "#ffffff", "face": "Inter, sans-serif", "size": 13}
                    })
                    node_ids.add(pub_id)

                # Edge: Card -> Publisher
                edges.append({
                    "from": card_id,
                    "to": pub_id,
                    "label": "WRITTEN_BY",
                    "arrows": "to",
                    "color": {"color": "rgba(112, 224, 0, 0.5)", "highlight": "#9ef01a"},
                    "font": {"color": "#70e000", "size": 10, "align": "middle"}
                })

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FITS Metadata Graph Explorer</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: 'Inter', sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            overflow: hidden;
            height: 100vh;
            width: 100vw;
        }}
        #header {{
            position: absolute;
            top: 15px;
            left: 20px;
            z-index: 10;
            background: rgba(22, 27, 34, 0.85);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 14px 20px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            max-width: 420px;
        }}
        h1 {{
            font-size: 18px;
            font-weight: 700;
            color: #f0f6fc;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        p.subtitle {{
            font-size: 12px;
            color: #8b949e;
            margin-bottom: 12px;
        }}
        .legend {{
            display: flex;
            gap: 12px;
            font-size: 12px;
            margin-top: 8px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }}
        .dot-concept {{ background: #9d4edd; }}
        .dot-card {{ background: #00b4d8; border-radius: 2px; }}
        .dot-pub {{ background: #38b000; transform: rotate(45deg); width: 8px; height: 8px; }}

        #controls {{
            position: absolute;
            top: 15px;
            right: 20px;
            z-index: 10;
            background: rgba(22, 27, 34, 0.85);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 12px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            display: flex;
            gap: 8px;
        }}
        input[type="text"] {{
            background: #161b22;
            border: 1px solid #30363d;
            color: #f0f6fc;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 13px;
            outline: none;
            width: 220px;
        }}
        input[type="text"]:focus {{
            border-color: #58a6ff;
        }}
        button {{
            background: #238636;
            color: #ffffff;
            border: none;
            padding: 8px 14px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        button:hover {{
            background: #2ea043;
        }}

        #inspector {{
            position: absolute;
            bottom: 20px;
            right: 20px;
            z-index: 10;
            background: rgba(22, 27, 34, 0.9);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 16px;
            border-radius: 12px;
            width: 320px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
            display: none;
        }}
        #inspector h3 {{
            font-size: 15px;
            color: #58a6ff;
            margin-bottom: 8px;
        }}
        #inspector p {{
            font-size: 13px;
            color: #c9d1d9;
            margin-bottom: 6px;
            line-height: 1.4;
        }}

        #mynetwork {{
            width: 100vw;
            height: 100vh;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>🌌 FITS Metadata Graph Explorer</h1>
        <p class="subtitle">Interactive topology of Canonical Concepts, FITS Header Cards, & Software Publishers</p>
        <div class="legend">
            <div class="legend-item"><div class="dot dot-concept"></div> Concept ({len(dict_data)})</div>
            <div class="legend-item"><div class="dot dot-card"></div> Card ({len([n for n in nodes if n['group']=='HeaderCard'])})</div>
            <div class="legend-item"><div class="dot dot-pub"></div> Publisher ({len([n for n in nodes if n['group']=='Publisher'])})</div>
        </div>
    </div>

    <div id="controls">
        <input type="text" id="searchInput" placeholder="Search concept, card, publisher..." onkeyup="handleSearch(event)">
        <button onclick="resetView()">Reset Zoom</button>
    </div>

    <div id="inspector">
        <h3 id="inspTitle">Node Inspection</h3>
        <p id="inspType"></p>
        <p id="inspDetail"></p>
        <p id="inspConnections"></p>
    </div>

    <div id="mynetwork"></div>

    <script type="text/javascript">
        const rawNodes = {json.dumps(nodes)};
        const rawEdges = {json.dumps(edges)};

        const nodes = new vis.DataSet(rawNodes);
        const edges = new vis.DataSet(rawEdges);

        const container = document.getElementById('mynetwork');
        const data = {{ nodes: nodes, edges: edges }};

        const options = {{
            nodes: {{
                borderWidth: 2,
                shadow: true,
            }},
            edges: {{
                width: 1.5,
                smooth: {{
                    type: 'continuous',
                    roundness: 0.2
                }},
                shadow: true
            }},
            physics: {{
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {{
                    gravitationalConstant: -35,
                    centralGravity: 0.005,
                    springLength: 120,
                    springConstant: 0.08
                }},
                maxVelocity: 50,
                minVelocity: 0.1,
                stabilization: {{ iterations: 150 }}
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100,
                zoomView: true
            }}
        }};

        const network = new vis.Network(container, data, options);

        network.on("click", function (params) {{
            const inspector = document.getElementById("inspector");
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                const clickedNode = nodes.get(nodeId);
                const connectedNodeIds = network.getConnectedNodes(nodeId);
                const connectedLabels = connectedNodeIds.map(id => nodes.get(id).label.replace('\\n', ' '));

                document.getElementById("inspTitle").innerText = clickedNode.label.replace('\\n', ' - ');
                document.getElementById("inspType").innerHTML = `<strong>Group:</strong> ${"{clickedNode.group}"}`;
                document.getElementById("inspDetail").innerHTML = `<strong>Node ID:</strong> <code>${"{clickedNode.id}"}</code>`;
                document.getElementById("inspConnections").innerHTML = `<strong>Connected (${"{connectedLabels.length}"}):</strong><br>${"{connectedLabels.slice(0, 8).join(', ')}"}${"{connectedLabels.length > 8 ? '...' : ''}"}`;

                inspector.style.display = "block";
            }} else {{
                inspector.style.display = "none";
            }}
        }});

        function resetView() {{
            network.fit({{ animation: true }});
            document.getElementById("inspector").style.display = "none";
        }}

        function handleSearch(e) {{
            const query = document.getElementById("searchInput").value.toLowerCase().trim();
            if (!query) return;

            const matchingNode = rawNodes.find(n => n.label.toLowerCase().includes(query));
            if (matchingNode) {{
                network.selectNodes([matchingNode.id]);
                network.focus(matchingNode.id, {{ scale: 1.2, animation: true }});
            }}
        }}
    </script>
</body>
</html>
"""

    abs_output = os.path.abspath(output_file)
    with open(abs_output, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return abs_output
