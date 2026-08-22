"""일일 브리핑 HTML 템플릿 (PRD v2.1 §15.2).

모바일에서 가로스크롤 없이 읽을 수 있는 카드형 HTML 을 생성합니다.
"""

from __future__ import annotations

import html
from datetime import date

from ..models import PriorityLevel, Resource, RunReport, SummaryBasis

PRIORITY_COLORS = {
    PriorityLevel.P1: ("#c62828", "#ffebee"),
    PriorityLevel.P2: ("#ef6c00", "#fff3e0"),
    PriorityLevel.P3: ("#1565c0", "#e3f2fd"),
    PriorityLevel.P4: ("#546e7a", "#eceff1"),
}

BASIS_LABELS = {
    SummaryBasis.FULLTEXT: ("원문 전체 분석", "#2e7d32"),
    SummaryBasis.ABSTRACT: ("초록만 분석", "#ef6c00"),
    SummaryBasis.METADATA_ONLY: ("서지정보만 분석", "#757575"),
}


def _esc(value: object) -> str:
    return html.escape(str(value or ""))


def render_email(
    report: RunReport,
    *,
    card_resources: list[Resource],
    listed_resources: list[Resource],
    collected_on: date,
) -> str:
    """일일 브리핑 HTML 본문을 생성합니다."""
    header = _render_header(report, card_resources, collected_on)
    cards = "".join(_render_card(index, r) for index, r in enumerate(card_resources, start=1))
    if not card_resources:
        cards = (
            '<div style="background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;'
            'padding:20px;text-align:center;color:#616161;font-size:14px;">'
            "오늘 새로 확인된 P1·P2 중요 자료가 없습니다.</div>"
        )

    listed = _render_listed(listed_resources)
    errors = _render_errors(report)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DL-RCIS 일일 리서치 브리핑</title>
</head>
<body style="margin:0;padding:12px;background-color:#f4f5f7;
 font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Noto Sans KR',sans-serif;">
<div style="max-width:640px;margin:0 auto;">
{header}
<div style="padding:12px 0;">{cards}</div>
{listed}
{errors}
<div style="font-size:11px;color:#78909c;text-align:center;padding:14px 8px;
 border-top:1px solid #cfd8dc;line-height:1.6;">
  본 브리핑은 공식 API·OAI-PMH·RSS 를 통해 수집한 공개자료를 대상으로 자동 생성되었습니다.<br>
  원문 파일은 첨부하지 않으며 공식 링크를 제공합니다. 라이선스가 불명확한 자료는 내부 열람용으로만 사용하세요.
</div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------

def _render_header(report: RunReport, cards: list[Resource], collected_on: date) -> str:
    p1 = sum(1 for r in cards if r.priority_level == PriorityLevel.P1)
    p2 = sum(1 for r in cards if r.priority_level == PriorityLevel.P2)
    failed = len(report.failed_sources)

    stats = [
        ("신규", report.new_count),
        ("수정", report.updated_count),
        ("P1", p1),
        ("P2", p2),
        ("수집실패", failed),
    ]
    cells = "".join(
        f'<td style="padding:6px 4px;text-align:center;">'
        f'<div style="font-size:19px;font-weight:700;color:#ffffff;">{value}</div>'
        f'<div style="font-size:11px;color:#e3f2fd;">{_esc(label)}</div></td>'
        for label, value in stats
    )
    return f"""<div style="background:#1a73e8;border-radius:10px 10px 0 0;padding:16px 14px 12px;">
  <div style="font-size:17px;font-weight:700;color:#ffffff;">📚 DL-RCIS 일일 리서치 브리핑</div>
  <div style="font-size:12px;color:#e3f2fd;margin-top:3px;">
    수집일 {_esc(collected_on.isoformat())} · 실행유형 {_esc(report.run_type.value)}
    · 검색어사전 {_esc(report.dictionary_version)}
  </div>
  <table style="width:100%;margin-top:10px;border-collapse:collapse;"><tr>{cells}</tr></table>
</div>"""


def _render_card(index: int, resource: Resource) -> str:
    color, bg = PRIORITY_COLORS.get(resource.priority_level, PRIORITY_COLORS[PriorityLevel.P4])
    basis_label, basis_color = BASIS_LABELS.get(
        resource.summary_basis, BASIS_LABELS[SummaryBasis.METADATA_ONLY]
    )

    title_ko = resource.title_ko or resource.title_original
    original_line = ""
    if resource.title_original and resource.title_original != title_ko:
        original_line = (
            f'<div style="font-size:12px;color:#78909c;margin-top:2px;">'
            f"{_esc(resource.title_original)}</div>"
        )

    meta_bits = [
        resource.publisher or resource.source_id,
        ", ".join(resource.authors[:3]) if resource.authors else "",
        resource.publication_date.isoformat() if resource.publication_date else "발행일 미상",
    ]
    meta = " · ".join(_esc(b) for b in meta_bits if b)

    summary_lines = _summary_lines(resource)
    summary_html = "".join(
        f'<li style="margin-bottom:3px;">{_esc(line)}</li>' for line in summary_lines
    )

    education = _section_of(resource.summary_ko, "법무교육 활용 포인트")
    education_html = ""
    if education:
        education_html = (
            f'<div style="margin-top:8px;padding:8px 10px;background:#f1f8e9;border-radius:6px;'
            f'font-size:12.5px;color:#33691e;line-height:1.6;">'
            f"<strong>🎓 교육 활용</strong><br>{_esc(education)}</div>"
        )

    links = [_link("원문보기", resource.canonical_url())]
    if resource.file_path:
        links.append(
            f'<span style="font-size:12px;color:#2e7d32;">💾 저장: '
            f'{_esc(_shorten_path(resource.file_path))}</span>'
        )
    if resource.doi:
        links.append(_link("DOI", f"https://doi.org/{resource.doi}"))
    links_html = " · ".join(links)

    license_note = ""
    if resource.license_unknown:
        license_note = (
            '<div style="font-size:11.5px;color:#b71c1c;margin-top:6px;">'
            "⚠ 라이선스 불명확 — 외부 재배포 금지, 내부 열람용</div>"
        )

    return f"""<div style="background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;
 padding:14px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
  <div style="margin-bottom:6px;">
    <span style="display:inline-block;background:{bg};color:{color};font-size:11px;font-weight:700;
     padding:2px 8px;border-radius:10px;">{_esc(resource.priority_level.value)} · {resource.relevance_score}점</span>
    <span style="display:inline-block;background:#eceff1;color:#455a64;font-size:11px;
     padding:2px 8px;border-radius:10px;margin-left:4px;">{_esc(resource.topic_primary)}</span>
    <span style="display:inline-block;color:{basis_color};font-size:11px;margin-left:4px;">● {_esc(basis_label)}</span>
  </div>
  <div style="font-size:15.5px;font-weight:700;color:#1a237e;line-height:1.45;">
    {index}. {_esc(title_ko)}
  </div>
  {original_line}
  <div style="font-size:12.5px;color:#546e7a;margin-top:5px;">{meta}</div>
  <ul style="margin:8px 0 0;padding-left:18px;font-size:13px;color:#37474f;line-height:1.65;">
    {summary_html}
  </ul>
  {education_html}
  <div style="margin-top:9px;font-size:12.5px;">{links_html}</div>
  {license_note}
</div>"""


def _render_listed(resources: list[Resource]) -> str:
    """P3 이하 — 본문 카드 대신 목록 링크로 제공 (§15.3)."""
    if not resources:
        return ""
    items = "".join(
        f'<li style="margin-bottom:4px;line-height:1.5;">'
        f'<a href="{_esc(r.canonical_url())}" style="color:#1565c0;text-decoration:none;">'
        f"{_esc(r.best_title()[:90])}</a>"
        f'<span style="color:#90a4ae;font-size:11px;"> · {_esc(r.source_id)} · '
        f"{_esc(r.priority_level.value)}</span></li>"
        for r in resources[:40]
    )
    more = (
        f'<div style="font-size:11.5px;color:#90a4ae;margin-top:6px;">'
        f"…외 {len(resources) - 40}건은 첨부 Excel 을 확인하세요.</div>"
        if len(resources) > 40
        else ""
    )
    return f"""<div style="background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;
 padding:14px;margin-bottom:12px;">
  <div style="font-size:14px;font-weight:700;color:#37474f;margin-bottom:8px;">
    📋 참고 목록 (P3 이하 {len(resources)}건)
  </div>
  <ul style="margin:0;padding-left:18px;font-size:12.5px;">{items}</ul>
  {more}
</div>"""


def _render_errors(report: RunReport) -> str:
    """수집 실패 소스 경고 섹션 (§15.3)."""
    failed = report.failed_sources
    if not failed:
        return ""
    items = "".join(
        f'<li style="margin-bottom:4px;line-height:1.55;"><strong>{_esc(s.source_name or s.source_id)}</strong> '
        f'<span style="color:#b71c1c;">[{_esc(s.error_code)}]</span><br>'
        f'<span style="color:#5d4037;font-size:12px;">{_esc(s.error_message[:220])}</span></li>'
        for s in failed
    )
    return f"""<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;
 padding:14px;margin-bottom:12px;">
  <div style="font-size:14px;font-weight:700;color:#e65100;margin-bottom:8px;">
    ⚠ 수집 실패·건너뛴 소스 ({len(failed)}건)
  </div>
  <ul style="margin:0;padding-left:18px;font-size:12.5px;color:#4e342e;">{items}</ul>
</div>"""


# ---------------------------------------------------------------------------

def _summary_lines(resource: Resource, limit: int = 3) -> list[str]:
    """요약 본문에서 3줄을 뽑습니다."""
    if not resource.summary_ko:
        return [resource.abstract_original[:150] or "요약이 생성되지 않았습니다."]

    lines: list[str] = []
    for raw in resource.summary_ko.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("**한줄 핵심**"):
            lines.append(line.replace("**한줄 핵심**:", "").strip())
        elif line.startswith("- ") and len(lines) < limit:
            lines.append(line[2:].strip())
        if len(lines) >= limit:
            break
    return lines or [resource.summary_ko[:150]]


def _section_of(summary: str, heading: str) -> str:
    """요약 마크다운에서 특정 섹션의 첫 항목을 뽑습니다."""
    if not summary or heading not in summary:
        return ""
    after = summary.split(f"**{heading}**", 1)[1]
    for raw in after.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            return line[2:].strip()
        if line.startswith(":"):
            return line.lstrip(":").strip()
        if line and not line.startswith("**"):
            return line
    return ""


def _link(label: str, url: str) -> str:
    if not url:
        return ""
    return (
        f'<a href="{_esc(url)}" style="color:#1a73e8;font-weight:600;text-decoration:none;">'
        f"{_esc(label)} ›</a>"
    )


def _shorten_path(path: str, limit: int = 46) -> str:
    from pathlib import Path

    name = Path(path).name
    return name if len(name) <= limit else name[: limit - 1] + "…"


def render_text_fallback(report: RunReport, resources: list[Resource]) -> str:
    """HTML 을 표시하지 못하는 클라이언트용 평문 본문."""
    lines = [
        "DL-RCIS 일일 리서치 브리핑",
        f"신규 {report.new_count}건 / 수정 {report.updated_count}건 / 실패 소스 {len(report.failed_sources)}개",
        "",
    ]
    for index, r in enumerate(resources, start=1):
        lines.append(f"{index}. [{r.priority_level.value}] {r.best_title()}")
        lines.append(f"   출처: {r.publisher or r.source_id} · 주제: {r.topic_primary}")
        lines.append(f"   링크: {r.canonical_url()}")
        lines.append(f"   요약근거: {r.summary_basis.value}")
        lines.append("")
    return "\n".join(lines)
