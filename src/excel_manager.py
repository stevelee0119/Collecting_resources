import os
import csv
import pandas as pd
from openpyxl import Workbook, load_workbook
from datetime import datetime
from typing import List, Dict, Any

class ResourceListManager:
    """
    다운로드한 자료의 목록을 list_download_resources.csv 및
    통합시트와 월별 시트로 구성된 list_download_resources.xlsx 파일로 관리하는 클래스
    """
    def __init__(self, csv_path="list_download_resources.csv", excel_path="list_download_resources.xlsx"):
        self.csv_path = csv_path
        self.excel_path = excel_path
        self.headers = ["수집일자", "발간연월", "발행기관", "자료제목", "원문유형", "출처URL", "저장경로", "비고"]
        self._init_csv()

    def _init_csv(self):
        """CSV 파일이 존재하지 않는 경우 헤더 작성"""
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, mode='w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)

    def save_resources(self, items: List[Dict[str, Any]]):
        """
        다운로드된 리소스 항목들을 CSV에 추가하고 엑셀 통합/월별 시트를 업데이트합니다.
        """
        if not items:
            return

        today_str = datetime.now().strftime("%Y-%m-%d")

        # 1. CSV 파일에 기록 추가 (UTF-8-SIG 인코딩)
        rows_to_add = []
        for item in items:
            year_month = item.get("year_month", datetime.now().strftime("%Y-%m"))
            row = [
                today_str,
                year_month,
                item.get("publisher", "기관미상"),
                item.get("title", "제목없음"),
                item.get("access_type", "직접다운로드"),
                item.get("url", ""),
                item.get("saved_path", ""),
                item.get("remarks", "")
            ]
            rows_to_add.append(row)

        with open(self.csv_path, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_add)

        print(f"[ResourceListManager] CSV 저장 완료 ({len(rows_to_add)}건): {self.csv_path}")

        # 2. Excel 파일 갱신 (통합시트 + 월별 시트)
        self._update_excel()

    def _update_excel(self):
        """
        list_download_resources.csv 데이터를 읽어와
        list_download_resources.xlsx 엑셀 파일의 '통합 목록' 시트 및 '월별 시트'로 분리하여 갱신합니다.
        """
        try:
            if not os.path.exists(self.csv_path):
                return

            df = pd.read_csv(self.csv_path, encoding='utf-8-sig')

            with pd.ExcelWriter(self.excel_path, engine='openpyxl') as writer:
                # 1) [통합 목록] 시트 저장
                df.to_excel(writer, sheet_name="통합 목록", index=False)

                # 2) [월별 목록] 시트 저장 (발간연월 기준 그룹화)
                if "발간연월" in df.columns:
                    # NaN 값 처리
                    df['발간연월'] = df['발간연월'].fillna('기타_미상')
                    unique_months = df['발간연월'].unique()

                    for ym in sorted(unique_months, reverse=True):
                        sheet_name = f"{ym} 목록" if ym != '기타_미상' else '기타 목록'
                        # 엑셀 시트 이름 31자 제한 및 특수문자 제거
                        sheet_name = sheet_name.replace(":", "").replace("/", "-")[:30]
                        
                        df_month = df[df['발간연월'] == ym]
                        df_month.to_excel(writer, sheet_name=sheet_name, index=False)

            print(f"[ResourceListManager] Excel 통합 및 월별 시트 갱신 완료: {self.excel_path}")

        except Exception as e:
            print(f"[ResourceListManager] Excel 파일 생성/갱신 중 오류: {e}")
