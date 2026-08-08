import requests
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from typing import Tuple, Dict, Any

class LinkValidator:
    """
    지침 제5항(링크 유효성 검증)에 따라 수집 대상 URL에 대해
    1. 접속 확인, 2. 자료 일치 확인, 3. 무료 다운로드 확인의 3단계 검증을 수행하고
    날짜 필터링(최초: 2026.1.1~2026.7.31, 정기: 최근 1개월 이내)을 적용하는 클래스
    """
    def __init__(self, group_a_domains: list, group_b_domains: list):
        self.group_a_domains = group_a_domains
        self.group_b_domains = group_b_domains
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def is_invalid_session_link(self, url: str) -> bool:
        """세션 ID(jsessionid)나 일회성 파라미터 링크 포함 여부 검사"""
        url_lower = url.lower()
        invalid_keywords = ["jsessionid", "download.do?file", "tempfile", "sessionid", "token="]
        for kw in invalid_keywords:
            if kw in url_lower:
                return True
        return False

    def classify_access_group(self, url: str, content_type: str) -> str:
        """A그룹(영구 직접 PDF)과 B그룹(게시글 Landing Page) 분류"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if self.is_invalid_session_link(url):
            return "GROUP_B"

        for a_domain in self.group_a_domains:
            if a_domain in domain or "arxiv.org/pdf" in url or "doi.org" in url:
                return "GROUP_A"

        if "application/pdf" in content_type.lower():
            return "GROUP_A"

        return "GROUP_B"

    def is_date_within_range(self, date_str: str, is_first_run: bool) -> bool:
        """
        문서 및 페이지에서 추출된 발간/등록 날짜가 조건 범위 내인지 검증
        - 최초 실행 시: 2026.01.01 ~ 2026.07.31
        - 2회차 이후 시: 실행 시점 기준 1개월(30일) 이내
        """
        if not date_str:
            return True  # 날짜 확인 불가능 시 제외하지 않고 우선 통과 처리

        try:
            # 2026-05-12, 2026.05.12 등 연-월-일 파싱
            date_match = re.search(r'(202[0-6])[-.\s/]?([0-1]?[0-9])[-.\s/]?([0-3]?[0-9])?', date_str)
            if not date_match:
                return True

            year = int(date_match.group(1))
            month = int(date_match.group(2)) if date_match.group(2) else 1
            day = int(date_match.group(3)) if date_match.group(3) else 1

            doc_date = datetime(year, month, day)

            if is_first_run:
                # 2026.01.01 ~ 2026.07.31 범위 확인
                start_date = datetime(2026, 1, 1)
                end_date = datetime(2026, 7, 31)
                return start_date <= doc_date <= end_date
            else:
                # 최근 1개월(30일) 이내 확인
                one_month_ago = datetime.now() - timedelta(days=30)
                return doc_date >= one_month_ago
        except Exception:
            return True

    def validate_link(self, url: str, target_keyword: str, is_first_run: bool = False) -> Tuple[bool, Dict[str, Any]]:
        """
        3단계 실제 접속 검증 및 날짜 필터링 수행
        """
        result_info = {
            "valid": False,
            "group": "GROUP_B",
            "reason": "",
            "content_type": "",
            "title": "",
            "year_month": datetime.now().strftime("%Y-%m"),
            "url": url
        }

        if not url or not url.startswith(("http://", "https://")):
            result_info["reason"] = "유효하지 않은 URL 형식"
            return False, result_info

        try:
            resp = requests.get(url, headers=self.headers, timeout=10, allow_redirects=True)
            if resp.status_code != 200:
                result_info["reason"] = f"HTTP 응답 에러 (Status: {resp.status_code})"
                return False, result_info

            content_type = resp.headers.get('Content-Type', '')
            result_info["content_type"] = content_type

            if "application/pdf" in content_type.lower() or url.endswith('.pdf'):
                result_info["title"] = url.split('/')[-1]
                result_info["group"] = "GROUP_A"
            else:
                soup = BeautifulSoup(resp.text, 'html.parser')
                title_tag = soup.find('title')
                result_info["title"] = title_tag.get_text().strip() if title_tag else "제목 미상"

                page_text = resp.text.lower()
                paywall_keywords = ["로그인이 필요합니다", "유료 결제", "구독 신청", "login required"]
                for p_kw in paywall_keywords:
                    if p_kw in page_text:
                        result_info["reason"] = "로그인 또는 결제가 필요한 유료 자료"
                        return False, result_info

                # 본문 내 날짜 추출 및 기간 검증
                date_match = re.search(r'(2026[-.\s/][0-1]?[0-9](?:[-.\s/][0-3]?[0-9])?)', resp.text)
                found_date = date_match.group(1) if date_match else ""
                
                if found_date:
                    ym = found_date[:7].replace(".", "-").replace("/", "-")
                    result_info["year_month"] = ym
                    if not self.is_date_within_range(found_date, is_first_run):
                        result_info["reason"] = f"지정된 발간 기간 제외 대상 ({found_date})"
                        return False, result_info

            result_info["group"] = self.classify_access_group(url, content_type)
            result_info["valid"] = True
            return True, result_info

        except Exception as e:
            result_info["reason"] = f"접속 실패 또는 네트워크 오류: {str(e)}"
            return False, result_info
