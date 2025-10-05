"""Minimal admin UI for managing canonical mappings."""
from __future__ import annotations

import html
from typing import Iterable, Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..canonical.store import CanonicalCandidate, CanonicalStore
from ..resolver.canonicalizer import Canonicalizer

router = APIRouter()


@router.get("/admin/canonical", response_class=HTMLResponse)
async def canonical_admin(
    request: Request,
    dim: str = "area",
    q: str = "",
    success: Optional[str] = None,
) -> HTMLResponse:
    store = _get_store(request)
    canonicalizer = _get_canonicalizer(request)
    results: Iterable[CanonicalCandidate] = []
    if q:
        results = store.search(dim, q)
    current = store.current_mapping(dim, q) if q else None
    like_bypass = "%" in q if q else False
    dimensions = sorted(store.dimensions())
    html_body = _render_page(
        dim=dim,
        query=q,
        results=results,
        current=current,
        like_bypass=like_bypass,
        success=bool(success),
        canonicalizer_version=canonicalizer.version if canonicalizer else None,
        dimensions=dimensions,
    )
    return HTMLResponse(content=html_body)


@router.post("/admin/canonical/promote")
async def canonical_promote(
    request: Request,
    dim: str = Form(...),
    synonym: str = Form(...),
    canonical: str = Form(...),
    score: float = Form(...),
    promoted_by: Optional[str] = Form(None),
    q: str = Form(""),
) -> RedirectResponse:
    store = _get_store(request)
    canonicalizer = _get_canonicalizer(request)
    version = store.promote(dim, synonym, canonical, score, promoted_by=promoted_by)
    if canonicalizer:
        canonicalizer.load(store.load_mappings(), version)
    target = f"/admin/canonical?dim={dim}&q={synonym or q}&success=1"
    return RedirectResponse(url=target, status_code=303)


def _render_page(
    *,
    dim: str,
    query: str,
    results: Iterable[CanonicalCandidate],
    current: Optional[str],
    like_bypass: bool,
    success: bool,
    canonicalizer_version: Optional[int],
    dimensions: Iterable[str],
) -> str:
    rows = "\n".join(_render_row(dim, query, candidate) for candidate in results)
    if not rows:
        rows = "<tr><td colspan=4 class='empty'>No candidates yet. Try refining your search.</td></tr>"
    banner = ""
    if like_bypass:
        banner = "<div class='banner'>LIKE bypass is active for this search.</div>"
    toast = ""
    if success:
        toast = "<div class='toast'>Synonym promoted successfully.</div>"
    current_mapping = (
        f"<p class='current'>Current mapping for <strong>{html.escape(query)}</strong>:"
        f" <span>{html.escape(current)}</span></p>"
        if current
        else ""
    )
    version_label = (
        f"<span class='version'>Cache version: {canonicalizer_version}</span>"
        if canonicalizer_version is not None
        else ""
    )
    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Canonicalization Workbench</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f5f7fb; }}
            h1 {{ margin-bottom: 0.5rem; }}
            form.search {{ margin-bottom: 1.5rem; display: flex; gap: 0.5rem; align-items: center; }}
            input[type=text] {{ padding: 0.5rem; flex: 1; border: 1px solid #cbd5e1; border-radius: 4px; }}
            select {{ padding: 0.5rem; border: 1px solid #cbd5e1; border-radius: 4px; }}
            button {{ background: #2563eb; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; }}
            button:hover {{ background: #1d4ed8; }}
            table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 2px rgba(15,23,42,0.1); }}
            th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #e2e8f0; }}
            th {{ background: #f1f5f9; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; color: #475569; }}
            td.actions form {{ display: inline; }}
            td.actions button {{ background: #16a34a; }}
            td.actions button:hover {{ background: #15803d; }}
            .banner {{ background: #f59e0b; color: #111827; padding: 0.5rem 0.75rem; border-radius: 4px; margin-bottom: 1rem; }}
            .toast {{ background: #22c55e; color: white; padding: 0.5rem 0.75rem; border-radius: 4px; margin-bottom: 1rem; }}
            .current {{ margin-bottom: 1rem; color: #334155; }}
            .current span {{ font-weight: bold; }}
            .empty {{ text-align: center; color: #64748b; font-style: italic; }}
            footer {{ margin-top: 1.5rem; color: #64748b; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center; }}
            .version {{ background: #e0f2fe; color: #0369a1; padding: 0.25rem 0.5rem; border-radius: 999px; }}
        </style>
    </head>
    <body>
        <h1>Canonicalization Workbench</h1>
        {banner}
        {toast}
        <form class="search" method="get" action="/admin/canonical">
            <label for="dim">Dimension</label>
            <select name="dim" id="dim">
                {''.join(_render_option(dim, option) for option in dimensions)}
            </select>
            <input type="text" name="q" value="{html.escape(query)}" placeholder="Search for a synonym" />
            <button type="submit">Search</button>
        </form>
        {current_mapping}
        <table>
            <thead>
                <tr>
                    <th>Candidate</th>
                    <th>Score</th>
                    <th>Current Canonical</th>
                    <th class="actions">Action</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        <footer>
            <span>LIKE searches are bypassed when patterns are used.</span>
            {version_label}
        </footer>
    </body>
    </html>
    """


def _render_row(dim: str, query: str, candidate: CanonicalCandidate) -> str:
    score = f"{candidate.score:.2f}"
    canonical = candidate.canonical or "—"
    return (
        "<tr>"
        f"<td>{html.escape(candidate.candidate)}</td>"
        f"<td>{score}</td>"
        f"<td>{html.escape(canonical)}</td>"
        "<td class='actions'>"
        "<form method='post' action='/admin/canonical/promote'>"
        f"<input type='hidden' name='dim' value='{html.escape(dim)}' />"
        f"<input type='hidden' name='synonym' value='{html.escape(query)}' />"
        f"<input type='hidden' name='canonical' value='{html.escape(candidate.candidate)}' />"
        f"<input type='hidden' name='score' value='{candidate.score}' />"
        f"<input type='hidden' name='q' value='{html.escape(query)}' />"
        "<button type='submit'>Promote</button>"
        "</form>"
        "</td>"
        "</tr>"
    )


def _render_option(current: str, option: str) -> str:
    selected = " selected" if current == option else ""
    return f"<option value='{html.escape(option)}'{selected}>{html.escape(option.title())}</option>"


def _get_store(request: Request) -> CanonicalStore:
    store = getattr(request.app.state, "canonical_store", None)
    if not isinstance(store, CanonicalStore):
        raise HTTPException(status_code=503, detail="Canonical store not ready")
    return store


def _get_canonicalizer(request: Request) -> Optional[Canonicalizer]:
    canonicalizer = getattr(request.app.state, "canonicalizer", None)
    if canonicalizer is not None and not isinstance(canonicalizer, Canonicalizer):
        raise HTTPException(status_code=503, detail="Canonicalizer unavailable")
    return canonicalizer
