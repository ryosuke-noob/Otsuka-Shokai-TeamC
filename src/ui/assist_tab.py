# ui/assist_tab.py

import streamlit as st
import state
import utils
from services.dedup import dedup_questions
from streamlit.components.v1 import html as st_html
import html as _py_html

def render_summary_scroller(text: str, max_lines: int = 5, key: str = "live_summary"):
    # Markdownを完璧に解釈しない前提で、箇条書きテキストをそのまま表示
    # （必要なら markdown ライブラリで HTML 化してもOK）
    safe = _py_html.escape(text or "（要約を生成中…）").replace("\n", "<br>")
    # 1行の高さを1.5emとして、max_linesぶん＋パディングで高さを制限
    html_code = f"""
<div id="{key}" style="
  font-size: 0.95rem; 
  line-height: 1.5em;
  max-height: calc(1.5em * {max_lines} + 12px);
  overflow-y: auto;
  padding: 8px 10px;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 12px;
  background: rgba(255,255,255,.03);
  color: rgba(255,255,255,1);
">
  {safe}
  <div id="{key}-bottom" style="height:1px;"></div>
</div>
<script>
  const el = document.getElementById("{key}");
  function scrollBottom() {{
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }}
  // 初回＆再描画直後、レイアウト確定後にも実行
  scrollBottom();
  setTimeout(scrollBottom, 30);
  setTimeout(scrollBottom, 120);
</script>
"""
    # iframe の高さは内部の max-height + 余白より少し大きめに
    # 5行想定なら 140〜170px 程度が目安
    st_html(html_code, height=int(24 * max_lines + 60))


def summary_fragment():
    summarizer = st.session_state.get("sum")
    latest = summarizer.summary_markdown() if summarizer else None
    if latest is not None:
        st.session_state["summary_markdown"] = latest

    shared = st.session_state.get("shared_tr")
    latest_transcript = shared.get()
    if latest_transcript is not None:
        st.session_state["transcript_text"] = latest_transcript
    
    st.subheader("🧾 ライブ要約")
    #st.markdown(st.session_state.get("summary_markdown", "（要約を生成中…）"))
    render_summary_scroller(
        st.session_state.get("summary_markdown", "（要約を生成中…）"),
        max_lines=5,
        key="live_summary"
    )

@st.fragment(run_every="2s")
def _sync_snapshots_fragment():
    # メモと要約をスナップショットに常時コピー
    st.session_state["note_text_snapshot"] = st.session_state.get("note_text", "")
    st.session_state["summary_markdown_snapshot"] = st.session_state.get("summary_markdown", "")
    st.session_state["transcript_text_snapshot"] = st.session_state.get("transcript_text", "")


@st.fragment(run_every="5s")
def _render_assist_tab():
    all_tags_options = sorted(list(set(tag for q in st.session_state.get("questions", []) for tag in q.get("tags", []))))

    left, right = st.columns([0.55, 0.45], gap="large")

    with left:
        st.subheader("📝 メモ")
        st.text_area(
            "メモ", 
            height=260, 
            key="note_text", # keyを通じて st.session_state.note_text と自動的に同期されます
            label_visibility="collapsed"
        )
        if st.button("メモをDBへ保存", use_container_width=True):
            state._save_note_to_db()
        
    # ライブ要約セクション
    st.divider()
    summary_fragment()

    with right:
        st.subheader("🔥 今すぐ聞くべき3問")
        qs = st.session_state.get("questions", [])
        # enumerateのインデックスを第2ソートキーにして、同点なら新しい（インデックスが大きい）方を優先
        unanswered_enum = [(idx, q) for idx, q in enumerate(qs) if q.get("status") == "unanswered"]
        top3_pairs = sorted(
            unanswered_enum,
            key=lambda t: (t[1].get("priority", 50), t[0]),
            reverse=True
        )[:3]
        top3 = [q for _, q in top3_pairs]
        
        # 縦に並べる：各アイテムを1列で順番に表示
        for i, q in enumerate(top3):
            with st.container(border=True):
                # 左=質問文／右=操作ボタン（横並び）
                left_q, right_btns = st.columns([0.75, 0.25], gap="medium")
                with left_q:
                    tags_html = " ".join(f'<span class="badge">#{t}</span>' for t in q.get("tags", []))
                    st.markdown(f"**#{i+1}** P: {int(q.get('priority',50))} {tags_html}", unsafe_allow_html=True)
                    st.markdown(
                        f'<div style="min-height:36px;">{q.get("text","")}</div>',
                        unsafe_allow_html=True
                    )
                with right_btns:
                    b1, b2, b3 = st.columns(3, gap="small")
                    qid = q.get("id")
                    with b1:
                        if st.button("✅", key=f"top3_ok_{i}", help="聞けた", use_container_width=True):
                            if qid: state._set_status(qid, "resolved")
                            else: q['status'] = 'resolved'
                            st.rerun()
                    with b2:
                        if st.button("🧳", key=f"top3_take_{i}", help="持ち帰り", use_container_width=True):
                            if qid: state._set_status(qid, "take_home")
                            else: q['status'] = 'take_home'
                            st.rerun()
                    with b3:
                        if st.button("🕒", key=f"top3_hold_{i}", help="保留", use_container_width=True):
                            if qid: state._set_status(qid, "on_hold")
                            else: q['status'] = 'on_hold'
                            st.rerun()

    st.divider()
    st.subheader("📋 質問リスト")
    
    filter_cols = st.columns([2, 1.5, 1.5])
    with filter_cols[0]:
        search_keyword = st.text_input("キーワード検索", placeholder="質問内容で絞り込み...")
    
    with filter_cols[1]:
        selected_tags = st.multiselect("タグでフィルター", options=all_tags_options)
    
    with filter_cols[2]:
        status_options = ["すべて"] + utils.JP_ORDER
        selected_status = st.selectbox("取得状況でフィルター", options=status_options)

    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        with c1:
            new_q_text = st.text_input("新しい質問を入力", key="q_add_text", placeholder="新しい質問を入力してください")
        with c2:
            # `state`モジュールから関数を呼び出す
            st.button("追加", on_click=state.add_question_callback, use_container_width=True)

    filtered_list = st.session_state.get("questions", [])
    if search_keyword:
        filtered_list = [q for q in filtered_list if search_keyword.lower() in q.get("text", "").lower()]
    if selected_tags:
        filtered_list = [q for q in filtered_list if all(tag in q.get("tags", []) for tag in selected_tags)]
    if selected_status != "すべて":
        status_en = utils.EN[selected_status]
        filtered_list = [q for q in filtered_list if q.get("status") == status_en]

    st.caption(f"表示件数: {len(filtered_list)}件")
    for i, q in enumerate(filtered_list):
        # ウィジェットのkeyには、idが存在しない場合も考慮し、ループのインデックスiを使う
        unique_key_prefix = q.get("id") or f"new_q_{i}"

        with st.container(border=True):
            st.markdown(q.get("text", ""))
            c1, c2, c3 = st.columns([2.5, 1, 1.5])

            with c1:
                q_tags = q.get("tags", [])
                new_tags = st.multiselect(
                    "Tags", 
                    options=all_tags_options + [t for t in q_tags if t not in all_tags_options],
                    default=q_tags, 
                    key=f"tags_{unique_key_prefix}", 
                    label_visibility="collapsed"
                )
                if set(new_tags) != set(q_tags):
                    q["tags"] = new_tags
                    st.rerun()
            
            with c2:
                p_val = int(q.get("priority", 50))
                new_p = st.number_input("優先度", 0, 100, p_val, key=f"p_{unique_key_prefix}", label_visibility="collapsed")
                if new_p != p_val: 
                    q["priority"] = new_p
                    if q.get("id"):
                        state._set_priority(q["id"], new_p)
                    st.rerun()

            with c3:
                s_idx = utils.JP_ORDER.index(utils.JP.get(q.get('status'), '未取得'))
                new_s_jp = st.selectbox("ステータス", utils.JP_ORDER, index=s_idx, key=f"s_{unique_key_prefix}", label_visibility="collapsed")
                if utils.EN[new_s_jp] != q.get('status'): 
                    if q.get("id"):
                        state._set_status(q["id"], utils.EN[new_s_jp])
                    else:
                        q['status'] = utils.EN[new_s_jp]
                    st.rerun()

    if st.button("質問リストの変更をDBへ保存", use_container_width=True, type="primary"):
        state._save_questions_to_db()

def render_assist_tab():
    _render_assist_tab()
    _sync_snapshots_fragment()