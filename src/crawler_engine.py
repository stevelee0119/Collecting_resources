import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from bs4 import BeautifulSoup
from typing import List, Dict, Any

class ResearchCrawlerEngine:
    """
    학술, 사법, 국방, 작전법 필수 수집 기관 및 오픈액세스 저장소에서
    설정된 기간 내 업로드된 전체 자료/첨부파일을 수집하는 탐색 크롤러 엔진
    """
    def __init__(self, validator, database):
        self.validator = validator
        self.db = database
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def fetch_institution_documents(self, query_item: dict, is_first_run: bool, max_results: int = 15) -> List[Dict[str, Any]]:
        """
        특정 기관 쿼리에 대해 지정된 기간 내 업로드된 첨부파일 전체를 탐색하고 3단계 검증을 진행합니다.
        """
        results = []
        query_str = query_item["query"]
        inst_name = query_item["institution_name"]

        try:
            url = f"https://html.duckduckgo.com/html/?q={quote(query_str)}"
            resp = requests.post(url, data={'q': query_str}, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                links = soup.find_all('a', class_='result__url', limit=max_results)
                titles = soup.find_all('a', class_='result__title', limit=max_results)

                for i in range(min(len(links), len(titles))):
                    raw_url = links[i].get('href', '').strip()
                    if raw_url.startswith('//'):
                        raw_url = 'https:' + raw_url
                    
                    # 1. 이미 다운로드/수집된 자료 중복 체크
                    if self.db.is_already_collected(raw_url):
                        print(f"[CrawlerEngine] 이미 수집된 파일 건너뜀 ({inst_name}): {raw_url}")
                        continue

                    title = titles[i].get_text().strip()
                    
                    # 2. 3단계 유효성 검증 및 지정 발간 기간(최초: 2026.1.1~2026.7.31 / 이후: 최근 1개월) 검증
                    valid, v_info = self.validator.validate_link(raw_url, inst_name, is_first_run)
                    if valid:
                        access_type = "게시글 이동 후 다운로드" if v_info["group"] == "GROUP_B" else "직접 PDF 다운로드"
                        remarks = f"필수 수집 기관({inst_name}) / 무료 다운로드 검증 완료"

                        results.append({
                            "title": v_info["title"] if v_info["title"] else title,
                            "year": v_info["year_month"][:4],
                            "year_month": v_info["year_month"],
                            "publisher": inst_name,
                            "url": raw_url,
                            "group": v_info["group"],
                            "access_type": access_type,
                            "remarks": remarks
                        })
        except Exception as e:
            print(f"[CrawlerEngine] {inst_name} 기관 자료 탐색 중 오류 ({query_str}): {e}")
        return results

    def fetch_arxiv_documents(self, is_first_run: bool, max_results: int = 10) -> List[Dict[str, Any]]:
        """arXiv 최신 학술 논문 기간 내 전수 탐색"""
        results = []
        try:
            url = f"http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                
                for entry in root.findall('atom:entry', ns):
                    title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
                    published_raw = entry.find('atom:published', ns).text
                    pub_year = published_raw[:4]
                    year_month = published_raw[:7]
                    
                    pdf_url = ""
                    for link in entry.findall('atom:link', ns):
                        if link.attrib.get('title') == 'pdf':
                            pdf_url = link.attrib.get('href')
                            break
                    if not pdf_url:
                        id_url = entry.find('atom:id', ns).text
                        pdf_url = id_url.replace('/abs/', '/pdf/') + ".pdf"

                    if self.db.is_already_collected(pdf_url):
                        continue

                    valid, v_info = self.validator.validate_link(pdf_url, "arXiv", is_first_run)
                    if valid:
                        results.append({
                            "title": title,
                            "year": pub_year,
                            "year_month": year_month,
                            "publisher": "arXiv 오픈액세스",
                            "url": pdf_url,
                            "group": "GROUP_A",
                            "access_type": "직접 PDF 다운로드 (영구 링크)",
                            "remarks": "A그룹 저장소 — 직링크 제공 / 무료 다운로드 검증 완료"
                        })
        except Exception as e:
            print(f"[CrawlerEngine] arXiv 수집 중 오류: {e}")
        return results

    def crawl_all_institutions(self, institution_queries: list, is_first_run: bool) -> List[Dict[str, Any]]:
        """모든 필수 기관 전수 탐색 수집 프로세스 실행"""
        all_results = []

        # 1. 기관별 전수 탐색 수행
        for q_item in institution_queries:
            print(f"[CRAWL] 필수 기관 탐색 중: {q_item['institution_name']} ({q_item['target_domain']})")
            inst_items = self.fetch_institution_documents(q_item, is_first_run, max_results=10)
            all_results.extend(inst_items)

        # 2. arXiv 전수 탐색 수행
        arxiv_items = self.fetch_arxiv_documents(is_first_run, max_results=5)
        all_results.extend(arxiv_items)

        return all_results
