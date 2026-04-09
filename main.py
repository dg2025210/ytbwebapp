import streamlit as st
import pandas as pd
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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
    .stat-card {
        background: linear-gradient(135deg, #FF0000, #CC0000);
        color: white;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# YouTube API 키 가져오기
# ============================================================
def get_api_key():
    """Streamlit secrets에서 API 키를 가져옵니다."""
    try:
        return st.secrets["YOUTUBE_API_KEY"]
    except Exception:
        return None

# ============================================================
# 유튜브 영상 ID 추출
# ============================================================
def extract_video_id(url):
    """
    다양한 유튜브 URL 형식에서 영상 ID를 추출합니다.
    지원 형식:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    """
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',
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
    """영상의 기본 정보를 가져옵니다."""
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
                "description": snippet.get("description", "")[:200],
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
    """
    영상의 댓글을 가져옵니다.
    max_comments: 최대 수집 댓글 수
    """
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
                comment_data = {
                    "작성자": snippet.get("authorDisplayName", "익명"),
                    "댓글": snippet.get("textDisplay", ""),
                    "좋아요": snippet.get("likeCount", 0),
                    "작성일": snippet.get("publishedAt", "")[:10],
                    "수정일": snippet.get("updatedAt", "")[:10],
                }
                comments.append(comment_data)

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        return comments

    except HttpError as e:
        error_reason = e.error_details[0]["reason"] if e.error_details else "unknown"
        if error_reason == "commentsDisabled":
            st.warning("⚠️ 이 영상은 댓글이 비활성화되어 있습니다.")
        elif error_reason == "forbidden":
            st.error("🚫 API 키 권한이 부족합니다. YouTube Data API v3이 활성화되어 있는지 확인하세요.")
        else:
            st.error(f"댓글을 가져오는 중 오류 발생: {e}")
        return []

# ============================================================
# 숫자 포맷팅
# ============================================================
def format_number(num):
    """큰 숫자를 보기 좋게 포맷합니다."""
    if num >= 100000000:
        return f"{num / 100000000:.1f}억"
    elif num >= 10000:
        return f"{num / 10000:.1f}만"
    elif num >= 1000:
        return f"{num / 1000:.1f}천"
    return str(num)

# ============================================================
# 메인 앱
# ============================================================
def main():
    # 헤더
    st.markdown('<div class="main-header">🎬 유튜브 댓글 수집기</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">유튜브 영상 링크를 입력하면 댓글을 수집하고 분석합니다</div>', unsafe_allow_html=True)

    # API 키 확인
    api_key = get_api_key()

    if not api_key or api_key == "여기에_본인의_YouTube_Data_API_v3_키를_입력하세요":
        st.error("🔑 YouTube API 키가 설정되지 않았습니다!")
        st.info("""
        **API 키 설정 방법:**

        **1단계: Google Cloud Console에서 API 키 발급**
        1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
        2. 새 프로젝트 생성 또는 기존 프로젝트 선택
        3. 'API 및 서비스' → '라이브러리'에서 **YouTube Data API v3** 검색 후 활성화
        4. 'API 및 서비스' → '사용자 인증 정보' → 'API 키 만들기'

        **2단계: Streamlit Cloud에 API 키 등록**
        1. Streamlit Cloud 앱 대시보드 접속
        2. 앱 선택 → **Settings** → **Secrets**
        3. 아래 내용을 입력:
        ```
        YOUTUBE_API_KEY = "발급받은_API_키"
        ```
        """)
        return

    # YouTube API 클라이언트 생성
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
            help="유튜브 영상의 URL을 붙여넣기 하세요"
        )

    with col_option:
        max_comments = st.selectbox(
            "📊 수집할 댓글 수",
            options=[50, 100, 200, 500, 1000],
            index=1,
            help="수집할 최대 댓글 수를 선택하세요"
        )

    # 수집 버튼
    search_clicked = st.button("🔍 댓글 수집 시작", use_container_width=True, type="primary")

    # --------------------------------------------------------
    # 댓글 수집 및 표시
    # --------------------------------------------------------
    if search_clicked and url:
        # 영상 ID 추출
        video_id = extract_video_id(url)

        if not video_id:
            st.error("❌ 올바른 유튜브 링크를 입력해주세요!")
            return

        # 영상 정보 가져오기
        with st.spinner("📡 영상 정보를 불러오는 중..."):
            video_info = get_video_info(youtube, video_id)

        if not video_info:
            st.error("❌ 영상 정보를 찾을 수 없습니다. 링크를 확인해주세요.")
            return

        # 영상 정보 표시
        st.markdown("---")
        st.subheader("📺 영상 정보")

        col_thumb, col_info = st.columns([1, 2])

        with col_thumb:
            if video_info["thumbnail"]:
                st.image(video_info["thumbnail"], use_container_width=True)

        with col_info:
            st.markdown(f"### {video_info['title']}")
            st.markdown(f"**채널:** {video_info['channel']}")
            st.markdown(f"**게시일:** {video_info['published']}")

            stat1, stat2, stat3 = st.columns(3)
            with stat1:
                st.metric("👁️ 조회수", format_number(video_info["view_count"]))
            with stat2:
                st.metric("👍 좋아요", format_number(video_info["like_count"]))
            with stat3:
                st.metric("💬 댓글수", format_number(video_info["comment_count"]))

        # 댓글 수집
        st.markdown("---")
        st.subheader("💬 댓글 수집")

        with st.spinner(f"📝 댓글을 수집하는 중... (최대 {max_comments}개)"):
            comments = get_comments(youtube, video_id, max_comments)

        if not comments:
            st.warning("수집된 댓글이 없습니다.")
            return

        st.success(f"✅ 총 **{len(comments)}개**의 댓글을 수집했습니다!")

        # DataFrame 생성
        df = pd.DataFrame(comments)

        # --------------------------------------------------------
        # 탭으로 결과 표시
        # --------------------------------------------------------
        tab1, tab2, tab3 = st.tabs(["📋 댓글 목록", "📊 데이터 테이블", "⬇️ 다운로드"])

        # 탭1: 댓글 목록 (카드 형식)
        with tab1:
            # 정렬 옵션
            sort_option = st.selectbox(
                "정렬 기준",
                ["관련성순 (기본)", "좋아요 많은순", "최신순", "오래된순"]
            )

            df_sorted = df.copy()
            if sort_option == "좋아요 많은순":
                df_sorted = df_sorted.sort_values("좋아요", ascending=False)
            elif sort_option == "최신순":
                df_sorted = df_sorted.sort_values("작성일", ascending=False)
            elif sort_option == "오래된순":
                df_sorted = df_sorted.sort_values("작성일", ascending=True)

            # 검색 필터
            search_term = st.text_input("🔍 댓글 내 검색", placeholder="검색어를 입력하세요...")
            if search_term:
                df_sorted = df_sorted[
                    df_sorted["댓글"].str.contains(search_term, case=False, na=False)
                ]
                st.info(f"'{search_term}' 검색 결과: {len(df_sorted)}개")

            # 댓글 표시
            for idx, row in df_sorted.iterrows():
                st.markdown(f"""
                <div class="comment-box">
                    <div class="comment-author">👤 {row['작성자']}</div>
                    <div class="comment-text">{row['댓글']}</div>
                    <div class="comment-meta">👍 {row['좋아요']}  ·  📅 {row['작성일']}</div>
                </div>
                """, unsafe_allow_html=True)

        # 탭2: 데이터 테이블
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
                    "수정일": st.column_config.TextColumn("✏️ 수정일", width="small"),
                }
            )

            # 간단한 통계
            st.markdown("#### 📈 간단 통계")
            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
            with stat_col1:
                st.metric("총 댓글 수", f"{len(df)}개")
            with stat_col2:
                st.metric("평균 좋아요", f"{df['좋아요'].mean():.1f}개")
            with stat_col3:
                st.metric("최다 좋아요", f"{df['좋아요'].max()}개")
            with stat_col4:
                unique_authors = df["작성자"].nunique()
                st.metric("작성자 수", f"{unique_authors}명")

        # 탭3: 다운로드
        with tab3:
            st.markdown("#### 📥 댓글 데이터 다운로드")

            col_dl1, col_dl2 = st.columns(2)

            with col_dl1:
                # CSV 다운로드
                csv_data = df.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="📄 CSV 파일 다운로드",
                    data=csv_data,
                    file_name=f"youtube_comments_{video_id}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            with col_dl2:
                # TXT 다운로드
                txt_lines = []
                for _, row in df.iterrows():
                    txt_lines.append(
                        f"[{row['작성자']}] ({row['작성일']}) 좋아요:{row['좋아요']}\n{row['댓글']}\n"
                    )
                txt_data = "\n".join(txt_lines)
                st.download_button(
                    label="📝 TXT 파일 다운로드",
                    data=txt_data.encode("utf-8"),
                    file_name=f"youtube_comments_{video_id}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

            st.info("💡 CSV 파일은 엑셀에서 바로 열 수 있습니다. (UTF-8 인코딩)")

    elif search_clicked and not url:
        st.warning("⚠️ 유튜브 링크를 입력해주세요!")

    # --------------------------------------------------------
    # 하단 안내
    # --------------------------------------------------------
    st.markdown("---")
    with st.expander("ℹ️ 사용 안내"):
        st.markdown("""
        **사용 방법:**
        1. 유튜브 영상의 URL을 복사합니다
        2. 위 입력창에 붙여넣기 합니다
        3. 수집할 댓글 수를 선택합니다
        4. '댓글 수집 시작' 버튼을 클릭합니다
        5. 수집된 댓글을 확인하고 다운로드합니다

        **지원되는 URL 형식:**
        - `https://www.youtube.com/watch?v=...`
        - `https://youtu.be/...`
        - `https://www.youtube.com/shorts/...`

        **참고 사항:**
        - YouTube Data API v3의 일일 할당량이 있습니다 (기본 10,000 단위)
        - 댓글이 비활성화된 영상은 수집할 수 없습니다
        - 대댓글(답글)은 수집하지 않으며, 최상위 댓글만 수집합니다
        """)


if __name__ == "__main__":
    main()
