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
# 한국어 불용어
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
    "합니다", "됩니다", "입니다", "습니다", "ㄹ", "ㅎ", "ㅋ",
}


# ============================================================
# 함수들
# ============================================================
def get_api_key():
    try:
        return st.secrets["YOUTUBE_API_KEY"]
    except Exception:
        return None


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
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "published": snippet.get("publishedAt", "")[:10],
                "description": snippet.get("description", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "view_count": int(statistics.get("viewCount", 0)),
                "like_count": int(statistics.get("likeCount", 0)),
                "comment_count": int(statistics.get("commentCount", 0)),
            }
        return None
    except HttpError as e:
        st.error(f"영상 정보 오류: {e}")
        return None


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
            st.warning("이 영상은 댓글이 비활성화되어 있습니다.")
        else:
            st.error(f"댓글 수집 오류: {e}")
        return []


def format_number(num):
    if num >= 100000000:
        return f"{num / 100000000:.1f}억"
    elif num >= 10000:
        return f"{num / 10000:.1f}만"
    elif num >= 1000:
        return f"{num / 1000:.1f}천"
    return str(num)


def extract_keywords(texts, top_n=20):
    all_words = []
    for text in texts:
        korean_words = re.findall(r'[가-힣]{2,}', text)
        english_words = re.findall(r'[a-zA-Z]{3,}', text.lower())
        all_words.extend(korean_words)
        all_words.extend(english_words)
    filtered = [w for w in all_words if w not in STOPWORDS and len(w) >= 2]
    counter = Counter(filtered)
    return counter.most_common(top_n)


def simple_sentiment(text):
    positive_words = [
        "좋", "최고", "감사", "사랑", "행복", "대박", "멋",
        "훌륭", "완벽", "감동", "응원", "추천", "재밌", "재미",
        "굿", "짱", "아름", "예쁘", "힐링", "기대", "축하",
        "존경", "귀엽", "좋아", "웃기", "꿀잼",
        "love", "great", "good", "best", "amazing", "awesome",
        "nice", "beautiful", "perfect", "wow", "cool", "fantastic",
    ]
    negative_words = [
        "싫", "별로", "나쁘", "최악", "짜증", "화나", "실망",
        "슬프", "힘들", "아쉽", "안타", "걱정", "무섭", "답답",
        "지루", "노잼", "그만", "혐",
        "hate", "bad", "worst", "terrible", "awful", "boring",
        "sad", "angry", "disappointed", "horrible",
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
# 메인 앱
# ============================================================
def main():
    st.markdown('<div class="main-header">🎬 유튜브 댓글 수집 & 분석기</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">유튜브 영상 링크를 입력하면 댓글을 수집하고 분석합니다</div>', unsafe_allow_html=True)

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

        **2단계: Streamlit Cloud Secrets에 등록**
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
    # 수집 실행
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

        st.session_state.comments_data = comments
        st.session_state.video_info = video_info
        st.session_state.video_id = video_id

    elif search_clicked and not url:
        st.warning("⚠️ 유튜브 링크를 입력해주세요!")

    # --------------------------------------------------------
    # 결과 표시
    # --------------------------------------------------------
    if st.session_state.comments_data is None:
        st.info("👆 위에 유튜브 링크를 입력하고 '댓글 수집 시작' 버튼을 눌러주세요!")
        return

    comments = st.session_state.comments_data
    video_info = st.session_state.video_info
    video_id = st.session_state.video_id
    df = pd.DataFrame(comments)

    # 영상 정보 카드
    st.markdown("---")
    st.subheader("📺 영상 정보")

    col_thumb, col_info = st.columns([1, 2])
    with col_thumb:
        if video_info["thumbnail"]:
            st.image(video_info["thumbnail"], use_container_width=True)
    with col_info:
        st.markdown(f"### {video_info['title']}")
        st.markdown(f"**채널:** {video_info['channel']}  |  **게시일:** {video_info['published']}")
        s1, s2, s3 = st.columns(3)
        with s1:
            st.metric("👁️ 조회수", format_number(video_info["view_count"]))
        with s2:
            st.metric("👍 좋아요", format_number(video_info["like_count"]))
        with s3:
            st.metric("💬 댓글수", format_number(video_info["comment_count"]))

    st.success(f"✅ 총 **{len(df)}개**의 댓글을 수집했습니다!")

    # --------------------------------------------------------
    # 탭
    # --------------------------------------------------------
    tab1, tab2, tab3 = st.tabs(["📋 댓글 목록", "📊 데이터 테이블", "🧠 댓글 분석"])

    # ==================== 탭1: 댓글 목록 ====================
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

    # ==================== 탭2: 데이터 테이블 ====================
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

        csv_data = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 CSV 다운로드",
            data=csv_data,
            file_name=f"comments_{video_id}.csv",
            mime="text/csv",
        )

    # ==================== 탭3: 댓글 분석 ====================
    with tab3:
        st.subheader("🧠 댓글 기반 영상 분석")

        with st.spinner("🔍 댓글을 분석하는 중..."):
            all_texts = df["댓글"].tolist()
            keywords = extract_keywords(all_texts, top_n=20)
            df_analysis = df.copy()
            df_analysis["감성"] = df_analysis["댓글"].apply(simple_sentiment)

        # ---- 감성 비율 숫자 카드 ----
        st.markdown("---")
        st.markdown("### 💭 감성 분석 결과")

        sentiment_counts = df_analysis["감성"].value_counts()
        total = len(df_analysis)

        pos_count = sentiment_counts.get("긍정 😊", 0)
        neg_count = sentiment_counts.get("부정 😞", 0)
        neu_count = sentiment_counts.get("중립 😐", 0)

        pos_pct = pos_count / total * 100
        neg_pct = neg_count / total * 100
        neu_pct = neu_count / total * 100

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("😊 긍정", f"{pos_count}개 ({pos_pct:.1f}%)")
        with m2:
            st.metric("😞 부정", f"{neg_count}개 ({neg_pct:.1f}%)")
        with m3:
            st.metric("😐 중립", f"{neu_count}개 ({neu_pct:.1f}%)")

        # ---- 차트 2개 나란히 ----
        st.markdown("---")
        st.markdown("### 📊 시각화")

        chart_col1, chart_col2 = st.columns(2)

        # 파이차트: 감성 비율
        with chart_col1:
            st.markdown("#### 감성 비율 차트")

            labels = sentiment_counts.index.tolist()
            sizes = sentiment_counts.values.tolist()
            colors_map = {
                "긍정 😊": "#4CAF50",
                "부정 😞": "#F44336",
                "중립 😐": "#9E9E9E",
            }
            colors = [colors_map.get(l, "#999") for l in labels]

            fig1, ax1 = plt.subplots(figsize=(5, 5))
            wedges, texts, autotexts = ax1.pie(
                sizes,
                labels=labels,
                autopct='%1.1f%%',
                colors=colors,
                startangle=90,
                textprops={'fontsize': 11},
            )
            for t in autotexts:
                t.set_fontsize(13)
                t.set_fontweight('bold')
            ax1.set_title("Sentiment Ratio", fontsize=14, fontweight='bold', pad=15)
            st.pyplot(fig1)
            plt.close(fig1)

        # 바차트: 키워드 빈도
        with chart_col2:
            st.markdown("#### 핵심 키워드 TOP 15")

            if keywords:
                top_kw = keywords[:15]
                words = [w for w, c in top_kw]
                counts = [c for w, c in top_kw]

                fig2, ax2 = plt.subplots(figsize=(5, 5))
                bar_colors = plt.cm.Reds(
                    [0.3 + 0.7 * (i / max(len(words), 1)) for i in range(len(words))]
                )
                bars = ax2.barh(range(len(words)), counts, color=bar_colors)
                ax2.set_yticks(range(len(words)))
                ax2.set_yticklabels(words, fontsize=10)
                ax2.invert_yaxis()
                ax2.set_xlabel("Frequency", fontsize=11)
                ax2.set_title("Top Keywords", fontsize=14, fontweight='bold')

                for bar, count in zip(bars, counts):
                    ax2.text(
                        bar.get_width() + max(counts) * 0.02,
                        bar.get_y() + bar.get_height() / 2,
                        str(count),
                        va='center', fontsize=10, fontweight='bold',
                    )
                plt.tight_layout()
                st.pyplot(fig2)
                plt.close(fig2)
            else:
                st.info("키워드를 추출할 수 없습니다.")

        # ---- 좋아요 분포 히스토그램 ----
        st.markdown("---")
        st.markdown("#### 👍 댓글 좋아요 분포")

        fig3, ax3 = plt.subplots(figsize=(10, 4))
        like_data = df_analysis["좋아요"]

        if like_data.max() > 0:
            ax3.hist(like_data, bins=30, color="#FF6B6B", edgecolor="white", alpha=0.8)
            ax3.set_xlabel("Likes", fontsize=12)
            ax3.set_ylabel("Count", fontsize=12)
            ax3.set_title("Comment Likes Distribution", fontsize=14, fontweight='bold')
            plt.tight_layout()
            st.pyplot(fig3)
        else:
            st.info("좋아요가 있는 댓글이 없습니다.")
        plt.close(fig3)

        # ---- 날짜별 댓글 수 ----
        st.markdown("---")
        st.markdown("#### 📅 날짜별 댓글 수 추이")

        df_date = df_analysis.copy()
        df_date["작성일"] = pd.to_datetime(df_date["작성일"], errors="coerce")
        df_date = df_date.dropna(subset=["작성일"])

        if not df_date.empty:
            date_counts = df_date.groupby(df_date["작성일"].dt.date).size().reset_index(name="댓글수")
            date_counts = date_counts.sort_values("작성일")

            fig4, ax4 = plt.subplots(figsize=(10, 4))
            ax4.fill_between(date_counts["작성일"], date_counts["댓글수"], alpha=0.3, color="#667eea")
            ax4.plot(date_counts["작성일"], date_counts["댓글수"], color="#667eea", linewidth=2)
            ax4.set_xlabel("Date", fontsize=12)
            ax4.set_ylabel("Comments", fontsize=12)
            ax4.set_title("Comments Over Time", fontsize=14, fontweight='bold')
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig4)
            plt.close(fig4)

        # ---- 종합 영상 분석 ----
        st.markdown("---")
        st.markdown("### 🎯 종합 영상 내용 분석")

        # 반응 판단
        if pos_pct >= 60:
            reaction = "🔥 매우 긍정적"
        elif pos_pct >= 40:
            reaction = "👍 대체로 긍정적"
        elif neg_pct >= 40:
            reaction = "⚠️ 부정적 반응이 많음"
        else:
            reaction = "🤔 다양한 반응"

        # 인기 댓글 Top 5
        top5 = df_analysis.nlargest(5, "좋아요")

        keyword_str = ", ".join([w for w, c in keywords[:10]]) if keywords else "없음"

        st.markdown(f"""
> **📌 영상 제목:** {video_info['title']}
>
> **📺 채널:** {video_info['channel']}

---

**🔑 댓글 핵심 키워드:** {keyword_str}

**📊 전체 시청자 반응:** {reaction}
- 긍정 {pos_pct:.1f}% / 부정 {neg_pct:.1f}% / 중립 {neu_pct:.1f}%

---

**🧠 댓글 기반 영상 내용 추론:**

영상 제목 **"{video_info['title']}"** 과 댓글에서 자주 등장하는 키워드
**{keyword_str}** 를 종합해 보면, 이 영상의 핵심 주제를 파악할 수 있습니다.

시청자 {total}명의 댓글 중 **{pos_pct:.1f}%가 긍정적** 반응을 보이고 있어
전반적으로 **{reaction}** 인 분위기입니다.
        """)

        # 영상 설명글
        desc = video_info.get("description", "")
        if desc:
            with st.expander("📝 영상 설명글 보기"):
                st.text(desc[:1000])

        # 인기 댓글 Top 5
        st.markdown("---")
        st.markdown("#### 🏆 가장 공감받은 댓글 TOP 5")

        for idx, row in top5.iterrows():
            st.markdown(f"""
            <div class="comment-box">
                <div class="comment-author">👤 {row['작성자']}  ·  👍 {row['좋아요']}</div>
                <div class="comment-text">{row['댓글']}</div>
                <div class="comment-meta">감성: {row['감성']}  ·  📅 {row['작성일']}</div>
            </div>
            """, unsafe_allow_html=True)

    # --------------------------------------------------------
    # 하단 안내
    # --------------------------------------------------------
    st.markdown("---")
    with st.expander("ℹ️ 사용 안내"):
        st.markdown("""
        **사용 방법:**
        1. 유튜브 영상 URL을 복사해서 붙여넣기
        2. 수집할 댓글 수 선택
        3. '댓글 수집 시작' 클릭
        4. 댓글 목록, 데이터 테이블, 분석 탭에서 결과 확인

        **지원 URL
