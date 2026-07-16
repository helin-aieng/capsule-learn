import streamlit as st
import pdfplumber
from openai import OpenAI
import edge_tts
import asyncio
import os

# --- Sayfa Yapılandırması ---
st.set_page_config(
    page_title="CapsuleLearn - Sesli Podcast Asistanı",
    page_icon="🎙️",
    layout="centered"
)

# --- Premium Özel CSS Enjeksiyonu ---
st.markdown("""
<style>
    /* Ana ekran arka planı */
    .main {
        background-color: #0f1117;
    }

    /* Yan menü (Sidebar) arka planı */
    div[data-testid="stSidebar"] {
        background-color: #161922;
    }

    /* Buton Tasarımı (Gradient ve Hover Efekti) */
    div.stButton > button:first-child {
        background: linear-gradient(135deg, #FF4B4B 0%, #8522E1 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 12px 24px;
        font-weight: 600;
        font-size: 1.1rem;
        transition: all 0.3s ease;
    }

    div.stButton > button:first-child:hover {
        transform: translateY(-2px);
        box-shadow: 0px 5px 15px rgba(133, 34, 225, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# --- Çok Dilli Arayüz Sözlüğü (Localization) ---
localization = {
    "tr": {
        "subheader": "Ders notlarınızı yüksek kaliteli sesli podcast'lere dönüştürün.",
        "sidebar_header": "⚙️ Yapılandırma",
        "sidebar_desc": "Yapay zeka sistemini çalıştırmak için bilgilerinizi girin.",
        "api_label": "Groq API Anahtarı",
        "api_help": "Ücretsiz anahtarınızı console.groq.com adresinden alabilirsiniz.",
        "lang_label": "🌐 Dil Seçimi",
        "lang_help": "Hem sayfa arayüzü hem de üretilecek podcast için dil seçin.",
        "sidebar_footer": "⚡ Llama 3.3 & Microsoft Neural TTS",
        "uploader_label": "Ders notunuzu PDF formatında yükleyin",
        "upload_success": "📄 Dosya başarıyla yüklendi!",
        "btn_generate": "🚀 Podcast Kapsülünü Oluştur",
        "api_error": "🔑 Lütfen devam etmek için yan menüye geçerli bir Groq API Anahtarı girin!",
        "step1_msg": "🔍 1. Aşama: PDF içeriği analiz ediliyor ve metinler ayıklanıyor...",
        "pdf_error": "❌ Bu PDF dosyasından okunabilir bir metin çıkartılamadı. Lütfen başka bir dosya deneyin.",
        "step2_msg": "🤖 2. Aşama: Llama 3.3 ile ders notu akıcı bir senaryoya dönüştürülüyor...",
        "success_msg": "✨ Podcast Senaryosu Başarıyla Hazırlandı!",
        "expander_title": "📖 Üretilen Podcast Senaryosunu Görüntüle",
        "listen_header": "### 🎧 Kapsülünüzü Dinleyin",
        "step3_msg": "🔊 3. Aşama: Yapay zeka ses dalgaları sentezleniyor...",
        "info_msg": "💡 Başlamak için yukarıdaki alana ders notu veya slayt PDF'inizi yükleyin.",
        "unexpected_error": "Sistem çalışırken beklenmedik bir hata oluştu: "
    },
    "en": {
        "subheader": "Your lecture notes, redesigned as high-quality audio podcasts.",
        "sidebar_header": "⚙️ Configuration",
        "sidebar_desc": "Enter your credentials to power the AI system.",
        "api_label": "Groq API Key",
        "api_help": "Get your free key from console.groq.com",
        "lang_label": "🌐 Language Selection",
        "lang_help": "Select the language for both interface and the generated podcast.",
        "sidebar_footer": "⚡ Powered by Llama 3.3 & Microsoft Neural TTS",
        "uploader_label": "Upload your lecture notes (PDF)",
        "upload_success": "📄 File successfully uploaded!",
        "btn_generate": "🚀 Generate Podcast Capsule",
        "api_error": "🔑 Please provide a valid Groq API Key in the sidebar to proceed!",
        "step1_msg": "🔍 Phase 1: Reading and parsing PDF context structure...",
        "pdf_error": "❌ Could not extract any readable text from this PDF. Please try another file.",
        "step2_msg": "🤖 Phase 2: Generating conversational script via Llama 3.3...",
        "success_msg": "✨ Podcast Script Compiled Successfully!",
        "expander_title": "📖 View Generated Script Text",
        "listen_header": "### 🎧 Listen Your Capsule",
        "step3_msg": "🔊 Phase 3: Splicing neural vocal waveforms...",
        "info_msg": "💡 Please upload a lecture note PDF above to activate the AI module.",
        "unexpected_error": "An unexpected production failure occurred: "
    }
}


# --- Çekirdek Fonksiyonlar ---

def extract_text_from_pdf(pdf_file_buffer):
    """
    Yüklenen PDF dosyasından ham metni ayıklar.
    """
    full_text = ""
    with pdfplumber.open(pdf_file_buffer) as pdf:
        for page in pdf.pages:
            extracted_text = page.extract_text()
            if extracted_text:
                full_text += extracted_text + "\n"
    return full_text


def generate_podcast_summary_universal(text_content, api_key, lang_code="en"):
    """
    Groq API kullanarak ders notunu belirlenen dilde podcast senaryosuna dönüştürür.
    Girdi dilinden bağımsız olarak çıktı dilini garanti eder.
    """
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key
    )

    if lang_code == "tr":
        system_instruction = (
            "SEN BİR TÜRK PODCAST SUNUCUSUSUN VE SADECE TÜRKÇE KONUŞURSUN.\n"
            "GÖREVİN: Sana verilen ders notunu (not hangi dilde yazılmış olursa olsun), "
            "2 dakikada okunabilecek akıcı, samimi ve eğitici bir Türkçe podcast konuşma metnine dönüştürmek.\n\n"
            "ÇOK KATI KURALLAR:\n"
            "1. YAZACAĞIN TÜM CÜMLELER %100 TÜRKÇE OLMAK ZORUNDADIR. TEK BİR İNGİLİZCE KELİME DAHİ KULLANMA.\n"
            "2. 'Merhaba!', 'Bugün sizlerle...' gibi doğal Türkçe hitaplarla başla.\n"
            "3. Metin içinde 'podcast host', 'script', 'welcome', 'introduction', 'outro', 'narrator' "
            "gibi hiçbir İngilizce sunucu terimi veya parantez içi açıklama yer alamaz.\n"
            "4. 'Brain' yerine 'Beyin', 'Nervous system' yerine 'Sinir sistemi' kullan. Yani ders notu İngilizce olsa bile, "
            "bunları Türkçe karşılıklarıyla anlat.\n"
            "5. Sadece doğrudan seslendirilecek konuşma metnini döndür. Giriş açıklaması veya çıkış notu ekleme."
        )
    else:
        system_instruction = (
            "YOU ARE AN EXPERT ENGLISH PODCAST HOST AND YOU ONLY SPEAK ENGLISH.\n"
            "YOUR TASK: Summarize the provided lecture note (regardless of its original language) into a dynamic, "
            "engaging, and conversational English script that can be read out loud in under 2 minutes.\n\n"
            "STRICT RULES:\n"
            "1. ALL SENTENCES MUST BE 100% IN ENGLISH. Do not use foreign terms.\n"
            "2. Start with natural English greetings like 'Hello everyone!', 'Today, we are diving into...'.\n"
            "3. Do not include brackets, cues like [music], 'Host:', or metadata.\n"
            "4. Just output the raw spoken podcast script. No introductory or concluding developer remarks."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"Lütfen bu ders notunu yukarıdaki kurallara göre özetle:\n\n{text_content}"}
        ],
        max_tokens=2000,
        temperature=0.6
    )
    return response.choices[0].message.content


async def convert_text_to_mp3_async(text_content, output_filename, lang_code):
    """
    Microsoft Neural ses motoru ile metni asenkron olarak MP3'e dönüştürür.
    Hız ayarı yerleşik oyuncu tarafından yapılacağı için sabit 1.0x hızda üretir.
    """
    voice = "tr-TR-AhmetNeural" if lang_code == "tr" else "en-US-AvaNeural"
    communicate = edge_tts.Communicate(text_content, voice)
    await communicate.save(output_filename)


def convert_text_to_mp3(text_content, output_filename="podcast.mp3", lang_code="en"):
    """
    Streamlit içinde asenkron ses fonksiyonunu çalıştırmak için yardımcı sarmalayıcı.
    """
    asyncio.run(convert_text_to_mp3_async(text_content, output_filename, lang_code))


# --- Dil Seçimi İçin İlk Aşama (Sidebar'dan önce dili yakalamak için) ---
if 'lang_choice' not in st.session_state:
    st.session_state['lang_choice'] = "Türkçe"

# --- Yan Menü (Sidebar): Dinamik Çok Dilli Yapılandırma ---
with st.sidebar:
    st.header("⚙️ Configuration" if st.session_state['lang_choice'] == "English" else "⚙️ Yapılandırma")

    language_choice = st.selectbox(
        "Language Selection / Dil Seçimi",
        options=["Türkçe", "English"],
        index=0 if st.session_state['lang_choice'] == "Türkçe" else 1,
        help="Select the interface and podcast language."
    )

    st.session_state['lang_choice'] = language_choice
    active_lang = "tr" if language_choice == "Türkçe" else "en"
    text = localization[active_lang]

    st.write(text["sidebar_desc"])
    user_api_key = st.text_input(text["api_label"], type="password", help=text["api_help"])

    st.divider()
    st.caption(text["sidebar_footer"])

# --- MÜKEMMEL HİZALANMIŞ VE KOD SIZMASI ENGELLENMİŞ BAŞLIK ALANI ---
# Girintiler sola tamamen sıfırlandı ve tek satıra indirgendi, böylece markdown motoru bunu asla kod bloğu olarak yorumlayamaz.
title_html = f'<div style="text-align: center; margin-top: -20px; margin-bottom: 35px; width: 100%;"><div style="font-size: 50px; margin-bottom: -15px; display: block;">🎙️</div><h1 style="background: linear-gradient(135deg, #FF4B4B 0%, #8522E1 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 72px; font-weight: 950; margin: 0px !important; padding: 0px !important; letter-spacing: -2px; line-height: 1.1; font-family: \'Copperplate Gothic Bold\', \'Copperplate Gothic\', \'Copperplate\', sans-serif; display: block;">CAPSULELEARN</h1><div style="color: #a3a8b4; font-size: 1.3rem; font-style: italic; margin: 5px 0px 0px 0px !important; padding: 0px !important; font-family: \'Source Sans Pro\', sans-serif; text-align: center; display: block; width: 100%;">{text["subheader"]}</div></div>'
st.markdown(title_html, unsafe_allow_html=True)

st.divider()

# --- Ana Ekran: Dosya Yükleme Alanı ---
uploaded_file = st.file_uploader(text["uploader_label"], type=["pdf"])

if uploaded_file is not None:
    st.success(text["upload_success"])

    generate_button = st.button(text["btn_generate"], use_container_width=True)

    if generate_button:
        if not user_api_key.strip():
            st.error(text["api_error"])
        else:
            try:
                # --- 1. Aşama: Metin Ayıklama ---
                with st.spinner(text["step1_msg"]):
                    raw_text = extract_text_from_pdf(uploaded_file)

                if not raw_text.strip():
                    st.error(text["pdf_error"])
                else:
                    # --- 2. Aşama: Yapay Zeka Özetleme ---
                    with st.spinner(text["step2_msg"]):
                        podcast_script = generate_podcast_summary_universal(raw_text, user_api_key,
                                                                            lang_code=active_lang)

                    st.session_state['podcast_script'] = podcast_script
                    st.session_state['lang_code'] = active_lang
                    st.success(text["success_msg"])

            except Exception as e:
                st.error(f"{text['unexpected_error']}{str(e)}")

    # --- Dinamik Podcast Alanı (Eğer senaryo hafızada hazırsa gösterilir) ---
    if 'podcast_script' in st.session_state:
        with st.expander(text["expander_title"], expanded=False):
            st.write(st.session_state['podcast_script'])

        st.divider()
        st.markdown(text["listen_header"])

        output_audio_path = "podcast_final.mp3"

        with st.spinner(text["step3_msg"]):
            convert_text_to_mp3(
                st.session_state['podcast_script'],
                output_audio_path,
                lang_code=st.session_state['lang_code']
            )

        with open(output_audio_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
            st.audio(audio_bytes, format="audio/mp3")

        if os.path.exists(output_audio_path):
            os.remove(output_audio_path)

else:
    if 'podcast_script' in st.session_state:
        del st.session_state['podcast_script']
    st.info(text["info_msg"])