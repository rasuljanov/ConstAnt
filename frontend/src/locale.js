export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "uz", label: "O‘zbekcha" },
  { code: "ko", label: "한국어" },
];
export const LOCALES = { en: "en-GB", uz: "uz-UZ", ko: "ko-KR" };

const labels = {
  "New chat": ["Yangi suhbat", "새 대화"],
  "Chats": ["Suhbatlar", "대화"],
  "Settings": ["Sozlamalar", "설정"],
  "Resources": ["Manbalar", "자료"],
  "Account": ["Hisob", "계정"],
  "Language": ["Til", "언어"],
  "Open resources": ["Manbalarni ochish", "자료 열기"],
  "Open account": ["Hisobni ochish", "계정 열기"],
  "Open sidebar": ["Yon panelni ochish", "사이드바 열기"],
  "Your chats will be saved here.": ["Suhbatlaringiz shu yerda saqlanadi.", "대화가 여기에 저장됩니다."],
  "What would you like to know?": ["Nimani bilishni istaysiz?", "무엇이 궁금하신가요?"],
  "Ask about your site using imagery, video, measurements, or the conversation so far.": ["Obyekt tasvirlari, video, o‘lchovlar yoki suhbat asosida savol bering.", "현장 이미지, 영상, 측정값이나 이전 대화를 바탕으로 질문하세요."],
  "PM measurements": ["PM o‘lchovlari", "미세먼지 측정"],
  "Site orthophoto": ["Obyekt ortofotosi", "현장 정사영상"],
  "Recorded video": ["Yozib olingan video", "녹화 영상"],
  "Compare flights, altitude settings, and pollution peaks": ["Parvozlar, balandliklar va ifloslanish cho‘qqilarini solishtiring", "비행, 고도 설정과 오염 최고값을 비교하세요"],
  "Find equipment and describe visible site activity": ["Texnikalarni toping va ko‘rinadigan ishlarni tavsiflang", "장비를 찾고 보이는 현장 작업을 설명하세요"],
  "Ask about actions, order, and video timestamps": ["Harakatlar, ketma-ketlik va video vaqtlari haqida so‘rang", "작업, 순서와 영상 시간에 대해 질문하세요"],
  "Ask ConstAnt": ["ConstAnt’dan so‘rang", "ConstAnt에 질문하기"],
  "Message ConstAnt": ["ConstAnt’ga xabar", "ConstAnt에 메시지 보내기"],
  "Add attachment": ["Fayl biriktirish", "파일 첨부"],
  "Upload files": ["Fayllarni yuklash", "파일 업로드"],
  "Add from resources": ["Manbalardan qo‘shish", "자료에서 추가"],
  "Add to chat": ["Suhbatga qo‘shish", "대화에 추가"],
  "Send message": ["Xabarni yuborish", "메시지 보내기"],
  "Stop analysis": ["Tahlilni to‘xtatish", "분석 중지"],
  "Stop": ["To‘xtatish", "중지"],
  "Stopping…": ["To‘xtatilmoqda…", "중지 중…"],
  "Thinking…": ["O‘ylanmoqda…", "생각 중…"],
  "Waiting for the GPU…": ["GPU kutilmoqda…", "GPU 대기 중…"],
  "Analyzing views": ["Tasvirlar tahlil qilinmoqda", "이미지 분석 중"],
  "views processed": ["tasvir tahlil qilindi", "개 이미지 처리됨"],
  "Copy response": ["Javobni nusxalash", "답변 복사"],
  "Copy request": ["Savolni nusxalash", "질문 복사"],
  "Copied": ["Nusxalandi", "복사됨"],
  "Could not copy this message. Select the text and copy it manually.": ["Xabar nusxalanmadi. Matnni belgilang va qo‘lda nusxalang.", "복사할 수 없습니다. 텍스트를 선택해 직접 복사해 주세요."],
  "Run details": ["Tahlil tafsilotlari", "실행 세부 정보"],
  "Loading chat…": ["Suhbat yuklanmoqda…", "대화 불러오는 중…"],
  "Using the previous scan": ["Oldingi tahlil ishlatilmoqda", "이전 분석 사용 중"],
  "Using earlier files in this chat": ["Suhbatdagi oldingi fayllar ishlatilmoqda", "이 대화의 이전 파일 사용 중"],
  "table sources": ["jadval manbasi", "개 표 자료"],
  "Rename": ["Nomini o‘zgartirish", "이름 변경"],
  "Pin chat": ["Suhbatni mahkamlash", "대화 고정"],
  "Unpin chat": ["Mahkamlashni bekor qilish", "고정 해제"],
  "Delete chat": ["Suhbatni o‘chirish", "대화 삭제"],
  "Your sources": ["Manbalaringiz", "내 자료"],
  "Attached files": ["Biriktirilgan fayllar", "첨부 파일"],
  "File viewer": ["Fayl ko‘rish", "파일 보기"],
  "Next steps": ["Keyingi qadamlar", "다음 단계"],
  "Chat settings": ["Suhbat sozlamalari", "대화 설정"],
  "Close": ["Yopish", "닫기"],
  "All sources": ["Barcha manbalar", "모든 자료"],
  "Select PM flights": ["PM parvozlarini tanlash", "미세먼지 비행 선택"],
  "Deselect PM flights": ["PM parvozlari tanlovini olib tashlash", "미세먼지 비행 선택 해제"],
  "all": ["barchasi", "전체"],
  "pm": ["PM", "미세먼지"],
  "images": ["tasvirlar", "이미지"],
  "videos": ["videolar", "영상"],
  "other": ["boshqa", "기타"],
  "Attach to next message": ["Keyingi xabarga biriktirish", "다음 메시지에 첨부"],
  "Original file": ["Asl fayl", "원본 파일"],
  "Statistics": ["Statistika", "통계"],
  "Previous": ["Oldingi", "이전"],
  "Next": ["Keyingi", "다음"],
  "Retry": ["Qayta urinish", "다시 시도"],
  "Name": ["Ism", "이름"],
  "Role or team": ["Lavozim yoki jamoa", "직책 또는 팀"],
  "Save profile": ["Profilni saqlash", "프로필 저장"],
  "Your profile": ["Profilingiz", "내 프로필"],
  "Model & connection": ["Model va ulanish", "모델 및 연결"],
  "Connect vLLM": ["vLLM’ga ulanish", "vLLM 연결"],
  "Load Qwen": ["Qwen’ni yuklash", "Qwen 불러오기"],
  "Release GPU": ["GPU’ni bo‘shatish", "GPU 메모리 해제"],
  "Reconnect": ["Qayta ulanish", "다시 연결"],
  "Appearance": ["Ko‘rinish", "화면 모드"],
  "Light": ["Yorug‘", "라이트"],
  "Dark": ["Qorong‘i", "다크"],
  "Inference budget": ["Tahlil chegaralari", "추론 설정"],
  "Image edge": ["Tasvir o‘lchami", "이미지 크기"],
  "Output tokens": ["Javob tokenlari", "출력 토큰"],
  "Video sampling": ["Video kadrlarini tanlash", "영상 프레임 추출"],
  "Cancel": ["Bekor qilish", "취소"],
  "Save": ["Saqlash", "저장"],
  "Delete": ["O‘chirish", "삭제"],
  "Dataset details": ["Ma’lumotlar tafsilotlari", "데이터 세부 정보"],
  "View calculated evidence": ["Hisoblangan dalillarni ko‘rish", "계산 근거 보기"],
};

export function translate(language, text) {
  return labels[text]?.[language === "uz" ? 0 : language === "ko" ? 1 : -1] || text;
}

export function messageTime(value, language) {
  const date = value ? new Date(value) : null;
  return date && Number.isFinite(date.getTime())
    ? new Intl.DateTimeFormat(LOCALES[language] || LOCALES.en, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date) : "";
}

export function responseDuration(run, language) {
  const seconds = run.wall_seconds ?? run.metrics?.inference_seconds;
  return typeof seconds === "number" && Number.isFinite(seconds) && seconds >= 0
    ? new Intl.NumberFormat(LOCALES[language] || LOCALES.en, { maximumFractionDigits: 1 }).format(seconds) + " s" : "";
}
