import sys
import os
import yaml
import schedule
import time
import argparse
from datetime import datetime

# Windows 콘솔 인코딩 대응
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from src.database import CollectionDatabase
from src.query_builder import QueryBuilder
from src.validator import LinkValidator
from src.crawler_engine import ResearchCrawlerEngine
from src.downloader import PDFDownloader
from src.mail_sender import MobileOptimizedMailSender
from src.excel_manager import ResourceListManager

def load_config(config_path="config.yaml"):
    """config.yaml 환경 설정 파일 로드"""
    if not os.path.exists(config_path):
        print(f"[Main] 설정 파일이 존재하지 않습니다: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run_collection_workflow(config: dict):
    """
    지정된 기간 내 필수 기관 전수 업로드 자료 크롤링 및 다운로드 메인 워크플로 실행
    """
    print("\n==================================================")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 필수 기관 기간 내 전체 자료 수집 작업을 시작합니다.")
    print("==================================================")

    # 1. 모듈 객체 및 기관 설정 초기화
    db = CollectionDatabase()
    excel_mgr = ResourceListManager()
    
    essential_institutions = config.get("essential_institutions", {})
    query_builder = QueryBuilder(essential_institutions)
    
    group_a = config.get("domains", {}).get("group_a", [])
    group_b = config.get("domains", {}).get("group_b", [])
    validator = LinkValidator(group_a, group_b)
    
    crawler = ResearchCrawlerEngine(validator, db)
    downloader = PDFDownloader(base_download_dir="downloads")
    mail_sender = MobileOptimizedMailSender(config.get("email", {}))

    # 2. 최초 실행 여부 판단 (최초: 2026.1.1~2026.7.31 전수 / 이후: 최근 1개월 이내 전수)
    is_first_run = db.is_first_run()
    if is_first_run:
        print("[MODE] 최초 실행 전수 수집 모드: 2026년 1월 1일 ~ 2026년 7월 31일 동안 업로드된 파일 전체를 수집합니다.")
    else:
        print("[MODE] 정기 실행 전수 수집 모드: 최근 1개월 이내 업로드된 파일 전체를 수집합니다.")

    mode = config.get("mode", 1)

    # 3. 필수 기관별 전수 탐색 쿼리 생성 및 크롤링 실행
    institution_queries = query_builder.build_institution_all_queries()
    collected_items = crawler.crawl_all_institutions(institution_queries, is_first_run)

    print(f"\n[DOWNLOAD] 탐색 완료 항목 ({len(collected_items)}건) 파일 다운로드 및 이력 등록 진행 중...")

    processed_items = []
    for item in collected_items:
        url = item["url"]
        title = item["title"]
        publisher = item["publisher"]
        access_type = item["access_type"]

        # 1안(자동 다운로드 모드)인 경우 파일 다운로드 수행
        saved_path = ""
        if mode == 1:
            saved_path = downloader.download_file(item)
            item["saved_path"] = saved_path

        # DB 등록 (중복 수집 방지)
        db.add_collection(title, publisher, url, access_type, saved_path)
        processed_items.append(item)

    print(f"\n[COMPLETE] 총 {len(processed_items)}건의 수집 및 다운로드 작업이 완료되었습니다.")

    # 4. list_download_resources.csv 및 list_download_resources.xlsx (통합/월별 시트) 갱신
    if processed_items:
        excel_mgr.save_resources(processed_items)

    # 5. 최초 수집 성공 시 완료 상태 기록
    if is_first_run:
        db.mark_first_run_completed()

    # 6. 모바일 최적화 세로형 카드 리스트 메일 전송
    if config.get("email", {}).get("enabled", True):
        mail_sender.send_email(processed_items, mode)

    print("==================================================")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 지정 기간 필수 기관 전수 수집이 성공적으로 완료되었습니다.")
    print("==================================================\n")

def start_scheduler(config: dict):
    """매월 1일 오전 09:00에 수집 작업을 자동 실행하는 데몬 스케줄러"""
    sched_cfg = config.get("schedule", {})
    target_day = sched_cfg.get("day_of_month", 1)
    target_time = sched_cfg.get("time", "09:00")
    
    print(f"[Scheduler] 매월 {target_day}일 오전 [{target_time}]에 수집 작업이 자동 실행되도록 스케줄러가 대기 중입니다...")
    
    def monthly_job():
        now = datetime.now()
        # 매월 지정한 일(1일) 및 시간에 맞춰 실행
        if now.day == target_day:
            print(f"[Scheduler] 매월 {target_day}일 정기 실행 조건 충족 ({now.strftime('%Y-%m-%d %H:%M')}). 수집을 시작합니다.")
            run_collection_workflow(config)

    # 매일 09:00에 검사하여 1일인 경우 수집 실행
    schedule.every().day.at(target_time).do(monthly_job)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="필수 기관 기간 내 파일 전수 크롤링 프로그램")
    parser.add_argument("--now", action="store_true", help="스케줄 대기 없이 즉시 수집 실행")
    parser.add_argument("--schedule", action="store_true", help="정기 스케줄러 데몬 모드 실행")
    args = parser.parse_args()

    config = load_config()

    if args.schedule:
        start_scheduler(config)
    else:
        run_collection_workflow(config)
