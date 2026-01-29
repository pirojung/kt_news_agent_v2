import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
import difflib

# ================= 1. 설정값 (직접 수정 필요) =================
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID") 
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
KEYWORD = "kt" 

EMAIL_SENDER = "pirojung@gmail.com"  
EMAIL_APP_PWD = os.getenv("EMAIL_APP_PWD") 
# EMAIL_RECEIVER = "po.jung@kt.com"
EMAIL_RECEIVER = ["po.jung@kt.com", "5422540656@kt.com"]

# [기존] 제외 키워드 및 사이트
EXCLUDE_KEYWORDS = [
    "위즈", "소닉붐", "롤스터", "LCK", "e스포츠", "T1", "젠지", "디플러스",
    "야구", "농구", "축구", "프로농구", "KBO", "KBL",
    "연승", "연패", "감독", "선수", "득점", "홈런", "역전", "더비",
    "연예", "방송", "드라마", "예능", "시청률", "출연", "가수", "배우", "아이돌", "Genie"
]

EXCLUDE_SITES = [
    "sports", "entertain", "basketkorea", "jumpball", "rookie",
    "inven", "fomos", "game", "thisisgame",
    "spotv", "xports", "osen", "stardaily", "joynews", "tvreport"
]

# [신규] 4가지 유형별 분류 키워드
CATEGORY_KEYWORDS = {
    "1. IT/AI 동향 기사": [
        "AI", "인공지능", "LLM", "AX", "클라우드", "Cloud", "빅데이터", "IDC", 
        "5G", "6G", "로봇", "자율주행", "디지털 전환", "DX", "양자암호", "초거대"
    ],
    "2. CEO/경영/인사 관련 기사": [
        "박윤영", "김영섭", "대표", "CEO", "사장", "임원", "인사", "조직개편", 
        "경영", "주주", "배당", "실적", "영업이익", "이사회", "노조", "단체협약"
    ],
    "3. 신상품/서비스 출시 기사": [
        "출시", "신상품", "요금제", "프로모션", "신규", "서비스", "오픈", 
        "이벤트", "가입자", "OTT", "스마트폰", "갤럭시", "아이폰"
    ],
    "4. 정부규제/컴플라이언스 기사": [
        "방통위", "방송통신위원회", "공정위", "과기정통부", "국감", "국정감사", 
        "규제", "과징금", "소송", "재판", "조사", "단통법", "망사용료", "통신비", "위반"
    ]
}

# ============================================================

def is_similar(title1, title2):
    return difflib.SequenceMatcher(None, title1, title2).ratio()

def get_filtered_news():
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    params = {'query': KEYWORD, 'display': 100, 'sort': 'date'} 
    
    response = requests.get(url, headers=headers, params=params, verify=False)
    
    if response.status_code != 200:
        return {}

    data = response.json()
    now = datetime.now(timezone(timedelta(hours=9)))
    time_limit = now - timedelta(hours=24)
    
    accepted_titles = []
    
    # [수정] 결과를 저장할 그룹핑 딕셔너리 초기화
    grouped_news = {
        "1. IT/AI 동향 기사": [],
        "2. CEO/경영/인사 관련 기사": [],
        "3. 신상품/서비스 출시 기사": [],
        "4. 정부규제/컴플라이언스 기사": [],
        "5. 기타 KT 관련 기사": []
    }

    for item in data['items']:
        pub_date = datetime.strptime(item['pubDate'], "%a, %d %b %Y %H:%M:%S %z")
        if pub_date < time_limit:
            continue

        clean_title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').strip()
        link = item['originallink'] or item['link']

        # 1. 제외 필터링 (기존 유지)
        is_unwanted = False
        if any(site in link.lower() for site in EXCLUDE_SITES):
            is_unwanted = True
        elif any(kw in clean_title for kw in EXCLUDE_KEYWORDS):
            is_unwanted = True
            
        if is_unwanted:
            continue 
        
        # 2. 중복 기사 제외 (기존 유지)
        is_duplicate = False
        for existing_title in accepted_titles:
            if is_similar(clean_title, existing_title) > 0.65:
                is_duplicate = True
                break
        
        if not is_duplicate:
            item['clean_title'] = clean_title 
            accepted_titles.append(clean_title)
            
            # [신규] 3. 기사 카테고리 분류 로직
            # 제목과 본문 요약을 모두 검색하여 정확도 향상
            search_text = clean_title + " " + item['description']
            assigned_category = "5. 기타 KT 관련 기사" # 기본값
            
            for category, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in search_text for kw in keywords):
                    assigned_category = category
                    break # 가장 먼저 매칭되는 카테고리에 할당
            
            grouped_news[assigned_category].append(item)

    return grouped_news

def send_email(grouped_news):
    # 전체 뉴스 개수 계산
    total_news_count = sum(len(news_list) for news_list in grouped_news.values())
    
    if total_news_count == 0:
        print("새로운 뉴스가 없어 메일을 발송하지 않습니다.")
        return

    subject = f"[NewsAgent] 오늘의 '{KEYWORD}' 핵심 뉴스 브리핑 ({total_news_count}건)"
    
    # 이메일 헤더 생성
    html_content = f"""
    <html>
    <body style="font-family: sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto;">
        <h2 style="color: #003366;">📰 [{KEYWORD}] 24시간 핵심 뉴스 브리핑</h2>
        <p style="color:gray;">분류된 최신 뉴스 총 <b>{total_news_count}건</b>입니다.</p>
        <hr style="border: 1px solid #ddd;">
    """
    
    # [수정] 카테고리별로 순회하며 HTML 생성
    for category, news_list in grouped_news.items():
        if not news_list: # 해당 카테고리에 뉴스가 없으면 건너뜀
            continue
            
        # 카테고리 제목
        html_content += f"<h3 style='color: #008080; margin-top: 25px;'>📌 {category} ({len(news_list)}건)</h3>"
        html_content += "<ul style='margin-bottom: 20px;'>"
        
        # 해당 카테고리 내 뉴스 리스트
        for item in news_list: 
            link = item['originallink'] or item['link']
            desc = item['description'].replace('<b>', '').replace('</b>', '')
            html_content += f"<li style='margin-bottom: 15px;'><b><a href='{link}' target='_blank' style='text-decoration:none; color:#1a0dab; font-size:16px;'>{item['clean_title']}</a></b><br>"
            html_content += f"<span style='font-size:13px; color:#555;'>{desc}...</span></li>"
        
        html_content += "</ul>"

    html_content += "</body></html>"

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    # msg['To'] = EMAIL_RECEIVER
    # [수정] 리스트 형태의 수신자들을 "주소1, 주소2" 형태의 문자열로 변환하여 넣습니다.
    msg['To'] = ", ".join(EMAIL_RECEIVER)
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_APP_PWD)
            server.send_message(msg)
        print("✅ 이메일 발송 성공! 메일함을 확인해주세요.")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")

if __name__ == "__main__":
    print("뉴스 수집, 필터링 및 분류 중...")
    grouped_news = get_filtered_news()
    send_email(grouped_news)
