#!/usr/bin/env python3
"""FITS Dictionary & Graph Database CLI.

Provides lookup, publisher querying, and header interpretation tools
backed by the KùzuDB Graph Engine and fits_dictionary mapping definitions.
"""

import os
import sys
import json
import argparse
from astro_tracker.fits_graph_db import FITSGraphDB
from fits_header_analyzer import extract_header


def main():
    parser = argparse.ArgumentParser(
        description="FITS Dictionary & Graph Database Query Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--lookup', help="Look up a FITS header card (e.g., --lookup DET-TEMP)")
    parser.add_argument('--publisher', help="List all FITS header cards associated with a publisher (e.g., --publisher DWARFLAB)")
    parser.add_argument('--test', help="Test header translation on a specific FITS/XISF file")
    parser.add_argument('--graph-stats', action='store_true', help="Display property graph node & edge counts")
    parser.add_argument('--show-concepts', action='store_true', help="List all canonical concepts and their synonyms")
    parser.add_argument('--visualize', action='store_true', help="Generate and open interactive HTML graph visualization (graph_explorer.html)")
    parser.add_argument('-u', '--dictionary-ui', action='store_true', help="Generate and open interactive web dictionary explorer (fits_dictionary_explorer.html)")
    parser.add_argument('-s', '--studio', action='store_true', help="Open unified 3-tab Web Application Suite (fits_studio.html)")
    parser.add_argument('--reset-corpus', action='store_true', help="Reset the cumulative graph DB and dictionary to fresh seed state.")

    args = parser.parse_args()

    graph_db = FITSGraphDB()

    if args.reset_corpus:
        graph_db.reset_database()
        sys.exit(0)

    if args.studio:
        import webbrowser
        studio_path = os.path.abspath("fits_studio.html")
        print("=" * 70)
        print(" 🌌 FITS STUDIO UNIFIED WEB SUITE LAUNCHED")
        print("=" * 70)
        print(f" Opening: file://{studio_path}")
        print("=" * 70)
        webbrowser.open(f"file://{studio_path}")
        sys.exit(0)

    if args.dictionary_ui:
        from astro_tracker.dictionary_ui_generator import generate_dictionary_ui_html
        import webbrowser

        html_path = generate_dictionary_ui_html()
        print("=" * 70)
        print(" 📖 INTERACTIVE FITS DICTIONARY WEB UI GENERATED")
        print("=" * 70)
        print(f" Saved interactive dictionary UI to: file://{html_path}")
        print(" Opening in your default web browser...")
        print("=" * 70)
        webbrowser.open(f"file://{html_path}")
        sys.exit(0)

    if args.visualize:
        from astro_tracker.graph_visualizer import generate_graph_html
        import webbrowser

        html_path = generate_graph_html()
        print("=" * 70)
        print(" 🌌 FITS METADATA GRAPH VISUALIZER GENERATED")
        print("=" * 70)
        print(f" Saved interactive HTML visualization to: file://{html_path}")
        print(" Opening in your default web browser...")
        print("=" * 70)
        webbrowser.open(f"file://{html_path}")
        sys.exit(0)

    if args.lookup:
        res = graph_db.lookup_card(args.lookup)
        if res:
            print("=" * 60)
            print(f" 🔍 CARD LOOKUP RESULTS: '{res['card']}'")
            print("=" * 60)
            print(f"  Canonical Concept : {res['concept']}")
            print(f"  Display Name      : {res['display_name']}")
            print(f"  Publishers        : {', '.join(res['publishers']) if res['publishers'] else 'None'}")
            print("=" * 60)
        else:
            print(f"❌ Card '{args.lookup}' is not found in the FITS mapping dictionary.")

    elif args.publisher:
        results = graph_db.query_publisher(args.publisher)
        print("=" * 70)
        print(f" 🏢 PUBLISHER CARD ASSOCIATIONS: '{args.publisher}'")
        print("=" * 70)
        if results:
            print(f"{'Header Card':<15} | {'Canonical Concept':<20} | {'Display Name':<30}")
            print("-" * 70)
            for r in results:
                print(f"{r['card']:<15} | {r['concept']:<20} | {r['display_name']:<30}")
            print(f"\nTotal Cards Associated: {len(results)}")
        else:
            print(f"No cards found matching publisher '{args.publisher}'.")
        print("=" * 70)

    elif args.graph_stats:
        stats = graph_db.get_graph_stats()
        print("=" * 60)
        print(" 📊 FITS METADATA PROPERTY GRAPH STATISTICS")
        print("=" * 60)
        for k, v in stats.items():
            print(f"  {k:<22} : {v}")
        print("=" * 60)

    elif args.test:
        test_path = os.path.expanduser(args.test)
        if not os.path.exists(test_path):
            print(f"❌ Error: File '{test_path}' does not exist.")
            sys.exit(1)

        raw_header = extract_header(test_path)
        if not raw_header:
            print(f"❌ Failed to extract header from '{test_path}'.")
            sys.exit(1)

        interpreted = graph_db.interpret_header(raw_header)
        print("=" * 70)
        print(f" 🧪 FITS HEADER INTERPRETATION TEST: {os.path.basename(test_path)}")
        print("=" * 70)
        print(" Detected Publishers:", ", ".join(interpreted.get("detected_publishers", [])))
        print("-" * 70)
        print(f"{'Canonical Concept':<22} | {'Value':<25} | {'Source Card':<15}")
        print("-" * 70)
        for k, v in interpreted.items():
            if not k.endswith("_source_card") and k != "detected_publishers":
                src = interpreted.get(f"{k}_source_card", "(default)")
                print(f"{k:<22} | {str(v):<25} | {src:<15}")
        print("=" * 70)

    elif args.show_concepts:
        with open(os.path.join(os.path.dirname(__file__), "astro_tracker", "fits_dictionary.json"), 'r') as f:
            data = json.load(f)
        print("=" * 70)
        print(" 📖 CANONICAL CONCEPTS & SYNONYMS")
        print("=" * 70)
        for concept, info in data.items():
            print(f"\n🔹 Concept: {concept} ({info['display_name']})")
            for syn in info.get("synonyms", []):
                pubs = ", ".join(syn.get("publishers", []))
                print(f"   • Card: {syn['card']:<12} | Publishers: {pubs}")
        print("=" * 70)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
