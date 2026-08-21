"""Best-effort webshop product import.

Fetches a product page and pulls a name, brand, colour, price and candidate
images out of its JSON-LD and OpenGraph/meta tags. Uses only the standard
library so no extra dependency is needed. Everything degrades gracefully:
if the server can't reach the URL, a clear error is returned and the user
falls back to filling the form manually.
"""

from __future__ import annotations

import json
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..models import User
from ..schemas import ScrapeResult

router = APIRouter(prefix="/api/import", tags=["import"])

_MAX_HTML = 3 * 1024 * 1024  # 3 MB of HTML is plenty for a product page

# A realistic browser fingerprint: many webshops (e.g. State of Art) reject
# requests from unknown clients with a 403, which is why the import used to
# fail. These headers make the request look like an ordinary browser visit.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}


class _ProductParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metas: list[dict[str, str]] = []
        self.title: str | None = None
        self.ldjson: list[str] = []
        self.images: list[str] = []
        self._in_title = False
        self._in_ldjson = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            self.metas.append(a)
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_ldjson = True
            self.ldjson.append("")
        elif tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if src:
                self.images.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ldjson:
            self._in_ldjson = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data
        elif self._in_ldjson and self.ldjson:
            self.ldjson[-1] += data


def _meta(parser: _ProductParser, *keys: str) -> str | None:
    """Look up a meta tag by property/name/itemprop (case-insensitive)."""
    wanted = {k.lower() for k in keys}
    for m in parser.metas:
        for attr in ("property", "name", "itemprop"):
            if m.get(attr, "").lower() in wanted and m.get("content"):
                return unescape(m["content"]).strip()
    return None


def _walk_ldjson(node, out: dict) -> None:
    """Recursively pull product fields out of a JSON-LD structure."""
    if isinstance(node, list):
        for n in node:
            _walk_ldjson(n, out)
        return
    if not isinstance(node, dict):
        return
    if "@graph" in node:
        _walk_ldjson(node["@graph"], out)

    types = node.get("@type", "")
    types = types if isinstance(types, list) else [types]
    if "Product" in types:
        if not out.get("name") and node.get("name"):
            out["name"] = str(node["name"]).strip()
        if node.get("color") and not out.get("color"):
            out["color"] = str(node["color"]).strip()
        if node.get("description") and not out.get("description"):
            out["description"] = str(node["description"]).strip()
        brand = node.get("brand")
        if brand and not out.get("brand"):
            out["brand"] = (brand.get("name") if isinstance(brand, dict) else str(brand)).strip()
        image = node.get("image")
        if image:
            imgs = image if isinstance(image, list) else [image]
            for im in imgs:
                url = im.get("url") if isinstance(im, dict) else im
                if url:
                    out.setdefault("images", []).append(str(url))
        offers = node.get("offers")
        if offers and not out.get("price"):
            offer = offers[0] if isinstance(offers, list) else offers
            if isinstance(offer, dict):
                price = offer.get("price") or offer.get("lowPrice")
                if price:
                    cur = offer.get("priceCurrency", "")
                    out["price"] = f"{price} {cur}".strip()
    # Recurse into nested values to reach graphs and offers.
    for v in node.values():
        if isinstance(v, (dict, list)):
            _walk_ldjson(v, out)


@router.get("/scrape", response_model=ScrapeResult)
def scrape(
    url: str,
    _: User = Depends(get_current_user),
):
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Voer een geldige http(s)-URL in")
    try:
        req = Request(url, headers=_BROWSER_HEADERS)
        with urlopen(req, timeout=15) as resp:  # noqa: S310 (user-provided URL)
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read(_MAX_HTML).decode(charset, errors="replace")
            final_url = resp.geturl()
    except HTTPError as exc:
        # The shop answered but refused us (403 bot-block, 404 dead link, ...).
        raise HTTPException(
            status_code=502,
            detail=(
                f"De webshop weigerde het verzoek (foutcode {exc.code}). "
                "Deze winkel blokkeert mogelijk automatisch importeren; "
                "vul de gegevens handmatig in."
            ),
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Kon de webshop-pagina niet ophalen. Vul de gegevens handmatig in.",
        )

    parser = _ProductParser()
    parser.feed(html)

    data: dict = {}
    for block in parser.ldjson:
        try:
            _walk_ldjson(json.loads(block), data)
        except (json.JSONDecodeError, TypeError):
            continue

    name = data.get("name") or _meta(parser, "og:title", "twitter:title") or (parser.title or "").strip() or None
    brand = data.get("brand") or _meta(parser, "product:brand", "og:brand", "og:site_name")
    color = data.get("color") or _meta(parser, "product:color")
    description = data.get("description") or _meta(parser, "og:description", "description")
    price = data.get("price")
    if not price:
        amount = _meta(parser, "product:price:amount", "og:price:amount")
        if amount:
            cur = _meta(parser, "product:price:currency", "og:price:currency") or ""
            price = f"{amount} {cur}".strip()

    # Collect candidate images: JSON-LD, OpenGraph, then a few page <img>s.
    images: list[str] = list(data.get("images", []))
    og_img = _meta(parser, "og:image", "og:image:secure_url", "twitter:image")
    if og_img:
        images.insert(0, og_img)
    images.extend(parser.images)

    seen: set[str] = set()
    absolute: list[str] = []
    for src in images:
        if not src or src.startswith("data:"):
            continue
        full = urljoin(final_url, src.strip())
        if full in seen:
            continue
        seen.add(full)
        absolute.append(full)
        if len(absolute) >= 12:
            break

    return ScrapeResult(
        name=name,
        brand=brand,
        color=color,
        price=price,
        description=(description[:500] if description else None),
        images=absolute,
    )
