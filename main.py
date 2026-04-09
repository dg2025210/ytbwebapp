import streamlit as st
import pandas as pd
import re
import matplotlib.pyplot as plt
import matplotlib
from collections import Counter
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ============================================================
# 한글 폰트 설정 (Streamlit Cloud 환경)
# ============================================================
matplotlib.rcParams['font.family'] = 'DejaVu Sans'
matplotlib.rcParams['axes.unicode_minus'] = False

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="유튜브 댓글 수집기",
    page_icon="🎬",
    layout="wide"
)

# ============================================================
# 스타일
# ============================================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        color: #FF0000;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .comment-box {
        background-color: #f9f9f9;
        border-left: 4px solid #FF0000;
        padding: 12px 16px;
        margin-bottom: 10px;
        border-radius: 0 8px 8px 0;
    }
    .comment-author {
        font-weight: bold;
        color: #333;
        font-size: 0.95rem;
    }
    .comment-text {
        color: #555;
        font-size: 0.9rem;
        margin-top: 4px;
    }
    .comment-meta {
        color: #999;
        font-size: 0.75rem;
        margin-top: 4px;
    }
    .analysis-card {
        background: #f0f2f6;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 16px;
    }
    .insight-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 24px;
        border-radius: 12px;
        margin: 16px 0;
        line-height: 1.8;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# session_state 초기화
# ============================================================
if "comments_data" not in st.session_state:
    st.session_state.comments_data = None
if "video_info" not in st.session_state:
    st.session_state.video_info = None
if "video_id" not in st.session_state:
    st.session_state.video_id = None

# ============================================================
# 한국어 불용어 리스트
# ============================================================
STOPWORDS = {
    "의", "가", "이", "은", "들", "는", "좀", "잘", "걍", "과",
    "도", "를", "으로", "자", "에", "와", "한", "하다", "것", "그",
    "되", "수", "보", "않", "없", "나", "사람", "주", "아니",
    "등", "같", "때", "년", "한", "하", "대", "및", "더", "인",
    "로", "에서", "하고", "해서", "그리고", "너무", "정말", "진짜",
    "ㅋㅋ", "ㅋㅋㅋ", "ㅋㅋㅋㅋ", "ㅎㅎ", "ㅎㅎㅎ", "ㅠㅠ", "ㅜㅜ",
    "the", "a", "an", "is", "are", "was", "were", "to", "of",
    "in", "for", "on", "with", "at", "by", "this", "that", "it",
    "and", "or", "but", "not", "be", "have", "has", "had", "do",
    "does", "did", "will", "would", "can", "could", "should",
    "i", "you", "he", "she", "we", "they", "me", "my", "your",
    "so", "if", "just", "about", "up", "out", "no", "what", "all",
    "있", "없는", "하는", "있는", "되는", "된", "할", "하면", "해도",
    "인데", "건데", "거", "게", "네", "데", "지", "요", "죠", "거든요",
    "이거", "저거", "뭐", "어", "음", "아", "오", "이건", "저", "제",
    "거의", "매우", "아주", "많이", "다", "또", "왜", "어떻게",
    "합니다", "합니다", "됩니다", "입니다", "습니다", "ㄹ", "ㅎ", "ㅋ",
}


# ============================================================
# YouTube API 키 가져오기
# ============================================================
def get_api_key():
    try:
        return st.secrets["YOUTUBE_API_KEY"]
    except Exception:
        return None


# ============================================================
# 유튜브 영상 ID 추출
# ============================================================
def extract_video_id(url):
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


# ============================================================
# 영상 정보 가져오기
# ============================================================
def get_video_info(youtube, video_id):
    try:
        request = youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        )
        response = request.execute()

        if response["items"]:
            item = response["items"][0]
            snippet = item["snippet"]
            statistics = item["statistics"]
            return {
                "title": snippet.get("title", "제목 없음"),
                "channel": snippet.get("channelTitle", "채널 없음"),
                "published": snippet.get("publishedAt", "")[:10],
                "description": snippet.get("description", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "view_count": int(statistics.get("viewCount", 0)),
                "like_count": int(statistics.get("likeCount", 0)),
                "comment_count": int(statistics.get("commentCount", 0)),
            }
        return None
    except HttpError as e:
        st.error(f"영상 정보를 가져오는 중 오류 발생: {e}")
        return None


# ============================================================
# 댓글 가져오기
# ============================================================
def get_comments(youtube, video_id, max_comments=100):
    comments = []
    next_page_token = None

    try:
        while len(comments) < max_comments:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(100, max_comments - len(comments)),
                pageToken=next_page_token,
                order="relevance",
                textFormat="plainText"
            )
            response = request.execute()

            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "작성자": snippet.get("authorDisplayName", "익명"),
                    "댓글": snippet.get("textDisplay", ""),
                    "좋아요": snippet.get("likeCount", 0),
                    "작성일": snippet.get("publishedAt", "")[:10],
                })

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
        return comments

    except HttpError as e:
        error_reason = ""
        if e.error_details:
            error_reason = e.error_details[0].get("reason", "")
        if error_reason == "commentsDisabled":
            st.warning("⚠️ 이 영상은 댓글이 비활성화되어 있습니다.")
        else:
            st.error(f"댓글을 가져오는 중 오류 발생: {e}")
        return []


# ============================================================
# 숫자 포맷팅
# ============================================================
def format_number(num):
    if num >= 100000000:
        return f"{num / 100000000:.1f}억"
    elif num >= 10000:
        return f"{num / 10000:.1f}만"
    elif num >= 1000:
        return f"{num / 1000:.1f}천"
    return str(num)


# ============================================================
# 키워드 추출 (형태소 분석기 없이)
# ============================================================
def extract_keywords(texts, top_n=20):
    """댓글 텍스트에서 키워드를 추출합니다."""
    all_words = []
    for text in texts:
        # 한글 2글자 이상 단어 추출
        korean_words = re.findall(r'[가-힣]{2,}', text)
        # 영어 2글자 이상 단어 추출
        english_words = re.findall(r'[a-zA-Z]{3,}', text.lower())
        all_words.extend(korean_words)
        all_words.extend(english_words)

    # 불용어 제거
    filtered = [w for w in all_words if w not in STOPWORDS and len(w) >= 2]
    counter = Counter(filtered)
    return counter.most_common(top_n)


# ============================================================
# 감성 분석 (간단한 규칙 기반)
# ============================================================
def simple_sentiment(text):
    """간단한 규칙 기반 감성 분석"""
    positive_words = [
        "좋", "최고", "감사", "사랑", "행복", "대박", "멋",
        "훌륭", "완벽", "감동", "응원", "추천", "재밌", "재미",
        "굿", "짱", "아름", "예쁘", "힐링", "기대", "축하",
        "존경", "귀엽", "좋아", "웃기", "꿀잼", "ㅋㅋ",
        "love", "great", "good", "best", "amazing", "awesome",
        "nice", "beautiful", "perfect", "wow", "cool", "fantastic",
        "excellent", "wonderful", "funny", "like", "thank",
    ]
    negative_words = [
        "싫", "별로", "나쁘", "최악", "짜증", "화나", "실망",
        "슬프", "힘들", "아쉽", "안타", "걱정", "무섭", "답답",
        "지루", "노잼", "ㅠㅠ", "ㅜㅜ", "그만", "혐", "욕",
        "hate", "bad", "worst", "terrible", "awful", "boring",
        "sad", "angry", "disappointed", "horrible", "ugly", "poor",
    ]

    text_lower = text.lower()
    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)

    if pos_count > neg_count:
        return "긍정 😊"
    elif neg_count > pos_count:
        return "부정 😞"
    else:
        return "중립 😐"


# ============================================================
# 영상 내용 추론
# ============================================================
def infer_video_content(video_info, keywords, sentiments, df):
    """댓글 키워드 + 영상 메타데이터로 영상 내용을 추론합니다."""

    title = video_info.get("title", "")
    description = video_info.get("description", "")[:500]

    # 키워드 정리
    top_keywords = [word for word, count in keywords[:15]]
    keyword_str = ", ".join(top_keywords) if top_keywords else "추출된 키워드 없음"

    # 감성 비율
    total = len(sentiments)
    if total > 0:
        pos_ratio = sentiments.count("긍정 😊") / total * 100
        neg_ratio = sentiments.count("부정 😞") / total * 100
        neu_ratio = sentiments.count("중립 😐") / total * 100
    else:
        pos_ratio = neg_ratio = neu_ratio = 0

    # 좋아요 Top 5 댓글
    top_comments = df.nlargest(5, "좋아요")["댓글"].tolist()
    top_comments_str = "\n".join([f"  • {c[:80]}" for c in top_comments])

    # 반응 판단
    if pos_ratio >= 60:
        overall_reaction = "매우 긍정적"
        reaction_emoji = "🔥"
    elif pos_ratio >= 40:
        overall_reaction = "대체로 긍정적"
        reaction_emoji = "👍"
    elif neg_ratio >= 40:
        overall_reaction = "부정적 반응이 많음"
        reaction_emoji = "⚠️"
    else:
        overall_reaction = "반응이 다양함"
        reaction_emoji = "🤔"

    analysis_text = f"""
### 🎯 영상 내용 추론 분석

**📌 영상 제목:** {title}

**📺 채널:** {video_info.get('channel', '')}

---

#### 🔑 댓글에서 추출한 핵심 키워드
{keyword_str}

---

#### 📊 시청자 반응 요약
- **전체 반응:** {reaction_emoji} {overall_reaction}
- **긍정 비율:** {pos_ratio:.1f}%
- **부정 비율:** {neg_ratio:.1f}%
- **중립 비율:** {neu_ratio:.1f}%

---

#### 💬 가장 공감받은 댓글 TOP 5
{top_comments_str}

---

#### 🧠 종합 분석

**[영상 주제 추정]**
영상 제목과 댓글 키워드를 종합하면, 이 영상은 **"{title}"**에 관한 내용이며,
시청자들이 가장 많이 언급한 주제는 **{', '.join(top_keywords[:5])}** 등입니다.

**[시청자 반응]**
전체 {total}개 댓글 중 긍정 반응이 {pos_ratio:.1f}%로,
시청자들의 반응은 **{overall_reaction}**입니다.
"""

    if description:
        analysis_text += f"""
---

#### 📝 영상 설명글 (일부)
> {description[:300]}{'...' if len(description) > 300 else ''}
"""

    return analysis_text


# ============================================================
# 메인 앱
# ============================================================
def main():
    st.markdown('<div class="main-header">🎬 유튜브 댓글 수집 & 분석기</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">유튜브 영상 링크를 입력하면 댓글을 수집하고 분석합니다</div>', unsafe_allow_html=True)

    # API 키 확인
    api_key = get_api_key()

    if not api_key or api_key == "여기에_본인의_YouTube_Data_API_v3_키를_입력하세요":
        st.error("🔑 YouTube API 키가 설정되지 않았습니다!")
        st.info("""
        **API 키 설정 방법:**

        **1단계: Google Cloud Console에서 API 키 발급**
        1. [Google Cloud Console](https://console.cloud.google.com/) 접속
        2. 새 프로젝트 생성
        3. 'API 및 서비스' → '라이브러리'에서 **YouTube Data API v3** 활성화
        4. 'API 및 서비스' → '사용자 인증 정보' → 'API 키 만들기'

        **2단계: Streamlit Cloud에 API 키 등록**
        1. 앱 대시보드 → **Settings** → **Secrets**
        2. 아래 내용 입력:
        ```
        YOUTUBE_API_KEY = "발급받은_API_키"
        ```
        """)
        return

    try:
        youtube = build("youtube", "v3", developerKey=api_key)
    except Exception as e:
        st.error(f"YouTube API 연결 실패: {e}")
        return

    # --------------------------------------------------------
    # 입력 영역
    # --------------------------------------------------------
    st.markdown("---")

    col_input, col_option = st.columns([3, 1])

    with col_input:
        url = st.text_input(
            "🔗 유튜브 영상 링크를 입력하세요",
            placeholder="https://www.youtube.com/watch?v=...",
        )

    with col_option:
        max_comments = st.selectbox(
            "📊 수집할 댓글 수",
            options=[50, 100, 200, 500, 1000],
            index=1,
        )

    search_clicked = st.button("🔍 댓글 수집 시작", use_container_width=True, type="primary")

    # --------------------------------------------------------
    # 댓글 수집
    # --------------------------------------------------------
    if search_clicked and url:
        video_id = extract_video_id(url)

        if not video_id:
            st.error("❌ 올바른 유튜브 링크를 입력해주세요!")
            return

        with st.spinner("📡 영상 정보를 불러오는 중..."):
            video_info = get_video_info(youtube, video_id)

        if not video_info:
            st.error("❌ 영상 정보를 찾을 수 없습니다.")
            return

        with st.spinner(f"📝 댓글을 수집하는 중... (최대 {max_comments}개)"):
            comments = get_comments(youtube, video_id, max_comments)

        if not comments:
            st.warning("수집된 댓글이 없습니다.")
            return

        # session_state에 저장 → 정렬/탭 전환해도 유지
        st.session_state.comments_data = comments
        st.session_state.video_info = video_info
        st.session_state.video_id = video_id

    elif search_clicked and not url:
        st.warning("⚠️ 유튜브 링크를 입력해주세요!")

    # --------------------------------------------------------
    # 결과 표시 (session_state에 데이터가 있을 때)
    # --------------------------------------------------------
    if st.session_state.comments_data is None:
        st.info("👆 위에 유튜브 링크를 입력하고 '댓글 수집 시작' 버튼을 눌러주세요!")
        return

    comments = st.session_state.comments_data
    video_info = st.session_state.video_info
    video_id = st.session_state.video_id
    df = pd.DataFrame(comments)

    # 영상 정보 표시
    st.markdown("---")
    st.subheader("📺 영상 정보")

    col_thumb, col_info = st.columns([1, 2])

    with col_thumb:
        if video_info["thumbnail"]:
            st.image(video_info["thumbnail"], use_container_width=True)

    with col_info:
        st.markdown(f"### {video_info['title']}")
        st.markdown(f"**채널:** {video_info['channel']}  |  **게시일:** {video_info['published']}")

        stat1, stat2, stat3 = st.columns(3)
        with stat1:
            st.metric("👁️ 조회수", format_number(video_info["view_count"]))
        with stat2:
            st.metric("👍 좋아요", format_number(video_info["like_count"]))
        with stat3:
            st.metric("💬 댓글수", format_number(video_info["comment_count"]))

    st.success(f"✅ 총 **{len(df)}개**의 댓글을 수집했습니다!")

    # --------------------------------------------------------
    # 탭 구성: 댓글 목록 / 데이터 테이블 / 댓글 분석
    # --------------------------------------------------------
    tab1, tab2, tab3 = st.tabs(["📋 댓글 목록", "📊 데이터 테이블", "🧠 댓글 분석"])

    # ========================================
    # 탭1: 댓글 목록
    # ========================================
    with tab1:
        sort_option = st.selectbox(
            "정렬 기준",
            ["관련성순 (기본)", "좋아요 많은순", "최신순", "오래된순"],
            key="sort_selector"
        )

        df_sorted = df.copy()
        if sort_option == "좋아요 많은순":
            df_sorted = df_sorted.sort_values("좋아요", ascending=False).reset_index(drop=True)
        elif sort_option == "최신순":
            df_sorted = df_sorted.sort_values("작성일", ascending=False).reset_index(drop=True)
        elif sort_option == "오래된순":
            df_sorted = df_sorted.sort_values("작성일", ascending=True).reset_index(drop=True)

        search_term = st.text_input("🔍 댓글 내 검색", placeholder="검색어를 입력하세요...", key="search_input")
        if search_term:
            df_sorted = df_sorted[
                df_sorted["댓글"].str.contains(search_term, case=False, na=False)
            ].reset_index(drop=True)
            st.info(f"'{search_term}' 검색 결과: {len(df_sorted)}개")

        for _, row in df_sorted.iterrows():
            st.markdown(f"""
            <div class="comment-box">
                <div class="comment-author">👤 {row['작성자']}</div>
                <div class="comment-text">{row['댓글']}</div>
                <div class="comment-meta">👍 {row['좋아요']}  ·  📅 {row['작성일']}</div>
            </div>
            """, unsafe_allow_html=True)

    # ========================================
    # 탭2: 데이터 테이블
    # ========================================
    with tab2:
        st.dataframe(
            df,
            use_container_width=True,
            height=500,
            column_config={
                "좋아요": st.column_config.NumberColumn("👍 좋아요", format="%d"),
                "작성자": st.column_config.TextColumn("👤 작성자", width="medium"),
                "댓글": st.column_config.TextColumn("💬 댓글", width="large"),
                "작성일": st.column_config.TextColumn("📅 작성일", width="small"),
            }
        )

        st.markdown("#### 📈 기본 통계")
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric("총 댓글 수", f"{len(df)}개")
        with s2:
            st.metric("평균 좋아요", f"{df['좋아요'].mean():.1f}개")
        with s3:
            st.metric("최다 좋아요", f"{df['좋아요'].max()}개")
        with s4:
            st.metric("작성자 수", f"{df['작성자'].nunique()}명")

        # CSV 다운로드 (작게 하나만)
        csv_data = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 CSV 다운로드",
            data=csv_data,
            file_name=f"youtube_comments_{video_id}.csv",
            mime="text/csv",
        )

    # ========================================
    # 탭3: 댓글 분석
    # ========================================
    with tab3:
        st.subheader("🧠 댓글 기반 영상 분석")

        with st.spinner("🔍 댓글을 분석하는 중..."):

            # 1) 키워드 추출
            all_texts = df["댓글"].tolist()
            keywords = extract_keywords(all_texts, top_n=20)

            # 2) 감성 분석
            df["감성"] = df["댓글"].apply(simple_sentiment)
            sentiments = df["감성"].tolist()

            # ----------------------------------------
            # 감성 분석 파이차트 + 키워드 바차트 나란히
            # ----------------------------------------
            st.markdown("---")
            st.markdown("### 📊 시각화 분석")

            chart_col1, chart_col2 = st.columns(2)

            # 파이차트: 감성 비율
            with chart_col1:
                st.markdown("#### 💭 댓글 감성 비율")

                sentiment_counts = df["감성"].value_counts()
                labels = sentiment_counts.index.tolist()
                sizes = sentiment_counts.values.tolist()

                colors_map = {
                    "긍정 😊": "#4CAF50",
                    "부정 😞": "#F44336",
                    "중립 😐": "#9E9E9E",
                }
                colors = [colors_map.get(l, "#999") for l in labels]

                fig1, ax1 = plt.subplots(figsize=(6, 6))
                wedges, texts, autotexts = ax1.pie(
                    sizes,
                    labels=labels,
                    autopct='%1.1f%%',
                    colors=colors,
                    startangle=90,
                    textprops={'fontsize': 13},
                    pctdistance=0.75,
                )
                for t in autotexts:
                    t.set_fontsize(14)
                    t.set_fontweight('bold')
                ax1.set_title("Comment Sentiment Ratio", fontsize=16, fontweight='bold', pad=20)
                st.pyplot(fig1)

            # 바차트: 키워드 빈도
            with chart_col2:
                st.markdown("#### 🔑 댓글 핵심 키워드 TOP 15")

                if keywords:
                    top_kw = keywords[:15]
                    words = [w for w, c in top_kw]
                    counts = [c for w, c in top_kw]

                    fig2, ax2 = plt.subplots(figsize=(6, 6))
                    bars = ax2.barh(
                        range(len(words)),
                        counts,
                        color=plt.cm.Reds(
                            [0.3 + 0.7 * (i / len(words)) for i in range(len(words))]
                        ),
                    )
                    ax2.set_yticks(range(len(words)))
                    ax2.set_yticklabels(words, fontsize=12)
                    ax2.invert_yaxis()
                    ax2.set_xlabel("Frequency", fontsize=12)
                    ax2.set_title("Top Keywords in Comments", fontsize=16, fontweight='bold')

                    for bar, count in zip(bars, counts):
                        ax2.text(
                            bar.get_width() + max(counts) * 0.02,
                            bar.get_y() + bar.get_height() / 2,
                            str(count),
                            va='center',
                            fontsize=11,
                            fontweight='bold',
                        )
                    plt.tight_layout()
                    st.pyplot(fig2)
                else:
                    st.info("키워드를 추출할 수 없습니다.")

            # ----------------------------------------
            # 좋아요 분포 히스토그램
            # ----------------------------------------
            st.markdown("---")
            st.markdown("#### 👍 댓글 좋아요 분포
