# # ui/assist_tab.py

# import streamlit as st
# import state
# import utils
# from services.dedup import dedup_questions

# def render_assist_tab():
#     # --- ここが重要(1): ページ全体を左右の2カラムに分割 ---
#     left, right = st.columns([0.55, 0.45], gap="large")

#     # --- 左パネル: メモ ---
#     with left:
#         st.subheader("📝 メモ")
#         st.session_state.note_text = st.text_area(
#             "メモ", height=260, value=st.session_state.get("note_text", ""), label_visibility="collapsed"
#         )
#         if st.button("メモをDBへ保存", use_container_width=True):
#             state._save_note_to_db()

#     # --- 右パネル: Top3の質問 ---
#     with right:
#         st.subheader("🔥 今すぐ聞くべき3問")
#         unanswered = [q for q in st.session_state.questions if q.get("status") == "unanswered"]
#         top3 = sorted(unanswered, key=lambda x: x.get("priority", 0.5), reverse=True)[:3]
        
#         # --- ここが重要(2): 右パネル内をさらに3つのカラムに分割して横並びにする ---
#         cols = st.columns(len(top3) if top3 else 1)
        
#         for i, q in enumerate(top3):
#             with cols[i]:  # 各カラムに1つずつ質問カードを描画
#                 with st.container(border=True, height=290):
#                     st.markdown(f"**#{i+1}**")
#                     # 質問内容の表示（高さが揃うように最小高さを設定）
#                     st.markdown(f'<div style="min-height: 80px;">{q.get("text", "")}</div>', unsafe_allow_html=True)
                    
#                     tags_html = " ".join(f'<span class="badge">#{t}</span>' for t in q.get("tags", []))
#                     st.markdown(f"P: {int(q.get('priority',0.5)*100)} {tags_html}", unsafe_allow_html=True)
#                     qid = q.get("id", str(id(q)))
                    
#                     # ボタン
#                     if st.button("✅ 聞けた", key=f"top3_ok_{qid}", use_container_width=True):
#                         state._set_status(q["id"], "resolved"); st.rerun()
#                     if st.button("🧳 持ち帰り", key=f"top3_take_{qid}", use_container_width=True):
#                         state._set_status(q["id"], "take_home"); st.rerun()
#                     if st.button("🕒 保留", key=f"top3_hold_{qid}", use_container_width=True):
#                         state._set_status(q["id"], "on_hold"); st.rerun()

#     st.divider()
#     st.subheader("📋 質問リスト")
    
#     # --- フィルター機能 ---
#     filter_cols = st.columns([2, 1.5, 1.5])
#     with filter_cols[0]:
#         search_keyword = st.text_input("キーワード検索", placeholder="質問内容で絞り込み...")
    
#     all_tags = sorted(list(set(tag for q in st.session_state.get("questions", []) for tag in q.get("tags", []))))
#     with filter_cols[1]:
#         selected_tags = st.multiselect("タグでフィルター", options=all_tags)
    
#     with filter_cols[2]:
#         status_options = ["すべて"] + utils.JP_ORDER
#         selected_status = st.selectbox("取得状況でフィルター", options=status_options)

#     # --- 質問追加ロジック ---
#     with st.container(border=True):
#         c1, c2 = st.columns([4, 1])
#         with c1:
#             new_q_text = st.text_input("新しい質問を入力", key="q_add_text", placeholder="新しい質問を入力してください")
#         with c2:
#             if st.button("追加", use_container_width=True):
#                 if new_q_text:
#                     st.session_state.questions.append({
#                         "id": None, "text": new_q_text, "tags": [],
#                         "priority": 50, "status": "unanswered", "source": "ui"
#                     })
#                     st.session_state.questions = dedup_questions(st.session_state.questions, 0.9)
#                     st.session_state.q_add_text = ""
#                     st.rerun()

#     # --- フィルターロジック ---
#     filtered_list = st.session_state.get("questions", [])
#     if search_keyword:
#         filtered_list = [q for q in filtered_list if search_keyword.lower() in q.get("text", "").lower()]
#     if selected_tags:
#         filtered_list = [q for q in filtered_list if all(tag in q.get("tags", []) for tag in selected_tags)]
#     if selected_status != "すべて":
#         status_en = utils.EN[selected_status]
#         filtered_list = [q for q in filtered_list if q.get("status") == status_en]

#     # --- 質問リストの表示 ---
#     st.caption(f"表示件数: {len(filtered_list)}件")
#     for q in filtered_list:
#         qid = q.get("id", str(id(q)))
#         with st.container(border=True):
#             c1, c2, c3 = st.columns([4, 1, 1.5])
#             c1.markdown(q.get("text", ""))
            
#             p_val = int(q.get("priority", 0.5) * 100)
#             new_p = c2.number_input("優先度", 0, 100, p_val, key=f"p_{qid}", label_visibility="collapsed")
#             if new_p != p_val: 
#                 state._set_priority(q["id"], new_p); st.rerun()

#             s_idx = utils.JP_ORDER.index(utils.JP.get(q.get('status'), '未取得'))
#             new_s_jp = c3.selectbox("ステータス", utils.JP_ORDER, index=s_idx, key=f"s_{qid}", label_visibility="collapsed")
#             if utils.EN[new_s_jp] != q.get('status'): 
#                 state._set_status(q["id"], utils.EN[new_s_jp]); st.rerun()

#     if st.button("質問リストの変更をDBへ保存", use_container_width=True, type="primary"):
#         state._save_questions_to_db()

# ui/assist_tab.py

import streamlit as st
import state
import utils
from services.dedup import dedup_questions

def render_assist_tab():
    left, right = st.columns([0.55, 0.45], gap="large")

    with left:
        st.subheader("📝 メモ")
        st.session_state.note_text = st.text_area(
            "メモ", height=260, value=st.session_state.get("note_text", ""), label_visibility="collapsed"
        )
        if st.button("メモをDBへ保存", use_container_width=True):
            state._save_note_to_db()

        st.divider()
        st.subheader("🧾 ライブ要約")
        summary_md = st.session_state.get("summary_markdown") or "（要約を生成中…）"
        with st.container(border=True, height=300):
            st.markdown(summary_md)
        # 手動更新したい時の簡易リロード（任意）
        if st.button("要約を更新", key="refresh_summary_assist", use_container_width=True):
            st.rerun()

    with right:
        st.subheader("🔥 今すぐ聞くべき3問")
        unanswered = [q for q in st.session_state.questions if q.get("status") == "unanswered"]
        top3 = sorted(unanswered, key=lambda x: x.get("priority", 50), reverse=True)[:3]
        
        cols = st.columns(len(top3) if top3 else 1)
        for i, q in enumerate(top3):
            with cols[i]:
                with st.container(border=True, height=290):
                    st.markdown(f"**#{i+1}**")
                    st.markdown(f'<div style="min-height: 80px;">{q.get("text", "")}</div>', unsafe_allow_html=True)
                    
                    tags_html = " ".join(f'<span class="badge">#{t}</span>' for t in q.get("tags", []))
                    st.markdown(f"P: {int(q.get('priority',50))} {tags_html}", unsafe_allow_html=True)

                    qid = q.get("id", str(id(q)))
                    
                    if st.button("✅ 聞けた", key=f"top3_ok_{qid}", use_container_width=True):
                        state._set_status(q["id"], "resolved"); st.rerun()
                    if st.button("🧳 持ち帰り", key=f"top3_take_{qid}", use_container_width=True):
                        state._set_status(q["id"], "take_home"); st.rerun()
                    if st.button("🕒 保留", key=f"top3_hold_{qid}", use_container_width=True):
                        state._set_status(q["id"], "on_hold"); st.rerun()

    st.divider()
    st.subheader("📋 質問リスト")
    
    filter_cols = st.columns([2, 1.5, 1.5])
    with filter_cols[0]:
        search_keyword = st.text_input("キーワード検索", placeholder="質問内容で絞り込み...")
    
    all_tags = sorted(list(set(tag for q in st.session_state.get("questions", []) for tag in q.get("tags", []))))
    with filter_cols[1]:
        # --- ここから変更 ---
        # st.multoselect -> st.multiselect に修正
        selected_tags = st.multiselect("タグでフィルター", options=all_tags)
        # --- ここまで変更 ---
    
    with filter_cols[2]:
        status_options = ["すべて"] + utils.JP_ORDER
        selected_status = st.selectbox("取得状況でフィルター", options=status_options)

    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        with c1:
            new_q_text = st.text_input("新しい質問を入力", key="q_add_text", placeholder="新しい質問を入力してください")
        with c2:
            if st.button("追加", use_container_width=True):
                if new_q_text:
                    st.session_state.questions.append({
                        "id": None, "text": new_q_text, "tags": [],
                        "priority": 50, "status": "unanswered", "source": "ui"
                    })
                    st.session_state.questions = dedup_questions(st.session_state.questions, 0.9)
                    st.session_state.q_add_text = ""
                    st.rerun()

    filtered_list = st.session_state.get("questions", [])
    if search_keyword:
        filtered_list = [q for q in filtered_list if search_keyword.lower() in q.get("text", "").lower()]
    if selected_tags:
        filtered_list = [q for q in filtered_list if all(tag in q.get("tags", []) for tag in selected_tags)]
    if selected_status != "すべて":
        status_en = utils.EN[selected_status]
        filtered_list = [q for q in filtered_list if q.get("status") == status_en]

    st.caption(f"表示件数: {len(filtered_list)}件")
    for q in filtered_list:
        qid = q.get("id", str(id(q)))
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 1, 1.5])
            c1.markdown(q.get("text", ""))
            
            p_val = int(q.get("priority", 50))
            new_p = c2.number_input("優先度", 0, 100, p_val, key=f"p_{qid}", label_visibility="collapsed")
            if new_p != p_val: 
                state._set_priority(q["id"], new_p); st.rerun()

            s_idx = utils.JP_ORDER.index(utils.JP.get(q.get('status'), '未取得'))
            new_s_jp = c3.selectbox("ステータス", utils.JP_ORDER, index=s_idx, key=f"s_{qid}", label_visibility="collapsed")
            if utils.EN[new_s_jp] != q.get('status'): 
                state._set_status(q["id"], utils.EN[new_s_jp]); st.rerun()

    if st.button("質問リストの変更をDBへ保存", use_container_width=True, type="primary"):
        state._save_questions_to_db()