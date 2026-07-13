import os
import re
import ssl
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

DOWNLOADABLE_EXTENSIONS = {
    ".csv",
    ".xlsx",
    ".xlsm",
    ".zip",
    ".xml",
    ".pdf",
    ".xls",
    ".dcf",
}
IMPORTABLE_EXTENSIONS = {".csv", ".xlsx", ".xlsm", ".zip", ".dcf"}
SEARCH_TERMS = [
    "prezzario lavori pubblici",
    "prezziario lavori pubblici",
    "prezzario",
]
KEYWORDS = ("prezzario", "prezziario", "lavori pubblici", "lavori-pubblici")


@dataclass(frozen=True)
class RegionalSource:
    key: str
    name: str
    homepage: str
    notes: str = ""
    search_urls: list[str] = field(default_factory=list)


class RegionalSourceError(RuntimeError):
    pass


class _AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        self._href = ""
        self._text_parts = []
        for key, value in attrs:
            if key.lower() == "href" and value:
                self._href = value
                break

    def handle_data(self, data):
        if self._href:
            self._text_parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or not self._href:
            return
        text = " ".join(
            part.strip() for part in self._text_parts if part.strip()
        )
        self.links.append((self._href, text))
        self._href = ""
        self._text_parts = []


REGIONAL_SOURCES: list[RegionalSource] = [
    RegionalSource("abruzzo", "Abruzzo", "https://www.regione.abruzzo.it"),
    RegionalSource(
        "basilicata", "Basilicata", "https://www.regione.basilicata.it"
    ),
    RegionalSource("calabria", "Calabria", "https://www.regione.calabria.it"),
    RegionalSource("campania", "Campania", "https://www.regione.campania.it"),
    RegionalSource(
        "emilia-romagna",
        "Emilia-Romagna",
        "https://www.regione.emilia-romagna.it",
    ),
    RegionalSource(
        "friuli-venezia-giulia",
        "Friuli Venezia Giulia",
        "https://www.regione.fvg.it",
    ),
    RegionalSource("lazio", "Lazio", "https://www.regione.lazio.it"),
    RegionalSource("liguria", "Liguria", "https://www.regione.liguria.it"),
    RegionalSource(
        "lombardia", "Lombardia", "https://www.regione.lombardia.it"
    ),
    RegionalSource("marche", "Marche", "https://www.regione.marche.it"),
    RegionalSource("molise", "Molise", "https://www.regione.molise.it"),
    RegionalSource("piemonte", "Piemonte", "https://www.regione.piemonte.it"),
    RegionalSource("puglia", "Puglia", "https://www.regione.puglia.it"),
    RegionalSource("sardegna", "Sardegna", "https://www.regione.sardegna.it"),
    RegionalSource("sicilia", "Sicilia", "https://www.regione.sicilia.it"),
    RegionalSource("toscana", "Toscana", "https://www.regione.toscana.it"),
    RegionalSource(
        "trento",
        "Trentino-Alto Adige / Provincia di Trento",
        "https://www.provincia.tn.it",
    ),
    RegionalSource(
        "bolzano",
        "Trentino-Alto Adige / Provincia di Bolzano",
        "https://www.provincia.bz.it",
    ),
    RegionalSource("umbria", "Umbria", "https://www.regione.umbria.it"),
    RegionalSource(
        "valle-d-aosta", "Valle d'Aosta", "https://www.regione.vda.it"
    ),
    RegionalSource("veneto", "Veneto", "https://www.regione.veneto.it"),
]


def _extract_year(text: str) -> int:
    years = re.findall(r"20\d{2}", text or "")
    return max((int(year) for year in years), default=0)


def _sanitize_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name.strip("._") or "prezzario"


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _ensure_http_url(url: str) -> str:
    """Allow only http(s) URLs — blocks file://, ftp:// and custom schemes."""
    scheme = urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"URL non consentito / URL scheme not allowed: {url}")
    return url


class RegionalPriceListService:
    def __init__(
        self,
        request_timeout: int = 45,
        max_search_candidates: int | None = None,
        verify_ssl: bool = True,
    ):
        if verify_ssl:
            self._ssl_context = ssl.create_default_context()
        else:
            # Opt-out esplicito solo per portali istituzionali con catene di
            # certificati non valide; mai attivo di default.
            self._ssl_context = (
                ssl._create_unverified_context()
            )  # nosec B323 - opt-in esplicito
        self.request_timeout = request_timeout
        self.max_search_candidates = max_search_candidates

    def list_sources(self) -> list[RegionalSource]:
        return REGIONAL_SOURCES

    def get_source(self, key: str) -> RegionalSource:
        for source in REGIONAL_SOURCES:
            if source.key == key:
                return source
        raise KeyError(key)

    def get_portal_url(self, key: str) -> str:
        source = self.get_source(key)
        if source.search_urls:
            return source.search_urls[0]
        return self._search_candidates(source)[0]

    def download_latest(
        self, key: str, download_root: str, progress_callback=None
    ) -> dict[str, str | bool]:
        source = self.get_source(key)
        self._emit_progress(
            progress_callback,
            0,
            0,
            f"Ricerca del prezziario ufficiale per {source.name}...",
        )
        page_url, page_html = self._resolve_source_page(source)
        file_url = self._best_download_link(page_html, page_url, source)
        if not file_url and self._looks_like_download(page_url):
            file_url = page_url

        if not file_url:
            raise RegionalSourceError(
                "Nessun file prezziario individuato automaticamente sul "
                "portale ufficiale. "
                "Usa il link ufficiale aperto dal plugin oppure registra un "
                "link manuale."
            )

        self._emit_progress(
            progress_callback, 0, 0, "Download del file ufficiale in corso..."
        )
        file_path = self._download_file(
            file_url,
            Path(download_root) / source.key,
            progress_callback=progress_callback,
        )
        extension = Path(file_path).suffix.lower()
        return {
            "source_name": source.name,
            "page_url": page_url,
            "file_url": file_url,
            "file_path": file_path,
            "file_extension": extension,
            "importable": extension in IMPORTABLE_EXTENSIONS,
        }

    def _emit_progress(
        self, progress_callback, downloaded: int, total: int, message: str
    ):
        if progress_callback:
            progress_callback(downloaded, total, message)

    def _search_candidates(self, source: RegionalSource) -> list[str]:
        if source.search_urls:
            return source.search_urls

        candidates: list[str] = []
        base = source.homepage.rstrip("/")
        for term in SEARCH_TERMS:
            encoded = quote_plus(term)
            candidates.extend(
                [
                    f"{base}/?s={encoded}",
                    f"{base}/search/{encoded}/",
                    f"{base}/ricerca?query={encoded}",
                    f"{base}/cerca?query={encoded}",
                    f"{base}/ricerca?search={encoded}",
                    f"{base}/search?q={encoded}",
                ]
            )
        candidates.append(base)
        if self.max_search_candidates is not None:
            return candidates[: self.max_search_candidates]
        return candidates

    def _fetch_text(self, url: str) -> str:
        request = Request(
            _ensure_http_url(url),
            headers={"User-Agent": "ComputoMetricoGIS/0.2"},
        )
        with urlopen(  # nosec B310 - schema validato sopra
            request, timeout=self.request_timeout, context=self._ssl_context
        ) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            payload = response.read()
        if "text/html" not in content_type and "xml" not in content_type:
            return payload.decode("utf-8", errors="ignore")
        return payload.decode("utf-8", errors="ignore")

    def _extract_links(
        self, html: str, base_url: str
    ) -> list[tuple[str, str]]:
        parser = _AnchorCollector()
        parser.feed(html)
        links: list[tuple[str, str]] = []
        for href, text in parser.links:
            absolute = urljoin(base_url, href)
            links.append((absolute, text))
        return links

    def _score_page_link(
        self, url: str, text: str, source: RegionalSource
    ) -> tuple[int, int, int]:
        haystack = f"{url} {text}".lower()
        keyword_hits = sum(1 for keyword in KEYWORDS if keyword in haystack)
        domain_bonus = 1 if _domain(url) == _domain(source.homepage) else 0
        year = _extract_year(haystack)
        return (domain_bonus, keyword_hits, year)

    def _resolve_source_page(self, source: RegionalSource) -> tuple[str, str]:
        best_page: tuple[tuple[int, int, int], str, str] | None = None
        best_direct_file: tuple[tuple[int, int, int], str, str] | None = None

        for candidate_url in self._search_candidates(source):
            try:
                html = self._fetch_text(candidate_url)
            except Exception:
                continue

            links = self._extract_links(html, candidate_url)
            for url, text in links:
                score = self._score_page_link(url, text, source)
                if score[1] <= 0 and _domain(url) != _domain(source.homepage):
                    continue
                if self._looks_like_download(url):
                    if best_direct_file is None or score > best_direct_file[0]:
                        best_direct_file = (score, url, html)
                    continue
                if best_page is None or score > best_page[0]:
                    best_page = (score, url, html)

            if best_direct_file:
                return best_direct_file[1], best_direct_file[2]

        if best_page:
            page_url = best_page[1]
            page_html = self._fetch_text(page_url)
            return page_url, page_html

        raise RegionalSourceError(
            f"Impossibile individuare automaticamente la pagina del "
            f"prezziario per {source.name}."
        )

    def _best_download_link(
        self, html: str, base_url: str, source: RegionalSource
    ) -> str:
        best: tuple[tuple[int, int, int, int], str] | None = None
        for url, text in self._extract_links(html, base_url):
            if not self._looks_like_download(url):
                continue
            domain_bonus = 1 if _domain(url) == _domain(source.homepage) else 0
            haystack = f"{url} {text}".lower()
            keyword_hits = sum(
                1 for keyword in KEYWORDS if keyword in haystack
            )
            year = _extract_year(haystack)
            extension = Path(urlparse(url).path).suffix.lower()
            extension_bonus = {
                ".csv": 6,
                ".xlsx": 6,
                ".xlsm": 5,
                ".zip": 4,
                ".xml": 3,
                ".xls": 2,
                ".dcf": 2,
                ".pdf": 1,
            }.get(extension, 0)
            score = (domain_bonus, keyword_hits, year, extension_bonus)
            if best is None or score > best[0]:
                best = (score, url)
        return best[1] if best else ""

    def _looks_like_download(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return any(
            path.endswith(extension) for extension in DOWNLOADABLE_EXTENSIONS
        )

    def _download_file(
        self, url: str, output_dir: Path, progress_callback=None
    ) -> str:
        output_dir.mkdir(parents=True, exist_ok=True)
        request = Request(
            _ensure_http_url(url),
            headers={"User-Agent": "ComputoMetricoGIS/0.2"},
        )
        with urlopen(  # nosec B310 - schema validato sopra
            request,
            timeout=max(self.request_timeout, 30),
            context=self._ssl_context,
        ) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            total = int(response.headers.get("Content-Length", "0") or "0")

            file_name = (
                os.path.basename(urlparse(url).path) or "prezzario_scaricato"
            )
            file_name = _sanitize_filename(file_name)
            extension = Path(file_name).suffix.lower()
            if not extension:
                if "sheet" in content_type or "excel" in content_type:
                    extension = ".xlsx"
                elif "csv" in content_type:
                    extension = ".csv"
                elif "pdf" in content_type:
                    extension = ".pdf"
                else:
                    extension = ".bin"
                file_name = f"{file_name}{extension}"

            target = output_dir / file_name
            downloaded = 0
            preview = b""
            with open(target, "wb") as output_handle:
                while True:
                    chunk = response.read(1024 * 128)
                    if not chunk:
                        break
                    if len(preview) < 256:
                        preview += chunk[: 256 - len(preview)]
                    output_handle.write(chunk)
                    downloaded += len(chunk)
                    self._emit_progress(
                        progress_callback,
                        downloaded,
                        total,
                        f"Scaricati {downloaded} "
                        f"byte{f' di {total}' if total else ''}",
                    )

        if preview[:200].lstrip().lower().startswith(
            b"<!doctype html"
        ) or preview[:50].lstrip().lower().startswith(b"<html"):
            if target.exists():
                target.unlink()
            raise RegionalSourceError(
                "L'URL ufficiale ha restituito una pagina HTML invece del "
                "file da scaricare."
            )

        self._emit_progress(
            progress_callback,
            downloaded,
            total or downloaded,
            "Download completato",
        )
        return str(target)
