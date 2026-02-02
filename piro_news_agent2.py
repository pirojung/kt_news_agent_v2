import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
import difflib

# ================= 1. 설정값 =================
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID") 
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
KEYWORD = "kt" 

EMAIL_SENDER = "pirojung@gmail.com"  
EMAIL_APP_PWD = os.getenv("EMAIL_APP_PWD") 
EMAIL_RECEIVER = ["po.jung@kt.com"]  # , "5422540656@kt.com"]

# [강화된] 제외 키워드 - 스포츠 및 연예계 특화 용어 추가
EXCLUDE_KEYWORDS = [
    "위즈", "소닉붐", "롤스터", "LCK", "e스포츠", "T1", "젠지", "디플러스",
    "야구", "농구", "축구", "배구", "프로농구", "KBO", "KBL", "코트", "그라운드",
    "연승", "연패", "감독", "선수", "득점", "홈런", "역전", "더비", "안타", "타점", "라운드",
    "연예", "방송", "드라마", "예능", "시청률", "출연", "가수", "배우", "아이돌", "데뷔",
    "컴백", "음원", "빌보드", "차트", "영화", "개봉", "시사회", "캐스팅", "종영", "제작발표회"
]

# [강화된] 제외 사이트 - 도메인 기반 필터링
EXCLUDE_SITES = [
    "sports", "entertain", "basketkorea", "jumpball", "rookie",
    "inven", "fomos", "game", "thisisgame", "spotv", "xports", "osen", 
    "stardaily", "joynews", "tvreport", "sportschosun", "sportsdonga", "sportsworld"
]

CATEGORY_KEYWORDS = {
    "1. IT/AI 동향 기사": ["AI", "인공지능", "LLM", "AX", "클라우드", "Cloud", "빅데이터", "IDC", "5G", "6G", "로봇", "자율주행", "디지털 전환", "DX", "양자", "초거대"],
    "2. CEO/경영/인사 관련 기사": ["박윤영", "김영섭", "대표", "CEO", "사장", "임원", "인사", "조직개편", "경영", "주주", "배당", "실적", "영업이익", "이사회", "노조", "단협"],
    "3. 신상품/서비스 출시 기사": ["출시", "신상품", "요금제", "프로모션", "신규", "서비스", "오픈", "이벤트", "가입자", "OTT", "스마트폰", "갤럭시", "아이폰"],
    "4. 정부규제/컴플라이언스 기사": ["방통위", "공정위", "과기정통부", "국감", "국정감사", "규제", "과징금", "소송", "재판", "조사", "단통법", "망사용료", "통신비"]
}

# ============================================

def is_similar(title1, title2):
    return difflib.SequenceMatcher(None, title1, title2).ratio()

def get_filtered_news():
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    params = {'query': KEYWORD, 'display': 100, 'sort': 'date'} 
    
    # SSL 경고 방지를 위해 verify=True 권장 (환경에 따라 조절)
    response = requests.get(url, headers=headers, params=params, verify=True)
    
    if response.status_code != 200:
        return {}

    data = response.json()
    now = datetime.now(timezone(timedelta(hours=9)))
    time_limit = now - timedelta(hours=24)
    
    accepted_titles = []
    grouped_news = {cat: [] for cat in CATEGORY_KEYWORDS.keys()}
    grouped_news["5. 기타 KT 관련 기사"] = []

    for item in data['items']:
        pub_date = datetime.strptime(item['pubDate'], "%a, %d %b %Y %H:%M:%S %z")
        if pub_date < time_limit: continue

        clean_title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&amp;', '&').strip()
        link = item['originallink'] or item['link']

        # 1. 사이트 도메인 및 키워드 기반 필터링 (강화)
        if any(site in link.lower() for site in EXCLUDE_SITES) or \
           any(kw in clean_title for kw in EXCLUDE_KEYWORDS):
            continue 
        
        # 2. 중복 기사 제거 (유사도 0.65 이상)
        if any(is_similar(clean_title, t) > 0.65 for t in accepted_titles):
            continue
        
        item['clean_title'] = clean_title
        accepted_titles.append(clean_title)
        
        # 3. 카테고리 분류
        search_text = clean_title + " " + item['description']
        assigned_category = "5. 기타 KT 관련 기사"
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in search_text for kw in keywords):
                assigned_category = category
                break
        
        grouped_news[assigned_category].append(item)

    return grouped_news

def send_email(grouped_news):
    total_news_count = sum(len(news_list) for news_list in grouped_news.values())
    if total_news_count == 0:
        print("발송할 뉴스가 없습니다.")
        return

    # 요약 정보 생성을 위한 로직
    summary_lines = []
    for cat, news in grouped_news.items():
        if news:
            summary_lines.append(f"<li>{cat}: {len(news)}건</li>")
    
    # 하이라이트 (가장 중요한 카테고리에서 상위 기사 추출)
    highlights = []
    for cat in ["1. IT/AI 동향 기사", "2. CEO/경영/인사 관련 기사"]:
        for item in grouped_news[cat][:2]: # 카테고리별 최대 2개
            highlights.append(item['clean_title'])

    subject = f"[NewsAgent] {datetime.now().strftime('%m/%d')} KT 주요 뉴스 브리핑 (총 {total_news_count}건)"
    
    # HTML 이메일 본문
    html_content = f"""
    <html>
    <body style="font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; color: #333;">
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px;">
            <h2 style="color: #e61e2b;">🚀 Today's KT News Summary</h2>
            <p style="font-size: 14px; color: #666;">수집 기간: 최근 24시간 | 검색어: <b>{KEYWORD}</b></p>
            
            <div style="background-color: #ffffff; padding: 15px; border-left: 5px solid #e61e2b; margin-bottom: 20px;">
                <b style="font-size: 16px;">📊 카테고리별 요약</b>
                <ul style="margin: 5px 0; padding-left: 20px;">
                    {"".join(summary_lines)}
                </ul>
                <hr style="border: 0.5px thin #eee;">
                <b style="font-size: 16px;">🌟 주요 헤드라인</b>
                <ul style="margin: 5px 0; padding-left: 20px; color: #0056b3;">
                    {"".join([f"<li>{h}</li>" for h in highlights[:3]])}
                </ul>
            </div>
    """

    for category, news_list in grouped_news.items():
        if not news_list: continue
        html_content += f"<h3 style='border-bottom: 2px solid #333; padding-bottom: 5px; color: #333;'>📌 {category}</h3>"
        for item in news_list:
            link = item['originallink'] or item['link']
            desc = item['description'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"')
            html_content += f"""
            <div style='margin-bottom: 15px;'>
                <a href='{link}' style='text-decoration: none; color: #1a0dab; font-weight: bold; font-size: 15px;'>· {item['clean_title']}</a><br>
                <span style='font-size: 12px; color: #666;'>{desc}</span>
            </div>"""

    html_content += "</div></body></html>"

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = ", ".join(EMAIL_RECEIVER)
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_APP_PWD)
            server.send_message(msg)
        print(f"✅ 발송 완료: {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ 발송 실패: {e}")

if __name__ == "__main__":
    grouped_news = get_filtered_news()
    send_email(grouped_news)
