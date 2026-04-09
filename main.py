import streamlit as st
import pandas as pd
import re
import matplotlib.pyplot as plt
import matplotlib
from collections import Counter
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from deep_translator import GoogleTranslator

matplotlib.rcParams['font.family'] = 'DejaVu Sans'
matplotlib.rcParams['axes.unicode_minus'] = False

st.set_page_config(page_title="유튜브 댓글 수집기", page_icon="🎬", layout="wide")

st.markdown("""
<style>
.comment-box {
    background:#f9f9f9; border-left:4px solid #FF0000;
    padding:12px 16px; margin-bottom:10px; border-radius:0 8px 8px 0;
}
.comment-box .author {font-weight:bold; color:#333;}
.comment-box .text {color:#555; margin-top:4px;}
.comment-box .translated {color:#1a73e8; margin-top:6px; font-style:italic;
    background:#e8f0fe; padding:8px; border-radius:6px;}
.comment-box .meta {color:#999; font-size:0.8rem; margin-top:4px;}
</style>
""", unsafe_allow_html=True)

if "comments" not in st.session_state:
    st.session_state.comments = None
    st.session_state.vinfo = None
    st.session_state.vid = None
if "translated" not in st.session_state:
    st.session_state.translated = {}

STOPWORDS = {
    "의","가","이","은","들","는","좀","잘","걍","과","도","를","으로",
    "자","에","와","한","하다","것","그","되","수","보","않","없","나",
    "사람","주","아니","등","같","때","년","하","대","및","더","인","로",
    "에서","하고","해서","그리고","너무","정말","진짜","있","없는","하는",
    "있는","되는","된","할","하면","해도","인데","건데","거","게","네",
    "데","지","요","죠","이거","저거","뭐","어","음","아","오","저","제",
    "많이","다","또","왜","어떻게","합니다","됩니다","입니다","습니다",
    "ㅋㅋ","ㅋㅋㅋ","ㅋㅋㅋㅋ","ㅎㅎ","ㅎㅎㅎ","ㅠㅠ","ㅜㅜ","ㅋ","ㅎ",
    "the","a","an","is","are","was","were","to","of","in","for","on",
    "with","at","by","this","that","it","and","or","but","not","be",
    "have","has","had","do","does","did","will","would","can","could",
    "i","you","he","she","we","they","me","my","your","so","if","just",
    "about","up","out","no","what","all","should",
}

LANG_OPTIONS = {
    "한국어": "ko",
    "영어": "en",
    "일본어": "ja",
    "중국어(간체)": "zh-CN",
    "중국어(번체)": "zh-TW",
    "스페인어": "es",
    "프랑스어": "fr",
    "독일어": "de",
    "러시아어": "ru",
    "베트남어": "vi",
    "태국어": "th",
    "인도네시아어": "id",
    "아랍어": "ar",
    "포르투갈어": "pt",
    "이탈리아어": "it",
}


def translate_text(text, target_lang="ko"):
    """텍스트를 목표 언어로 번역합니다."""
    try:
        if not text or text.strip() == "":
            return ""
        # 5000자 제한
        text = text[:5000]
        result = GoogleTranslator(source='auto', target=target_lang).translate(text)
        return result if result else text
    except Exception:
        return text


def translate_comments_batch(comments_list, target_lang="ko"):
    """여러 댓글을 한번에 번역합니다."""
    translated = []
    for text in comments_list:
        t = translate_text(text, target_lang)
        translated.append(t)
    return translated


def get_api_key():
    try:
        return st.secrets["YOUTUBE_API_KEY"]
    except Exception:
        return None


def extract_video_id(url):
    for p in [r'watch\?v=([a-zA-Z0-9_-]{11})', r'youtu\.be/([a-zA-Z0-9_-]{11})',
              r'shorts/([a-zA-Z0-9_-]{11})', r'embed/([a-zA-Z0-9_-]{11})']:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_video_info(yt, vid):
    try:
        r = yt.videos().list(part="snippet,statistics", id=vid).execute()
        if r["items"]:
            s, st2 = r["items"][0]["snippet"], r["items"][0]["statistics"]
            return {
                "title": s.get("title",""), "channel": s.get("channelTitle",""),
                "published": s.get("publishedAt","")[:10],
                "description": s.get("description",""),
                "thumbnail": s.get("thumbnails",{}).get("high",{}).get("url",""),
                "views": int(st2.get("viewCount",0)),
                "likes": int(st2.get("likeCount",0)),
                "comments": int(st2.get("commentCount",0)),
            }
    except HttpError as e:
        st.error(f"오류: {e}")
    return None


def get_comments(yt, vid, max_n=100):
    comments, npt = [], None
    try:
        while len(comments) < max_n:
            r = yt.commentThreads().list(
                part="snippet", videoId=vid,
                maxResults=min(100, max_n-len(comments)),
                pageToken=npt, order="relevance", textFormat="plainText"
            ).execute()
            for item in r.get("items",[]):
                sn = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "작성자": sn.get("authorDisplayName",""),
                    "댓글": sn.get("textDisplay",""),
                    "좋아요": sn.get("likeCount",0),
                    "작성일": sn.get("publishedAt","")[:10],
                })
            npt = r.get("nextPageToken")
            if not npt:
                break
    except HttpError as e:
        st.error(f"댓글 수집 오류: {e}")
    return comments


def fmt(n):
    if n >= 1e8: return f"{n/1e8:.1f}억"
    if n >= 1e4: return f"{n/1e4:.1f}만"
    if n >= 1e3: return f"{n/1e3:.1f}천"
    return str(n)


def extract_keywords(texts, top_n=15):
    words = []
    for t in texts:
        words += re.findall(r'[가-힣]{2,}', t)
        words += re.findall(r'[a-zA-Z]{3,}', t.lower())
    filtered = [w for w in words if w not in STOPWORDS]
    return Counter(filtered).most_common(top_n)


def sentiment(text):
    pos = ["좋","최고","감사","사랑","대박","멋","훌륭","완벽","감동","추천",
           "재밌","재미","굿","짱","힐링","기대","귀엽","웃기","꿀잼",
           "love","great","good","best","amazing","awesome","nice","perfect","wow","cool"]
    neg = ["싫","별로","나쁘","최악","짜증","화나","실망","슬프","힘들","아쉽",
           "답답","지루","노잼","혐","hate","bad","worst","terrible","boring","sad","angry"]
    t = text.lower()
    p = sum(1 for w in pos if w in t)
    n = sum(1 for w in neg if w in t)
    if p > n: return "긍정"
    if n > p: return "부정"
    return "중립"


# ============================================================
# 메인
# ============================================================
def main():
    st.markdown("## 🎬 유튜브 댓글 수집 & 분석기")

    api_key = get_api_key()
    if not api_key:
        st.error("🔑 API 키가 없습니다. Streamlit Secrets에 YOUTUBE_API_KEY를 등록하세요.")
        return

    yt = build("youtube", "v3", developerKey=api_key)

    # 입력
    c1, c2 = st.columns([3,1])
    with c1:
        url = st.text_input("🔗 유튜브 링크", placeholder="https://www.youtube.com/watch?v=...")
    with c2:
        max_n = st.selectbox("수집 수", [50,100,200,500,1000], index=1)

    if st.button("🔍 댓글 수집 시작", use_container_width=True, type="primary"):
        if not url:
            st.warning("링크를 입력해주세요!")
            return
        vid = extract_video_id(url)
        if not vid:
            st.error("올바른 유튜브 링크가 아닙니다!")
            return
        with st.spinner("수집 중..."):
            vinfo = get_video_info(yt, vid)
            if not vinfo:
                st.error("영상 정보를 찾을 수 없습니다.")
                return
            comments = get_comments(yt, vid, max_n)
            if not comments:
                st.warning("댓글이 없습니다.")
                return
        st.session_state.comments = comments
        st.session_state.vinfo = vinfo
        st.session_state.vid = vid
        st.session_state.translated = {}

    if st.session_state.comments is None:
        st.info("👆 유튜브 링크를 입력하고 버튼을 눌러주세요!")
        return

    df = pd.DataFrame(st.session_state.comments)
    vi = st.session_state.vinfo

    # 영상 정보
    st.markdown("---")
    c1, c2 = st.columns([1,2])
    with c1:
        if vi["thumbnail"]:
            st.image(vi["thumbnail"], use_container_width=True)
    with c2:
        st.markdown(f"### {vi['title']}")
        st.caption(f"📺 {vi['channel']}  |  📅 {vi['published']}")
        m1,m2,m3 = st.columns(3)
        m1.metric("👁️ 조회수", fmt(vi["views"]))
        m2.metric("👍 좋아요", fmt(vi["likes"]))
        m3.metric("💬 댓글", fmt(vi["comments"]))

    st.success(f"✅ {len(df)}개 댓글 수집 완료!")

    # 탭
    tab1, tab2, tab3, tab4 = st.tabs(["📋 댓글 목록", "🌐 번역", "📊 데이터 테이블", "🧠 댓글 분석"])

    # ==================== 탭1: 댓글 목록 ====================
    with tab1:
        sort = st.selectbox("정렬", ["관련성순","좋아요순","최신순","오래된순"], key="sort")
        d = df.copy()
        if sort == "좋아요순": d = d.sort_values("좋아요", ascending=False)
        elif sort == "최신순": d = d.sort_values("작성일", ascending=False)
        elif sort == "오래된순": d = d.sort_values("작성일", ascending=True)
        d = d.reset_index(drop=True)

        q = st.text_input("🔍 검색", key="q")
        if q:
            d = d[d["댓글"].str.contains(q, case=False, na=False)].reset_index(drop=True)
            st.info(f"검색 결과: {len(d)}개")

        for _, r in d.iterrows():
            st.markdown(f"""<div class="comment-box">
                <div class="author">👤 {r['작성자']}</div>
                <div class="text">{r['댓글']}</div>
                <div class="meta">👍 {r['좋아요']}  ·  📅 {r['작성일']}</div>
            </div>""", unsafe_allow_html=True)

    # ==================== 탭2: 번역 ====================
    with tab2:
        st.subheader("🌐 댓글 번역")

        tc1, tc2 = st.columns([1,1])
        with tc1:
            target_name = st.selectbox("번역할 언어 선택", list(LANG_OPTIONS.keys()), key="lang")
        with tc2:
            translate_count = st.selectbox(
                "번역할 댓글 수",
                [10, 20, 50, 100, "전체"],
                index=0,
                key="tr_count"
            )

        target_code = LANG_OPTIONS[target_name]

        if st.button("🌐 번역 시작", use_container_width=True, type="primary", key="tr_btn"):
            if translate_count == "전체":
                n = len(df)
            else:
                n = min(int(translate_count), len(df))

            texts = df["댓글"].tolist()[:n]
            translated_list = []

            progress = st.progress(0)
            status = st.empty()

            for i, text in enumerate(texts):
                status.text(f"번역 중... {i+1}/{n}")
                t = translate_text(text, target_code)
                translated_list.append(t)
                progress.progress((i+1)/n)

            progress.empty()
            status.empty()

            st.session_state.translated = {
                "lang": target_name,
                "results": translated_list,
                "count": n
            }
            st.success(f"✅ {n}개 댓글 번역 완료! ({target_name})")

        # 번역 결과 표시
        if st.session_state.translated:
            tr = st.session_state.translated
            st.markdown(f"#### 📝 번역 결과 ({tr['lang']}, {tr['count']}개)")

            sort_tr = st.selectbox("정렬", ["관련성순","좋아요순","최신순"], key="sort_tr")
            d_tr = df.head(tr["count"]).copy()
            d_tr["번역"] = tr["results"]

            if sort_tr == "좋아요순":
                d_tr = d_tr.sort_values("좋아요", ascending=False).reset_index(drop=True)
            elif sort_tr == "최신순":
                d_tr = d_tr.sort_values("작성일", ascending=False).reset_index(drop=True)

            search_tr = st.text_input("🔍 번역 결과에서 검색", key="q_tr")
            if search_tr:
                mask = (d_tr["댓글"].str.contains(search_tr, case=False, na=False) |
                        d_tr["번역"].str.contains(search_tr, case=False, na=False))
                d_tr = d_tr[mask].reset_index(drop=True)
                st.info(f"검색 결과: {len(d_tr)}개")

            for _, r in d_tr.iterrows():
                st.markdown(f"""<div class="comment-box">
                    <div class="author">👤 {r['작성자']}</div>
                    <div class="text">{r['댓글']}</div>
                    <div class="translated">🌐 {r['번역']}</div>
                    <div class="meta">👍 {r['좋아요']}  ·  📅 {r['작성일']}</div>
                </div>""", unsafe_allow_html=True)

            # 번역 결과 CSV 다운로드
            csv_tr = d_tr.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                "📥 번역 결과 CSV 다운로드", csv_tr,
                f"translated_{st.session_state.vid}.csv", "text/csv"
            )

    # ==================== 탭3: 데이터 테이블 ====================
    with tab3:
        st.dataframe(df, use_container_width=True, height=400)
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("총 댓글", f"{len(df)}개")
        m2.metric("평균 좋아요", f"{df['좋아요'].mean():.1f}")
        m3.metric("최다 좋아요", f"{df['좋아요'].max()}")
        m4.metric("작성자 수", f"{df['작성자'].nunique()}명")
        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥 CSV", csv, f"comments_{st.session_state.vid}.csv", "text/csv")

    # ==================== 탭4: 분석 ====================
    with tab3_analysis := tab4:
        st.subheader("🧠 댓글 분석")

        df_a = df.copy()
        df_a["감성"] = df_a["댓글"].apply(sentiment)
        total = len(df_a)
        sc = df_a["감성"].value_counts()
        pos_n = sc.get("긍정",0)
        neg_n = sc.get("부정",0)
        neu_n = sc.get("중립",0)
        pos_p, neg_p, neu_p = pos_n/total*100, neg_n/total*100, neu_n/total*100

        m1,m2,m3 = st.columns(3)
        m1.metric("😊 긍정", f"{pos_n}개 ({pos_p:.1f}%)")
        m2.metric("😞 부정", f"{neg_n}개 ({neg_p:.1f}%)")
        m3.metric("😐 중립", f"{neu_n}개 ({neu_p:.1f}%)")

        keywords = extract_keywords(df["댓글"].tolist())

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 감성 비율")
            fig1, ax1 = plt.subplots(figsize=(5,5))
            labels = sc.index.tolist()
            sizes = sc.values.tolist()
            cmap = {"긍정":"#4CAF50","부정":"#F44336","중립":"#9E9E9E"}
            colors = [cmap.get(l,"#999") for l in labels]
            ax1.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
            ax1.set_title("Sentiment", fontsize=14, fontweight='bold')
            st.pyplot(fig1)
            plt.close(fig1)

        with col2:
            st.markdown("#### 핵심 키워드 TOP 15")
            if keywords:
                words = [w for w,c in keywords]
                counts = [c for w,c in keywords]
                fig2, ax2 = plt.subplots(figsize=(5,5))
                bar_c = plt.cm.Reds([0.3+0.7*(i/len(words)) for i in range(len(words))])
                bars = ax2.barh(range(len(words)), counts, color=bar_c)
                ax2.set_yticks(range(len(words)))
                ax2.set_yticklabels(words)
                ax2.invert_yaxis()
                ax2.set_title("Top Keywords", fontsize=14, fontweight='bold')
                for b,c in zip(bars,counts):
                    ax2.text(b.get_width()+max(counts)*0.02, b.get_y()+b.get_height()/2,
                             str(c), va='center', fontsize=10, fontweight='bold')
                plt.tight_layout()
                st.pyplot(fig2)
                plt.close(fig2)

        st.markdown("---")
        st.markdown("#### 👍 좋아요 분포")
        fig3, ax3 = plt.subplots(figsize=(10,3))
        ax3.hist(df_a["좋아요"], bins=30, color="#FF6B6B", edgecolor="white")
        ax3.set_xlabel("Likes"); ax3.set_ylabel("Count")
        ax3.set_title("Likes Distribution", fontweight='bold')
        plt.tight_layout(); st.pyplot(fig3); plt.close(fig3)

        st.markdown("---")
        st.markdown("#### 📅 날짜별 댓글 추이")
        df_d = df_a.copy()
        df_d["작성일"] = pd.to_datetime(df_d["작성일"], errors="coerce")
        df_d = df_d.dropna(subset=["작성일"])
        if not df_d.empty:
            dc = df_d.groupby(df_d["작성일"].dt.date).size().reset_index(name="n")
            dc = dc.sort_values("작성일")
            fig4, ax4 = plt.subplots(figsize=(10,3))
            ax4.fill_between(dc["작성일"], dc["n"], alpha=0.3, color="#667eea")
            ax4.plot(dc["작성일"], dc["n"], color="#667eea", linewidth=2)
            ax4.set_title("Comments Over Time", fontweight='bold')
            plt.xticks(rotation=45); plt.tight_layout(); st.pyplot(fig4); plt.close(fig4)

        st.markdown("---")
        st.markdown("### 🎯 종합 분석")

        if pos_p >= 60: reaction = "🔥 매우 긍정적"
        elif pos_p >= 40: reaction = "👍 대체로 긍정적"
        elif neg_p >= 40: reaction = "⚠️ 부정적 반응 많음"
        else: reaction = "🤔 반응 다양"

        kw_str = ", ".join([w for w,c in keywords[:10]]) if keywords else "없음"
        top5 = df_a.nlargest(5, "좋아요")
        top5_str = ""
        for _, r in top5.iterrows():
            top5_str += f"- 👍{r['좋아요']} | {r['댓글'][:60]}...\n"

        st.markdown(f"""
**📌 영상:** {vi['title']}

**🔑 핵심 키워드:** {kw_str}

**📊 시청자 반응:** {reaction} (긍정 {pos_p:.1f}% / 부정 {neg_p:.1f}% / 중립 {neu_p:.1f}%)

**🧠 분석 요약:**
댓글에서 자주 등장하는 키워드 **{kw_str}** 를 통해 영상의 주요 주제를 파악할 수 있습니다.
총 {total}개 댓글 중 긍정 반응이 {pos_p:.1f}%로, 전반적으로 **{reaction}** 분위기입니다.

**🏆 인기 댓글 TOP 5:**
{top5_str}
        """)

        desc = vi.get("description","")
        if desc:
            with st.expander("📝 영상 설명글 보기"):
                st.text(desc[:1000])


if __name__ == "__main__":
    main()
