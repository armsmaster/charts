"""Serves the plotly.js bundle that ships inside the installed plotly package.

The work PC has no access to public CDNs, and vendoring a 3 MB minified file
into the repository is worse than reusing the copy pip already installed.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(prefix="/vendor", tags=["vendor"])


@router.get("/plotly.min.js")
async def plotly_js() -> Response:
    from plotly.offline import get_plotlyjs

    return Response(
        content=get_plotlyjs(),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/plotly-locale-ru.js")
async def plotly_locale_ru() -> Response:
    """Russian locale module for plotly.js - not in the pip package, and the
    deploy host has no CDN. Loaded after ``plotly.min.js`` so it self-registers.
    """
    from ...charting.locale import locale_js

    return Response(
        content=locale_js(),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=86400"},
    )
