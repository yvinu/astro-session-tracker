"""Embedded Graph Database & Translation Engine for FITS Metadata.

Uses KùzuDB embedded property graph database (with SQLite fallback) to maintain
canonical concepts, vendor header card synonyms, publisher associations,
and multi-drive cumulative scan topologies.
"""

import os
import json
import sqlite3
from collections import Counter
from datetime import datetime

try:
    import kuzu
    KUZU_AVAILABLE = True
except ImportError:
    KUZU_AVAILABLE = False

DEFAULT_GRAPH_PATH = os.path.join(os.path.dirname(__file__), "astro_fits_graph.kuzu_db")
DEFAULT_SQLITE_GRAPH_PATH = os.path.join(os.path.dirname(__file__), "astro_fits_graph.sqlite")
SEED_JSON_PATH = os.path.join(os.path.dirname(__file__), "fits_dictionary.json")


class FITSGraphDB:
    """Property Graph Database interface using KùzuDB with SQLite fallback."""

    def __init__(self, db_path=DEFAULT_GRAPH_PATH):
        self.db_path = db_path
        self.use_kuzu = KUZU_AVAILABLE
        self.conn = None
        self.db = None
        self.sqlite_conn = None

        self._initialize_database()
        self.seed_from_json(SEED_JSON_PATH)

    def reset_database(self):
        """Reset the property graph database, deleting all custom nodes and re-seeding default dictionary schema."""
        if self.conn:
            try:
                self.conn = None
                self.db = None
            except Exception:
                pass
        if self.sqlite_conn:
            try:
                self.sqlite_conn.close()
                self.sqlite_conn = None
            except Exception:
                pass

        import shutil
        if os.path.exists(self.db_path):
            try:
                if os.path.isdir(self.db_path):
                    shutil.rmtree(self.db_path)
                else:
                    os.remove(self.db_path)
            except Exception as e:
                print(f"Notice: KuzuDB cleanup warning: {e}")

        if os.path.exists(DEFAULT_SQLITE_GRAPH_PATH):
            try:
                os.remove(DEFAULT_SQLITE_GRAPH_PATH)
            except Exception:
                pass

        cum_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cumulative_catalog.json")
        if os.path.exists(cum_path):
            try:
                os.remove(cum_path)
            except Exception:
                pass

        self.use_kuzu = KUZU_AVAILABLE
        self._initialize_database()
        self.seed_from_json(SEED_JSON_PATH)
        print("🔄 Corpus reset complete! Graph DB and cumulative catalog re-initialized.")

    def _initialize_database(self):
        """Initialize KùzuDB schema or SQLite property graph schema."""
        if self.use_kuzu:
            try:
                parent_dir = os.path.dirname(self.db_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)
                self.db = kuzu.Database(self.db_path)
                self.conn = kuzu.Connection(self.db)
                self._create_kuzu_schema()
                return
            except Exception as e:
                print(f"⚠️ KùzuDB initialization failed ({e}), falling back to SQLite Property Graph.")
                self.use_kuzu = False

        # Fallback to SQLite Property Graph
        self.sqlite_conn = sqlite3.connect(DEFAULT_SQLITE_GRAPH_PATH)
        self._create_sqlite_schema()

    def _create_kuzu_schema(self):
        """Create Node and Relationship tables in KùzuDB."""
        schemas = [
            # Node tables
            "CREATE NODE TABLE IF NOT EXISTS CanonicalConcept(name STRING, display_name STRING, data_type STRING, default_val STRING, PRIMARY KEY (name))",
            "CREATE NODE TABLE IF NOT EXISTS HeaderCard(card_name STRING, data_type STRING, notes STRING, PRIMARY KEY (card_name))",
            "CREATE NODE TABLE IF NOT EXISTS Publisher(name STRING, category STRING, PRIMARY KEY (name))",
            "CREATE NODE TABLE IF NOT EXISTS ScanDrive(path STRING, last_scanned STRING, PRIMARY KEY (path))",
            "CREATE NODE TABLE IF NOT EXISTS FitsFile(file_path STRING, file_name STRING, PRIMARY KEY (file_path))",
            
            # Relationship tables
            "CREATE REL TABLE IF NOT EXISTS MAPS_TO(FROM HeaderCard TO CanonicalConcept)",
            "CREATE REL TABLE IF NOT EXISTS WRITTEN_BY(FROM HeaderCard TO Publisher)",
            "CREATE REL TABLE IF NOT EXISTS HAS_CARD(FROM FitsFile TO HeaderCard)",
            "CREATE REL TABLE IF NOT EXISTS PRODUCED_BY(FROM FitsFile TO Publisher)",
            "CREATE REL TABLE IF NOT EXISTS LOCATED_IN(FROM FitsFile TO ScanDrive)"
        ]

        for stmt in schemas:
            try:
                self.conn.execute(stmt)
            except Exception:
                pass

    def _create_sqlite_schema(self):
        """Create property graph nodes and edges in SQLite."""
        cur = self.sqlite_conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                properties TEXT
            );
            CREATE TABLE IF NOT EXISTS edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                relation TEXT NOT NULL,
                properties TEXT,
                PRIMARY KEY (source, target, relation)
            );
        """)
        self.sqlite_conn.commit()

    def seed_from_json(self, json_path=SEED_JSON_PATH):
        """Seed canonical concepts, header cards, and publisher relationships from JSON."""
        if not os.path.exists(json_path):
            return

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if self.use_kuzu:
            self._seed_kuzu(data)
        else:
            self._seed_sqlite(data)

    def _seed_kuzu(self, data):
        """Insert seed nodes and edges into KùzuDB."""
        for concept_key, info in data.items():
            disp_name = info.get("display_name", concept_key)
            d_type = info.get("data_type", "str")
            def_val = str(info.get("default", ""))

            # Upsert CanonicalConcept
            try:
                self.conn.execute(
                    "MERGE (c:CanonicalConcept {name: $name}) ON CREATE SET c.display_name = $disp, c.data_type = $dtype, c.default_val = $def",
                    {"name": concept_key, "disp": disp_name, "dtype": d_type, "def": def_val}
                )
            except Exception:
                pass

            for syn in info.get("synonyms", []):
                card_name = syn.get("card", "").upper().strip()
                notes = syn.get("notes", "")
                if not card_name:
                    continue

                # Upsert HeaderCard
                try:
                    self.conn.execute(
                        "MERGE (h:HeaderCard {card_name: $card}) ON CREATE SET h.data_type = $dtype, h.notes = $notes",
                        {"card": card_name, "dtype": d_type, "notes": notes}
                    )
                except Exception:
                    pass

                # Connect HeaderCard -> CanonicalConcept
                try:
                    self.conn.execute(
                        "MATCH (h:HeaderCard {card_name: $card}), (c:CanonicalConcept {name: $concept}) MERGE (h)-[:MAPS_TO]->(c)",
                        {"card": card_name, "concept": concept_key}
                    )
                except Exception:
                    pass

                # Upsert Publishers & connect
                for pub in syn.get("publishers", []):
                    pub_clean = pub.strip()
                    if not pub_clean:
                        continue

                    try:
                        self.conn.execute(
                            "MERGE (p:Publisher {name: $pub}) ON CREATE SET p.category = 'Acquisition/Processing'",
                            {"pub": pub_clean}
                        )
                    except Exception:
                        pass

                    try:
                        self.conn.execute(
                            "MATCH (h:HeaderCard {card_name: $card}), (p:Publisher {name: $pub}) MERGE (h)-[:WRITTEN_BY]->(p)",
                            {"card": card_name, "pub": pub_clean}
                        )
                    except Exception:
                        pass

    def _seed_sqlite(self, data):
        """Insert seed nodes and edges into SQLite property graph."""
        cur = self.sqlite_conn.cursor()
        for concept_key, info in data.items():
            disp_name = info.get("display_name", concept_key)
            d_type = info.get("data_type", "str")
            def_val = str(info.get("default", ""))

            concept_id = f"concept:{concept_key}"
            cur.execute(
                "INSERT OR REPLACE INTO nodes (id, type, properties) VALUES (?, ?, ?)",
                (concept_id, "CanonicalConcept", json.dumps({"name": concept_key, "display_name": disp_name, "data_type": d_type, "default": def_val}))
            )

            for syn in info.get("synonyms", []):
                card_name = syn.get("card", "").upper().strip()
                if not card_name:
                    continue

                card_id = f"card:{card_name}"
                cur.execute(
                    "INSERT OR REPLACE INTO nodes (id, type, properties) VALUES (?, ?, ?)",
                    (card_id, "HeaderCard", json.dumps({"card_name": card_name, "data_type": d_type, "notes": syn.get("notes", "")}))
                )

                cur.execute(
                    "INSERT OR REPLACE INTO edges (source, target, relation) VALUES (?, ?, ?)",
                    (card_id, concept_id, "MAPS_TO")
                )

                for pub in syn.get("publishers", []):
                    pub_clean = pub.strip()
                    if not pub_clean:
                        continue

                    pub_id = f"pub:{pub_clean}"
                    cur.execute(
                        "INSERT OR REPLACE INTO nodes (id, type, properties) VALUES (?, ?, ?)",
                        (pub_id, "Publisher", json.dumps({"name": pub_clean}))
                    )
                    cur.execute(
                        "INSERT OR REPLACE INTO edges (source, target, relation) VALUES (?, ?, ?)",
                        (card_id, pub_id, "WRITTEN_BY")
                    )

        self.sqlite_conn.commit()

    def lookup_card(self, card_name):
        """Lookup a raw card name to find its canonical concept and associated publishers."""
        card_upper = card_name.upper().strip()

        if self.use_kuzu:
            try:
                res = self.conn.execute(
                    "MATCH (h:HeaderCard {card_name: $card})-[:MAPS_TO]->(c:CanonicalConcept) "
                    "OPTIONAL MATCH (h)-[:WRITTEN_BY]->(p:Publisher) "
                    "RETURN c.name AS concept, c.display_name AS display_name, collect(p.name) AS publishers",
                    {"card": card_upper}
                )
                if res.has_next():
                    row = res.get_next()
                    return {
                        "card": card_upper,
                        "concept": row[0],
                        "display_name": row[1],
                        "publishers": [p for p in row[2] if p]
                    }
            except Exception:
                pass

        # SQLite Fallback
        if self.sqlite_conn:
            cur = self.sqlite_conn.cursor()
            card_id = f"card:{card_upper}"
            cur.execute("SELECT target FROM edges WHERE source = ? AND relation = 'MAPS_TO'", (card_id,))
            concept_row = cur.fetchone()
            if concept_row:
                concept_id = concept_row[0]
                cur.execute("SELECT properties FROM nodes WHERE id = ?", (concept_id,))
                c_props = json.loads(cur.fetchone()[0])

                cur.execute("SELECT target FROM edges WHERE source = ? AND relation = 'WRITTEN_BY'", (card_id,))
                pub_rows = cur.fetchall()
                pubs = [p[0].replace("pub:", "") for p in pub_rows]

                return {
                    "card": card_upper,
                    "concept": c_props["name"],
                    "display_name": c_props["display_name"],
                    "publishers": pubs
                }

        return None

    def query_publisher(self, publisher_name):
        """Retrieve all header cards used by a given software publisher."""
        pub_clean = publisher_name.strip()

        if self.use_kuzu:
            try:
                res = self.conn.execute(
                    "MATCH (h:HeaderCard)-[:WRITTEN_BY]->(p:Publisher) "
                    "WHERE lower(p.name) CONTAINS lower($pub) "
                    "MATCH (h)-[:MAPS_TO]->(c:CanonicalConcept) "
                    "RETURN h.card_name AS card, c.name AS concept, c.display_name AS display_name, p.name AS pub_name",
                    {"pub": pub_clean}
                )
                results = []
                while res.has_next():
                    row = res.get_next()
                    results.append({"card": row[0], "concept": row[1], "display_name": row[2], "publisher": row[3]})
                return results
            except Exception as e:
                pass

        if self.sqlite_conn:
            cur = self.sqlite_conn.cursor()
            cur.execute(
                "SELECT e.source, e.target, n.properties FROM edges e "
                "JOIN nodes n ON e.source = n.id "
                "WHERE e.relation = 'WRITTEN_BY' AND LOWER(e.target) LIKE ?",
                (f"%{pub_clean.lower()}%",)
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                card_name = r[0].replace("card:", "")
                pub_name = r[1].replace("pub:", "")
                c_data = self.lookup_card(card_name)
                concept = c_data["concept"] if c_data else "Unknown"
                disp = c_data["display_name"] if c_data else "Unknown"
                results.append({"card": card_name, "concept": concept, "display_name": disp, "publisher": pub_name})
            return results

        return []

    def interpret_header(self, header_data):
        """Interpret a raw header dict, returning canonical fields and detected publisher sources."""
        if not header_data:
            return {}

        raw_keys = {k.upper().strip(): v for k, v in header_data.items() if k}
        interpreted = {}
        detected_publishers = Counter()

        # Load dictionary mapping
        with open(SEED_JSON_PATH, 'r', encoding='utf-8') as f:
            dict_schema = json.load(f)

        for concept_key, info in dict_schema.items():
            syn_list = info.get("synonyms", [])
            val = None
            found_card = None

            for syn in syn_list:
                card_name = syn.get("card", "").upper().strip()
                if card_name in raw_keys and raw_keys[card_name] not in [None, "", "Unknown", "N/A"]:
                    val = raw_keys[card_name]
                    found_card = card_name

                    # Increment publisher votes for found cards
                    for p in syn.get("publishers", []):
                        detected_publishers[p] += 1
                    break

            # Fallback if no non-empty value found
            if val is None:
                val = info.get("default", "Unknown")
            else:
                target_type = info.get("data_type", "str")
                if target_type == "float":
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
                elif target_type == "int":
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        pass

            interpreted[concept_key] = val
            if found_card:
                interpreted[f"{concept_key}_source_card"] = found_card

        # Add detected software origins
        top_pubs = [pub for pub, count in detected_publishers.most_common(3)]
        interpreted["detected_publishers"] = top_pubs

        return interpreted

    def get_graph_stats(self):
        """Return node and relationship count statistics from the property graph."""
        if self.use_kuzu:
            try:
                c_nodes = self.conn.execute("MATCH (c:CanonicalConcept) RETURN count(c)").get_next()[0]
                h_nodes = self.conn.execute("MATCH (h:HeaderCard) RETURN count(h)").get_next()[0]
                p_nodes = self.conn.execute("MATCH (p:Publisher) RETURN count(p)").get_next()[0]
                m_edges = self.conn.execute("MATCH ()-[r:MAPS_TO]->() RETURN count(r)").get_next()[0]
                w_edges = self.conn.execute("MATCH ()-[r:WRITTEN_BY]->() RETURN count(r)").get_next()[0]
                return {
                    "backend": "KùzuDB Embedded Property Graph",
                    "db_path": self.db_path,
                    "canonical_concepts": c_nodes,
                    "header_cards": h_nodes,
                    "publishers": p_nodes,
                    "maps_to_edges": m_edges,
                    "written_by_edges": w_edges
                }
            except Exception as e:
                pass

        if self.sqlite_conn:
            cur = self.sqlite_conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nodes")
            total_nodes = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM edges")
            total_edges = cur.fetchone()[0]
            return {
                "backend": "SQLite Embedded Property Graph",
                "db_path": DEFAULT_SQLITE_GRAPH_PATH,
                "total_nodes": total_nodes,
                "total_edges": total_edges
            }

        return {}
