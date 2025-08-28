# # ui/assist_tab.py

# import streamlit as st
# import state
# import utils
# from services.dedup import dedup_questions

# def render_assist_tab():
#     left, right = st.columns([0.55, 0.45], gap="large")

#     with left:
#         st.subheader("📝 メモ")
#         st.session_state.note_text = st.text_area(
#             "メモ", height=260, value=st.session_state.get("note_text", ""), label_visibility="collapsed"
#         )
#         if st.button("メモをDBへ保存", use_container_width=True):
#             state._save_note_to_db()

#         st.divider()
#         st.subheader("🧾 ライブ要約")
#         summary_md = st.session_state.get("summary_markdown") or "（要約を生成中…）"
#         with st.container(border=True, height=300):
#             st.markdown(summary_md)
#         # 手動更新したい時の簡易リロード（任意）
#         if st.button("要約を更新", key="refresh_summary_assist", use_container_width=True):
#             st.rerun()

#     with right:
#         st.subheader("🔥 今すぐ聞くべき3問")
#         unanswered = [q for q in st.session_state.questions if q.get("status") == "unanswered"]
#         top3 = sorted(unanswered, key=lambda x: x.get("priority", 50), reverse=True)[:3]
        
#         cols = st.columns(len(top3) if top3 else 1)
#         for i, q in enumerate(top3):
#             with cols[i]:
#                 with st.container(border=True, height=290):
#                     st.markdown(f"**#{i+1}**")
#                     st.markdown(f'<div style="min-height: 80px;">{q.get("text", "")}</div>', unsafe_allow_html=True)
                    
#                     tags_html = " ".join(f'<span class="badge">#{t}</span>' for t in q.get("tags", []))
#                     st.markdown(f"P: {int(q.get('priority',50))} {tags_html}", unsafe_allow_html=True)

#                     qid = q.get("id", str(id(q)))
                    
#                     if st.button("✅ 聞けた", key=f"top3_ok_{qid}", use_container_width=True):
#                         state._set_status(q["id"], "resolved"); st.rerun()
#                     if st.button("🧳 持ち帰り", key=f"top3_take_{qid}", use_container_width=True):
#                         state._set_status(q["id"], "take_home"); st.rerun()
#                     if st.button("🕒 保留", key=f"top3_hold_{qid}", use_container_width=True):
#                         state._set_status(q["id"], "on_hold"); st.rerun()

#     st.divider()
#     st.subheader("📋 質問リスト")
    
#     filter_cols = st.columns([2, 1.5, 1.5])
#     with filter_cols[0]:
#         search_keyword = st.text_input("キーワード検索", placeholder="質問内容で絞り込み...")
    
#     all_tags = sorted(list(set(tag for q in st.session_state.get("questions", []) for tag in q.get("tags", []))))
#     with filter_cols[1]:
#         # --- ここから変更 ---
#         # st.multoselect -> st.multiselect に修正
#         selected_tags = st.multiselect("タグでフィルター", options=all_tags)
#         # --- ここまで変更 ---
    
#     with filter_cols[2]:
#         status_options = ["すべて"] + utils.JP_ORDER
#         selected_status = st.selectbox("取得状況でフィルター", options=status_options)

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

#     filtered_list = st.session_state.get("questions", [])
#     if search_keyword:
#         filtered_list = [q for q in filtered_list if search_keyword.lower() in q.get("text", "").lower()]
#     if selected_tags:
#         filtered_list = [q for q in filtered_list if all(tag in q.get("tags", []) for tag in selected_tags)]
#     if selected_status != "すべて":
#         status_en = utils.EN[selected_status]
#         filtered_list = [q for q in filtered_list if q.get("status") == status_en]

#     st.caption(f"表示件数: {len(filtered_list)}件")
#     for q in filtered_list:
#         qid = q.get("id", str(id(q)))
#         with st.container(border=True):
#             c1, c2, c3 = st.columns([4, 1, 1.5])
#             c1.markdown(q.get("text", ""))
            
#             p_val = int(q.get("priority", 50))
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
    all_tags_options = sorted(list(set(tag for q in st.session_state.get("questions", []) for tag in q.get("tags", []))))

    left, right = st.columns([0.55, 0.45], gap="large")

    with left:
        st.subheader("📝 メモ")
        # st.session_state.note_text = st.text_area(
        #     "メモ", height=260, value=st.session_state.get("note_text", ""), label_visibility="collapsed"
        # )

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
        st.subheader("🧾 ライブ要約")
        summary_md = st.session_state.get("summary_markdown", "（要約を生成中…）")
        if summary_md == "":
            summary_md = "（要約を生成中…）"
        with st.container(border=True, height=300):
            st.markdown(summary_md)
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

                    # --- ここから変更 ---
                    # keyが重複しないように、ループのインデックス `i` を使う
                    qid = q.get("id")
                    
                    if st.button("✅ 聞けた", key=f"top3_ok_{i}", use_container_width=True):
                        # qidがあればそれを使って更新、なければオブジェクトを直接変更
                        if qid: state._set_status(qid, "resolved")
                        else: q['status'] = 'resolved'
                        st.rerun()

                    if st.button("🧳 持ち帰り", key=f"top3_take_{i}", use_container_width=True):
                        if qid: state._set_status(qid, "take_home")
                        else: q['status'] = 'take_home'
                        st.rerun()

                    if st.button("🕒 保留", key=f"top3_hold_{i}", use_container_width=True):
                        if qid: state._set_status(qid, "on_hold")
                        else: q['status'] = 'on_hold'
                        st.rerun()
                    # --- ここまで変更 ---

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
        # with c2:
        #     if st.button("追加", use_container_width=True):
        #         if new_q_text:
        #             st.session_state.questions.append({
        #                 "id": None, "text": new_q_text, "tags": [],
        #                 "priority": 50, "status": "unanswered", "source": "ui"
        #             })
        #             st.session_state.questions = dedup_questions(st.session_state.questions, 0.9)
        #             st.session_state.q_add_text = ""
        #             st.rerun()

        with c2:
            # --- ここから変更 ---
            # `state`モジュールから関数を呼び出す
            st.button("追加", on_click=state.add_question_callback, use_container_width=True)
            # --- ここまで変更 ---

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