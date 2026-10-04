import os, re, asyncio, json, ssl
from uuid import uuid4
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file
from dotenv import load_dotenv
import edge_tts
import edge_tts.voices
import edge_tts.communicate

# Add the OS trust store to the SDK's certifi contexts (including managed proxy CAs).
# TLS verification remains enabled.
system_ca = ssl.get_default_verify_paths().cafile
if system_ca:
    edge_tts.voices._SSL_CTX.load_verify_locations(system_ca)
    edge_tts.communicate._SSL_CTX.load_verify_locations(system_ca)

try:
    from langdetect import detect
except Exception:
    detect = None

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
except Exception:
    ElevenLabs = None

CODE_DIR = Path(__file__).resolve().parent
load_dotenv(CODE_DIR / ".env")
BASE_DIR = Path(globals().get("TENANT_BASE_DIR", os.getenv("STUDIO_DATA_ROOT") or CODE_DIR)).resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = BASE_DIR / "v7_voice_output"
OUTPUT_DIR.mkdir(exist_ok=True)
load_dotenv(CODE_DIR / ".env")

app = Flask(__name__, root_path=str(CODE_DIR), static_folder=str(CODE_DIR / "static"))
app.config["CODE_DIR"] = str(CODE_DIR)
app.config["IS_TENANT"] = bool(globals().get("IS_TENANT", False))
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
eleven_client = globals().get("SHARED_ELEVENCLIENT") if globals().get("IS_TENANT") else (ElevenLabs(api_key=ELEVENLABS_API_KEY) if (ELEVENLABS_API_KEY and ElevenLabs) else None)

ELEVENLABS_VOICE_MAP = {}
try:
    EDGE_VOICE_CATALOG = json.loads((CODE_DIR / "edge_voice_catalog.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    EDGE_VOICE_CATALOG = []

def load_elevenlabs_voices():
    """Load every voice visible to the connected ElevenLabs account."""
    global ELEVENLABS_VOICE_MAP
    ELEVENLABS_VOICE_MAP = {}

    if eleven_client is None:
        print("ELEVENLABS: API key/client not available")
        return ELEVENLABS_VOICE_MAP

    try:
        page_token = None
        while True:
            result = eleven_client.voices.search(page_size=100, next_page_token=page_token)
            for voice in getattr(result, "voices", []):
                name = getattr(voice, "name", "Voice")
                voice_id = getattr(voice, "voice_id", None)
                if voice_id:
                    label = f"ElevenLabs - {name}"
                    if label in ELEVENLABS_VOICE_MAP:
                        label += f" ({voice_id})"
                    ELEVENLABS_VOICE_MAP[label] = voice_id
            page_token = getattr(result, "next_page_token", None)
            if not getattr(result, "has_more", False) or not page_token:
                break

        print(f"ELEVENLABS: connected - loaded {len(ELEVENLABS_VOICE_MAP)} voices")
    except Exception as e:
        app.logger.warning("Cannot load ElevenLabs voices; check API credentials and connectivity")

    return ELEVENLABS_VOICE_MAP

if globals().get("IS_TENANT"):
    ELEVENLABS_VOICE_MAP = dict(globals().get("SHARED_ELEVENVOICES", {}))
else:
    load_elevenlabs_voices()

LANGUAGE_NAME_MAP = {
    "English (United States)": "en",
    "English (United Kingdom)": "en",
    "English (Canada)": "en",
    "Français (France)": "fr",
    "Français (Canada)": "fr",
    "Chinese (China)": "zh-cn",
    "Chinese (Taiwan)": "zh-tw",
    "Cantonese (Hong Kong)": "zh-cn",
    "Japanese (Japan)": "ja",
    "Korean (South Korea)": "ko",
    "Español (Spain)": "es",
    "Español (Mexico)": "es",
    "Deutsch (Germany)": "de",
    "Italiano (Italy)": "it",
    "Português (Brazil)": "pt",
    "Português (Portugal)": "pt",
    "Hindi (India)": "hi",
    "Tiếng Việt (Vietnam)": "vi",
    "Thai (Thailand)": "th",
    "Indonesian (Indonesia)": "id",
}

EDGE_AUTO_VOICES = {
    "vi": "vi-VN-HoaiMyNeural",
    "en": "en-US-AriaNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "zh-cn": "zh-CN-XiaoxiaoNeural",
    "zh-tw": "zh-TW-HsiaoChenNeural",
    "hi": "hi-IN-SwaraNeural",
    "th": "th-TH-PremwadeeNeural",
    "id": "id-ID-GadisNeural",
}

EDGE_REGIONAL_VOICES = {
    "English (United Kingdom)": "en-GB-SoniaNeural",
    "English (Canada)": "en-CA-ClaraNeural",
    "Français (Canada)": "fr-CA-SylvieNeural",
    "Chinese (Taiwan)": "zh-TW-HsiaoChenNeural",
    "Cantonese (Hong Kong)": "zh-HK-HiuMaanNeural",
    "Español (Mexico)": "es-MX-DaliaNeural",
    "Português (Portugal)": "pt-PT-RaquelNeural",
}

def resolve_language(text, selected_language):
    if selected_language and selected_language != "Tự động nhận diện":
        return LANGUAGE_NAME_MAP.get(selected_language, "en")
    if detect:
        try:
            lang = detect(text)
            if lang.startswith("zh"):
                return "zh-cn"
            return lang
        except Exception:
            pass
    return "en"

def resolve_auto_style(text, emotion):
    if emotion and emotion != "Tự động theo lời thoại":
        return {
            "Tự nhiên": "nu_tu_nhien",
            "Vui vẻ": "nam_nang_luong",
            "Cảm xúc": "nu_am",
            "Nghiêm túc": "nam_tram",
            "Năng lượng": "nam_nang_luong",
            "Nhẹ nhàng": "nu_am",
        }.get(emotion, "nu_tu_nhien")

    t = text.lower()
    serious = sum(k in t for k in ["tài chính","nghỉ hưu","kế hoạch","chi phí","rủi ro","đầu tư","quan trọng","phân tích","kinh tế"])
    energetic = sum(k in t for k in ["tuyệt vời","bắt đầu","khám phá","cơ hội","nhanh","ngay hôm nay","đừng bỏ lỡ"])
    warm = sum(k in t for k in ["gia đình","yêu thương","cảm ơn","chia sẻ","cuộc sống","tình yêu","kỷ niệm"])
    calm = sum(k in t for k in ["thư giãn","bình yên","nhẹ nhàng","thiền","ngủ ngon","chữa lành"])

    scores = {
        "nam_tram": serious,
        "nam_nang_luong": energetic,
        "nu_am": warm + calm,
        "nu_tu_nhien": 0,
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "nu_tu_nhien"

AUTO_VI_STYLE = {
    "nu_tu_nhien": ("vi-VN-HoaiMyNeural", "Nữ tự nhiên"),
    "nu_am": ("vi-VN-HoaiMyNeural", "Nữ ấm áp"),
    "nam_tram": ("vi-VN-NamMinhNeural", "Nam trầm"),
    "nam_nang_luong": ("vi-VN-NamMinhNeural", "Nam năng lượng"),
}

VOICE_PROFILES = {
    "Việt Nam - Nữ tự nhiên": "vi-VN-HoaiMyNeural",
    "Việt Nam - Nữ ấm áp": "vi-VN-HoaiMyNeural",
    "Việt Nam - Nam tự nhiên": "vi-VN-NamMinhNeural",
    "Việt Nam - Nam trầm": "vi-VN-NamMinhNeural",
    "Việt Nam - Nam năng lượng": "vi-VN-NamMinhNeural",
}

def split_script(text, max_chars=500):
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    chunks, current = [], ""
    for word in text.split():
        while len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(word[:max_chars])
            word = word[max_chars:]
        if not word:
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks

def analyze_voice_style(text):
    t = text.lower()
    serious = sum(k in t for k in ["tài chính","nghỉ hưu","kế hoạch","chi phí","rủi ro","đầu tư","lưu ý","quan trọng"])
    energetic = sum(k in t for k in ["tuyệt vời","bắt đầu","khám phá","cơ hội","nhanh","ngay hôm nay"])
    warm = sum(k in t for k in ["gia đình","yêu thương","cảm ơn","chia sẻ","cuộc sống"])
    if serious >= max(energetic, warm) and serious > 0: return "vi-VN-NamMinhNeural", "Nam trầm"
    if energetic > max(serious, warm): return "vi-VN-NamMinhNeural", "Nam năng lượng"
    if warm > serious: return "vi-VN-HoaiMyNeural", "Nữ ấm áp"
    return "vi-VN-HoaiMyNeural", "Nữ tự nhiên"

EMOTION_SETTINGS = {
    "Tự nhiên": (0, 0), "Vui vẻ": (8, 2), "Cảm xúc": (-5, -2),
    "Nghiêm túc": (-5, -2), "Năng lượng": (8, 0), "Nhẹ nhàng": (-7, -1),
}
PROFILE_SETTINGS = {
    "Việt Nam - Nữ ấm áp": (-8, -3),
    "Việt Nam - Nam trầm": (-10, -8),
    "Việt Nam - Nam năng lượng": (12, 2),
}

async def edge_generate(text, voice, output_file, emotion="", profile=""):
    rate, pitch = PROFILE_SETTINGS.get(profile, (0, 0))
    extra_rate, extra_pitch = EMOTION_SETTINGS.get(emotion, (0, 0))
    rate = max(-15, min(15, rate + extra_rate))
    pitch = max(-8, min(5, pitch + extra_pitch))
    await edge_tts.Communicate(text=text, voice=voice, proxy=os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY"), rate=f"{rate:+d}%", pitch=f"{pitch:+d}Hz").save(str(output_file))

def eleven_style_settings(emotion):
    stability, speed = {
        "Tự nhiên": (.5, 1.0), "Vui vẻ": (.35, 1.08), "Cảm xúc": (.3, .95),
        "Nghiêm túc": (.7, .95), "Năng lượng": (.35, 1.08), "Nhẹ nhàng": (.65, .93),
    }.get(emotion, (.5, 1.0))
    return VoiceSettings(stability=stability, similarity_boost=.75, speed=speed)

def make_voice(text, selected, output_file, selected_language="Tự động nhận diện", emotion="Tự động theo lời thoại"):
    language = resolve_language(text, selected_language)

    if selected.startswith("Gemini - "):
        return ai_service.gemini_speech(text, selected.removeprefix("Gemini - "), output_file, emotion)
    if selected.startswith("OpenAI - "):
        return ai_service.openai_speech(text, selected.removeprefix("OpenAI - "), output_file, emotion)

    # V4 behaviour: explicit ElevenLabs voice wins.
    if selected in ELEVENLABS_VOICE_MAP:
        if eleven_client is None:
            raise RuntimeError("ElevenLabs chưa được kết nối.")
        voice_id = ELEVENLABS_VOICE_MAP[selected]
        audio = eleven_client.text_to_speech.convert(
            voice_id=voice_id,
            model_id="eleven_flash_v2_5",
            text=text,
            voice_settings=eleven_style_settings(emotion),
            output_format="mp3_44100_128"
        )
        with open(output_file, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        return voice_id, selected.replace("ElevenLabs - ", "")

    if selected.startswith("ElevenLabs - "):
        raise ValueError("Giọng ElevenLabs không còn khả dụng. Hãy tải lại danh sách giọng.")
    if selected in VOICE_PROFILES:
        voice = VOICE_PROFILES[selected]
        asyncio.run(edge_generate(text, voice, output_file, emotion, selected))
        return voice, selected

    edge_name = selected.removeprefix("Edge - ")
    if selected.startswith("Edge - ") and any(v["ShortName"] == edge_name for v in EDGE_VOICE_CATALOG):
        asyncio.run(edge_generate(text, edge_name, output_file, emotion))
        return edge_name, edge_name

    if selected != "Tự động":
        raise ValueError("Giọng đọc không hợp lệ.")

    # Auto Vietnamese: Edge TTS + style analysis, like V4.
    if language == "vi":
        style = resolve_auto_style(text, emotion)
        voice, label = AUTO_VI_STYLE[style]
        asyncio.run(edge_generate(text, voice, output_file, emotion, "Việt Nam - " + label))
        return voice, label

    # Auto non-Vietnamese: use ElevenLabs when available.
    if eleven_client is not None and ELEVENLABS_VOICE_MAP:
        preferred_id = os.getenv("ELEVENLABS_AUTO_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        auto_label, auto_voice_id = next(
            ((label, value) for label, value in ELEVENLABS_VOICE_MAP.items() if value == preferred_id),
            next(iter(ELEVENLABS_VOICE_MAP.items())),
        )
        try:
            audio = eleven_client.text_to_speech.convert(
                voice_id=auto_voice_id,
                model_id="eleven_multilingual_v2",
                text=text,
                voice_settings=eleven_style_settings(emotion),
            output_format="mp3_44100_128"
            )
            with open(output_file, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
            return auto_voice_id, f"Tự động • {auto_label.replace('ElevenLabs - ', '')}"
        except Exception:
            app.logger.warning("Automatic ElevenLabs synthesis failed; using Edge TTS")

    # Edge fallback by language.
    edge_voice = EDGE_REGIONAL_VOICES.get(selected_language, EDGE_AUTO_VOICES.get(language, "en-US-AriaNeural"))
    asyncio.run(edge_generate(text, edge_voice, output_file, emotion))
    return edge_voice, "Edge TTS fallback"

@app.errorhandler(ValueError)
def invalid_voice(error):
    return jsonify({"ok": False, "error": str(error)}), 400

@app.errorhandler(500)
def provider_failure(error):
    return jsonify({"ok": False, "error": "Không tạo được âm thanh. Kiểm tra kết nối và cấu hình nhà cung cấp."}), 500

@app.errorhandler(400)
def invalid_request(error):
    return jsonify({"ok": False, "error": "Yêu cầu JSON không hợp lệ."}), 400

@app.errorhandler(415)
def invalid_content_type(error):
    return jsonify({"ok": False, "error": "Cần gửi Content-Type: application/json."}), 415

@app.get("/healthz")
def healthz():
    return jsonify(ok=True, status="ready")

@app.get("/")
def index():
    return send_file(CODE_DIR / "AI_Video_Studio_V7_5_Connected_V4Voice.html")

@app.get("/audio/<path:name>")
def audio(name):
    return send_from_directory(OUTPUT_DIR, name)


@app.get("/api/status")
def api_status():
    return jsonify({
        "ok": True,
        "elevenlabs_configured": eleven_client is not None,
        "elevenlabs_connected": bool(ELEVENLABS_VOICE_MAP),
        "elevenlabs_voice_count": len(ELEVENLABS_VOICE_MAP),
    })

@app.post("/api/edge-voices/refresh")
def refresh_edge_voices():
    global EDGE_VOICE_CATALOG
    try:
        EDGE_VOICE_CATALOG = asyncio.run(asyncio.wait_for(edge_tts.list_voices(proxy=os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")), 25))
        (BASE_DIR / "edge_voice_catalog.json").write_text(json.dumps(EDGE_VOICE_CATALOG, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return jsonify({"ok": False, "error": "Không tải được danh mục Edge TTS. Kiểm tra kết nối mạng."}), 502
    return api_voices()

@app.post("/api/voices/refresh")
def refresh_voices():
    load_elevenlabs_voices()
    return api_voices()

@app.get("/api/voices")
def api_voices():
    voices = [{"label": "Tự động", "value": "Tự động", "engine": "auto"}]

    if os.getenv("GEMINI_API_KEY"):
        from ai_providers import GEMINI_TTS_VOICES
        for voice in GEMINI_TTS_VOICES:
            voices.append({"label":"Gemini • " + voice,"value":"Gemini - " + voice,"engine":"gemini_tts"})
    if os.getenv("OPENAI_API_KEY"):
        for voice in ["alloy","ash","ballad","coral","echo","fable","nova","onyx","sage","shimmer","verse","marin","cedar"]:
            voices.append({"label":"OpenAI • " + voice,"value":"OpenAI - " + voice,"engine":"openai"})
    for label in VOICE_PROFILES:
        voices.append({"label": label, "value": label, "engine": "edge"})

    for item in EDGE_VOICE_CATALOG:
        voices.append({"label": f"{item['ShortName']} • {item.get('Gender', '')}",
                       "value": "Edge - " + item["ShortName"], "engine": "edge_catalog",
                       "locale": item.get("Locale", "")})
    for label in sorted(ELEVENLABS_VOICE_MAP):
        voices.append({"label": label, "value": label, "engine": "elevenlabs"})

    return jsonify({
        "ok": True,
        "elevenlabs_configured": eleven_client is not None,
        "elevenlabs_connected": bool(ELEVENLABS_VOICE_MAP),
        "elevenlabs_voice_count": len(ELEVENLABS_VOICE_MAP),
        "voices": voices,
    })

@app.post("/api/voice")
def create_voice():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Dữ liệu phải là JSON object."}), 400
    text = str(data.get("text", "")).strip()
    selected = str(data.get("voice", "Tự động"))
    selected_language = str(data.get("language", "Tự động nhận diện"))
    emotion = str(data.get("emotion", "Tự động theo lời thoại"))
    if not text:
        return jsonify({"ok": False, "error": "Vui lòng nhập kịch bản."}), 400

    if len(text) > 50000:
        return jsonify({"ok": False, "error": "Kịch bản tối đa 50.000 ký tự."}), 400
    job_id = uuid4().hex
    chunks = split_script(text, 500) or [text]
    parts = []
    for i, chunk in enumerate(chunks, 1):
        filename = f"{job_id}_part_{i:03d}.mp3"
        path = OUTPUT_DIR / filename
        voice_id, label = make_voice(chunk, selected, path, selected_language, emotion)
        parts.append({
            "index": i,
            "text": chunk,
            "file": filename,
            "url": f"/audio/{filename}",
            "voice": voice_id,
            "label": label,
        })
    return jsonify({"ok": True, "count": len(parts), "parts": parts})

@app.post("/api/test-voice")
def test_voice():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Dữ liệu phải là JSON object."}), 400
    text = str(data.get("text") or "Xin chào, đây là bản thử giọng AI Video Studio.").strip()[:300]
    selected = str(data.get("voice", "Tự động"))
    selected_language = str(data.get("language", "Tự động nhận diện"))
    emotion = str(data.get("emotion", "Tự động theo lời thoại"))
    filename = f"{uuid4().hex}_preview.mp3"
    path = OUTPUT_DIR / filename
    voice_id, label = make_voice(text, selected, path, selected_language, emotion)
    return jsonify({"ok": True, "url": f"/audio/{filename}", "voice": voice_id, "label": label})

from studio_pipeline import register_pipeline
register_pipeline(app, BASE_DIR, OUTPUT_DIR)
from studio_ai import register_ai
ai_service = register_ai(app, BASE_DIR, OUTPUT_DIR)

if not globals().get("IS_TENANT", False):
    from studio_accounts import register_accounts
    register_accounts(app, BASE_DIR, Path(__file__), {"SHARED_ELEVENCLIENT": eleven_client, "SHARED_ELEVENVOICES": ELEVENLABS_VOICE_MAP})

if __name__ == "__main__":
    print("AI Work Studio V8.3: http://127.0.0.1:5000")
    print("Dien thoai cung Wi-Fi: http://IP-MAY-TINH:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
