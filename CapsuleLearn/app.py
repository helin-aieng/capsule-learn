import os
import streamlit as st

FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"
FFPROBE_PATH = os.path.join(os.path.dirname(FFMPEG_PATH), "ffprobe.exe")

if os.path.exists(FFMPEG_PATH):
    os.environ["FFMPEG_BIN"] = FFMPEG_PATH
if os.path.exists(FFPROBE_PATH):
    os.environ["FFPROBE_BIN"] = FFPROBE_PATH

if "FAL_KEY" in st.secrets:
    os.environ["FAL_KEY"] = st.secrets["FAL_KEY"]

import pdfplumber
import re
import uuid
import hashlib
import tempfile
import datetime
import edge_tts
import asyncio

from openai import OpenAI

# st.dialog (modal pop-up) requires Streamlit >= 1.31. Older Streamlit exposed the same
# thing as st.experimental_dialog; fall back to rendering inline if neither is available
# so the app still runs (just without the small centered pop-up window).
_dialog_decorator = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
if _dialog_decorator is None:
    def _dialog_decorator(*_args, **_kwargs):
        def _wrap(fn):
            return fn
        return _wrap

# Bağlantı ve ayarlar
if "REPLICATE_API_TOKEN" in st.secrets:
    os.environ["REPLICATE_API_TOKEN"] = st.secrets["REPLICATE_API_TOKEN"]
if "GROQ_API_KEY" in st.secrets:
    os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]

# Page ve stil ayarları
st.set_page_config(
    page_title="CapsuleLearn - AI Podcast Assistant",
    page_icon="🎙️",
    layout="centered"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');

    .main { background-color: #0f1117; font-family: 'Inter', sans-serif; }

    .header-container { display: flex; flex-direction: column; align-items: center; margin-bottom: 20px; }
    .icon-box { margin-bottom: 15px; }
    .capsule-title { 
        font-size: 60px; font-weight: 900; 
        background: linear-gradient(90deg, #FF4B4B, #8522E1);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        letter-spacing: -1px; text-transform: uppercase;
    }
    .capsule-sub { color: #8e929e; font-size: 1.1rem; text-align: center; margin-bottom: 30px; }

    div.stButton > button:first-child {
        background: linear-gradient(135deg, #FF4B4B 0%, #8522E1 100%);
        color: white; border: none; border-radius: 12px; padding: 12px 24px;
        font-weight: 700; transition: all 0.3s ease; width: 100%;
    }
    div.stButton > button:first-child:hover { transform: scale(1.02); box-shadow: 0 4px 15px rgba(133, 34, 225, 0.3); }

    /* ---- Onboarding welcome preview ---- */
    .onboarding-preview-wrap { display: flex; justify-content: center; margin: 6px 0 18px 0; }

    /* ---- Compact capsule teaser (sidebar, always visible) ----
       Aynı oda/dekor yığını büyük detay görünümüyle birebir aynı yapıda (bkz. .capsule-room),
       sadece --room-scale ve --acc-scale ile TEK bir oranda (0.6 = 132/220) küçültülüyor.
       Önceki sürümde maskot ayrı, sabit piksel boyutlu bir kutuya (66x70) hapsedilmişti ve bu,
       yüzdesel konumlandırmayı küçük kutuya göre hesaplayıp maskotu gerçek oranından çok daha
       küçük gösteriyordu; şimdi maskot da tıpkı büyük görünümdeki gibi doğrudan yüzdesel
       konumlanıyor, böylece kenar çubuğundaki eşya/maskot boyutları normal ekrandakiyle orantılı. */
    .capsule-teaser-wrap { display: flex; justify-content: center; margin-bottom: 2px; }
    .capsule-teaser {
        position: relative; width: 132px; height: 156px;
        --room-scale: 0.6; --acc-scale: 0.6;
    }
    .capsule-shell {
        position: absolute; inset: 0;
        border-radius: 66px;
        background: linear-gradient(160deg, #23253ecc 0%, #14151d 100%);
        border: 1.5px solid #3d3a56;
        box-shadow: inset 0 0 26px rgba(133,34,225,0.22), 0 8px 20px rgba(0,0,0,0.4);
    }
    .capsule-shell::before {
        content: ""; position: absolute; left: 9%; top: 5%; width: 28%; height: 90%;
        border-radius: 50%; background: linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0));
    }
    .capsule-teaser-level-pill {
        display: table; margin: 10px auto 4px auto;
        background: linear-gradient(135deg, #FF4B4B 0%, #8522E1 100%);
        color: #fff; font-size: 0.78rem; font-weight: 800; padding: 5px 18px;
        border-radius: 20px; white-space: nowrap; box-shadow: 0 3px 10px rgba(133,34,225,0.35);
    }
    .capsule-teaser-name { text-align: center; color: #fff; font-weight: 800; font-size: 1rem; margin-top: 6px; }
    .capsule-teaser-points { text-align: center; color: #FF9F5A; font-weight: 700; font-size: 0.82rem; margin-bottom: 6px; }

    /* ---- Full capsule detail (inside the modal dialog) ---- */
    .capsule-panel-header { display: flex; flex-direction: column; align-items: center; margin-bottom: 6px; }
    .capsule-mascot-stage {
        position: relative; width: 220px; height: 260px; margin: 0 auto 4px auto;
        --acc-scale: 1; --room-scale: 1;
        border-radius: 110px;
        background: linear-gradient(160deg, #23253ecc 0%, #14151d 100%);
        border: 1.5px solid #3d3a56;
        box-shadow: inset 0 0 34px rgba(133,34,225,0.22), 0 10px 26px rgba(0,0,0,0.4);
        overflow: hidden;
    }
    .capsule-mascot-stage::before {
        content: ""; position: absolute; left: 8%; top: 4%; width: 26%; height: 92%;
        border-radius: 50%; background: linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0));
        pointer-events: none;
    }
    .capsule-level-pill {
        display: table; margin: 8px auto 6px auto;
        background: linear-gradient(135deg, #FF4B4B 0%, #8522E1 100%);
        color: #fff; font-size: 0.85rem; font-weight: 800; padding: 6px 20px;
        border-radius: 20px; white-space: nowrap; box-shadow: 0 4px 12px rgba(133,34,225,0.35);
    }
    .capsule-name { color: #fff; font-weight: 800; font-size: 1.2rem; text-align: center; display: block; }
    .capsule-points { color: #FF9F5A; font-weight: 700; font-size: 0.9rem; text-align: center; margin-bottom: 6px; margin-top: 2px; }
    .capsule {
    overflow: hidden;
    }
    /* ---- Capsule room: all shop objects are drawn as purposeful vector props.
       Nothing in the room is positioned as a floating emoji. Every object has a
       physical home: wall, floor, shelf, side table or furniture surface. ---- */
    .capsule-room { position: relative; width: 100%; height: 100%; }
    .capsule-floor-glow {
        position: absolute; bottom: 6%; left: 50%; transform: translateX(-50%);
        width: 70%; height: 17%; border-radius: 50%; z-index: 1;
        background: radial-gradient(ellipse at center, rgba(185,120,255,0.68) 0%, rgba(133,34,225,0.42) 42%, rgba(133,34,225,0.16) 68%, transparent 86%);
        box-shadow: 0 2px 0 rgba(0,0,0,0.15) inset;
    }
    .capsule-floor-glow::after {
        content: ""; position: absolute; inset: 20% 22%; border-radius: 50%;
        border: 1px dashed rgba(255,255,255,0.16);
    }
    .mascot-stack {
        position: absolute; top: 15%; left: 50%; transform: translateX(-50%);
        width: 58%; height: 76%;
        overflow: hidden;
    }
    .mascot-stack svg { position: absolute; inset: 0; width: 100%; height: 100%; z-index: 2; overflow: hidden; }

    .acc-headphones-svg,
    .acc-hat-custom, .acc-crown-custom, .acc-glasses-custom, .acc-bowtie-custom,
    .acc-cape-custom, .acc-medal-custom, .acc-hair-custom, .acc-clothing-custom,
    .acc-earrings-custom {
        position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none;
        filter: drop-shadow(0 3px 4px rgba(0,0,0,.38));
    }
    /* Explicit front-to-back stacking so items never fight each other:
       cape < clothing (shirt/dress) < medal < bowtie/earrings < hair < glasses < hat < crown < coffee cup.
       Hat now lives in its own slot (head_hat, see WEARABLE_CATALOG) so it can be worn
       together with hair, and it is deliberately stacked ABOVE hair — like the crown —
       so a hat always reads as sitting on top of the hair, never hidden behind it. */
    .acc-cape-custom { z-index: 2; }
    .acc-clothing-custom { z-index: 3; }
    .acc-medal-custom { z-index: 4; }
    .acc-bowtie-custom, .acc-earrings-custom { z-index: 5; }
    .acc-hair-custom, .acc-glasses-custom { z-index: 6; }
    .acc-hat-custom { z-index: 7; }
    .acc-crown-custom { z-index: 8; }
    .acc-hair-back-custom { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; filter: drop-shadow(0 3px 4px rgba(0,0,0,.28)); }
    .acc-coffee-custom { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9; filter: drop-shadow(0 3px 4px rgba(0,0,0,.38)); }
    .acc-headphones-svg { z-index: 6; filter: drop-shadow(0 3px 4px rgba(0,0,0,0.42)); }

    /* Realistic room-prop anchors */
    .room-object { position:absolute; z-index:1; pointer-events:none; }
    .room-object svg { width:100%; height:100%; display:block; overflow:visible; filter:drop-shadow(0 3px 4px rgba(0,0,0,.32)); }

    .room-lamp-custom { top:0%; left:50%; transform:translateX(-50%); width:25%; height:31%; z-index:3; }
    /* Abajur (floor lamp) artık sol kenara, kitaplıktan tamamen ayrı bir sütuna
       oturuyor (left:0%, width:18%) — kitaplığın sütunu (left:20%'den başlıyor)
       ile arasında boşluk var, böylece ikisi asla üst üste binip birbirini
       kapatmıyor. */
    .room-floorlamp-custom { bottom: 8%; left: 0%; width: 25%; height: 68%; z-index: 1; }
    .room-rug-custom { bottom:3%; left:50%; transform:translateX(-50%); width:76%; height:18%; z-index:0; }
    .room-candle-custom { bottom:5%; left:9%; width:22%; height:14%; z-index:2; }
    .room-candle-r-custom { bottom:5%; right:9%; width:22%; height:14%; z-index:2; }
    .room-plant-custom { bottom:18%; right:4%; width:27%; height:38%; z-index:2; }
    /* Kitaplık artık avatarı kapatmayacak şekilde sol kenar sütununda (left:1%) duruyor;
       genişliği (20%) mascot-stack'in sol sınırının (yaklaşık %21) içine girmeyecek
       kadar dar tutuldu, böylece robotun gövdesiyle/kollarıyla artık örtüşmüyor. */
    .room-bookshelf-custom { bottom:15%; left:1%; width:20%; height:40%; z-index:1; }
    .room-trophy-custom { bottom:16%; right:7%; width:18%; height:25%; z-index:2; }
    .room-poster-custom { top:15%; left:4%; width:24%; height:29%; z-index:0; }
    .room-window-custom { top:14%; right:4%; width:25%; height:31%; z-index:0; }
    .room-teddy-custom { bottom:12%; left:21%; width:20%; height:23%; z-index:2; }
    .room-clock-custom { top:15%; right:31%; width:16%; height:18%; z-index:1; }
    .room-fairy-custom { top:4%; left:10%; width:80%; height:20%; z-index:1; }
    .room-hanging-plant-custom { top:16%; right:5%; width:24%; height:31%; z-index:1; }
    .room-cushion-custom { bottom:6%; left:34%; width:30%; height:20%; z-index:2; }
    .room-coffee-custom { bottom:28%; right:12%; width:17%; height:15%; z-index:4; }
    /* Pikap artık kullanıcının işaretlediği konumda: üst-sol bölgede, lambanın soluna,
       poster satırının biraz üzerinde duruyor. Kapsülün kabuğu 220x260'lık kutuda
       110px border-radius ile üst kenarı tam bir yarım daire oluşturduğu için (merkez
       110,110 / yarıçap 110), bu üst-sol konum bilerek o dairenin içinde kalacak şekilde
       (top:12%, left:18%) seçildi — daha sola ya da daha yukarı taşınırsa kırpılır. */
    .room-vinyl-custom { top:12%; left:18%; width:20%; height:14%; z-index:1; }
    .room-cat-custom { bottom:8%; right:35%; width:22%; height:15%; z-index:3; }
    .room-guitar-custom { bottom:15%; left:5%; width:18%; height:45%; z-index:1; }

    /* Side tables are part of the object illustrations, with perspective legs. */
    .room-table-left,.room-table-right {
        position:absolute; bottom:16%; width:29%; height:29%; z-index:1;
    }
    .room-table-left { left:2%; } .room-table-right { right:2%; }
    .room-table-left::before,.room-table-right::before {
        content:""; position:absolute; left:8%; top:18%; width:84%; height:15%;
        border-radius:3px 3px 5px 5px;
        background:linear-gradient(180deg,#8b6041,#503522);
        box-shadow:inset 0 1px 1px rgba(255,255,255,.18),0 3px 4px rgba(0,0,0,.35);
        transform:perspective(80px) rotateX(7deg);
        z-index: 2;
    }
    .room-table-left::after,.room-table-right::after {
        content:""; position:absolute; left:12%; top:30%; width:76%; height:60%;
        background: transparent;
        border-left: 4px solid #3c2819;
        border-right: 4px solid #3c2819;
        box-shadow: 12px 0 0 -4px #3c2819, -12px 0 0 -4px #3c2819;
        transform: perspective(100px) rotateX(10deg);
    }

    /* Kept for the existing lamp implementation; now visually refined and used only
       when the lamp is selected. */
    .pendant-lamp { position:absolute; inset:0; width:100%; height:100%; }
    .pendant-lamp-cord { position:absolute; top:0; left:50%; width:2px; height:40%; background:linear-gradient(180deg,#8a8fa0,#707582); border-radius:2px; transform:translateX(-50%); }
    .pendant-lamp-shade { position:absolute; top:36%; left:50%; width:60%; height:34%; transform:translateX(-50%); clip-path:polygon(34% 0,66% 0,100% 88%,92% 100%,8% 100%,0 88%); border-radius:0 0 55% 55%/0 0 40% 40%; background:linear-gradient(180deg,#FFF9C4,#FBC02D); box-shadow:inset 0 -4px 8px rgba(180,120,20,.25); }
    .pendant-lamp-shade::after { content:""; position:absolute; left:50%; bottom:-10%; width:26%; height:24%; transform:translateX(-50%); border-radius:50%; background:#fff3d2; box-shadow:0 0 18px 9px rgba(255,214,122,.5); }
    .pendant-lamp::after { content:""; position:absolute; top:58%; left:50%; width:150%; height:150%; transform:translate(-50%,-10%); border-radius:50%; background:radial-gradient(circle,rgba(255,214,122,.28),transparent 68%); pointer-events:none; }
    .room-floor {
        position:absolute; bottom:4%; left:50%; transform:translateX(-50%);
        width:74%; height:calc(var(--room-scale,1) * 16px); border-radius:50%; z-index:0;
        background:radial-gradient(ellipse at center,rgba(255,159,90,.32),transparent 72%);
    }

    .quest-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #23242f; font-size: 0.88rem; }
    .quest-done { color: #6ce0a0; }
    .quest-pending { color: #d8d9e3; }
    .quest-reward { color: #8e929e; font-size: 0.8rem; }

    /* ---- Shop cards: same fixed-height fix as the onboarding cards ---- */
    .shop-item {
        background: #14151d; border: 1px solid #2a2c3a; border-radius: 12px; padding: 12px 8px;
        text-align: center; margin-bottom: 8px; min-height: 118px;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
    }
    .shop-emoji { font-size: 26px; }
    .shop-vector { width: 48px; height: 42px; display:flex; align-items:center; justify-content:center; margin-bottom:2px; }
    .shop-vector svg { width:100%; height:100%; filter:drop-shadow(0 2px 3px rgba(0,0,0,.3)); }
    .shop-swatch {
        width: 40px; height: 40px; border-radius: 50%;
        border: 2px solid rgba(255,255,255,0.25);
        box-shadow: 0 2px 8px rgba(0,0,0,0.4);
    }
    .shop-name { color: #fff; font-size: 0.82rem; font-weight: 700; margin-top: 4px; line-height: 1.25; }
    .shop-cost { color: #8e929e; font-size: 0.78rem; margin-top: 2px; min-height: 1.1em; }
    .shop-owned-tag { color: #6ce0a0; font-size: 0.78rem; font-weight: 700; }
    .shop-equipped-tag { color: #FF9F5A; font-size: 0.78rem; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# Localization ve içerikler
LOCALIZATION = {
    "tr": {
        "title": "CAPSULELEARN",
        "sub": "Ders notlarınızı yüksek kaliteli sesli podcast'lere dönüştürün.",
        "sidebar": "⚙️ Yapılandırma",
        "btn_gen": "🚀 Podcast Kapsülünü Oluştur",
        "step1": "🔍 1. Aşama: PDF analizi yapılıyor...",
        "step_condense": "🧩 Uzun içerik özetleniyor...",
        "step2": "🤖 2. Aşama: Senaryo üretiliyor...",
        "step3": "🔊 3. Aşama: Ses sentezleniyor...",
        "edit_label": "✍️ Senaryoyu Düzenle:",
        "play_btn": "🔊 Dinle / Güncelle",
        "download_btn": "⬇️ MP3 İndir",
        "multi_upload_label": "PDF (birden fazla dosya seçebilirsiniz)",
        "two_host_toggle": "🎭 İki kişilik podcast formatı ({h1} & {h2})",
        "host1_name": "Ahmet",
        "host2_name": "Emel",
        "single_host_label": "Tekli",
        "history_label": "🗂️ Geçmiş Senaryolar",
        "history_empty": "Henüz kayıtlı senaryo yok.",
        "history_load": "Yükle",
        "err_no_files": "Lütfen en az bir PDF dosyası yükleyin.",
        "err_extract_all": "Yüklenen dosyalardan hiçbirinden metin çıkarılamadı. Dosyaların taranmış görüntü olmadığından emin olun.",
        "err_extract_some": "Şu dosyalardan metin çıkarılamadı ve atlandı: {files}",
        "err_script": "Senaryo üretilirken bir hata oluştu: {err}",
        "err_audio": "Ses sentezlenirken bir hata oluştu: {err}",
        "err_empty_script": "Senaryo boş görünüyor, lütfen düzenleyip tekrar deneyin.",
        "warn_dialogue_parse": "İki kişilik format algılanamadı, senaryo tek anlatıcı olarak seslendirildi.",
        # --- Kapsül / gamification ---
        "onboarding_title": "Kapsülüne Hoş Geldin!",
        "onboarding_sub": "Öğrenme yolculuğunda sana eşlik edecek kapsül dostun Kıvılcım. Sen öğrendikçe o da gelişip evrim geçirecek.",
        "onboarding_name_label": "Ona farklı bir isim vermek ister misin?",
        "onboarding_start_btn": "🚀 Başla",
        "capsule_header": "🧬 Kapsülün",
        "points_unit": "EÇ",
        "points_label": "Enerji Çekirdeği",
        "level_label": "Seviye {lvl}",
        "next_evolution": "Sonraki evrim: Seviye {lvl}",
        "max_stage_note": "En yüksek forma ulaştı! ✨",
        "quests_header": "🎯 Görevler",
        "shop_header": "🛍️ Kapsülü Özelleştir",
        "shop_locked": "🔒 {cost} EÇ",
        "shop_unlock_btn": "Aç",
        "shop_unlocked_tag": "✅ Sende",
        "shop_free_tag": "🎁 Ücretsiz",
        "quest_done_toast": "🎉 Görev tamamlandı: {label} (+{reward} EÇ)",
        "evolve_toast": "✨ {name} evrim geçirdi! Yeni formuna kavuştu.",
        "listen_confirm_btn": "✅ Dinledim, ödülümü al!",
        "listen_confirm_done": "🙌 Bu podcast için ödülünü zaten aldın.",
        "listen_reward_toast": "🎧 Dinleme ödülü: +{amount} EÇ",
        "unlock_toast": "🔓 {name} açıldı!",
        "not_enough_points": "Yetersiz EÇ.",
        "mascots": {
            "robot": {"name": "Kıvılcım", "desc": "Meraklı bir yapay zekâ çekirdeği"},
        },
        "quest_list": [
            {"id": "first_script", "label": "İlk senaryonu oluştur", "reward": 15},
            {"id": "first_audio", "label": "İlk podcastini seslendir", "reward": 15},
            {"id": "first_listen", "label": "Bir podcasti sonuna kadar dinle", "reward": 20},
            {"id": "two_host_try", "label": "İki kişilik podcast formatını dene", "reward": 10},
            {"id": "multi_pdf", "label": "3 farklı kaynaktan senaryo üret", "reward": 20},
            {"id": "five_scripts", "label": "Toplam 5 senaryo üret", "reward": 30},
        ],
        "shop_wearables_tab": "👕 Giyilebilirler",
        "shop_room_tab": "🛋️ Oda Dekorasyonu",
        "shop_skins_tab": "🎨 Renk / Kaplama",
        "starter_gift_note": "🎁 Hoş geldin hediyesi olarak zaten sende.",
        "skin_equip_btn": "Kullan",
        "skin_equipped_tag": "🎨 Kullanımda",
        "item_show_btn": "👁️ Göster",
        "item_hide_btn": "🚫 Kaldır",
        "shop_wearables": [
            {"id": "headphones", "name": "Stüdyo Kulaklığı", "cost": 0},
            {"id": "bowtie", "name": "Şık Papyon", "cost": 0},
            {"id": "medal", "name": "Başarı Madalyonu", "cost": 0},
            {"id": "glasses", "name": "Bilgin Gözlüğü", "cost": 0},
            {"id": "hair_long", "name": "Uzun Saç", "cost": 0},
            {"id": "hair_short", "name": "Kısa Saç", "cost": 0},
            {"id": "vintage_shirt", "name": "Vintage Gömlek", "cost": 0},
            {"id": "dress", "name": "Şık Elbise", "cost": 0},
            {"id": "earrings", "name": "Zarif Küpeler", "cost": 0},
            {"id": "hat", "name": "Parlak Şapka", "cost": 0},
            {"id": "crown", "name": "Zafer Tacı", "cost": 0},
        ],
        "shop_room": [
            {"id": "candle", "name": "Aromatik Mum", "cost": 0},
            {"id": "rug", "name": "Yumuşak Halı", "cost": 0},
            {"id": "lamp", "name": "Sarkan Sıcak Lamba", "cost": 0},
            {"id": "floor_lamp", "name": "Abajur", "cost": 0},
            {"id": "plant", "name": "Mini Bitki", "cost": 0},
            {"id": "teddy", "name": "Sevimli Oyuncak Ayı", "cost": 0},
            {"id": "cushion", "name": "Yumuşak Minder", "cost": 0},
            {"id": "star_poster", "name": "Yıldız Haritası", "cost": 0},
            {"id": "fairy_lights", "name": "Peri Işıkları", "cost": 0},
            {"id": "clock", "name": "Ahşap Duvar Saati", "cost": 0},
            {"id": "hanging_plant", "name": "Sarkan Sarmaşık", "cost": 0},
            {"id": "bookshelf", "name": "Kitaplık", "cost": 0},
            {"id": "coffee_cup", "name": "Sıcak Kahve Fincanı", "cost": 0},
            {"id": "window", "name": "Manzara Penceresi", "cost": 0},
            {"id": "vinyl_player", "name": "Nostaljik Pikap", "cost": 0},
            {"id": "trophy", "name": "Şampiyon Kupası", "cost": 0},
            {"id": "cat", "name": "Uykucu Kedi", "cost": 0},
            {"id": "guitar", "name": "Akustik Gitar", "cost": 0},
        ],
        "shop_skins": [
            {"id": "skin_default", "name": "Varsayılan", "cost": 0},
            {"id": "skin_monochrome", "name": "Gümüş Mono", "cost": 0},
            {"id": "skin_sunset", "name": "Gün Batımı", "cost": 0},
            {"id": "skin_ocean", "name": "Okyanus", "cost": 20},
            {"id": "skin_forest", "name": "Orman", "cost": 50},
            {"id": "skin_royal", "name": "Asil Mor", "cost": 70},
        ],
    },
    "en": {
        "title": "CAPSULELEARN",
        "sub": "Your lecture notes, redesigned as high-quality audio podcasts.",
        "sidebar": "⚙️ Configuration",
        "btn_gen": "🚀 Generate Podcast Capsule",
        "step1": "🔍 Phase 1: Analyzing PDF...",
        "step_condense": "🧩 Condensing long content...",
        "step2": "🤖 Phase 2: Generating script...",
        "step3": "🔊 Phase 3: Synthesizing audio...",
        "edit_label": "✍️ Edit Script:",
        "play_btn": "🔊 Listen / Update",
        "download_btn": "⬇️ Download MP3",
        "multi_upload_label": "PDF (you can select multiple files)",
        "two_host_toggle": "🎭 Two-host podcast format ({h1} & {h2})",
        "host1_name": "Guy",
        "host2_name": "Ava",
        "single_host_label": "Single host",
        "history_label": "🗂️ Script History",
        "history_empty": "No saved scripts yet.",
        "history_load": "Load",
        "err_no_files": "Please upload at least one PDF file.",
        "err_extract_all": "Text could not be extracted from any of the uploaded files. Make sure they are not scanned images.",
        "err_extract_some": "Text could not be extracted from these files, so they were skipped: {files}",
        "err_script": "An error occurred while generating the script: {err}",
        "err_audio": "An error occurred while synthesizing audio: {err}",
        "err_empty_script": "The script looks empty, please edit it and try again.",
        "warn_dialogue_parse": "Two-host format could not be detected, the script was narrated as a single host.",
        # --- Capsule / gamification ---
        "onboarding_title": "Welcome to Your Capsule!",
        "onboarding_sub": "Spark is your capsule companion for this learning journey. It grows and evolves as you learn.",
        "onboarding_name_label": "Want to give it a different name?",
        "onboarding_start_btn": "🚀 Get Started",
        "capsule_header": "🧬 Your Capsule",
        "points_unit": "EC",
        "points_label": "Energy Core",
        "level_label": "Level {lvl}",
        "next_evolution": "Next evolution: Level {lvl}",
        "max_stage_note": "Reached its final form! ✨",
        "quests_header": "🎯 Quests",
        "shop_header": "🛍️ Customize Capsule",
        "shop_locked": "🔒 {cost} EC",
        "shop_unlock_btn": "Unlock",
        "shop_unlocked_tag": "✅ Owned",
        "shop_free_tag": "🎁 Free",
        "quest_done_toast": "🎉 Quest complete: {label} (+{reward} EC)",
        "evolve_toast": "✨ {name} evolved into a new form!",
        "listen_confirm_btn": "✅ I listened, claim reward!",
        "listen_confirm_done": "🙌 You already claimed the reward for this podcast.",
        "listen_reward_toast": "🎧 Listening reward: +{amount} EC",
        "unlock_toast": "🔓 {name} unlocked!",
        "not_enough_points": "Not enough EC.",
        "mascots": {
            "robot": {"name": "Spark", "desc": "A curious little AI core"},
        },
        "quest_list": [
            {"id": "first_script", "label": "Generate your first script", "reward": 15},
            {"id": "first_audio", "label": "Voice your first podcast", "reward": 15},
            {"id": "first_listen", "label": "Listen to a podcast fully", "reward": 20},
            {"id": "two_host_try", "label": "Try the two-host format", "reward": 10},
            {"id": "multi_pdf", "label": "Generate scripts from 3 different sources", "reward": 20},
            {"id": "five_scripts", "label": "Generate 5 scripts in total", "reward": 30},
        ],
        "shop_wearables_tab": "👕 Wearables",
        "shop_room_tab": "🛋️ Room Decor",
        "shop_skins_tab": "🎨 Color / Skin",
        "starter_gift_note": "🎁 Already yours — a welcome gift.",
        "skin_equip_btn": "Use",
        "skin_equipped_tag": "🎨 In use",
        "item_show_btn": "👁️ Show",
        "item_hide_btn": "🚫 Remove",
        "shop_wearables": [
            {"id": "headphones", "name": "Studio Headphones", "cost": 0},
            {"id": "bowtie", "name": "Dapper Bow Tie", "cost": 0},
            {"id": "medal", "name": "Achievement Medal", "cost": 0},
            {"id": "glasses", "name": "Scholar Glasses", "cost": 0},
            {"id": "hair_long", "name": "Long Hair", "cost": 0},
            {"id": "hair_short", "name": "Short Hair", "cost": 0},
            {"id": "vintage_shirt", "name": "Vintage Shirt", "cost": 0},
            {"id": "dress", "name": "Stylish Dress", "cost": 0},
            {"id": "earrings", "name": "Elegant Earrings", "cost": 0},
            {"id": "hat", "name": "Shiny Hat", "cost": 0},
            {"id": "crown", "name": "Victory Crown", "cost": 0},
        ],
        "shop_room": [
            {"id": "candle", "name": "Aromatic Candle", "cost": 0},
            {"id": "rug", "name": "Soft Rug", "cost": 0},
            {"id": "lamp", "name": "Hanging Cozy Lamp", "cost": 0},
            {"id": "floor_lamp", "name": "Floor Lamp", "cost": 0},
            {"id": "plant", "name": "Mini Plant", "cost": 0},
            {"id": "teddy", "name": "Cuddly Teddy Bear", "cost": 0},
            {"id": "cushion", "name": "Soft Cushion", "cost": 0},
            {"id": "star_poster", "name": "Star Chart Poster", "cost": 0},
            {"id": "fairy_lights", "name": "Fairy Lights", "cost": 0},
            {"id": "clock", "name": "Wooden Wall Clock", "cost": 0},
            {"id": "hanging_plant", "name": "Trailing Vine", "cost": 0},
            {"id": "bookshelf", "name": "Bookshelf", "cost": 0},
            {"id": "coffee_cup", "name": "Warm Coffee Cup", "cost": 0},
            {"id": "window", "name": "Landscape Window", "cost": 0},
            {"id": "vinyl_player", "name": "Nostalgic Vinyl", "cost": 0},
            {"id": "trophy", "name": "Champion Trophy", "cost": 0},
            {"id": "cat", "name": "Sleepy Cat", "cost": 0},
            {"id": "guitar", "name": "Acoustic Guitar", "cost": 0},
        ],
        "shop_skins": [
            {"id": "skin_default", "name": "Default", "cost": 0},
            {"id": "skin_monochrome", "name": "Silver Mono", "cost": 0},
            {"id": "skin_sunset", "name": "Sunset", "cost": 0},
            {"id": "skin_ocean", "name": "Ocean", "cost": 20},
            {"id": "skin_forest", "name": "Forest", "cost": 50},
            {"id": "skin_royal", "name": "Royal Purple", "cost": 70},
        ],
    }
}

# Kulaklık: artık maskotun kendi SVG'sine gömülü sabit bir çizim değil, tam gövde
# SVG'siyle aynı koordinat sistemini (viewBox 0 0 140 160) kullanan ayrı bir katman.
# Böylece her ölçekte (kenar çubuğu, modal, karşılama ekranı) hizası bozulmadan
# mağazadan açılıp takılıp çıkarılabilen normal bir aksesuara dönüşüyor.
_HEADPHONES_SVG = (
    '<svg class="acc-headphones-svg" viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
    '<defs>'
    '<linearGradient id="hpBand" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0%" stop-color="#ffffff"/><stop offset="50%" stop-color="#f0f2f5"/><stop offset="100%" stop-color="#cfd8dc"/>'
    '</linearGradient>'
    '<linearGradient id="hpCup" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0%" stop-color="#ffffff"/><stop offset="100%" stop-color="#eceff1"/>'
    '</linearGradient>'
    '</defs>'
    '<path d="M30 80 C30 38 48 18 70 18 C92 18 110 38 110 80" fill="none" stroke="#90a4ae" stroke-width="14" stroke-linecap="round"/>'
    '<path d="M30 80 C30 38 48 22 70 22 C92 22 110 38 110 80" fill="none" stroke="url(#hpBand)" stroke-width="10" stroke-linecap="round"/>'
    '<g transform="translate(14, 65)">'
    '<path d="M15 0 Q0 0 0 24 Q0 48 15 48 Q8 38 8 24 Q8 10 15 0Z" fill="url(#hpCup)" stroke="#b0bec5" stroke-width="1.5"/>'
    '<path d="M8 6 Q2 14 2 24 Q2 34 8 42 Q5 34 5 24 Q5 14 8 6Z" fill="#455a64"/>'
    '</g>'
    '<g transform="translate(126, 65) scale(-1, 1)">'
    '<path d="M15 0 Q0 0 0 24 Q0 48 15 48 Q8 38 8 24 Q8 10 15 0Z" fill="url(#hpCup)" stroke="#b0bec5" stroke-width="1.5"/>'
    '<path d="M8 6 Q2 14 2 24 Q2 34 8 42 Q5 34 5 24 Q5 14 8 6Z" fill="#455a64"/>'
    '</g>'
    '</svg>'
)

# Sıcak kahve fincanı artık bir "oda eşyası" değil, maskotun kendisine bindirilen bir
# aksesuar: sağ kulağın bir tık alt çaprazında, elinde tutuyormuş görüntüsü verecek
# şekilde tam gövde koordinat sistemine (viewBox 0 0 140 160) göre konumlanır ve
# giysi katmanlarının önünde (en üst katmanda) çizilir.
_COFFEE_ACCESSORY_SVG = (
    '<svg class="acc-coffee-custom" viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
    '<g transform="translate(96, 100)">'
    '<path d="M0 8 H26 V24 Q25 34 13 34 Q1 34 0 24Z" fill="#E2725B" stroke="#8C3A22" stroke-width="1.6"/>'
    '<path d="M26 13 H32 Q38 13 38 19 Q38 25 26 25" fill="none" stroke="#8C3A22" stroke-width="2.4"/>'
    '<ellipse cx="13" cy="8" rx="13" ry="3.2" fill="#432A17"/>'
    '<path d="M6 0 Q2 -7 6 -14 M14 0 Q10 -7 14 -14" stroke="#C9A876" stroke-width="1.6" fill="none" opacity="0.75"/>'
    '</g>'
    '</svg>'
)

# Giyilebilir aksesuarlar: maskotun üzerine/yanına binen öğeler. Her biri bir "yuvaya" (slot)
# takılır; aynı yuvada birden fazla öğe varsa (örn. uzun saç/kısa saç) yalnızca öncelikli
# olan gösterilir. Şapka (hat) ve Zafer Tacı (crown) artık KENDİ AYRI yuvalarında
# (sırasıyla head_hat ve head_crown) — bu sayede ikisi de saçla aynı anda takılabiliyor
# ve CSS'te saçtan daha üst z-index'e sahip oldukları için (bkz. .acc-hat-custom,
# .acc-crown-custom) her zaman saçın önünde, tam görünür şekilde durur; tıpkı gerçek bir
# şapka/taç gibi saçın üzerine oturur, saçı "değiştirmez". Tüm maskotlar aynı iç orana
# göre çizildiği için bu yuvalar (bkz. .acc-* CSS sınıfları) her karakterde hizalı kalır.
# "svg" anahtarı olan öğeler (bkz. kulaklık) emoji yerine tam gövdeyi kaplayan kendi
# vektör çizimini kullanır.
WEARABLE_CATALOG = {
    "headphones": {"slot": "head_full", "svg": _HEADPHONES_SVG, "priority": 1, "emoji": ""},
    "hat": {"slot": "head_hat", "css": "acc-hat-custom", "emoji": "", "priority": 1},
    "crown": {"slot": "head_crown", "css": "acc-crown-custom", "emoji": "", "priority": 1},
    "glasses": {"slot": "face", "css": "acc-glasses-custom", "emoji": "", "priority": 1},
    "bowtie": {"slot": "neck", "css": "acc-bowtie-custom", "emoji": "", "priority": 1},
    "cape": {"slot": "back", "css": "acc-cape-custom", "emoji": "", "priority": 1},
    "medal": {"slot": "chest", "css": "acc-medal-custom", "emoji": "", "priority": 1},
    "hair_long": {"slot": "head", "css": "acc-hair-custom", "emoji": "", "priority": 3},
    "hair_short": {"slot": "head", "css": "acc-hair-custom", "emoji": "", "priority": 3},
    "vintage_shirt": {"slot": "body", "css": "acc-clothing-custom", "emoji": "", "priority": 1},
    "dress": {"slot": "body", "css": "acc-clothing-custom", "emoji": "", "priority": 1},
    "earrings": {"slot": "face_acc", "css": "acc-earrings-custom", "emoji": "", "priority": 1},
}


def _wearable_svg(item_id):
    """Purpose-built vector drawings for wearable items — warm/cozy palette,
    aligned to the mascot's actual head/face geometry (viewBox 0 0 140 160)."""
    svgs = {
        # 80'ler/90'lar vintage fötr şapka: bej gövde, ortada kahverengi kuşak, yumuşak
        # geçişli (keskin köşesiz) kurdele ve hafif kıvrık kenarlar (bkz. referans görsel).
        "hat": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="hatBody" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%" stop-color="#E7D2A6"/><stop offset="100%" stop-color="#C9A876"/>'
            '</linearGradient></defs>'
            '<path d="M20 46 Q14 40 24 37 Q46 30 70 30 Q94 30 116 37 Q126 40 120 46 '
            'Q120 50 112 49 Q70 42 28 49 Q20 50 20 46Z" fill="url(#hatBody)" stroke="#9C7B4C" stroke-width="1.6"/>'
            '<path d="M34 37 Q34 8 70 6 Q106 8 106 37 Q70 28 34 37Z" fill="url(#hatBody)" stroke="#9C7B4C" stroke-width="1.8"/>'
            '<path d="M34 33 Q70 42 106 33 L106 22 Q70 31 34 22Z" fill="#8C5A2B" stroke="#6E4620" stroke-width="1.2"/>'
            '</svg>'
        ),
        # Sıcak altın taç, yumuşatılmış dişler. Kendi ayrı yuvasında (head_crown) olduğu
        # için saçla birlikte takılabiliyor; CSS'te en üst katmanda (bkz. .acc-crown-custom)
        # olduğundan hem saçın hem şapkanın önünde, tam görünür şekilde durur.
        "crown": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="crownG" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%" stop-color="#FCE29A"/><stop offset="100%" stop-color="#E8A33D"/>'
            '</linearGradient></defs>'
            '<path d="M34 44 L42 18 L58 36 L70 14 L82 36 L98 18 L106 44Z" fill="url(#crownG)" stroke="#B5762A" stroke-width="2" stroke-linejoin="round"/>'
            '<rect x="34" y="44" width="72" height="10" rx="3" fill="url(#crownG)" stroke="#B5762A" stroke-width="2"/>'
            '<circle cx="70" cy="15" r="3.4" fill="#C1502E"/>'
            '<circle cx="42" cy="19" r="2.6" fill="#7A9471"/>'
            '<circle cx="98" cy="19" r="2.6" fill="#7A9471"/>'
            '</svg>'
        ),
        # Vintage/retro güneş gözlüğü — düzeltildi: iki cam artık aralarında gerçek bir boşluk
        # (köprü payı) bırakacak şekilde konumlanıyor (sol cam x 42-66, sağ cam x 74-98),
        # önceki sürümde iki dikdörtgen 6px iç içe geçiyordu; şimdi köprü, iki camı üst üste
        # bindirmeden zarifçe birbirine bağlayan ayrı bir kavisle çiziliyor.
        "glasses": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="lensG" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%" stop-color="#F6C15C"/><stop offset="100%" stop-color="#E2722C"/>'
            '</linearGradient></defs>'
            '<rect x="42" y="60" width="24" height="19" rx="7" fill="url(#lensG)" fill-opacity="0.88" stroke="#6E4620" stroke-width="3"/>'
            '<rect x="74" y="60" width="24" height="19" rx="7" fill="url(#lensG)" fill-opacity="0.88" stroke="#6E4620" stroke-width="3"/>'
            '<path d="M67 67 Q70 64 73 67" fill="none" stroke="#6E4620" stroke-width="3" stroke-linecap="round"/>'
            '<path d="M42 66 L31 62 M98 66 L109 62" stroke="#6E4620" stroke-width="3" stroke-linecap="round"/>'
            '</svg>'
        ),
        # Ekose desenli örgü papyon, sıcak terracotta/krem.
        "bowtie": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<g transform="translate(70, 100)">'
            '<path d="M0 0 L-18 -11 Q-24 -13 -22 -3 L-15 10 Q-12 14 0 5Z" fill="#C1502E" stroke="#8C3A22" stroke-width="1.5"/>'
            '<path d="M0 0 L18 -11 Q24 -13 22 -3 L15 10 Q12 14 0 5Z" fill="#E2725B" stroke="#8C3A22" stroke-width="1.5"/>'
            '<path d="M-10 -6 L-6 4 M6 -6 L10 4" stroke="#F5E6CA" stroke-width="1" opacity="0.6"/>'
            '<circle cx="0" cy="0" r="6" fill="#E8A33D" stroke="#8C3A22" stroke-width="1.5"/>'
            '</g></svg>'
        ),
        # Kurdele + yıldız madalyon, gövdenin alt-orta kısmına oturur.
        "medal": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M56 96 L70 118 L84 96" fill="none" stroke="#7A9471" stroke-width="7" stroke-linecap="round"/>'
            '<circle cx="70" cy="124" r="11" fill="#F0C36D" stroke="#B5762A" stroke-width="2"/>'
            '<path d="M70 117 L72.4 121.8 L77.6 122.4 L73.8 126 L74.8 131.2 L70 128.6 L65.2 131.2 L66.2 126 L62.4 122.4 L67.6 121.8Z" fill="#B5762A"/>'
            '</svg>'
        ),
        # UZUN SAÇ — ön katman: referans görseldeki gibi ortadan ayrık, alına doğal biçimde
        # düşen ince perçemler + şakaklarda kulakların önünden geçip omuza doğru akan tutamlar.
        # Perçemler bilinçli olarak y≈58'in üzerinde tutuluyor (gözler cy=70, r=8, üst sınırı
        # ≈62), böylece gözleri KAPATMIYOR — sadece alnı çerçeveliyor, tıpkı referanstaki gibi
        # yüz tam görünür kalıyor. Ana saç kütlesi ayrı bir arka katmanda (bkz. _hair_long_back_svg)
        # gövdenin arkasında duruyor; bu ön katman sadece öndeki ince detayları taşıyor.
        "hair_long": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="hairFrontG" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%" stop-color="#8B5E3C"/><stop offset="100%" stop-color="#6B4527"/>'
            '</linearGradient></defs>'
            '<path d="M70 27 Q56 28 48 40 Q43 48 45 57 Q50 48 56 44 Q53 51 53 57 '
            'Q60 46 66 43 Q64 50 65 57 Q70 44 70 57 Q70 44 75 57 Q76 50 74 43 '
            'Q80 46 87 57 Q87 51 84 44 Q90 48 95 57 Q97 48 92 40 Q84 28 70 27Z" '
            'fill="url(#hairFrontG)" stroke="#4E3018" stroke-width="0.8"/>'
            '<path d="M33 58 Q20 71 24 91 Q27 109 21 128 Q28 122 31 133" '
            'fill="none" stroke="url(#hairFrontG)" stroke-width="7" stroke-linecap="round" opacity="0.95"/>'
            '<path d="M107 58 Q120 71 116 91 Q113 109 119 128 Q112 122 109 133" '
            'fill="none" stroke="url(#hairFrontG)" stroke-width="7" stroke-linecap="round" opacity="0.95"/>'
            '</svg>'
        ),
        # KISA SAÇ — düzeltildi: artık robotun kafa geometrisine (kulak daireleri cx=26/114,
        # cy=82, r=11; kafa üst kavisi rect(28,40,84,84,rx30)) tam oturacak şekilde çizildi.
        # Ana kütle üst kavisi kafanın kendi eğrisini takip ediyor, yanlarda kulak hizasında
        # (y≈62-100) hafif dışa kıvrılan "bob" uçları var — böylece kafanın her iki yanına da
        # simetrik ve boşluksuz şekilde yapışıyor.
        "hair_short": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="hairShortG" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%" stop-color="#71492C"/><stop offset="100%" stop-color="#5C3A21"/>'
            '</linearGradient></defs>'
            '<path d="M26 70 Q20 32 70 24 Q120 32 114 70 Q108 52 100 58 Q94 44 84 54 '
            'Q76 40 68 54 Q60 40 52 54 Q44 44 38 58 Q32 52 26 70Z" '
            'fill="url(#hairShortG)" stroke="#432A17" stroke-width="1"/>'
            '<path d="M24 62 Q14 74 22 88 Q28 96 20 100 Q30 98 32 84 Q34 72 24 62Z" '
            'fill="url(#hairShortG)" stroke="#432A17" stroke-width="1"/>'
            '<path d="M116 62 Q126 74 118 88 Q112 96 120 100 Q110 98 108 84 Q106 72 116 62Z" '
            'fill="url(#hairShortG)" stroke="#432A17" stroke-width="1"/>'
            '<path d="M40 40 Q50 30 60 34 M78 34 Q88 30 98 40" stroke="#8B5E3C" stroke-width="1" opacity="0.5" fill="none"/>'
            '</svg>'
        ),
        # Vintage gömlek — yeniden tasarlandı: yüzden (ekran altı y=94) net bir boşluk
        # bırakacak şekilde yaka çizgisi artık y≈97-99'da başlıyor, düğmeli ve daha
        # belirgin bir V yaka + yuvarlatılmış gövde kesimiyle robotun gövde formuna
        # (x 28-112 aralığı, yuvarlatılmış alt köşeler) düzgünce oturuyor.
        "vintage_shirt": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="vshirtG" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0%" stop-color="#E2A23A"/><stop offset="100%" stop-color="#C1502E"/>'
            '</linearGradient></defs>'
            '<path d="M31 99 Q29 114 33 123 Q70 133 107 123 Q111 114 109 99 '
            'Q93 111 70 105 Q47 111 31 99Z" fill="url(#vshirtG)" stroke="#8C3A22" stroke-width="2"/>'
            '<path d="M53 100 Q70 113 87 100 L81 97 Q70 106 59 97Z" fill="#F5E6CA" opacity="0.9"/>'
            '<circle cx="70" cy="113" r="1.6" fill="#8C3A22"/>'
            '<circle cx="70" cy="121" r="1.6" fill="#8C3A22"/>'
            '<path d="M41 115 Q70 125 99 115" stroke="#8C3A22" stroke-width="1" opacity="0.3" fill="none"/>'
            '</svg>'
        ),
        # Askılı, tül pileli, akıcı şık elbise — yeniden tasarlandı: askılar artık kulağın
        # (y 71-93 aralığı) TAMAMEN altından, y≈96'dan başlıyor (önceden y74'te, tam kulak
        # hizasında aniden kesiliyordu ve çok belirgindi); artık ince, uçları yumuşak dolgulu
        # (stroke değil fill) küçük şekiller olarak omuzdan iniyor, bu yüzden "kesilmiş" gibi
        # görünmüyor. Elbise ayrıca daha kısa: gövde y96/108'de başlıyor (önceden y74/92),
        # yüzdeki ağız çizgisinden (y88) net bir boşlukla ayrılıyor. Etek ucuna küçük bir
        # fırfır/pile detayı eklendi (dalgalı scallop kenar).
        "dress": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'

            # Omuzlar
            '<path d="M20 88 Q30 91 43 95 L48 106 L31 110 Q24 102 20 88 Z" '
            'fill="#829C75" stroke="#52664B" stroke-width="2"/>'

            '<path d="M120 88 Q110 91 97 95 L92 106 L109 110 Q116 102 120 88 Z" '
            'fill="#829C75" stroke="#52664B" stroke-width="2"/>'

            # KISA ETEK — daha yukarıda bitiyor
            '<path d="M30 94 '
            'Q70 106 110 94 '
            'L119 119 '
            'Q114 124 108 121 '
            'Q101 128 94 122 '
            'Q87 129 79 123 '
            'Q70 130 61 123 '
            'Q53 129 46 122 '
            'Q39 127 32 121 '
            'Q26 124 21 119 Z" '
            'fill="#829C75" stroke="#52664B" stroke-width="2.5"/>'

            # Üst çizgi
            '<path d="M30 94 Q70 106 110 94" '
            'fill="none" stroke="#B7C7A9" stroke-width="2.5"/>'

            # Kumaş detayı
            '<path d="M25 108 Q70 119 115 108" '
            'fill="none" stroke="#617756" stroke-width="1.5" opacity="0.55"/>'

            '</svg>'
        ),


        # Zarif küpeler — düzeltildi: artık tam yuvarlak değil, hafif oval (elips) halkalar;
        # kulak memesi hizasına (cx=26/114, cy=93) tam oturuyor.
        "earrings": (
            '<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">'
            '<ellipse cx="26" cy="94" rx="4.4" ry="6.4" fill="none" stroke="#E8A33D" stroke-width="2.2"/>'
            '<ellipse cx="114" cy="94" rx="4.4" ry="6.4" fill="none" stroke="#E8A33D" stroke-width="2.2"/>'
            '<circle cx="26" cy="87.5" r="1.4" fill="#B5762A"/>'
            '<circle cx="114" cy="87.5" r="1.4" fill="#B5762A"/>'
            '</svg>'
        ),
    }
    return svgs.get(item_id, "")


def _hair_long_back_svg():
    """Uzun saçın gövdenin ARKASINA düşen ana kütlesi — z-index olarak robot gövdesinin
    (mascot-stack svg, z-index 2) gerisinde kalır (bkz. .acc-hair-back-custom, z-index 1).
    Referans görseldeki gibi tepede ortadan ayrık (center part), her iki yandan omuzların
    altına kadar dalgalı biçimde akan, simetrik bir siluet."""
    return _flatten_html('''
    <svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">
      <defs><linearGradient id="hairBackG" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#8B5E3C"/><stop offset="100%" stop-color="#4E3018"/>
      </linearGradient></defs>
      <path d="M70 26 C50 26 32 40 26 66 C18 92 16 118 22 150 C28 142 26 128 32 132
      C38 136 36 148 44 150 C50 152 50 138 56 142 C62 146 62 156 70 156
      C78 156 78 146 84 142 C90 138 90 152 96 150 C104 148 102 136 108 132
      C114 128 112 142 118 150 C124 118 122 92 114 66 C108 40 90 26 70 26Z"
      fill="url(#hairBackG)" stroke="#3A2411" stroke-width="1"/>
      <path d="M70 26 Q64 44 56 62 M70 26 Q76 44 84 62" stroke="#6B4527" stroke-width="1" opacity="0.4" fill="none"/>
      <path d="M30 70 Q26 100 32 128 M110 70 Q114 100 108 128" stroke="#6B4527" stroke-width="0.8" opacity="0.35" fill="none"/>
    </svg>
    ''')


def render_worn_accessories(equipped_items):
    items = set(equipped_items)
    by_slot = {}
    for item_id in items:
        info = WEARABLE_CATALOG.get(item_id)
        if not info:
            continue
        current = by_slot.get(info["slot"])
        if current is None or info["priority"] > WEARABLE_CATALOG[current]["priority"]:
            by_slot[info["slot"]] = item_id
    html = ""
    # Uzun saç seçiliyse, ana kütle önce ve ayrı bir katman olarak (gövdenin arkasında
    # kalacak z-index ile) eklenir; ön taraftaki kahkül/perçem parçası normal akışta
    # (aşağıdaki döngüde) gövdenin önüne biner.
    if by_slot.get("head") == "hair_long":
        html += f'<div class="acc-hair-back-custom">{_hair_long_back_svg()}</div>'
    for item_id in by_slot.values():
        info = WEARABLE_CATALOG[item_id]
        if "svg" in info:
            html += info["svg"]
        else:
            html += f'<div class="{info["css"]}">{_wearable_svg(item_id)}</div>'
    # Sıcak kahve fincanı artık bir oda eşyası değil; sağ elde tutuluyormuş gibi
    # doğrudan maskotun üzerine, giysi katmanlarının en önüne biner.
    if "coffee_cup" in items:
        html += _COFFEE_ACCESSORY_SVG
    return html


# Oda dekorasyonları: maskotun kendisine değil, arka plandaki "odaya" yerleşen eşyalar.
# Cozy/sıcak konsepte uygun, her biri kendi sabit konumuna (bkz. .room-* CSS sınıfları)
# yerleşen genişletilmiş bir katalog. "custom" alanı olan öğeler emoji yerine özel HTML
# kullanır. "coffee_cup" artık odada değil, doğrudan maskotun üzerinde (elinde) göründüğü
# için render_room_decor bu öğeyi atlar — bkz. render_worn_accessories.
ROOM_CATALOG = {
    "lamp": {"css": "room-object room-lamp-custom", "custom": "pendant_lamp"},
    "floor_lamp": {"css": "room-object room-floorlamp-custom"},
    "rug": {"css": "room-object room-rug-custom"},
    "candle": {"css": "room-object room-candle-custom", "custom": "candle_set"},
    "plant": {"css": "room-object room-plant-custom"},
    "bookshelf": {"css": "room-object room-bookshelf-custom"},
    "trophy": {"css": "room-object room-trophy-custom"},
    "star_poster": {"css": "room-object room-poster-custom"},
    "window": {"css": "room-object room-window-custom"},
    "teddy": {"css": "room-object room-teddy-custom"},
    "clock": {"css": "room-object room-clock-custom"},
    "fairy_lights": {"css": "room-object room-fairy-custom"},
    "hanging_plant": {"css": "room-object room-hanging-plant-custom"},
    "cushion": {"css": "room-object room-cushion-custom"},
    "coffee_cup": {"css": "room-object room-coffee-custom", "custom": "held_by_mascot"},
    "vinyl_player": {"css": "room-object room-vinyl-custom"},
    "cat": {"css": "room-object room-cat-custom"},
    "guitar": {"css": "room-object room-guitar-custom"},
}

# Renk/kaplama (skin) seçenekleri: maskotun gövde rengini değiştiren gradyan çiftleri.
# "skin_default" -> None demek, maskotun kendi orijinal (aşamaya özel) renklerini kullan.
# Diğer skinler seçiliyse, yumurta/uykuda aşaması dahil TÜM aşamalarda gövde/tüy rengi
# bu çiftle değiştirilir — yani örneğin baykuşun yumurta hâli de kişiselleştirilebilir.
SKIN_CATALOG = {
    "skin_default": None,
    "skin_monochrome": ("#d7d9e0", "#6c6f7d"),
    "skin_sunset": ("#ffb37a", "#ff5f6d"),
    "skin_ocean": ("#7fe7ff", "#2f7dff"),
    "skin_forest": ("#b8f0a0", "#3fae5e"),
    "skin_royal": ("#e2c9ff", "#8522E1"),
}

# Ücretsiz "hoş geldin hediyesi" olarak her yeni kapsülde baştan açık olan öğeler
# (giyilebilirlerin/oda dekorasyonunun/renklerin yaklaşık yarısı ücretsiz başlıyor;
# geri kalanı düşük ya da yüksek EÇ karşılığında mağazadan açılıyor).
# Tüm ürünlerin kilidini test için kaldırıyoruz.
STARTER_ITEMS = set(list(WEARABLE_CATALOG.keys()) + list(ROOM_CATALOG.keys()) + list(SKIN_CATALOG.keys()))


def _room_prop_svg(item_id):
    """Vector prop library for room decor — warm/cozy living-room palette,
    each object drawn for its real physical function."""
    svgs = {
        "rug": (
            '<svg viewBox="0 0 300 90" xmlns="http://www.w3.org/2000/svg">'
            '<ellipse cx="150" cy="45" rx="140" ry="38" fill="#C1502E"/>'
            '<ellipse cx="150" cy="45" rx="112" ry="30" fill="#E8A33D"/>'
            '<ellipse cx="150" cy="45" rx="84" ry="22" fill="#C1502E"/>'
            '<ellipse cx="150" cy="45" rx="56" ry="14" fill="#7A9471"/>'
            '<ellipse cx="150" cy="45" rx="140" ry="38" fill="none" stroke="#6B2A16" stroke-width="2"/>'
            '</svg>'
        ),
        # Tek bir mum yerine büyüklü küçüklü, kompakt bir mum seti — kapsülün köşesine
        # sığacak ölçekte, zarif duracak şekilde küçük tutuluyor.
        "candle": (
            '<svg viewBox="0 0 120 90" xmlns="http://www.w3.org/2000/svg">'
            '<g>'
            '<path d="M10 58 Q19 52 28 58 L28 82 Q19 88 10 82Z" fill="#F5E6CA" fill-opacity="0.9" stroke="#C9A876" stroke-width="1.6"/>'
            '<ellipse cx="19" cy="58" rx="9" ry="3" fill="#F0DDB0"/>'
            '<path d="M19 56 Q15 47 19 40 Q23 47 19 56" fill="#E8A33D"/>'
            '</g>'
            '<g>'
            '<path d="M36 42 Q47 35 58 42 L58 82 Q47 89 36 82Z" fill="#F5E6CA" fill-opacity="0.9" stroke="#C9A876" stroke-width="1.6"/>'
            '<ellipse cx="47" cy="42" rx="11" ry="3.4" fill="#F0DDB0"/>'
            '<path d="M47 40 Q42 29 47 20 Q52 29 47 40" fill="#E8A33D"/>'
            '</g>'
            '<g>'
            '<path d="M66 64 Q73 59 80 64 L80 82 Q73 87 66 82Z" fill="#F5E6CA" fill-opacity="0.9" stroke="#C9A876" stroke-width="1.6"/>'
            '<ellipse cx="73" cy="64" rx="7" ry="2.4" fill="#F0DDB0"/>'
            '<path d="M73 62 Q70 55 73 49 Q76 55 73 62" fill="#E8A33D"/>'
            '</g>'
            '</svg>'
        ),
        "plant": (
            '<svg viewBox="0 0 150 250" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M42 178 L108 178 L100 236 Q75 244 50 236Z" fill="#C1502E" stroke="#8C3A22" stroke-width="2"/>'
            '<rect x="40" y="170" width="70" height="12" rx="3" fill="#E2725B" stroke="#8C3A22" stroke-width="1.5"/>'
            '<g fill="none" stroke="#4E6249" stroke-width="2.4" stroke-linecap="round">'
            '<path d="M75 178 Q60 120 30 60"/><path d="M75 178 Q92 118 118 64"/>'
            '<path d="M75 178 Q75 100 68 40"/><path d="M75 178 Q56 132 20 96"/>'
            '<path d="M75 178 Q98 130 132 100"/>'
            '</g>'
            '<g fill="#7A9471" stroke="#4E6249" stroke-width="0.8">'
            '<ellipse cx="30" cy="60" rx="9" ry="20" transform="rotate(-25 30 60)"/>'
            '<ellipse cx="118" cy="64" rx="9" ry="20" transform="rotate(28 118 64)"/>'
            '<ellipse cx="68" cy="40" rx="8" ry="24" transform="rotate(-4 68 40)"/>'
            '<ellipse cx="20" cy="96" rx="7" ry="16" transform="rotate(-40 20 96)"/>'
            '<ellipse cx="132" cy="100" rx="7" ry="16" transform="rotate(42 132 100)"/>'
            '<path d="M30 46 V74 M118 50 V78 M68 20 V60 M20 84 V108 M132 86 V114" stroke="#4E6249" stroke-width="0.6" opacity="0.5"/>'
            '</g></svg>'
        ),
        "bookshelf": (
            '<svg viewBox="0 0 150 220" xmlns="http://www.w3.org/2000/svg">'
            '<rect x="20" y="10" width="110" height="195" rx="5" fill="#6B4226" stroke="#432A17" stroke-width="2"/>'
            '<rect x="28" y="22" width="94" height="55" fill="#2E2019"/>'
            '<rect x="28" y="85" width="94" height="55" fill="#2E2019"/>'
            '<rect x="28" y="148" width="94" height="45" fill="#2E2019"/>'
            '<path d="M35 77V35h9v42ZM47 77V40h9v37ZM60 77V32h9v45ZM73 77V45h9v32ZM89 77V38h9v39ZM105 77V42h9v35" fill="#C1502E"/>'
            '<path d="M35 140V100h9v40ZM47 140V95h9v45ZM60 140V105h9v35ZM76 140V98h9v42ZM92 140V103h9v37ZM108 140V96h8v44" fill="#7A9471"/>'
            '<path d="M35 193V165h9v28ZM48 193V160h9v33ZM61 193V168h9v25ZM77 193V162h9v31ZM93 193V170h9v23" fill="#E8A33D"/>'
            '</svg>'
        ),
        "trophy": (
            '<svg viewBox="0 0 100 130" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M30 20 H70 V52 Q67 77 50 83 Q33 77 30 52Z" fill="#F0C36D" stroke="#B5762A" stroke-width="3"/>'
            '<path d="M30 28 H16 Q15 58 37 61M70 28 H84 Q85 58 63 61" fill="none" stroke="#E8A33D" stroke-width="7"/>'
            '<path d="M50 83V104M30 109H70" stroke="#B5762A" stroke-width="8" stroke-linecap="round"/>'
            '<circle cx="50" cy="45" r="12" fill="#C1502E"/>'
            '</svg>'
        ),
        "poster": (
            '<svg viewBox="0 0 150 180" xmlns="http://www.w3.org/2000/svg">'
            '<rect x="5" y="5" width="140" height="170" rx="3" fill="#2C2140" stroke="#8B5E3C" stroke-width="5"/>'
            '<circle cx="75" cy="80" r="40" fill="#E8A33D" opacity="0.15"/>'
            '<path d="M20 150 Q75 110 130 150" fill="none" stroke="#F0C36D" stroke-width="2" opacity="0.6"/>'
            '<circle cx="40" cy="40" r="2.6" fill="#F5E6CA"/><circle cx="110" cy="60" r="2" fill="#F5E6CA"/><circle cx="60" cy="120" r="2" fill="#F5E6CA"/>'
            '</svg>'
        ),
        # Sarı hava yerine sıcak, alacalı bir gün batımı manzarası.
        "window": (
            '<svg viewBox="0 0 170 190" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="sunsetG" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%" stop-color="#5A3A6B"/><stop offset="45%" stop-color="#C1502E"/>'
            '<stop offset="75%" stop-color="#E8A33D"/><stop offset="100%" stop-color="#F5E6CA"/>'
            '</linearGradient></defs>'
            '<rect x="8" y="8" width="154" height="174" rx="5" fill="#6B4226" stroke="#432A17" stroke-width="4"/>'
            '<rect x="20" y="20" width="130" height="150" fill="url(#sunsetG)"/>'
            '<circle cx="85" cy="100" r="26" fill="#FCE29A" opacity="0.9"/>'
            '<path d="M20 138 Q60 122 85 138 Q115 150 150 134 V170 H20Z" fill="#3A2C4A" opacity="0.75"/>'
            '<path d="M85 20V170M20 95H150" stroke="#432A17" stroke-width="4"/>'
            '</svg>'
        ),
        # Oturur pozisyonda, kitaplığa yaslanan sevimli oyuncak ayı.
        "teddy": (
            '<svg viewBox="0 0 130 150" xmlns="http://www.w3.org/2000/svg">'
            '<ellipse cx="65" cy="132" rx="42" ry="16" fill="#A9764F"/>'
            '<path d="M28 130 Q22 90 34 74 Q26 66 30 54 Q40 46 48 56 Q56 44 65 56 Q74 44 82 56 '
            'Q90 46 100 54 Q104 66 96 74 Q108 90 102 130 Q65 146 28 130Z" fill="#C08A5C" stroke="#8B5E3C" stroke-width="2"/>'
            '<circle cx="38" cy="58" r="10" fill="#A9764F"/><circle cx="92" cy="58" r="10" fill="#A9764F"/>'
            '<circle cx="38" cy="58" r="4.5" fill="#8B5E3C"/><circle cx="92" cy="58" r="4.5" fill="#8B5E3C"/>'
            '<circle cx="50" cy="90" r="4" fill="#3A2415"/><circle cx="80" cy="90" r="4" fill="#3A2415"/>'
            '<ellipse cx="65" cy="104" rx="15" ry="11" fill="#F0DDB0"/>'
            '<circle cx="65" cy="98" r="3.4" fill="#3A2415"/>'
            '<path d="M60 106 Q65 110 70 106" fill="none" stroke="#3A2415" stroke-width="1.6"/>'
            '<ellipse cx="34" cy="118" rx="9" ry="12" fill="#C08A5C" stroke="#8B5E3C" stroke-width="1.4"/>'
            '<ellipse cx="96" cy="118" rx="9" ry="12" fill="#C08A5C" stroke="#8B5E3C" stroke-width="1.4"/>'
            '</svg>'
        ),
        "clock": (
            '<svg viewBox="0 0 110 120" xmlns="http://www.w3.org/2000/svg">'
            '<circle cx="55" cy="58" r="43" fill="#6B4226" stroke="#432A17" stroke-width="3"/>'
            '<circle cx="55" cy="58" r="36" fill="#F5E6CA"/>'
            '<path d="M55 58V38M55 58L70 65" stroke="#432A17" stroke-width="3" stroke-linecap="round"/>'
            '<circle cx="55" cy="58" r="2" fill="#432A17"/>'
            '<path d="M55 28V32M82 58H78M55 88V84M28 58H32" stroke="#C1502E" stroke-width="2" stroke-linecap="round"/>'
            '</svg>'
        ),
        "fairy_lights": (
            '<svg viewBox="0 0 300 80" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M8 28 Q75 65 145 28 T292 28" fill="none" stroke="#6B4226" stroke-width="2"/>'
            '<g fill="#F0C36D"><circle cx="45" cy="47" r="5"/><circle cx="95" cy="48" r="5"/><circle cx="145" cy="28" r="5"/>'
            '<circle cx="195" cy="47" r="5"/><circle cx="245" cy="43" r="5"/></g>'
            '<g fill="#F0C36D" opacity="0.35"><circle cx="45" cy="47" r="10"/><circle cx="145" cy="28" r="10"/><circle cx="245" cy="43" r="10"/></g>'
            '</svg>'
        ),
        "hanging_plant": (
            '<svg viewBox="0 0 140 250" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M30 10 H110" stroke="#8B5E3C" stroke-width="4"/>'
            '<path d="M40 10 L70 42 L100 10" fill="none" stroke="#C9A876" stroke-width="2"/>'
            '<path d="M55 40 H95 L85 68 H65Z" fill="#C1502E" stroke="#8C3A22" stroke-width="2"/>'
            '<g fill="none" stroke="#7A9471" stroke-width="2.6" stroke-linecap="round">'
            '<path d="M60 68 Q35 118 44 236"/><path d="M70 68 Q56 138 50 216"/>'
            '<path d="M80 68 Q98 148 88 226"/><path d="M90 68 Q122 128 112 206"/>'
            '</g>'
            '<g fill="#8FA985" stroke="#4E6249" stroke-width="0.7">'
            '<circle cx="40" cy="100" r="5"/><circle cx="50" cy="140" r="6"/><circle cx="42" cy="180" r="5"/>'
            '<circle cx="112" cy="118" r="6"/><circle cx="116" cy="158" r="5"/>'
            '</g></svg>'
        ),
        "cushion": (
            '<svg viewBox="0 0 170 120" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M15 30 Q85 10 155 30 Q170 60 155 90 Q85 110 15 90 Q0 60 15 30Z" fill="#C1502E" stroke="#8C3A22" stroke-width="2"/>'
            '<path d="M30 40 Q85 25 140 40 M30 80 Q85 95 140 80" fill="none" stroke="#F5E6CA" stroke-width="1.5" stroke-dasharray="4 2" opacity="0.6"/>'
            '</svg>'
        ),
        # Mağaza kartında gösterilen küçük önizleme; canlı hâli artık maskotun elinde
        # bir aksesuar olarak render ediliyor (bkz. _COFFEE_ACCESSORY_SVG).
        "coffee_cup": (
            '<svg viewBox="0 0 80 90" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M25 35 H65 V70 Q63 85 45 85 Q27 85 25 70Z" fill="#E2725B" stroke="#8C3A22" stroke-width="2"/>'
            '<path d="M65 45 H75 Q85 45 85 55 Q85 65 65 65" fill="none" stroke="#8C3A22" stroke-width="4"/>'
            '<ellipse cx="45" cy="35" rx="18" ry="5" fill="#432A17"/>'
            '<path d="M35 25 Q30 15 35 5 M50 25 Q45 15 50 5" stroke="#C9A876" stroke-width="2" fill="none" opacity=".7"/>'
            '</svg>'
        ),
        # Duvar rafında eski pikap (turntable), rafın kendisiyle birlikte çizilir.
        "vinyl_player": (
            '<svg viewBox="0 0 170 150" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M6 40 H164 L156 50 H14Z" fill="#6B4226" stroke="#432A17" stroke-width="2"/>'
            '<rect x="18" y="8" width="134" height="34" rx="4" fill="#6B4226" stroke="#432A17" stroke-width="2"/>'
            '<circle cx="55" cy="25" r="15" fill="#2E2019" stroke="#432A17" stroke-width="2"/>'
            '<circle cx="55" cy="25" r="5" fill="#E8A33D"/>'
            '<rect x="82" y="14" width="58" height="22" rx="2" fill="#2E2019"/>'
            '<path d="M118 16 L136 12 L132 28" fill="none" stroke="#C9A876" stroke-width="2.4" stroke-linecap="round"/>'
            '</svg>'
        ),
        # Abajur — klasik trapez lamba başlığı ve içinde parlayan bir ampul. Ayrı bir
        # sütunda (bkz. .room-floorlamp-custom, left:0%) durduğu için kitaplıkla artık
        # örtüşmüyor.
        "floor_lamp": (
            '<svg viewBox="0 0 90 220" xmlns="http://www.w3.org/2000/svg">'
            '<ellipse cx="30" cy="212" rx="26" ry="7" fill="#432A17"/>'
            '<ellipse cx="30" cy="208" rx="20" ry="5" fill="#6B4226"/>'
            '<path d="M30 205 Q24 120 34 66 Q38 40 44 26" fill="none" stroke="#4E3018" stroke-width="5" stroke-linecap="round"/>'
            '<path d="M30 205 Q24 120 34 66 Q38 40 44 26" fill="none" stroke="#8B5E3C" stroke-width="2.2" stroke-linecap="round"/>'
            '<circle cx="44" cy="24" r="3" fill="#8B5E3C"/>'
            '<path d="M24 26 L64 26 L74 6 L14 6 Z" fill="#FBC02D" fill-opacity="0.35" stroke="#8B5E3C" stroke-width="2" stroke-linejoin="round"/>'
            '<ellipse cx="44" cy="6" rx="16" ry="3" fill="#FCE29A" fill-opacity="0.7"/>'
            '<ellipse cx="44" cy="20" rx="12" ry="8" fill="#fff3d2" opacity="0.85"/>'
            '</svg>'
        ),
        # Önden bakışta tatlı bir kedi surati: kapalı gözler, minik ağız, kıvrık
        # kuyruğu gövdesini saran daha gerçekçi bir yatış pozisyonu.
        "cat": (
            '<svg viewBox="0 0 140 90" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M70 78 Q22 82 18 55 Q16 30 45 24 Q42 12 52 14 Q58 4 66 14 Q70 6 76 15 '
            'Q86 12 84 24 Q112 28 116 52 Q120 80 70 78Z" fill="#E8A33D" stroke="#B5762A" stroke-width="1.6"/>'
            '<path d="M44 22 L40 8 L52 18 M84 22 L90 8 L78 18" fill="#E8A33D" stroke="#B5762A" stroke-width="1.6"/>'
            '<path d="M44 24 L41 12 L50 20 M84 24 L87 12 L78 20" fill="#F3C98A"/>'
            '<path d="M52 42 q6 5 12 0 M64 42 q6 5 12 0" stroke="#5A3A22" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
            '<path d="M66 50 q4 3 8 0" stroke="#5A3A22" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
            '<path d="M36 44 h8 M96 44 h8 M36 50 h8 M96 50 h8" stroke="#B5762A" stroke-width="1" opacity="0.6"/>'
            '<path d="M112 55 Q132 48 130 26 Q129 16 120 18" fill="none" stroke="#E8A33D" stroke-width="8" stroke-linecap="round"/>'
            '<path d="M112 55 Q132 48 130 26 Q129 16 120 18" fill="none" stroke="#B5762A" stroke-width="1" opacity="0.4"/>'
            '</svg>'
        ),
        # Duvara yaslı gerçekçi akustik gitar: gövde inceltilmiş kum saati formu,
        # ses deliği, köprü/tel detayları ve doğru oranlı sap+burgu kafası.
        "guitar": (
            '<svg viewBox="0 0 100 220" xmlns="http://www.w3.org/2000/svg">'
            '<defs><radialGradient id="guitarBody" cx="45%" cy="35%" r="75%">'
            '<stop offset="0%" stop-color="#E2A23A"/><stop offset="100%" stop-color="#A8631F"/>'
            '</radialGradient></defs>'
            '<path d="M50 118 C24 118 16 138 22 156 C27 172 40 180 50 180 '
            'C60 180 73 172 78 156 C84 138 76 118 50 118Z" fill="url(#guitarBody)" stroke="#5C3A17" stroke-width="2"/>'
            '<path d="M50 96 C30 96 24 108 28 120 C31 130 40 136 50 136 '
            'C60 136 69 130 72 120 C76 108 70 96 50 96Z" fill="url(#guitarBody)" stroke="#5C3A17" stroke-width="2"/>'
            '<circle cx="50" cy="148" r="15" fill="#3A2415" stroke="#2A1A0E" stroke-width="1.4"/>'
            '<rect x="46" y="6" width="8" height="112" rx="2" fill="#6B4226" stroke="#3A2415" stroke-width="1"/>'
            '<rect x="47" y="10" width="6" height="106" fill="#3A2415" opacity="0.5"/>'
            '<rect x="38" y="0" width="24" height="14" rx="3" fill="#432A17" stroke="#2A1A0E" stroke-width="1"/>'
            '<circle cx="42" cy="4" r="1.6" fill="#C9A876"/><circle cx="58" cy="4" r="1.6" fill="#C9A876"/>'
            '<circle cx="42" cy="10" r="1.6" fill="#C9A876"/><circle cx="58" cy="10" r="1.6" fill="#C9A876"/>'
            '<path d="M46 118 V178 M50 118 V180 M54 118 V178" stroke="#E7D2A6" stroke-width="0.6" opacity="0.7"/>'
            '<rect x="42" y="176" width="16" height="4" rx="1.5" fill="#3A2415"/>'
            '</svg>'
        ),
    }
    return svgs.get(item_id, "")


def render_room_decor(equipped_items):
    items = set(equipped_items)
    html = ""
    for item_id, info in ROOM_CATALOG.items():
        if item_id not in items:
            continue
        # Sıcak kahve fincanı artık maskotun elinde gösteriliyor (bkz. render_worn_accessories),
        # bu yüzden burada bir oda eşyası olarak çizilmiyor.
        if info.get("custom") == "held_by_mascot":
            continue
        if info.get("custom") == "pendant_lamp":
            html += '<div class="room-object room-lamp-custom"><div class="pendant-lamp"><div class="pendant-lamp-cord"></div><div class="pendant-lamp-shade"></div></div></div>'
        elif info.get("custom") == "candle_set":
            # Küçük mum setleri kapsülün şeklini takip ederek hem sol hem sağ alt
            # köşeye simetrik şekilde yerleştirilir; kapsül kabuğunun oval kenarı
            # tarafından kırpılmaması için köşelerden biraz daha içeri (bkz.
            # .room-candle-custom / .room-candle-r-custom, left/right:9%) alınmıştır.
            html += f'<div class="room-object room-candle-custom">{_room_prop_svg("candle")}</div>'
            html += f'<div class="room-object room-candle-r-custom">{_room_prop_svg("candle")}</div>'
        else:
            svg_id = "poster" if item_id == "star_poster" else item_id
            html += f'<div class="{info["css"]}">{_room_prop_svg(svg_id)}</div>'
    # Side tables/shelves are rendered as furniture, not attached to the icon itself.
    # Bitki ve kitaplık artık kendi masalarını GETİRMİYOR (kullanıcı isteği) — yalnızca
    # sevimli oyuncak ayı (teddy) hâlâ altında bir masa/zemin gösteriyor.
    if "teddy" in items:
        html += '<div class="room-table-left"></div>'
    return html


def _robot_svg(stage, skin_pair=None):
    """stage 0: uykuda çekirdek, 1: uyanmış, 2: usta formu (parıltılı enerji halkası).
    skin_pair verilmişse gövde rengi (yumurta/uykuda aşaması dahil tüm aşamalarda) bu çiftle değiştirilir.
    Kulaklık artık burada gömülü değil: ayrı bir "head_full" giyilebilir aksesuar olarak
    (bkz. _HEADPHONES_SVG / WEARABLE_CATALOG) maskotun üzerine ayrıca bindiriliyor, böylece
    mağazadan açılıp takılıp çıkarılabiliyor."""
    body = {0: ("#4b5165", "#2a2c3a"), 1: ("#8fd7ff", "#4b7bff"), 2: ("#e2c9ff", "#8522E1")}[stage]
    if skin_pair:
        body = skin_pair
    eyes = (
        '<path d="M53 68 q6 5 12 0" stroke="#4b5165" stroke-width="3" fill="none" stroke-linecap="round"/>'
        '<path d="M75 68 q6 5 12 0" stroke="#4b5165" stroke-width="3" fill="none" stroke-linecap="round"/>'
        '<text x="96" y="50" font-size="13" fill="#aeb4c4" font-family="Inter">z Z</text>'
        if stage == 0 else
        '<circle cx="59" cy="70" r="8" fill="#fff"/><circle cx="60.5" cy="71" r="3.4" fill="#151626"/>'
        '<circle cx="81" cy="70" r="8" fill="#fff"/><circle cx="82.5" cy="71" r="3.4" fill="#151626"/>'
        '<circle cx="57.5" cy="68" r="1.6" fill="#fff" opacity="0.9"/>'
        '<circle cx="79.5" cy="68" r="1.6" fill="#fff" opacity="0.9"/>'
    )
    ring = (
        '<circle cx="70" cy="76" r="52" fill="none" stroke="#ffb877" stroke-width="2" opacity="0.55"/>'
        if stage == 2 else ""
    )
    return f'''<svg viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="rb{stage}" cx="35%" cy="28%" r="80%">
          <stop offset="0%" stop-color="{body[0]}"/><stop offset="100%" stop-color="{body[1]}"/>
        </radialGradient>
        <filter id="rbShadow{stage}"><feDropShadow dx="0" dy="5" stdDeviation="5" flood-opacity="0.35"/></filter>
      </defs>
      <ellipse cx="70" cy="146" rx="34" ry="7" fill="#000" opacity="0.28"/>
      {ring}
      <circle cx="26" cy="82" r="11" fill="url(#rb{stage})"/>
      <circle cx="114" cy="82" r="11" fill="url(#rb{stage})"/>
      <rect x="28" y="40" width="84" height="84" rx="30" fill="url(#rb{stage})" filter="url(#rbShadow{stage})"/>
      <rect x="44" y="58" width="52" height="36" rx="17" fill="#151626"/>
      {eyes}
      <path d="M60 88 q10 8 20 0" stroke="#aeb4c4" stroke-width="2.4" fill="none" stroke-linecap="round" opacity="0.8"/>
    </svg>'''


_MASCOT_SVG_BUILDERS = {"robot": _robot_svg}


def _flatten_html(html):
    """Çok satırlı/girintili (ör. üçlü tırnaklı) HTML ya da SVG parçalarını tek satıra
    indirger. Streamlit'in markdown ayrıştırıcısı, satır başında 4+ boşluk gördüğünde
    o kısmı 'kod bloğu' sanıp etiketleri render etmeden düz metin olarak basıyor —
    üretilen tüm HTML/SVG parçacıklarının satır sonu ve girinti içermemesi gerekiyor."""
    return " ".join(html.split())


def render_mascot_visual(mascot_id, stage, equipped_items=None, skin_id="skin_default"):
    """Belirtilen maskot/aşama için katmanlı SVG + kullanıcının o an takılı seçtiği aksesuarları döndürür."""
    skin_pair = SKIN_CATALOG.get(skin_id)
    svg = _flatten_html(_MASCOT_SVG_BUILDERS[mascot_id](stage, skin_pair))
    accessories_html = render_worn_accessories(equipped_items or set())
    return f'<div class="mascot-stack">{svg}{accessories_html}</div>'


def get_mascot_name(txt):
    """Kullanıcı onboarding sırasında Kıvılcım'a özel bir isim verdiyse onu, vermediyse
    varsayılan lokalize ismi döndürür."""
    custom = st.session_state.get("mascot_name")
    return custom if custom else txt["mascots"][st.session_state.mascot_id]["name"]

# Seviye eşikleri: LEVEL_THRESHOLDS[i] = seviye i'ye ulaşmak için gereken toplam puan
LEVEL_THRESHOLDS = [0, 20, 45, 80, 125, 180, 250, 340, 450]
MAX_LEVEL = len(LEVEL_THRESHOLDS) - 1
# 3 evrim aşaması, seviyelere eşit şekilde dağıtılmış
STAGE_LEVEL_STARTS = [0, 3, 6]  # stage 0 -> seviye 0'dan, stage 1 -> seviye 3'ten, stage 2 -> seviye 6'dan itibaren

CHUNK_CHAR_THRESHOLD = 12000

# İki kişilik podcast formatındaki konuşmacıların dile göre görünen adları.
# Senaryodaki satır etiketleri de (örn. "AHMET:"/"EMEL:" ya da "GUY:"/"AVA:") artık
# doğrudan bu isimlerden türetiliyor, böylece kullanıcı senaryoyu düzenlerken hangi
# dilde olursa olsun her zaman gerçek sunucu adlarını görüyor — sabit/teknik bir
# etiket asla ekrana sızmıyor (bkz. generate_script, parse_dialogue, generate_audio_dialogue).
HOST_NAMES = {
    "tr": ("Ahmet", "Emel"),
    "en": ("Guy", "Ava"),
}


def _host_tags(lang):
    """İlgili dil için senaryoda kullanılan satır etiketlerini (büyük harf) döndürür."""
    h1, h2 = HOST_NAMES.get(lang, HOST_NAMES["en"])
    return h1.upper(), h2.upper()


def get_level(points):
    lvl = 0
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if points >= threshold:
            lvl = i
    return lvl


def get_stage(level):
    stage = 0
    for i, start in enumerate(STAGE_LEVEL_STARTS):
        if level >= start:
            stage = i
    return stage


def points_progress(points):
    """Mevcut seviye içindeki ilerleme yüzdesini ve bir sonraki seviye için gereken puanı döndürür."""
    lvl = get_level(points)
    if lvl >= MAX_LEVEL:
        return 1.0, None
    current_th = LEVEL_THRESHOLDS[lvl]
    next_th = LEVEL_THRESHOLDS[lvl + 1]
    frac = (points - current_th) / (next_th - current_th)
    return max(0.0, min(1.0, frac)), next_th


def next_evolution_level(stage):
    if stage >= len(STAGE_LEVEL_STARTS) - 1:
        return None
    return STAGE_LEVEL_STARTS[stage + 1]


# --- Backend Functions ---
def get_groq_client():
    return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=st.secrets["GROQ_API_KEY"])

def extract_text_multi(files):
    combined = ""
    failed_files = []
    for f in files:
        try:
            with pdfplumber.open(f) as pdf:
                file_text = ""
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        file_text += extracted + "\n"
            if file_text.strip():
                combined += f"\n\n--- {f.name} ---\n\n" + file_text
            else:
                failed_files.append(f.name)
        except:
            failed_files.append(f.name)
    return combined, failed_files

def compute_files_signature(files):
    hashes = []
    for f in files:
        f.seek(0)
        content = f.read()
        f.seek(0)
        hashes.append(hashlib.md5(content).hexdigest())
    hashes.sort()
    return hashlib.md5("".join(hashes).encode()).hexdigest()

def chunk_text(text, max_chars=6000):
    paragraphs = text.split("\n")
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 1 > max_chars:
            if current:
                chunks.append(current)
            current = p
        else:
            current += ("\n" if current else "") + p
    if current:
        chunks.append(current)
    return chunks

def condense_text(text, lang, client):
    chunks = chunk_text(text)
    if len(chunks) <= 1:
        return text
    target_lang = "Turkish" if lang == "tr" else "English"
    summaries = []
    for chunk in chunks:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Summarize the key concepts, definitions and important facts from this study "
                        f"material section in {target_lang}. Be concise but information-dense, and do not "
                        "lose important facts, numbers or definitions."
                    )
                },
                {"role": "user", "content": chunk}
            ],
            temperature=0.3
        )
        summaries.append(response.choices[0].message.content)
    return "\n\n".join(summaries)

def generate_script(text, lang, two_host=False):
    client = get_groq_client()
    target_lang = "Turkish" if lang == "tr" else "English"
    # Satır etiketleri artık doğrudan sunucuların gerçek adlarından türetiliyor
    # (örn. TR için 'AHMET:'/'EMEL:', EN için 'GUY:'/'AVA:'), böylece model iki
    # farklı isimlendirme şeması arasında kalıp karıştırmıyor ve düzenleme ekranında
    # kullanıcı her zaman doğru dildeki adları görüyor.
    host1_name, host2_name = HOST_NAMES.get(lang, HOST_NAMES["en"])
    tag1, tag2 = _host_tags(lang)
    if two_host:
        system_prompt = (
            f"You are writing a script for a two-host study podcast in {target_lang}. "
            f"The two hosts are named '{host1_name}' and '{host2_name}'. They discuss and explain "
            "the study material in a natural, conversational, engaging way, as if recording a real "
            "podcast together. "
            "RULES: "
            f"1. Alternate turns between {host1_name} and {host2_name} naturally, like a real conversation. "
            f"2. Each line MUST start with exactly '{tag1}:' for {host1_name}'s lines or '{tag2}:' for "
            f"{host2_name}'s lines, followed only by that host's own spoken words. "
            f"3. Never write the other host's name or tag inside a line — a line starting with '{tag2}:' "
            f"must not also contain the text '{tag1}:' anywhere in it, and vice versa. "
            "4. Use short, punchy, natural spoken sentences suitable for text-to-speech. "
            "5. Keep the total conversation strictly 3-5 minutes when read aloud. "
            f"6. Output MUST be entirely in {target_lang}. "
            f"7. Do not include any narration, stage directions, or text outside the '{tag1}:'/'{tag2}:' format. "
            "8. Sound friendly, curious, and fluent, like real podcast hosts riffing off each other."
        )
    else:
        system_prompt = (
            f"You are a charismatic, fast-paced, and engaging study podcast host in {target_lang}. "
            "Your script will be read by a text-to-speech engine. "
            "RULES: "
            "1. Use short, punchy sentences to make the narration sound natural. "
            "2. Emphasize key terms by phrasing them in a way that sounds important. "
            "3. Keep it strictly 3-5 minutes. "
            f"4. Output MUST be in {target_lang}. "
            "5. Sound natural and humanlike. "
            "6. Sound friendly and talk fluent. "
        )
    text_label = "Metin" if lang == "tr" else "Text"
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"{text_label}:\n\n{text}"}],
        temperature=0.6
    )
    return response.choices[0].message.content

async def generate_audio_edge(text, lang, output_path):
    voice = "tr-TR-İsmetNeural" if lang == "tr" else "en-US-AvaNeural"
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
    except:
        fallback = "tr-TR-EmelNeural" if lang == "tr" else "en-US-AvaNeural"
        communicate = edge_tts.Communicate(text, fallback)
        await communicate.save(output_path)

def parse_dialogue(script_text, lang):
    tag1, tag2 = _host_tags(lang)
    pattern = re.compile(rf'^({re.escape(tag1)}|{re.escape(tag2)}):\s*(.+)$', re.MULTILINE)
    return pattern.findall(script_text)

async def generate_audio_dialogue(script_text, lang, output_path):
    tag1, tag2 = _host_tags(lang)
    voices = {
        "tr": {"AHMET": "tr-TR-AhmetNeural", "EMEL": "tr-TR-EmelNeural"},
        "en": {"GUY": "en-US-GuyNeural", "AVA": "en-US-AvaNeural"}
    }
    turns = parse_dialogue(script_text, lang)
    if not turns:
        await generate_audio_edge(script_text, lang, output_path)
        return False
    lang_voices = voices.get(lang, voices["en"])
    segment_bytes = []
    fallback = lang_voices.get(tag1)
    with tempfile.TemporaryDirectory() as tmp_dir:
        for idx, (host, line) in enumerate(turns):
            voice = lang_voices.get(host, fallback)
            seg_path = os.path.join(tmp_dir, f"seg_{idx}.mp3")
            try:
                communicate = edge_tts.Communicate(line, voice)
                await communicate.save(seg_path)
            except:
                communicate = edge_tts.Communicate(line, fallback)
                await communicate.save(seg_path)
            with open(seg_path, "rb") as f:
                segment_bytes.append(f.read())
    with open(output_path, "wb") as out_f:
        for b in segment_bytes:
            out_f.write(b)
    return True


# --- Gamification helpers ---
def award_points(amount):
    st.session_state.points += amount

def check_quests(txt):
    """Görev koşullarını kontrol eder, yeni tamamlananlar için puan verir ve toast gösterir."""
    s = st.session_state
    conditions = {
        "first_script": s.script_count >= 1,
        "first_audio": s.audio_count >= 1,
        "first_listen": s.listen_count >= 1,
        "two_host_try": s.two_host_used,
        "multi_pdf": len(s.unique_pdf_signatures) >= 3,
        "five_scripts": s.script_count >= 5,
    }
    for quest in txt["quest_list"]:
        qid = quest["id"]
        if qid in s.completed_quests:
            continue
        if conditions.get(qid, False):
            s.completed_quests.add(qid)
            award_points(quest["reward"])
            st.toast(txt["quest_done_toast"].format(label=quest["label"], reward=quest["reward"]))
    check_evolution(txt)

def check_evolution(txt):
    s = st.session_state
    level = get_level(s.points)
    new_stage = get_stage(level)
    if new_stage > s.mascot_stage:
        s.mascot_stage = new_stage
        name = get_mascot_name(txt)
        st.toast(txt["evolve_toast"].format(name=name))
        st.balloons()


def _render_shop_group(txt, items, key_prefix):
    """Bir aksesuar grubunu (giyilebilir ya da oda dekorasyonu) 2 sütunlu kartlar halinde çizer.
    Sahip olmak ile takılı/yerleşik olmak ayrı şeylerdir: sahip olunan her öğe için kullanıcı
    'Göster'/'Kaldır' ile maskotta görünüp görünmeyeceğini kendisi seçer."""
    s = st.session_state
    cols = st.columns(2)
    for idx, item in enumerate(items):
        with cols[idx % 2]:
            iid = item["id"]
            owned = iid in s.unlocked_items
            equipped = iid in s.equipped_items
            is_free = item["cost"] == 0
            if owned:
                cost_html = ""
            elif is_free:
                cost_html = txt["shop_free_tag"]
            else:
                cost_html = txt["shop_locked"].format(cost=item["cost"])
            if iid in WEARABLE_CATALOG and iid != "headphones":
                preview = f'<div class="shop-vector">{_wearable_svg(iid)}</div>'
            elif iid == "headphones":
                preview = f'<div class="shop-vector">{_HEADPHONES_SVG}</div>'
            elif iid == "lamp":
                preview = '<div class="shop-vector"><div class="pendant-lamp" style="position:relative;width:48px;height:42px;"><div class="pendant-lamp-cord"></div><div class="pendant-lamp-shade"></div></div></div>'
            elif iid in ROOM_CATALOG:
                preview_id = "poster" if iid == "star_poster" else iid
                preview = f'<div class="shop-vector">{_room_prop_svg(preview_id)}</div>'
            else:
                preview = '<div class="shop-emoji">•</div>'
            card_html = (
                '<div class="shop-item">'
                f'{preview}'
                f'<div class="shop-name">{item["name"]}</div>'
                f'<div class="shop-cost">{cost_html}</div>'
                '</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)
            if owned:
                tag = txt["starter_gift_note"] if iid in STARTER_ITEMS else txt["shop_unlocked_tag"]
                st.markdown(f'<div class="shop-owned-tag" style="text-align:center;">{tag}</div>', unsafe_allow_html=True)
                if equipped:
                    if st.button(txt["item_hide_btn"], key=f"{key_prefix}_hide_{iid}", use_container_width=True):
                        s.equipped_items.discard(iid)
                        st.rerun()
                else:
                    if st.button(txt["item_show_btn"], key=f"{key_prefix}_show_{iid}", use_container_width=True):
                        s.equipped_items.add(iid)
                        st.rerun()
            else:
                if st.button(txt["shop_unlock_btn"], key=f"{key_prefix}_{iid}",
                             disabled=s.points < item["cost"], use_container_width=True):
                    s.points -= item["cost"]
                    s.unlocked_items.add(iid)
                    s.equipped_items.add(iid)
                    st.toast(txt["unlock_toast"].format(name=item["name"]))
                    st.rerun()


def _render_skin_shop(txt):
    """Renk/kaplama seçeneklerini iki sütunlu kartlar halinde çizer. Diğer gruplardan farkı:
    aynı anda yalnızca bir tanesi 'kullanımda' olabilir, bu yüzden sahiplenilenler için
    Aç/Kilit yerine bir 'Kullan' butonu gösterilir."""
    s = st.session_state
    cols = st.columns(2)
    for idx, skin in enumerate(txt["shop_skins"]):
        with cols[idx % 2]:
            sid = skin["id"]
            owned = sid in s.unlocked_items
            equipped = s.skin_id == sid
            is_free = skin["cost"] == 0
            if owned:
                cost_html = ""
            elif is_free:
                cost_html = txt["shop_free_tag"]
            else:
                cost_html = txt["shop_locked"].format(cost=skin["cost"])
            pair = SKIN_CATALOG.get(sid) or ("#8fd7ff", "#4b7bff")
            card_html = (
                '<div class="shop-item">'
                f'<div class="shop-swatch" style="background: linear-gradient(135deg, {pair[0]}, {pair[1]});"></div>'
                f'<div class="shop-name">{skin["name"]}</div>'
                f'<div class="shop-cost">{cost_html}</div>'
                '</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)
            if owned:
                if equipped:
                    st.markdown(
                        f'<div class="shop-equipped-tag" style="text-align:center;">{txt["skin_equipped_tag"]}</div>',
                        unsafe_allow_html=True
                    )
                elif st.button(txt["skin_equip_btn"], key=f"skin_eq_{sid}", use_container_width=True):
                    s.skin_id = sid
                    st.rerun()
            else:
                if st.button(txt["shop_unlock_btn"], key=f"shop_sk_{sid}",
                             disabled=s.points < skin["cost"], use_container_width=True):
                    s.points -= skin["cost"]
                    s.unlocked_items.add(sid)
                    s.skin_id = sid
                    st.toast(txt["unlock_toast"].format(name=skin["name"]))
                    st.rerun()


def render_capsule_detail(txt):
    """Kapsülün tüm ayrıntıları: büyük maskot (giydirilmiş aksesuarlar + oda dekorasyonuyla), seviye, görevler, mağaza.
    Bu içerik yalnızca modal diyalog içinde gösterilir."""
    s = st.session_state
    name = get_mascot_name(txt)
    level = get_level(s.points)
    frac, next_th = points_progress(s.points)

    mascot_html = render_mascot_visual(s.mascot_id, s.mascot_stage, s.equipped_items, s.skin_id)
    room_html = render_room_decor(s.equipped_items)

    # NOT: HTML tek satırda (baştaki boşluksuz) üretiliyor. Bu string Python girinti
    # seviyesine göre çok satırlı ve baştan boşluklu yazılırsa, Streamlit'in markdown
    # ayrıştırıcısı 4+ boşlukla başlayan satırları "kod bloğu" sanıp etiketleri
    # render etmeden düz metin olarak basıyor — önceki sürümdeki hatanın kaynağı buydu.
    capsule_html = (
        '<div class="capsule-panel-header">'
        '<div class="capsule-mascot-stage"><div class="capsule-room">'
        '<div class="capsule-floor-glow"></div>'
        f'{mascot_html}{room_html}'
        '</div></div>'
        f'<div class="capsule-level-pill">{txt["level_label"].format(lvl=level)}</div>'
        f'<span class="capsule-name">{name}</span>'
        f'<div class="capsule-points">{s.points} {txt["points_unit"]}</div>'
        '</div>'
    )
    st.markdown(capsule_html, unsafe_allow_html=True)
    st.progress(frac)
    next_evo = next_evolution_level(s.mascot_stage)
    if next_evo is not None:
        st.caption(txt["next_evolution"].format(lvl=next_evo))
    else:
        st.caption(txt["max_stage_note"])

    st.markdown(f"**{txt['quests_header']}**")
    for quest in txt["quest_list"]:
        done = quest["id"] in s.completed_quests
        mark = "✅" if done else "⬜"
        css_class = "quest-done" if done else "quest-pending"
        st.markdown(
            f'<div class="quest-item"><span class="{css_class}">{mark} {quest["label"]}</span>'
            f'<span class="quest-reward">+{quest["reward"]}</span></div>',
            unsafe_allow_html=True
        )

    st.markdown(f"**{txt['shop_header']}**")
    tab_wearables, tab_room, tab_skins = st.tabs(
        [txt["shop_wearables_tab"], txt["shop_room_tab"], txt["shop_skins_tab"]]
    )
    with tab_wearables:
        _render_shop_group(txt, txt["shop_wearables"], "shop_w")
    with tab_room:
        _render_shop_group(txt, txt["shop_room"], "shop_r")
    with tab_skins:
        _render_skin_shop(txt)


@_dialog_decorator("🧬")
def _capsule_dialog():
    """Küçük kapsül rozetine tıklanınca açılan, sayfadan daha küçük ortalanmış pencere."""
    txt = LOCALIZATION[st.session_state.get("lang", "tr")]
    st.subheader(txt["capsule_header"])
    render_capsule_detail(txt)


def render_capsule_panel(txt):
    """Sidebar'da her zaman görünen küçük, şık kapsül rozeti. Tıklanınca ayrıntılar
    (giydirilmiş aksesuarlar, görevler, mağaza) daha küçük, ortalanmış bir pencerede açılır."""
    s = st.session_state
    name = get_mascot_name(txt)
    level = get_level(s.points)
    mascot_html = render_mascot_visual(s.mascot_id, s.mascot_stage, s.equipped_items, s.skin_id)
    room_html = render_room_decor(s.equipped_items)

    # Tek satır HTML — bkz. render_capsule_detail üstündeki not (girinti = kod bloğu hatası).
    # mascot_html artık büyük detay görünümündeki gibi doğrudan .capsule-teaser'ın içine
    # yerleşiyor (sabit piksel boyutlu ayrı bir kutuya hapsedilmiyor), böylece --room-scale
    # ile aynı orantıda büyüyüp küçülüyor.
    teaser_html = (
        '<div class="capsule-teaser-wrap"><div class="capsule-teaser">'
        '<div class="capsule-shell"></div>'
        '<div class="capsule-floor-glow"></div>'
        f'{mascot_html}{room_html}'
        '</div></div>'
        f'<div class="capsule-teaser-level-pill">{txt["level_label"].format(lvl=level)}</div>'
        f'<div class="capsule-teaser-name">{name}</div>'
        f'<div class="capsule-teaser-points">{s.points} {txt["points_unit"]}</div>'
    )

    with st.sidebar:
        st.markdown("---")
        st.markdown(teaser_html, unsafe_allow_html=True)
        if st.button(f"🧬 {txt['capsule_header']}", key="open_capsule_dialog", use_container_width=True):
            _capsule_dialog()


def render_onboarding(txt):
    """Karşılama ekranı: 'Kapsüle Hoş Geldin' mesajı, Kıvılcım'ın (boş/dekorasyonsuz) varsayılan
    kapsül önizlemesi ve isteğe bağlı isim değiştirme alanı. Artık aralarından seçim yapılacak
    birden çok maskot yok — kapsül tek dostla (Kıvılcım) başlıyor."""
    header_html = (
        '<div class="header-container">'
        f'<div class="capsule-title" style="font-size:38px;">{txt["onboarding_title"]}</div>'
        '</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)
    st.markdown(f'<p class="capsule-sub">{txt["onboarding_sub"]}</p>', unsafe_allow_html=True)

    # Başlangıçta kapsül neredeyse boş: yalnızca Kıvılcım'ın imzası olan stüdyo kulaklığı
    # varsayılan takılı geliyor (hoş geldin hediyesi), oda dekorasyonunun geri kalanını
    # kullanıcı ilerledikçe mağazadan kendi zevkine göre dolduracak.
    mascot_html = render_mascot_visual("robot", 0, equipped_items={"headphones"}, skin_id="skin_default")
    preview_html = (
        '<div class="capsule-panel-header"><div class="capsule-mascot-stage">'
        '<div class="capsule-room"><div class="capsule-floor-glow"></div>'
        f'{mascot_html}'
        '</div></div></div>'
    )
    _, mid_col, _ = st.columns([1, 2, 1])
    with mid_col:
        st.markdown(preview_html, unsafe_allow_html=True)
        default_name = txt["mascots"]["robot"]["name"]
        chosen_name = st.text_input(
            txt["onboarding_name_label"], value="", placeholder=default_name, key="onboarding_name_input"
        )
        if st.button(txt["onboarding_start_btn"], key="onboarding_start", use_container_width=True):
            st.session_state.mascot_id = "robot"
            st.session_state.mascot_stage = 0
            st.session_state.mascot_name = chosen_name.strip() or None
            st.session_state.onboarded = True
            st.rerun()
    st.stop()


# --- Session State ---
if 'lang' not in st.session_state:
    st.session_state.lang = "tr"
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if 'history' not in st.session_state:
    st.session_state.history = []
if 'two_host' not in st.session_state:
    st.session_state.two_host = False

# Gamification state
if 'mascot_id' not in st.session_state:
    st.session_state.mascot_id = "robot"
if 'mascot_name' not in st.session_state:
    st.session_state.mascot_name = None
if 'onboarded' not in st.session_state:
    st.session_state.onboarded = False
if 'mascot_stage' not in st.session_state:
    st.session_state.mascot_stage = 0
if 'points' not in st.session_state:
    st.session_state.points = 0
if 'completed_quests' not in st.session_state:
    st.session_state.completed_quests = set()
if 'unlocked_items' not in st.session_state:
    st.session_state.unlocked_items = set(STARTER_ITEMS)
if 'equipped_items' not in st.session_state:
    # Sahip olmak otomatik takılı/yerleşik olmak anlamına gelmiyor — hediye edilen
    # veya satın alınan öğeler mağazada kullanıcı "Göster" demeden maskotta görünmez.
    # İstisna: stüdyo kulaklığı Kıvılcım'ın imzası olduğu için varsayılan takılı geliyor,
    # kullanıcı isterse mağazadan "Kaldır" diyerek çıkarabilir.
    st.session_state.equipped_items = {"headphones"}
if 'skin_id' not in st.session_state:
    st.session_state.skin_id = "skin_default"
if 'script_count' not in st.session_state:
    st.session_state.script_count = 0
if 'audio_count' not in st.session_state:
    st.session_state.audio_count = 0
if 'listen_count' not in st.session_state:
    st.session_state.listen_count = 0
if 'unique_pdf_signatures' not in st.session_state:
    st.session_state.unique_pdf_signatures = set()
if 'two_host_used' not in st.session_state:
    st.session_state.two_host_used = False
if 'current_audio_listened' not in st.session_state:
    st.session_state.current_audio_listened = True  # henüz üretilmiş ses yok
if 'audio_path' not in st.session_state:
    st.session_state.audio_path = None

with st.sidebar:
    st.header(LOCALIZATION[st.session_state.lang]["sidebar"])
    lang_sel = st.selectbox("Language / Dil", ["Türkçe", "English"])
    st.session_state.lang = "tr" if lang_sel == "Türkçe" else "en"

txt = LOCALIZATION[st.session_state.lang]

# Maskot seçilmediyse önce onboarding ekranını göster
if not st.session_state.onboarded:
    render_onboarding(txt)

render_capsule_panel(txt)

with st.sidebar:
    st.markdown("---")
    st.subheader(txt["history_label"])
    if not st.session_state.history:
        st.caption(txt["history_empty"])
    else:
        for entry in reversed(st.session_state.history):
            with st.expander(f"{entry['timestamp']} · {entry['title']}"):
                for variant_key, variant in entry["variants"].items():
                    mode_label = f"{txt['host1_name']} & {txt['host2_name']}" if variant["two_host"] else txt["single_host_label"]
                    cols = st.columns([3, 1])
                    with cols[0]:
                        st.caption(f"{variant['lang'].upper()} · {mode_label}")
                    with cols[1]:
                        if st.button(txt["history_load"], key=f"load_{entry['id']}_{variant_key}"):
                            st.session_state.script = variant["script"]
                            st.session_state.lang = variant["lang"]
                            st.session_state.two_host = variant["two_host"]
                            st.rerun()

# Logo ve alt yazı
logo_html = _flatten_html("""
<div class="header-container">
    <div class="icon-box">
        <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="url(#gradient)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <defs><linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#FF4B4B"/><stop offset="100%" style="stop-color:#8522E1"/></linearGradient></defs>
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"></path>
        </svg>
    </div>
    <div class="capsule-title">CAPSULELEARN</div>
</div>
""")
st.markdown(logo_html, unsafe_allow_html=True)
st.markdown(f'<div class="capsule-sub"><i>{txt["sub"]}</i></div>', unsafe_allow_html=True)

uploaded_files = st.file_uploader(txt["multi_upload_label"], type=["pdf"], accept_multiple_files=True)
two_host_label = txt["two_host_toggle"].format(h1=txt["host1_name"], h2=txt["host2_name"])
st.session_state.two_host = st.checkbox(two_host_label, value=st.session_state.two_host)

if uploaded_files:
    if st.button(txt["btn_gen"]):
        with st.spinner(txt["step1"]):
            try:
                raw_text, failed_files = extract_text_multi(uploaded_files)
            except Exception as e:
                st.error(txt["err_script"].format(err=str(e)))
                st.stop()
        if not raw_text.strip():
            st.error(txt["err_extract_all"])
            st.stop()
        if failed_files:
            st.warning(txt["err_extract_some"].format(files=", ".join(failed_files)))
        try:
            if len(raw_text) > CHUNK_CHAR_THRESHOLD:
                with st.spinner(txt["step_condense"]):
                    client = get_groq_client()
                    raw_text = condense_text(raw_text, st.session_state.lang, client)
        except Exception as e:
            st.error(txt["err_script"].format(err=str(e)))
            st.stop()
        with st.spinner(txt["step2"]):
            try:
                script = generate_script(raw_text, st.session_state.lang, st.session_state.two_host)
                st.session_state.script = script
                signature = compute_files_signature(uploaded_files)
                variant_key = f"{st.session_state.lang}_{st.session_state.two_host}"
                variant = {
                    "lang": st.session_state.lang,
                    "two_host": st.session_state.two_host,
                    "script": script
                }
                existing_entry = next(
                    (e for e in st.session_state.history if e["signature"] == signature), None
                )
                if existing_entry:
                    existing_entry["variants"][variant_key] = variant
                    existing_entry["timestamp"] = datetime.datetime.now().strftime("%H:%M:%S")
                else:
                    if len(uploaded_files) == 1:
                        title_source = uploaded_files[0].name
                    else:
                        title_source = f"{uploaded_files[0].name} +{len(uploaded_files) - 1}"
                    st.session_state.history.append({
                        "id": str(uuid.uuid4()),
                        "title": title_source,
                        "signature": signature,
                        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                        "variants": {variant_key: variant}
                    })

                # --- Gamification: senaryo üretim ödülü ---
                st.session_state.script_count += 1
                st.session_state.unique_pdf_signatures.add(signature)
                if st.session_state.two_host:
                    st.session_state.two_host_used = True
                st.session_state.current_audio_listened = True  # yeni senaryo, henüz sesi yok
                award_points(10)
                check_quests(txt)
                st.rerun()
            except Exception as e:
                st.error(txt["err_script"].format(err=str(e)))
                st.stop()
elif uploaded_files is not None and len(uploaded_files) == 0:
    pass

if 'script' in st.session_state:
    with st.expander(txt["edit_label"], expanded=True):
        st.session_state.script = st.text_area("", value=st.session_state.script, height=300)
    if st.button(txt["play_btn"]):
        if not st.session_state.script.strip():
            st.error(txt["err_empty_script"])
            st.stop()
        output_path = os.path.join(tempfile.gettempdir(), f"capsulelearn_{st.session_state.session_id}.mp3")
        with st.spinner(txt["step3"]):
            try:
                if st.session_state.two_host:
                    asyncio.run(
                        generate_audio_dialogue(st.session_state.script, st.session_state.lang, output_path)
                    )
                else:
                    asyncio.run(
                        generate_audio_edge(st.session_state.script, st.session_state.lang, output_path)
                    )
            except Exception as e:
                st.error(txt["err_audio"].format(err=str(e)))
                st.stop()

        # --- Gamification: ses üretim ödülü ---
        st.session_state.audio_count += 1
        st.session_state.current_audio_listened = False
        st.session_state.audio_path = output_path
        award_points(15)
        check_quests(txt)
        st.rerun()

if st.session_state.get("audio_path") and os.path.exists(st.session_state.audio_path):
    st.audio(st.session_state.audio_path)
    with open(st.session_state.audio_path, "rb") as f:
        st.download_button(
            label=txt["download_btn"],
            data=f.read(),
            file_name="capsulelearn_podcast.mp3",
            mime="audio/mpeg"
        )

    if st.session_state.current_audio_listened:
        st.caption(txt["listen_confirm_done"])
    else:
        if st.button(txt["listen_confirm_btn"]):
            st.session_state.listen_count += 1
            st.session_state.current_audio_listened = True
            award_points(20)
            st.toast(txt["listen_reward_toast"].format(amount=20))
            check_quests(txt)
            st.rerun()
