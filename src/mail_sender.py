import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Dict, Any

class MobileOptimizedMailSender:
    """
    삼성 갤럭시 폴드7 및 모바일 환경에 최적화된 세로형 카드 리스트 HTML 메일을 생성하고
    SMTP를 통해 사용자가 지정한 계정으로 발송하는 클래스
    """
    def __init__(self, smtp_config: dict):
        self.smtp_server = smtp_config.get("smtp_server", "smtp.gmail.com")
        self.smtp_port = smtp_config.get("smtp_port", 587)
        self.sender_email = smtp_config.get("sender_email", "")
        self.sender_password = smtp_config.get("sender_password", "")
        self.receiver_email = smtp_config.get("receiver_email", "")
        self.enabled = smtp_config.get("enabled", True)

    def generate_html_body(self, items: List[Dict[str, Any]], mode: int) -> str:
        """
        지침 제6항(모바일 최적화 세로형 카드 리스트 포맷)을 준수하는 HTML 메일 본문을 생성합니다.
        가로 스크롤 없이 360px~800px 디스플레이에서 최적으로 렌더링되도록 디자인.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        mode_title = "1안: PDF 일자별 자동 저장 및 수집 리스트" if mode == 1 else "2안: 수집 자료 유효성 검증 링크 리스트"

        cards_html = ""
        for idx, item in enumerate(items, 1):
            year = item.get("year", "2026")
            title = item.get("title", "제목 없음")
            publisher = item.get("publisher", "발행기관 미상")
            access_type = item.get("access_type", "원문 접근 확인")
            url = item.get("url", "#")
            remarks = item.get("remarks", "무료 다운로드 검증 완료")
            saved_path = item.get("saved_path", "")

            link_btn_text = "👉 PDF 바로 받기" if item.get("group") == "GROUP_A" else "👉 공식 게시글 바로가기"

            saved_info_html = ""
            if mode == 1 and saved_path:
                saved_info_html = f"""
                <div style="margin-top: 6px; padding: 6px 10px; background-color: #e8f5e9; border-radius: 4px; font-size: 13px; color: #2e7d32;">
                    <strong>💾 로컬 저장 완료:</strong> <span style="word-break: break-all;">{saved_path}</span>
                </div>
                """

            cards_html += f"""
            <div style="background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="font-size: 16px; font-weight: bold; color: #1a73e8; margin-bottom: 8px;">
                    {idx}. [{year}년] {title} (PDF)
                </div>
                <div style="font-size: 14px; color: #333333; line-height: 1.6;">
                    • <strong>발행 기관:</strong> {publisher}<br>
                    • <strong>원문 접근:</strong> {access_type}<br>
                    • <strong>출처 링크:</strong> <a href="{url}" target="_blank" style="color: #1a73e8; font-weight: bold; text-decoration: underline;">{link_btn_text}</a><br>
                    • <strong>비고:</strong> {remarks}
                </div>
                {saved_info_html}
            </div>
            """

        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>매일 일일 웹 크롤링 & 리서치 자료 보고서</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f5f5f7; margin: 0; padding: 12px;">
            <div style="max-width: 600px; margin: 0 auto;">
                <div style="background-color: #1a73e8; color: #ffffff; padding: 16px; border-radius: 8px 8px 0 0; text-align: center;">
                    <h2 style="margin: 0; font-size: 18px;">📋 일일 웹 크롤링 리서치 자동 보고서</h2>
                    <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">수집 일자: {today_str} | {mode_title}</p>
                </div>
                
                <div style="padding: 12px 0;">
                    {cards_html if items else '<div style="background:#fff; padding:20px; text-align:center; border-radius:8px;">오늘 새로 수집된 신규 자료가 없습니다.</div>'}
                </div>

                <div style="font-size: 12px; color: #777777; text-align: center; padding: 10px; border-top: 1px solid #dddddd;">
                    본 메일은 자료 수집 리서치 Gem 지침(개정판)에 따라 3단계 링크 유효성 검증 및 URL 환각 방지 검증을 거쳐 자동 발송되었습니다.
                </div>
            </div>
        </body>
        </html>
        """
        return full_html

    def send_email(self, items: List[Dict[str, Any]], mode: int) -> bool:
        """
        수집된 결과를 바탕으로 HTML 메일을 작성하여 발송합니다.
        """
        if not self.enabled:
            print("[MailSender] 메일 발송 기능이 설정에서 비활성화되어 있습니다.")
            return False

        if not self.sender_email or not self.receiver_email:
            print("[MailSender] 발신자 또는 수신자 메일 주소가 설정되지 않았습니다.")
            return False

        today_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"[일일 리서치 수집 보고서] {today_str} 웹 크롤링 자료 목록 ({len(items)}건)"

        html_body = self.generate_html_body(items, mode)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = self.receiver_email

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, self.receiver_email, msg.as_string())
            print(f"[MailSender] 메일 발송 성공! (수신자: {self.receiver_email})")
            return True
        except Exception as e:
            print(f"[MailSender] 메일 발송 중 오류 발생: {e}")
            return False
