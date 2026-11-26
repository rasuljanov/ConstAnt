"""Translate authored result labels while retaining source names and units."""

MESSAGES = {
    "CSV file": ("CSV fayl", "CSV 파일"), "CSV files": ("CSV fayl", "CSV 파일"),
    "Source file": ("Manba fayli", "원본 파일"), "Speed setting": ("Tezlik sozlamasi", "속도 설정"),
    "Altitude setting (m)": ("Balandlik sozlamasi (m)", "고도 설정 (m)"), "Trial": ("Sinov", "실험"),
    "recorded environmental sensor measurements": ("qayd etilgan ekologik sensor o‘lchovi", "기록된 환경 센서 측정값"),
    "tabular records": ("jadval yozuvi", "표 기록"),
    "This **{files} {file_label}** contains **{rows} {record_type}**.": ("Ushbu **{files} ta {file_label}**da **{rows} ta {record_type}** mavjud.", "이 **{files}개 {file_label}**에는 **{rows}개 {record_type}**이 있습니다."),
    "These **{files} {file_label}** contain **{rows} {record_type}**.": ("Ushbu **{files} ta {file_label}**da **{rows} ta {record_type}** mavjud.", "이 **{files}개 {file_label}**에는 **{rows}개 {record_type}**이 있습니다."),
    "Air quality": ("Havo sifati", "대기질"), "Weather": ("Ob-havo", "기상"),
    "Position and time": ("Joylashuv va vaqt", "위치 및 시간"), "Other fields": ("Boshqa ustunlar", "기타 필드"),
    "Columns": ("Ustunlar", "열"), "Recorded": ("Qayd etilgan sana", "기록 날짜"),
    "{start} to {end}": ("{start} – {end}", "{start} ~ {end}"),
    "speed (units unspecified)": ("tezlik (birligi ko‘rsatilmagan)", "속도 (단위 미지정)"),
    "altitude (m)": ("balandlik (m)", "고도 (m)"), "trial": ("sinov", "실험"),
    "Filename settings": ("Fayl nomidagi sozlamalar", "파일명 설정"),
    "The files contain {count} distinct column schemas.": ("Fayllarda {count} xil ustun tuzilmasi mavjud.", "파일에 {count}개의 서로 다른 열 구조가 있습니다."),
    "**{rows} matching rows** from {files} selected {file_label}.": ("Tanlangan {files} ta {file_label}dan **{rows} ta mos qator**.", "선택한 {files}개 {file_label}에서 **{rows}개 일치 행**."),
    "Filters": ("Filtrlar", "필터"), "contains": ("o‘z ichiga oladi", "포함"),
    "No measurements matched. No concentration values are reported.": ("Mos o‘lchovlar topilmadi. Konsentratsiya qiymatlari keltirilmaydi.", "일치하는 측정값이 없어 농도 값을 표시하지 않습니다."),
    "Measurement": ("O‘lchov", "측정 항목"), "Valid": ("Yaroqli", "유효"),
    "Missing/invalid": ("Yetishmagan/yaroqsiz", "누락/유효하지 않음"), "Min": ("Eng kichik", "최솟값"),
    "Mean": ("O‘rtacha", "평균"), "Max": ("Eng katta", "최댓값"), "Median": ("Mediana", "중앙값"), "Std dev": ("Standart og‘ish", "표준편차"),
    "Means are per measurement row; standard deviation is the sample standard deviation.": ("O‘rtacha qiymatlar o‘lchov qatorlari bo‘yicha; standart og‘ish tanlanma uchun hisoblangan.", "평균은 측정 행 기준이며 표준편차는 표본 표준편차입니다."),
    "Degree-labeled wind direction uses a circular mean; its standard deviation is not calculated.": ("Gradusdagi shamol yo‘nalishi uchun aylanma o‘rtacha olinadi; standart og‘ish hisoblanmaydi.", "도 단위 풍향은 원형 평균을 사용하며 표준편차는 계산하지 않습니다."),
    "Showing {count} records": ("{count} ta yozuv ko‘rsatilmoqda", "{count}개 기록 표시"),
    ", sorted by {column} ({direction})": (", {column} bo‘yicha saralangan ({direction})", ", {column} 기준 정렬 ({direction})"),
    "descending": ("kamayish tartibida", "내림차순"), "ascending": ("o‘sish tartibida", "오름차순"),
    "Measurement A": ("A o‘lchovi", "측정 항목 A"), "Measurement B": ("B o‘lchovi", "측정 항목 B"), "Valid pairs": ("Yaroqli juftliklar", "유효 쌍"),
    "Uses pairwise complete observations. Unavailable correlations are shown as —. Correlation does not establish a cause.": ("To‘liq juft kuzatuvlar ishlatiladi. Mavjud bo‘lmagan korrelyatsiya — bilan ko‘rsatiladi. Korrelyatsiya sababni isbotlamaydi.", "완전한 관측 쌍을 사용합니다. 계산할 수 없는 상관계수는 —로 표시하며 상관관계가 원인을 입증하지는 않습니다."),
    "— means unavailable.": ("— ma’lumot mavjud emasligini bildiradi.", "—는 사용 가능한 값이 없음을 뜻합니다."),
    "Cars": ("Yengil avtomobillar", "승용차"), "Trucks": ("Yuk mashinalari", "트럭"),
    "Trucks (excluding dump trucks)": ("Yuk mashinalari (samosvallarsiz)", "트럭 (덤프트럭 제외)"),
    "Dump trucks": ("Samosvallar", "덤프트럭"), "Excavators": ("Ekskavatorlar", "굴착기"),
    "Loaders": ("Yuklagichlar", "로더"), "Cranes": ("Kranlar", "크레인"), "People": ("Odamlar", "작업자"), "Other vehicles": ("Boshqa transport", "기타 차량"),
    "Model-estimated counts": ("Model baholagan sonlar", "모델 추정 개수"), "Class": ("Tur", "분류"),
    "Min–max per sampled frame": ("Tanlangan kadr bo‘yicha eng kam–eng ko‘p", "추출 프레임별 최소–최대"),
    "Visible count": ("Ko‘rinadigan son", "보이는 개수"), "Views with counts": ("Son qayd etilgan tasvirlar", "개수가 기록된 이미지"),
    "Counts cover numeric observations only; uncertain or failed views make totals incomplete.": ("Faqat sonli kuzatuvlar hisobga olingan; noaniq yoki muvaffaqiyatsiz tasvirlar sababli jami son to‘liq emas.", "수치 관측만 포함합니다. 불확실하거나 분석에 실패한 이미지로 인해 합계가 불완전할 수 있습니다."),
    "Video frame counts are not unique vehicles across the recording.": ("Videodagi kadr sonlari butun yozuvdagi takrorlanmas transport soni emas.", "프레임별 개수는 전체 영상의 중복 없는 차량 수가 아닙니다."),
    "Tile boundary errors, resizing and orthophoto stitching can affect totals.": ("Bo‘lak chegaralari, o‘lchamni o‘zgartirish va ortofotoni birlashtirish jami songa ta’sir qilishi mumkin.", "타일 경계, 크기 조정과 정사영상 정합 오류가 합계에 영향을 줄 수 있습니다."),
}


def message(language, key, **values):
    index = {"uz": 0, "ko": 1}.get(language)
    template = MESSAGES[key][index] if index is not None and key in MESSAGES else key
    return template.format(**values)
