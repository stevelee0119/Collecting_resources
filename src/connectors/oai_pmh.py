"""OAI-PMH 클라이언트 (PRD v2.1 §4.1 우선순위 2).

`ListRecords` 를 datestamp 기반으로 순회하며 resumptionToken 을 따라갑니다.
Dublin Core(oai_dc) 레코드를 표준 dict 로 변환합니다.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import date
from typing import Any

from ..http_client import PoliteClient

logger = logging.getLogger(__name__)

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}

DC_FIELDS = (
    "title",
    "creator",
    "subject",
    "description",
    "publisher",
    "contributor",
    "date",
    "type",
    "format",
    "identifier",
    "source",
    "language",
    "relation",
    "coverage",
    "rights",
)


class OaiPmhError(RuntimeError):
    """OAI-PMH 프로토콜 오류."""


class OaiPmhClient:
    """최소 기능의 OAI-PMH 하베스터."""

    def __init__(self, client: PoliteClient, endpoint: str, metadata_prefix: str = "oai_dc"):
        self.client = client
        self.endpoint = endpoint
        self.metadata_prefix = metadata_prefix

    def list_records(
        self,
        *,
        since: date,
        until: date,
        set_spec: str | None = None,
        max_records: int = 500,
    ) -> Iterator[dict[str, Any]]:
        """기간 내 레코드를 순회합니다."""
        params: dict[str, str] = {
            "verb": "ListRecords",
            "metadataPrefix": self.metadata_prefix,
            "from": since.isoformat(),
            "until": until.isoformat(),
        }
        if set_spec:
            params["set"] = set_spec

        harvested = 0
        while True:
            try:
                response = self.client.get(self.endpoint, params=params)
                response.raise_for_status()
                root = ET.fromstring(response.content)
            except ET.ParseError as exc:
                raise OaiPmhError(f"OAI-PMH 응답 파싱 실패: {exc}") from exc

            error = root.find("oai:error", NS)
            if error is not None:
                code = error.attrib.get("code", "")
                # 해당 기간에 레코드가 없는 것은 정상 상황입니다.
                if code == "noRecordsMatch":
                    return
                raise OaiPmhError(f"OAI-PMH 오류 [{code}]: {(error.text or '').strip()}")

            for record in root.findall(".//oai:record", NS):
                parsed = self._parse_record(record)
                if parsed is None:
                    continue
                yield parsed
                harvested += 1
                if harvested >= max_records:
                    return

            token_node = root.find(".//oai:resumptionToken", NS)
            token = (token_node.text or "").strip() if token_node is not None else ""
            if not token:
                return
            params = {"verb": "ListRecords", "resumptionToken": token}

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_record(record: ET.Element) -> dict[str, Any] | None:
        header = record.find("oai:header", NS)
        if header is None:
            return None
        # 삭제된 레코드는 건너뜁니다.
        if header.attrib.get("status") == "deleted":
            return None

        identifier_node = header.find("oai:identifier", NS)
        datestamp_node = header.find("oai:datestamp", NS)

        payload: dict[str, Any] = {
            "oai_identifier": (identifier_node.text or "").strip() if identifier_node is not None else "",
            "datestamp": (datestamp_node.text or "").strip() if datestamp_node is not None else "",
            "setSpec": [
                (s.text or "").strip() for s in header.findall("oai:setSpec", NS) if s.text
            ],
        }

        metadata = record.find("oai:metadata", NS)
        if metadata is None:
            return payload

        for field in DC_FIELDS:
            values = [
                (node.text or "").strip()
                for node in metadata.findall(f".//dc:{field}", NS)
                if node is not None and node.text
            ]
            if values:
                payload[field] = values
        return payload
