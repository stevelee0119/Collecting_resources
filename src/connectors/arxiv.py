"""arXiv Connector (PRD v2.1 §4.4 G).

공식 Atom API 를 사용합니다. arXiv 이용약관상 요청 간격을 지켜야 하므로
`rate_limit_rps` 를 낮게 유지합니다 (기본 0.33 = 약 3초 간격).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from datetime import date

from ..models import CandidateKind, DownloadCandidate, Query, RawItem, Resource
from ..normalizers.normalize import (
    build_work_id,
    clean_whitespace,
    normalize_doi,
    parse_date,
)
from ..http_client import describe_http_error
from .base import SourceConnector

logger = logging.getLogger(__name__)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivConnector(SourceConnector):
    connector_id = "arxiv"

    MAX_RESULTS = 50

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        categories = list(getattr(self.config, "arxiv_categories", []) or [])
        cat_filter = " OR ".join(f"cat:{c}" for c in categories)
        seen: set[str] = set()
        emitted = 0

        for query in queries:
            if emitted >= self._limit():
                return
            search = f"all:({query.query_string})"
            if cat_filter:
                search = f"({search}) AND ({cat_filter})"

            params = {
                "search_query": search,
                "start": 0,
                "max_results": self.MAX_RESULTS,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            try:
                response = self.ctx.client.get(method.endpoint, params=params)
                response.raise_for_status()
                root = ET.fromstring(response.content)
            except Exception as exc:
                logger.warning(
                    "[arxiv] 질의 실패: %s (질의: %.40s)",
                    describe_http_error(exc), query.query_string,
                )
                continue

            for entry in root.findall("atom:entry", ATOM_NS):
                payload = _entry_to_dict(entry)
                entry_id = payload.get("id", "")
                if not entry_id or entry_id in seen:
                    continue

                # API 가 날짜 필터를 직접 지원하지 않으므로 클라이언트에서 기간을 적용합니다.
                published = parse_date(payload.get("published"))
                updated = parse_date(payload.get("updated"))
                newest = max(filter(None, [published, updated]), default=None)
                if newest and not (since <= newest <= until):
                    continue

                seen.add(entry_id)
                yield RawItem(
                    source_id=self.config.source_id, payload=payload, discovered_by_query=query
                )
                emitted += 1
                if emitted >= self._limit():
                    return

    def normalize(self, raw: RawItem) -> Resource | None:
        payload = raw.payload
        title = clean_whitespace(payload.get("title"))
        if not title:
            return None

        entry_id = clean_whitespace(payload.get("id"))
        arxiv_id = entry_id.rsplit("/", 1)[-1] if entry_id else ""
        pdf_url = clean_whitespace(payload.get("pdf_url")) or (
            entry_id.replace("/abs/", "/pdf/") if entry_id else ""
        )

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(
                doi=normalize_doi(payload.get("doi")), identifier=f"arxiv:{arxiv_id}"
            ),
            title_original=title,
            authors=payload.get("authors", []),
            publisher="arXiv",
            journal_or_series=clean_whitespace(payload.get("journal_ref")) or "arXiv preprint",
            publication_date=parse_date(payload.get("published")),
            source_registered_date=parse_date(payload.get("published")),
            source_modified_date=parse_date(payload.get("updated")),
            discovered_at=self._now(),
            doi=normalize_doi(payload.get("doi")),
            official_identifier=f"arxiv:{arxiv_id}",
            landing_url=entry_id,
            download_url=pdf_url,
            oa_url=pdf_url,
            license=clean_whitespace(payload.get("license")) or "arXiv 공개 라이선스",
            # arXiv 는 공개 원문을 제공하는 저장소이므로 OA 로 취급합니다.
            license_unknown=False,
            language="en",
            document_type="프리프린트",
            keywords=payload.get("categories", []),
            abstract_original=clean_whitespace(payload.get("summary")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )

    def resolve_download(self, metadata: Resource) -> DownloadCandidate | None:
        url = metadata.download_url or metadata.oa_url
        if not url:
            return None
        return DownloadCandidate(
            url=url,
            kind=CandidateKind.DIRECT_FILE,
            source_id=self.config.source_id,
            license=metadata.license,
            is_open_access=True,
            origin="connector:arxiv",
        )


def _entry_to_dict(entry: ET.Element) -> dict:
    def text(path: str) -> str:
        node = entry.find(path, ATOM_NS)
        return clean_whitespace(node.text) if node is not None and node.text else ""

    authors = [
        clean_whitespace(node.text)
        for node in entry.findall("atom:author/atom:name", ATOM_NS)
        if node.text
    ]
    categories = [
        c.attrib.get("term", "") for c in entry.findall("atom:category", ATOM_NS) if c.attrib.get("term")
    ]
    pdf_url = ""
    for link in entry.findall("atom:link", ATOM_NS):
        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
            pdf_url = link.attrib.get("href", "")
            break

    return {
        "id": text("atom:id"),
        "title": text("atom:title"),
        "summary": text("atom:summary"),
        "published": text("atom:published"),
        "updated": text("atom:updated"),
        "doi": text("arxiv:doi"),
        "journal_ref": text("arxiv:journal_ref"),
        "authors": authors,
        "categories": categories,
        "pdf_url": pdf_url,
    }
