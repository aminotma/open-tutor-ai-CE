#!/usr/bin/env python3
"""
Écoute en temps réel les nouveaux messages de Lina
et capture le contexte RAG + mémoires envoyé au tuteur.

Usage : python3 watch_context.py
"""
import time
import sqlite3
import requests
import json
from datetime import datetime

BASE_URL  = "http://localhost:8080"
DB_PATH   = "backend/data/webui.db"
USER_ID   = "e7e856a2-0e10-4187-80ce-10a8b09d91aa"
TOKEN_FILE = "/tmp/lina_token.txt"

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
MAGENTA= "\033[95m"
RED    = "\033[91m"
GREY   = "\033[90m"


def get_token():
    try:
        return open(TOKEN_FILE).read().strip()
    except FileNotFoundError:
        resp = requests.post(f"{BASE_URL}/api/v1/auths/signin",
                             json={"email": "lina@otmani.com", "password": "123"})
        token = resp.json()["token"]
        open(TOKEN_FILE, "w").write(token)
        return token


def get_last_memory_id(conn):
    row = conn.execute(
        "SELECT id FROM opentutorai_memory WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
        (USER_ID,)
    ).fetchone()
    return row[0] if row else None


def get_new_memories(conn, since_id):
    rows = conn.execute("""
        SELECT id, memory_type, content, created_at, memory_metadata
        FROM opentutorai_memory
        WHERE user_id=? AND created_at > (
            SELECT created_at FROM opentutorai_memory WHERE id=?
        )
        ORDER BY created_at ASC
    """, (USER_ID, since_id)).fetchall()
    return rows


def fetch_context(token, query, topic=""):
    try:
        resp = requests.post(
            f"{BASE_URL}/api/v1/context/retrieve",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": query,
                "max_results": 5,
                "include_source_types": ["pedagogical", "memory"],
                "topic": topic
            },
            timeout=10
        )
        return resp.json() if resp.ok else []
    except Exception:
        return []


def print_separator(label=""):
    ts = datetime.now().strftime("%H:%M:%S")
    line = "─" * 60
    if label:
        print(f"\n{CYAN}{line}{RESET}")
        print(f"{BOLD}{CYAN}[{ts}] {label}{RESET}")
        print(f"{CYAN}{line}{RESET}")
    else:
        print(f"{GREY}{line}{RESET}")


def display_context(results, query):
    if not results:
        print(f"  {GREY}Aucun contexte retourné{RESET}")
        return
    print(f"\n  {YELLOW}Contexte assemblé pour : \"{query}\"{RESET}")
    for r in results:
        rank   = r.get("rank", "?")
        source = r.get("source", "?")
        meta   = r.get("metadata", {})
        scores = r.get("scores", {})
        title  = meta.get("title") or meta.get("type") or "?"
        score  = scores.get("composite", scores.get("normalized", 0))
        preview = r.get("content_preview") or r.get("full_content", "")

        color = GREEN if source == "pedagogical" else MAGENTA
        print(f"\n  {color}[rank {rank}] {source.upper()} | {title[:45]} | score={score:.3f}{RESET}")
        print(f"  {GREY}→ {preview[:120].strip()}...{RESET}")


def main():
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║   OpenTutorAI — Écoute contexte en temps réel ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════╝{RESET}")
    print(f"  Utilisateur : lina@otmani.com")
    print(f"  Polling toutes les 2 secondes...\n")

    token = get_token()
    conn  = sqlite3.connect(DB_PATH)
    last_id = get_last_memory_id(conn)
    print(f"{GREY}  Dernière mémoire connue : {last_id}{RESET}\n")
    print(f"{GREEN}  En attente d'un nouveau message...{RESET}")

    try:
        while True:
            time.sleep(2)
            conn = sqlite3.connect(DB_PATH)
            new_rows = get_new_memories(conn, last_id) if last_id else []
            conn.close()

            if not new_rows:
                continue

            for row in new_rows:
                mid, mtype, content, cat, meta_raw = row
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
                ts   = datetime.fromisoformat(str(cat)).strftime("%H:%M:%S") if "T" in str(cat) else str(cat)

                print_separator(f"NOUVEAU MESSAGE CAPTURÉ")
                print(f"  {BOLD}Type mémoire :{RESET} {mtype}")
                print(f"  {BOLD}Horodatage   :{RESET} {ts}")
                print(f"  {BOLD}Contenu      :{RESET} {content[:150]}")
                if meta:
                    topic = meta.get("topic") or meta.get("concept") or ""
                    inter = meta.get("interaction_type") or ""
                    if topic or inter:
                        print(f"  {BOLD}Topic/Type   :{RESET} {topic or inter}")

                # Extraire la requête du message apprenant pour fetch le contexte
                query = content
                if "Q:" in content:
                    query = content.split("Q:")[1].split("|")[0].strip()
                elif content.startswith("Learner:"):
                    query = content.replace("Learner:", "").strip()

                if query and len(query) > 2:
                    print(f"\n  {YELLOW}↳ Récupération du contexte pour : \"{query[:60]}\"...{RESET}")
                    ctx = fetch_context(token, query)
                    display_context(ctx, query)

                last_id = mid

            print(f"\n{GREEN}  En attente du prochain message...{RESET}")

    except KeyboardInterrupt:
        print(f"\n\n{CYAN}  Arrêt de l'écoute. Bye !{RESET}\n")


if __name__ == "__main__":
    main()
