from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from app_src.components.top3_cards import render_top3
from app_src.components.questions_panel import render_questions_panel
from app_src.components.whisper_page import render_whisper_page
from app_src.services.priority import recompute_priorities, temperature_from_transcript
from app_src.services.dedup import dedup_questions
from app_src.services import supabase_db as dbsvc

load_dotenv()
st.set_page_config(page_title="Sales Live Assist v3.3 (Supabase)", layout="wide")

# --- env check ---
if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_ANON_KEY"):
    st.error("環境変数 SUPABASE_URL / SUPABASE_ANON_KEY を .env に設定してください。")
    st.stop()

dbsvc.init_db(None)
dbsvc.seed_if_empty(None, None)

if "initialized" not in st.session_state:
    st.session_state.initialized = True
    customers = dbsvc.list_customers(None)
    st.session_state.customer_list = customers
    st.session_state.customer_id = customers[0]["id"] if customers else None
    meets = dbsvc.list_meetings(None, st.session_state.customer_id) if st.session_state.customer_id else []
    st.session_state.meeting_list = meets
    st.session_state.meeting_id = meets[0]["id"] if meets else None

with st.container(border=True):
    c1, c2, c3, c4 = st.columns([1.4, 1.4, 1.4, 1])
    with c1: st.caption("セッション情報")
    with c2:
        customers = dbsvc.list_customers(None)
        st.session_state.customer_list = customers
        if customers:
            idx = st.selectbox("顧客", options=list(range(len(customers))), format_func=lambda i: customers[i]["name"], label_visibility="collapsed")
            st.session_state.customer_id = customers[idx]["id"]
        else: st.caption("顧客なし")
    with c3:
        meets = dbsvc.list_meetings(None, st.session_state.customer_id) if st.session_state.customer_id else []
        st.session_state.meeting_list = meets
        if meets:
            midx = st.selectbox("商談", options=list(range(len(meets))), format_func=lambda i: f"{meets[i]['meeting_date']} / {meets[i]['title']}", label_visibility="collapsed")
            st.session_state.meeting_id = meets[midx]["id"]
        else: st.caption("商談なし")
    with c4:
        if st.button("新規商談開始"):
            if st.session_state.customer_id:
                new_id = dbsvc.new_meeting(None, st.session_state.customer_id, "新規商談")
                st.session_state.meeting_id = new_id; st.rerun()
        st.caption(datetime.now().strftime("%m/%d %H:%M"))

bundle = dbsvc.get_meeting_bundle(None, st.session_state.meeting_id) if st.session_state.meeting_id else {"transcript": [], "questions": [], "notes": []}
profile = dbsvc.get_customer(None, st.session_state.customer_id) if st.session_state.customer_id else {}

st.session_state.profile = profile or {}
st.session_state.transcript = bundle["transcript"]
st.session_state.questions = bundle["questions"]
st.session_state.backlog = [q for q in bundle["questions"] if q.get("status")=="take_home"]
st.session_state.on_hold = [q for q in bundle["questions"] if q.get("status")=="on_hold"]

tab_assist, tab_trans, tab_backlog, tab_profile, tab_history, tab_whisper = st.tabs(
    ["Assist（メモ × 質問）", "Transcript（見やすい表示）", "Backlog / On-Hold / 取得状況", "Lead Profile（DB保存）", "履歴 / DB", "Whisper文字起こし"]
)

with tab_assist:
    temp = temperature_from_transcript(st.session_state.transcript[-16:])
    st.progress(min(1.0, temp), text=f"温度感（直近発話）: {temp:.2f}")
    st.divider()

    left, right = st.columns([0.55, 0.45], gap="large")
    with left:
        st.subheader("📝 メモ（DB保存）")
        note = st.text_area("1行=1要点で入力（Enterで改行）", height=280, key="note_text")
        c1,c2,c3 = st.columns(3)
        if c1.button("メモを保存（DB）", use_container_width=True):
            if note.strip():
                dbsvc.add_note(None, st.session_state.meeting_id, note.strip()); st.success("メモを保存しました")
        if c2.button("メモから追質問生成（モック）", use_container_width=True):
            base=(note.strip() or "メモ要点")[:50]
            new_qs = [
                {"id": None, "text": f"{base}の背景と影響範囲は？（どの部署・どの業務に影響？）", "tags":["課題","要件"], "role":"ニーズ把握", "priority":0.66, "status":"unanswered", "source":"note"},
                {"id": None, "text": f"{base}に関する評価指標（KPI）と受け入れ条件は？", "tags":["要件"], "role":"前提確認", "priority":0.62, "status":"unanswered", "source":"note"},
                {"id": None, "text": f"{base}の現状コスト/工数と回収見込みは？", "tags":["価格","要件"], "role":"価格/予算", "priority":0.6, "status":"unanswered", "source":"note"},
            ]
            st.session_state.questions.extend(new_qs)
            st.session_state.questions = dedup_questions(st.session_state.questions, threshold=0.88)
            dbsvc.upsert_questions(None, st.session_state.meeting_id, st.session_state.questions)
            st.success("追質問を追加しDBへ保存しました")
        if c3.button("最新メモを表示", use_container_width=True):
            st.write(pd.DataFrame(bundle["notes"]))

        st.divider()
        st.subheader("🔥 今すぐ聞くべき3問")
        st.session_state.questions = recompute_priorities(
            st.session_state.questions,
            stage=st.session_state.profile.get("stage", "初回"),
            temperature=temp,
            profile=st.session_state.profile,
            transcript=[t for _, t in st.session_state.transcript[-30:]],
        )
        top3=[q for q in sorted(st.session_state.questions, key=lambda x:x.get("priority",0), reverse=True) if q.get("status")=="unanswered"][:3]
        render_top3(top3)

    with right:
        st.subheader("📋 質問リスト")
        st.session_state.questions, st.session_state.backlog, st.session_state.on_hold = render_questions_panel(
            st.session_state.questions, backlog=st.session_state.backlog, on_hold=st.session_state.on_hold,
            meeting_id=st.session_state.meeting_id
        )

with tab_trans:
    st.subheader("会話ログ（チャット表示）")
    c1,c2,c3 = st.columns([1.2,0.8,0.8])
    keyword = c1.text_input("キーワード検索（例：SAML / 予算）", key="kw")
    limit = c2.slider("表示件数", 10, 300, 120, 10)
    as_table = c3.toggle("テーブル表示")

    logs = st.session_state.transcript[-limit:]
    if keyword: logs = [x for x in logs if keyword in x[1]]
    if as_table:
        df = pd.DataFrame(logs, columns=["time","utterance"])
        st.dataframe(df, use_container_width=True, height=560)
    else:
        for i, (ts, text) in enumerate(logs):
            role = "assistant" if i % 2 == 0 else "user"
            with st.chat_message(role):
                st.markdown(f"**{ts}**  \n{text}")

    st.divider()
    new_line = st.text_input("新しい発話を追加（例：稟議は部長決裁です）", key="asr_line", value="")
    add_col, save_col = st.columns(2)
    if add_col.button("発話を追加（セッション）", type="primary"):
        if new_line.strip():
            st.session_state.transcript.append((datetime.now().strftime("%H:%M:%S"), new_line.strip()))
            st.toast("発話をセッションに追加しました"); st.rerun()
    if save_col.button("最新発話をDB保存"):
        if st.session_state.transcript:
            ts, text = st.session_state.transcript[-1]
            dbsvc.add_transcript_line(None, st.session_state.meeting_id, ts, "sales", text)
            st.success("直近の発話をDBへ保存しました")

with tab_backlog:
    st.subheader("取得状況まとめ")
    pending=[q for q in st.session_state.questions if q.get("status")=="unanswered"]
    resolved=[q for q in st.session_state.questions if q.get("status")=="resolved"]
    c1,c2 = st.columns(2)
    with c1:
        st.markdown(f"### ❗聞けてない（未取得）  — {len(pending)}件")
        if pending:
            st.dataframe(pd.DataFrame([{"id":q["id"],"質問":q["text"],"役割":q.get("role","—"),"優先度":round(q.get("priority",0),2)} for q in sorted(pending, key=lambda x:x.get("priority",0), reverse=True)]), use_container_width=True, height=300)
        else: st.caption("未取得はありません")
    with c2:
        st.markdown(f"### ✅聞けた（取得済み）  — {len(resolved)}件")
        if resolved:
            st.dataframe(pd.DataFrame([{"id":q["id"],"質問":q["text"],"役割":q.get("role","—"),"優先度":round(q.get("priority",0),2)} for q in resolved]), use_container_width=True, height=300)
        else: st.caption("取得済みはまだありません")
    st.divider()
    st.subheader("保留 / 会社持ち帰り")
    c3,c4 = st.columns(2)
    with c3:
        on_hold=[q for q in st.session_state.questions if q.get("status")=="on_hold"]
        st.markdown(f"#### 🕒 保留（On-Hold） — {len(on_hold)}件"); st.dataframe(pd.DataFrame(on_hold), use_container_width=True, height=240)
    with c4:
        backlog=[q for q in st.session_state.questions if q.get("status")=="take_home"]
        st.markdown(f"#### 🧳 会社持ち帰り（Take-Home） — {len(backlog)}件"); st.dataframe(pd.DataFrame(backlog), use_container_width=True, height=240)

with tab_profile:
    st.subheader("顧客・案件プロフィール（DB保存）")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("会社名", value=st.session_state.profile.get("name",""))
        industry = st.text_input("業種", value=st.session_state.profile.get("industry",""))
        size = st.selectbox("規模", ["~100名","100-500名","500-1000名","1000名~"], index=["~100名","100-500名","500-1000名","1000名~"].index(st.session_state.profile.get("size","100-500名")) if st.session_state.profile.get("size") in ["~100名","100-500名","500-1000名","1000名~"] else 1)
        usecase = st.text_input("想定用途（例：見積自動化）", value=st.session_state.profile.get("usecase",""))
    with col2:
        kpi = st.text_input("最重要KPI（例：工数削減）", value=st.session_state.profile.get("kpi",""))
        budget_upper = st.text_input("稟議上限額（例：300万円）", value=st.session_state.profile.get("budget_upper",""))
        deadline = st.text_input("希望導入時期（例：2025/12）", value=st.session_state.profile.get("deadline",""))
        constraints = st.text_input("制約（例：SaaSのみ/持出禁止）", value=st.session_state.profile.get("constraints",""))
    stage = st.selectbox("商談フェーズ（メモ用・DB未保存）", ["初回","要件定義","見積・稟議","クロージング"])

    if st.button("顧客情報をDB保存"):
        payload={"id":st.session_state.customer_id,"name":name,"industry":industry,"size":size,"usecase":usecase,"kpi":kpi,"budget_upper":budget_upper,"deadline":deadline,"constraints":constraints}
        cid = dbsvc.upsert_customer(None, payload)
        st.session_state.customer_id = cid; st.success("顧客情報を保存しました")

with tab_history:
    st.subheader("過去の商談（この顧客名に紐付く会話）")
    meetings = dbsvc.list_meetings(None, st.session_state.customer_id) if st.session_state.customer_id else []
    st.dataframe(pd.DataFrame(meetings), use_container_width=True, height=300)
    st.caption("※ conversations.customer_id が無い環境向けに、customers.name と conversations.customer_company の一致で紐付けています。")

with tab_whisper:
    render_whisper_page(dbsvc, st.session_state.meeting_id)