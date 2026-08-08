from typing import List, Dict, Any

class QueryBuilder:
    """
    지침에 규정된 학술, 사법, 국방, 작전법 및 분야별 필수 기관에 대해
    키워드 검색에 의존하지 않고 지정된 기간 내 발간/업로드된 전체 자료(filetype:pdf, hwp)를
    전수 탐색할 수 있는 쿼리를 자동 생성하는 클래스
    """
    def __init__(self, essential_institutions: dict):
        self.essential_institutions = essential_institutions
        self.filetypes = ["pdf", "hwp", "hwpx", "docx"]

    def build_institution_all_queries(self) -> List[Dict[str, str]]:
        """
        config.yaml에 정의된 모든 필수 검색 기관의 도메인을 기반으로
        기간 내 전수 첨부파일 수집 쿼리 목록을 생성합니다.
        """
        queries = []
        collected_domains = set()

        # 1. 학술, 사법, 국방, 확장 분야 필수 기관 도메인 수집
        for category, inst_list in self.essential_institutions.items():
            for inst in inst_list:
                domain = inst.get("domain", "")
                name = inst.get("name", "")
                if domain and domain not in collected_domains:
                    collected_domains.add(domain)

                    # 각 기관별 전수 PDF/HWP 첨부파일 탐색 쿼리 생성
                    queries.append({
                        "query": f"site:{domain} filetype:pdf OR filetype:hwp OR filetype:hwpx",
                        "institution_name": name,
                        "target_domain": domain
                    })

        # 2. 해외 및 주요 오픈액세스 전수 탐색 쿼리 (arXiv, SSRN, CLAMO 등)
        queries.append({
            "query": "site:arxiv.org filetype:pdf",
            "institution_name": "arXiv Open Access",
            "target_domain": "arxiv.org"
        })
        queries.append({
            "query": "site:tjaglcs.army.mil filetype:pdf",
            "institution_name": "미 육군 작전법센터 (CLAMO)",
            "target_domain": "tjaglcs.army.mil"
        })

        return queries
