import os
import re
import requests
from datetime import datetime
from typing import Dict, Any

class PDFDownloader:
    """
    1안(자동 다운로드 모드) 요구사항을 수행하는 클래스.
    확인된 자료의 PDF를 [downloads/YYYY-MM-DD] 하위 일자별 폴더로 저장
    """
    def __init__(self, base_download_dir="downloads"):
        self.base_download_dir = base_download_dir
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def _get_today_dir(self) -> str:
        """오늘 날짜 기준 일자별 저장 폴더 생성 및 경로 반환 (downloads/YYYY-MM-DD)"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        target_dir = os.path.join(self.base_download_dir, today_str)
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def _sanitize_filename(self, filename: str) -> str:
        """파일명에서 윈도우/리눅스 예약 특수문자를 제거합니다."""
        clean_name = re.sub(r'[\\/*?:"<>|]', "", filename)
        clean_name = clean_name.replace(" ", "_")
        return clean_name[:100]  # 길이지한

    def download_file(self, item: Dict[str, Any]) -> str:
        """
        자료 항목(item) 정보를 받아 PDF 파일을 다운로드하고 로컬 경로를 반환합니다.
        다운로드가 불가능하거나 B그룹(게시글 Landing Page)인 경우 다운로드를 건너뛰고 빈 문자열을 반환합니다.
        """
        url = item.get("url", "")
        title = item.get("title", "document")
        publisher = item.get("publisher", "기관")
        group = item.get("group", "GROUP_B")

        # B그룹 페이지는 직접 파일 다운로드가 아닌 게시글 페이지이므로 다운로드 생략
        if group == "GROUP_B" and not url.endswith(".pdf"):
            return ""

        try:
            today_dir = self._get_today_dir()
            safe_title = self._sanitize_filename(f"[{publisher}]_{title}")
            if not safe_title.endswith(".pdf"):
                safe_title += ".pdf"
            
            file_path = os.path.join(today_dir, safe_title)

            # 이미 동일 파일이 존재하면 다운로드 생략
            if os.path.exists(file_path):
                print(f"[Downloader] 이미 저장된 파일: {file_path}")
                return file_path

            resp = requests.get(url, headers=self.headers, timeout=15, stream=True)
            if resp.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                print(f"[Downloader] 파일 자동 저장 완료: {file_path}")
                return file_path
            else:
                print(f"[Downloader] 다운로드 실패 (Status {resp.status_code}): {url}")
                return ""
        except Exception as e:
            print(f"[Downloader] 파일 다운로드 중 오류 ({url}): {e}")
            return ""
