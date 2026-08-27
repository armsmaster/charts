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
