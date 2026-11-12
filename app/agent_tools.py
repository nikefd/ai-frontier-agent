"""Agent tools for the AI-frontier agent — injected into the sparrow harness.

Tools are built per request and bound to the logged-in user's id (``uid``) via
``build_tools(uid)``: reads query the news store (global articles/sources plus
the user's tracks/guides/pins/deep-dives); write tools touch only that user's
config (tracks.json) and pins (pins.json). Every result carries a ``source`` for
citation. Results are kept compact to respect the harness context budget.
"""
from __future__ import annotations

import secrets

from .agent_runtime import tool

from .routers import ai_news as news
from .storage import read_json, update_json_atomic


_MAX_ARTICLES = 15  # per query, to stay within the context budget


def build_tools(uid: str) -> list:
    """Return a fresh tool set bound to ``uid``. Called once per chat request."""

    # ── Read tools ───────────────────────────────────────────────────
    @tool(name="query_articles", label="search articles", source="articles.json",
          description="Search the latest AI articles. Filter by track keyword, "
                      "category (vendor/expert/x-ai/community/media/paper/trending), "
                      "free-text keyword, or pinned-only. Returns newest first.")
    def query_articles(keyword: str = "", category: str = "", track: str = "",
                       pinned_only: bool = False, limit: int = 10) -> dict:
        articles = news._load_articles()
        pins = news._load_pins(uid)
        # If a track name/id is given, expand it into its keywords for matching.
        if track:
            tracks = {t.get("id"): t for t in news._load_tracks(uid)}
            tracks.update({t.get("name"): t for t in news._load_tracks(uid)})
            t = tracks.get(track)
            if t and t.get("keywords"):
                kws = [k.lower() for k in t["keywords"]]
                articles = [a for a in articles
                            if any(k in ((a.get("title") or "") + (a.get("summary") or "")).lower()
                                   for k in kws)]
        if pinned_only:
            articles = [a for a in articles if a.get("id") in pins]
        if category:
            articles = [a for a in articles if (a.get("category") or "") == category]
        if keyword:
            kl = keyword.lower()
            articles = [a for a in articles
                        if kl in ((a.get("title") or "") + (a.get("summary") or "")
                                  + (a.get("title_zh") or "") + (a.get("summary_zh") or "")).lower()]
        articles.sort(key=lambda a: (a.get("id") not in pins, -(news._parse_ts(a.get("date") or ""))))
        total = len(articles)
        limit = max(1, min(int(limit), _MAX_ARTICLES))
        ddir = news.deep_dives_dir(uid)
        items = [{
            "id": a.get("id"),
            "url": a.get("url"),
            "title": a.get("title_zh") or a.get("title"),
            "source": a.get("source"),
            "category": a.get("category"),
            "date": a.get("date"),
            "summary": (a.get("summary_zh") or a.get("summary") or "")[:200],
            "pinned": a.get("id") in pins,
            "has_deep_dive": (ddir / f"{a.get('id')}.json").exists(),
        } for a in articles[:limit]]
        return {"total_matched": total, "showing": len(items), "articles": items,
                "source": "articles.json"}

    @tool(name="query_tracks", label="list tracks", source="tracks.json",
          description="List the user's tracking topics (each has a name and keywords "
                      "used to filter articles).")
    def query_tracks() -> dict:
        tracks = news._load_tracks(uid)
        return {"tracks": [{"id": t.get("id"), "name": t.get("name"),
                            "keywords": t.get("keywords", [])} for t in tracks],
                "source": "tracks.json"}

    @tool(name="read_article", label="read article", source="articles.json",
          description="Read one article in depth by its id: full summary plus a "
                      "deep-dive analysis if the user has generated one.")
    def read_article(id: str = "") -> dict:
        articles = {a.get("id"): a for a in news._load_articles()}
        a = articles.get(id)
        if not a:
            return {"error": f"no article with id {id}"}
        out = {
            "id": id,
            "title": a.get("title"),
            "title_zh": a.get("title_zh"),
            "date": a.get("date"),
            "publication": a.get("source"),
            "url": a.get("url"),
            "source": a.get("source"),
            "summary": a.get("summary_zh") or a.get("summary"),
            "_citation": "articles.json",
        }
        # Attach the user's deep dive if present
        dive = news.deep_dives_dir(uid) / f"{id}.json"
        if dive.exists():
            d = read_json(dive, {})
            out["deep_dive"] = (d.get("body") or "")[:3000]
        out["source"] = f"articles.json: {id}"
        return out

    @tool(name="query_guides", label="list guides", source="guides.json",
          description="List hands-on / how-to learning guides the user has saved.")
    def query_guides() -> dict:
        guides = news._load_guides(uid)
        return {"guides": [{"id": g.get("id"), "title": g.get("title"),
                            "tags": g.get("tags", [])} for g in guides],
                "source": "guides.json"}

    @tool(name="query_sources", label="list sources", source="sources.json",
          description="List the configured RSS feeds and their categories / health.")
    def query_sources() -> dict:
        srcs = news.list_sources()
        # compact: name + category + ok/err, drop verbose metadata
        out = [{"name": s.get("name"), "category": s.get("category"),
                "ok": bool(s.get("last_ok") and not s.get("last_error"))} for s in srcs]
        return {"count": len(out), "sources": out, "source": "sources.json"}

    # ── Write tools (touch only this user's config) ──────────────────
    @tool(name="create_track", label="create track", writes=True, source="tracks.json",
          description="Create a new tracking topic so future article queries can "
                      "filter by it. Only call after the user explicitly agrees. "
                      "keywords is a list of strings the topic matches on.")
    def create_track(name: str = "", keywords: list = None, conversation_id: str = "") -> dict:
        if not name:
            return {"error": "name is required"}
        # Some models serialize a list arg as a comma/JSON string; normalize it.
        if isinstance(keywords, str):
            s = keywords.strip()
            if s.startswith("["):
                import json as _json
                try:
                    keywords = _json.loads(s)
                except (ValueError, TypeError):
                    keywords = []
            else:
                import re as _re
                # split on commas (en/zh), zh enumeration comma, semicolons, spaces
                keywords = [k.strip() for k in _re.split(r"[,，、;；\s]+", s) if k.strip()]
        if not isinstance(keywords, list):
            keywords = []
        # Flatten any single-string element that itself holds separators.
        flat = []
        for k in keywords:
            if isinstance(k, str) and any(sep in k for sep in ",，、;；"):
                import re as _re
                flat.extend(x.strip() for x in _re.split(r"[,，、;；]+", k) if x.strip())
            else:
                flat.append(k)
        keywords = flat
        new = {"id": "t_" + secrets.token_hex(4), "name": name,
               "keywords": keywords or [], "sources": []}

        def append_track(data):
            tracks = data if isinstance(data, list) else list(news.DEFAULT_TRACKS)
            if any(t.get("name") == name for t in tracks):
                raise ValueError(f"track '{name}' already exists")
            tracks.append(new)
            return tracks

        try:
            update_json_atomic(news.tracks_file(uid), list(news.DEFAULT_TRACKS), append_track)
        except ValueError as exc:
            return {"error": str(exc)}
        return {"ok": True, "id": new["id"], "message": f"track '{name}' created",
                "source": "tracks.json"}

    @tool(name="pin_article", label="pin article", writes=True, source="articles.json",
          description="Pin (bookmark) an article by id so it stays in the feed and "
                      "bubbles to the top. Call again to unpin.")
    def pin_article(id: str = "", conversation_id: str = "") -> dict:
        if not any(a.get("id") == id for a in news._load_articles()):
            return {"error": f"no article with id {id}"}
        pinned = False

        def toggle(data):
            nonlocal pinned
            pins = set(data) if isinstance(data, list) else set()
            if id in pins:
                pins.discard(id)
                pinned = False
            else:
                pins.add(id)
                pinned = True
            return sorted(pins)

        update_json_atomic(news.pins_file(uid), [], toggle)
        return {"ok": True, "pinned": pinned,
                "message": f"article {'pinned' if pinned else 'unpinned'}",
                "source": "articles.json"}

    read_tools = [query_articles, query_tracks, read_article, query_guides, query_sources]
    write_tools = [create_track, pin_article]
    return read_tools + write_tools
