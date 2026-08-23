"""Source Connector 레지스트리.

`sources.yaml` 의 `connector` 값으로 구현체를 찾습니다.
새 소스를 추가할 때는 이 표에만 등록하면 파이프라인이 자동으로 인식합니다.
"""

from __future__ import annotations

from ..models import SourceConfig
from .arxiv import ArxivConnector
from .assembly_open import AssemblyOpenConnector
from .base import (
    ConnectorContext,
    ConnectorError,
    CredentialMissingError,
    EndpointNotConfiguredError,
    PassiveConnector,
    SourceConnector,
)
from .core import CoreConnector
from .crossref import CrossrefConnector, CrossrefResolver
from .doaj import DoajConnector
from .generic_api import GenericApiConnector
from .institution_feed import InstitutionFeedConnector
from .kci import KciConnector
from .kknowledge import KKnowledgeConnector
from .law_openapi import LawOpenApiConnector
from .nars import NarsConnector
from .nkis import NkisConnector
from .openalex import OpenAlexConnector
from .prism import PrismConnector
from .riss import RissConnector
from .scienceon import ScienceOnConnector
from .semantic_scholar import SemanticScholarConnector
from .ssrn import SsrnConnector
from .unpaywall import UnpaywallConnector
from .zenodo import ZenodoConnector

CONNECTOR_REGISTRY: dict[str, type[SourceConnector]] = {
    "kci": KciConnector,
    "riss": RissConnector,
    "scienceon": ScienceOnConnector,
    "nars": NarsConnector,
    "assembly_open": AssemblyOpenConnector,
    "nkis": NkisConnector,
    "kknowledge": KKnowledgeConnector,
    "prism": PrismConnector,
    "law_openapi": LawOpenApiConnector,
    "institution_feed": InstitutionFeedConnector,
    "crossref": CrossrefConnector,
    "openalex": OpenAlexConnector,
    "semantic_scholar": SemanticScholarConnector,
    "core": CoreConnector,
    "unpaywall": UnpaywallConnector,
    "doaj": DoajConnector,
    "arxiv": ArxivConnector,
    "ssrn": SsrnConnector,
    "zenodo": ZenodoConnector,
}


class UnknownConnectorError(ConnectorError):
    def __init__(self, connector_id: str, source_id: str):
        super().__init__(
            f"알 수 없는 connector '{connector_id}' (source_id={source_id}). "
            f"src/connectors/__init__.py 의 CONNECTOR_REGISTRY 에 등록하세요."
        )


def build_connector(config: SourceConfig, ctx: ConnectorContext) -> SourceConnector:
    """소스 설정에 맞는 Connector 인스턴스를 만듭니다."""
    cls = CONNECTOR_REGISTRY.get(config.connector)
    if cls is None:
        raise UnknownConnectorError(config.connector, config.source_id)
    return cls(config, ctx)


__all__ = [
    "CONNECTOR_REGISTRY",
    "ConnectorContext",
    "ConnectorError",
    "CredentialMissingError",
    "CrossrefResolver",
    "EndpointNotConfiguredError",
    "GenericApiConnector",
    "PassiveConnector",
    "SourceConnector",
    "UnknownConnectorError",
    "build_connector",
]
