import streamlit as st
from PIL import Image
import google.generativeai as genai
import io
import datetime
import gspread # 🚨 CSV 대신 gspread 임포트

# ✅ 페이지 설정 (가장 먼저 실행되어야 합니다)
st.set_page_config(page_title="🎨 미술 감상 챗봇", page_icon="🎨")

# -------------------------
# 1. Google Sheets & API 설정
# -------------------------

# ✅ Google Sheets 인증 (Streamlit의 캐시된 리소스 사용)
@st.cache_resource
def init_gspread_connection():
    """
    Google Sheets에 연결하고 gspread 클라이언트 객체를 반환합니다.
    st.secrets의 "gcp_service_account"를 사용합니다.
    """
    try:
        # st.secrets에서 서비스 계정 정보를 사전(dict) 형태로 가져옵니다.
        creds_dict = st.secrets["gcp_service_account"] 
        
        # gspread가 이 사전을 사용하여 인증하도록 설정합니다.
        client = gspread.service_account_from_dict(creds_dict)
        return client
    except Exception as e:
        st.error(f"Gspread 연결 실패: {e}")
        st.error("st.secrets에 'gcp_service_account' 키가 올바르게 설정되었는지 확인하세요.")
        st.stop()

@st.cache_resource
def get_worksheet():
    """
    인증된 클라이언트를 사용하여 특정 스프레드시트의 첫 번째 워크시트를 엽니다.
    st.secrets의 "GOOGLE_SHEET_URL"을 사용합니다.
    """
    try:
        client = init_gspread_connection()
        sheet_url = st.secrets["GOOGLE_SHEET_URL"]
        
        if not sheet_url:
            st.error("st.secrets에 'GOOGLE_SHEET_URL'이 설정되지 않았습니다.")
            st.stop()
            
        spreadsheet = client.open_by_url(sheet_url)
        worksheet = spreadsheet.sheet1 # 첫 번째 시트를 선택합니다.
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("스프레드시트를 찾을 수 없습니다. URL을 확인하거나 서비스 계정에 '편집자' 공유 권한을 주었는지 확인하세요.")
        st.stop()
    except Exception as e:
        st.error(f"워크시트를 여는 중 오류 발생: {e}")
        st.stop()

# ✅ 로그 기록 함수 (Google Sheets 버전)
def write_log(interaction_type, question, student_answer, bot_response):
    """
    학생 정보와 대화 내용을 Google Sheets에 한 줄씩 추가합니다.
    """
    try:
        worksheet = get_worksheet() # 캐시된 워크시트 객체를 가져옵니다.
        
        grade = st.session_state.get('grade', 'N/A')
        classroom = st.session_state.get('classroom', 'N/A')
        number = st.session_state.get('number', 'N/A')
        name = st.session_state.get('name', 'N/A')
        KST= datetime.timezone(datetime.timedelta(hours=9))
        timestamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        
        # Google Sheets에 추가할 새 행 (리스트 형태)
        new_row = [
            timestamp, grade, classroom, number, name,
            interaction_type, question, student_answer, bot_response
        ]
        
        # 첫 번째 행(헤더) 바로 다음에 새 행을 추가합니다. (append_row는 마지막에 추가)
        # append_row(row_data, index)
        worksheet.append_row(new_row) 
        
    except Exception as e:
        st.error(f"Google Sheets 로그 기록 중 오류 발생: {e}")
        st.warning("데이터가 저장되지 않았을 수 있습니다.")

# -------------------------
# 2. Gemini API 설정
# -------------------------

# ✅ 환경설정: Gemini API 키 (st.secrets 방식)
try:
    GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY") 
    
    if not GOOGLE_API_KEY:
        st.error("Streamlit Secrets에 GOOGLE_API_KEY가 설정되지 않았습니다.")
        st.stop()
        
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"API 키 설정 중 오류 발생: {e}")
    st.stop()

# ✅ 모델 불러오기
text_model = genai.GenerativeModel("gemini-2.5-flash")
vision_model = genai.GenerativeModel("gemini-2.5-flash")

# ✅ 감상 단계 질문 리스트 (Feldman)
feldman_questions = [
    "1단계 - 서술: 그림에 무엇이 보이나요?",
    "2단계 - 분석: 색, 구도, 형태는 어떻게 표현되었나요?",
    "3단계 - 해석: 작가가 전하려는 감정이나 메시지는 무엇일까요?",
    "4단계 - 평가: 그림이 마음에 드나요? 왜 그런가요?"
]

# ✅ 세션 상태 초기화 (🚨 오류 수정된 부분)
for key, default in {
    "step": 0,
    "image_bytes": None,
    "image_description": None,
    "feedback_history": [],
    "free_chat_history": [],
    "image_uploaded": False, # 👈 별표(*)가 삭제되었습니다!
    "user_info_submitted": False,
    "grade": None,
    "classroom": None,
    "number": None,
    "name": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# -------------------------
# 3. 사용자 정보 입력 (시작 페이지)
# -------------------------
if not st.session_state.user_info_submitted:
    # st.set_page_config()는 최상단에 있어야 하므로 여기서는 제목만 설정
    st.title("👤 미술 감상 챗봇 입장하기")
    st.subheader("학생 정보를 입력하세요")

    st.session_state.grade = st.selectbox("학년을 선택하세요", ["1학년", "2학년", "3학년", "4학년", "5학년", "6학년"])
    st.session_state.classroom = st.selectbox("반을 선택하세요", [f"{i}반" for i in range(1, 11)])
    st.session_state.number = st.number_input("번호를 입력하세요", min_value=1, max_value=50)
    st.session_state.name = st.text_input("이름을 입력하세요")

    if st.button("🎨 감상 챗봇 시작"):
        if st.session_state.name:
            st.session_state.user_info_submitted = True
            st.rerun()
        else:
            st.warning("이름을 입력해주세요!")
    st.stop() # 👈 사용자 정보 입력이 완료될 때까지 앱의 나머지 부분 실행 중지

# -------------------------
# 4. 메인 챗봇 앱
# -------------------------

# ✅ (수정) 메인 앱이 시작될 때 CSV 대신 Gspread 연결을 시도합니다.
# (실제 연결은 get_worksheet()가 처음 호출될 때 발생합니다)
try:
    # 연결 테스트 겸, 워크시트 객체를 미리 로드합니다.
    get_worksheet() 
except Exception as e:
    st.error("로그 시트 연결에 실패했습니다. 관리자에게 문의하세요.")
    st.stop()


# ✅ 페이지 상단 표시
st.title("🎨 초등학생 미술 감상 챗봇")
st.markdown(f"##### 🙋‍♂️ {st.session_state.grade} {st.session_state.classroom} {st.session_state.number}번 {st.session_state.name} 학생")

# ✍️ 팝업 스타일
MINT_POPUP_STYLE = """
position: fixed;
top: 40%;
left: 50%;
transform: translate(-50%, -50%);
background-color: #D9F7E6; /* 민트색 */
color: #000000; /* 검은색 */
padding: 20px;
border-radius: 10px;
box-shadow: 2px 2px 10px gray;
z-index: 9999;
"""

# -------------------------
# 4-1. 그림 업로드
# -------------------------
st.header("🖼 1. 그림 업로드")
uploaded_file = st.file_uploader("🖼 감상할 그림 파일을 업로드하세요", type=["png", "jpg", "jpeg"])
if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="업로드한 그림", width="stretch")

    buffered = io.BytesIO()
    file_format = image.format if image.format in ["JPEG", "PNG"] else "PNG"
    image.save(buffered, format=file_format)
    image_bytes = buffered.getvalue()

    if st.session_state.image_bytes != image_bytes:
        st.session_state.image_uploaded = False 
        st.session_state.image_bytes = image_bytes
        st.session_state.image_description = None
        st.session_state.step = 0
        st.session_state.feedback_history = []
        st.session_state.free_chat_history = []


    if not st.session_state.image_uploaded:
        loading = st.empty()
        try:
            loading.markdown(f"<div style='{MINT_POPUP_STYLE}'>🧠 그림 분석 중입니다...</div>", unsafe_allow_html=True)
            
            img_for_model = Image.open(io.BytesIO(st.session_state.image_bytes))

            response = vision_model.generate_content([
                "이 그림을 초등학생에게 feldman감상 단계에 맞게 1단계부터 4단계까지 친절하게 설명해줘.",
                img_for_model
            ])
            st.session_state.image_description = response.text
            st.session_state.image_uploaded = True
            loading.empty()
            st.success("✅ AI 그림 설명 완료!")
        except Exception as e:
            loading.empty()
            st.error(f"그림 분석 중 오류 발생: {e}")

# -------------------------
# 4-2. AI 그림 설명 출력
# -------------------------
if st.session_state.image_description:
    st.subheader("📌 AI 그림 설명")
    st.write(st.session_state.image_description)

# -------------------------
# 4-3. 자유 질문
# -------------------------
def submit_free_question():
    question = st.session_state.get("free_question_input", "")
    if not question:
        return

    loading = st.empty()
    try:
        loading.markdown(f"<div style='{MINT_POPUP_STYLE}'>🤖 AI가 답변 중입니다...</div>", unsafe_allow_html=True)

        bot_response_text = "답변을 생성하지 못했습니다."

        if st.session_state.image_description:
            response = text_model.generate_content(
                f"학생이 이렇게 질문했어: {question}\n그림에 대한 설명은 다음과 같아:\n{st.session_state.image_description}\n이 정보를 바탕으로 초등학생에게 친절하게 답변해줘."
            )
            bot_response_text = response.text
        elif st.session_state.image_bytes:
            img_for_model = Image.open(io.BytesIO(st.session_state.image_bytes))
            response = vision_model.generate_content([
                f"학생이 이렇게 질문했어: {question}\n그림을 함께 참고해서 초등학생 수준으로 대답해줘.",
                img_for_model
            ])
            bot_response_text = response.text
        else:
            response = text_model.generate_content(
                f"초등학생이 이렇게 질문했어: {question}\n친절하고 쉽게 대답해줘."
            )
            bot_response_text = response.text

        loading.empty()
        
        st.session_state.free_chat_history.append(("user", question))
        st.session_state.free_chat_history.append(("bot", bot_response_text))
        
        # ✅ 로그 기록 (Google Sheets)
        write_log(
            interaction_type="자유 질문",
            question=question,
            student_answer="N/A",
            bot_response=bot_response_text
        )
        
        # st.rerun() # 👈 [수정됨] 이 줄을 주석 처리하여 'no-op' 경고를 제거합니다.
        
    except Exception as e:
        loading.empty()
        st.error(f"자유 질문 처리 중 오류 발생: {e}")

st.header("💬 2. 자유 질문")
st.text_input("그림이나 미술에 대해 자유롭게 질문해보세요:", key="free_question_input", on_change=submit_free_question)

st.subheader("💬 자유 대화 기록")
if st.session_state.free_chat_history:
    for role, text in st.session_state.free_chat_history:
        if role == "user":
            st.markdown(f"**🙋‍♂️ {st.session_state.name}**: {text}")
        else:
            st.markdown(f"**🤖 챗봇**: {text}")
    st.markdown("---")
else:
    st.info("자유롭게 질문해보세요! 질문과 답변이 여기에 표시됩니다.")

# -------------------------
# 4-4. 단계별 감상
# -------------------------
def submit_step_answer():
    step = st.session_state.step
    user_answer = st.session_state.get(f"step_answer_input_{step}", "")
    if not user_answer:
        return

    current_question = feldman_questions[step]
    
    loading = st.empty()
    try:
        loading.markdown(f"<div style='{MINT_POPUP_STYLE}'>💬 감상 피드백 생성 중...</div>", unsafe_allow_html=True)

        prompt = (
            f"초등학생이 미술 감상 시간에 아래와 같이 대답했어.\n"
            f"질문: {current_question}\n"
            f"대답: {user_answer}\n"
            f"칭찬과 격려를 해주고, 아이가 다음 감상 단계로 이어가도록 유도하는 피드백을 줘."
            f"절대 욕설과 비방을 해서는 안돼."
        )

        feedback = "피드백 생성에 실패했습니다."

        if st.session_state.image_description:
            prompt += f"\n참고할 그림 설명: {st.session_state.image_description}"
            response = text_model.generate_content(prompt)
            feedback = response.text
        elif st.session_state.image_bytes:
            img_for_model = Image.open(io.BytesIO(st.session_state.image_bytes))
            response = vision_model.generate_content([prompt, img_for_model])
            feedback = response.text
        else:
            response = text_model.generate_content(prompt)
            feedback = response.text

        st.session_state.feedback_history.append((current_question, user_answer, feedback))

        loading.empty()
        st.success("✅ 피드백 생성 완료!")
        st.subheader("😊 감상 피드백")
        st.write(feedback)

        # ✅ 로그 기록 (Google Sheets)
        write_log(
            interaction_type="단계별 감상",
            question=current_question,
            student_answer=user_answer,
            bot_response=feedback
        )

        st.session_state.step += 1
        st.rerun()
        
    except Exception as e:
        loading.empty()
        st.error(f"단계별 감상 처리 중 오류 발생: {e}")

st.header("📘 3. 단계별 감상 (펠드만 4단계)")
step = st.session_state.step
if step < len(feldman_questions):
    current_question = feldman_questions[step]
    st.markdown(f"**{current_question}**")
    st.text_input("📝 감상 대답을 입력해주세요:", key=f"step_answer_input_{step}", on_change=submit_step_answer)
else:
    st.success("🎉 모든 감상 단계를 마쳤어요!")
    if st.button("🔄 처음부터 다시 시작 (같은 그림)"):
        st.session_state.step = 0
        st.session_state.feedback_history = []
        st.session_state.free_chat_history = []
        st.rerun()

# -------------------------
# 4-5. 이전 피드백 보기
# -------------------------
if st.session_state.feedback_history:
    with st.expander("📚 이전 감상 기록 보기"):
        for q, a, f in st.session_state.feedback_history:
            st.markdown(f"**{q}**")
            st.markdown(f"- ✏️ 대답: {a}")
            st.markdown(f"- 💡 피드백: {f}")
            st.divider()