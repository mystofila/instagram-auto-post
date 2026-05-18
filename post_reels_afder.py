"""
AFDER.RECOVERY — Reels Instagram automatique
Citation générée par Gemini, vidéo 9:16 animation machine à écrire
Publié via Instagram Graph API (même compte que le carrousel)
"""

import os, math, random, tempfile, requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import AudioFileClip
from moviepy.video.VideoClip import VideoClip
import cloudinary, cloudinary.uploader

# ── Config ─────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
IG_TOKEN       = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID     = os.environ["INSTAGRAM_USER_ID"]

cloudinary.config(
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key    = os.environ["CLOUDINARY_API_KEY"],
    api_secret = os.environ["CLOUDINARY_API_SECRET"],
)

WIDTH, HEIGHT = 1080, 1920
DURATION      = 13
FPS           = 30
FONT_SIZE_Q   = 62
SAFE_MARGIN   = 95
LINE_HEIGHT   = 92

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
]

# ── Palettes AFDER (douces, bienveillantes) ────────────────────────────────────
PALETTES = [
    {"bg": "#1A0A2E", "a1": "#6B21A8", "a2": "#E879F9", "txt": "#FAF5FF", "tag": "#C084FC"},
    {"bg": "#0C1A2E", "a1": "#1E40AF", "a2": "#38BDF8", "txt": "#EFF6FF", "tag": "#7DD3FC"},
    {"bg": "#0F1F0F", "a1": "#166534", "a2": "#4ADE80", "txt": "#F0FDF4", "tag": "#86EFAC"},
    {"bg": "#1F0A0A", "a1": "#991B1B", "a2": "#FB923C", "txt": "#FFF7ED", "tag": "#FCA5A5"},
    {"bg": "#1A0F1F", "a1": "#831843", "a2": "#F472B6", "txt": "#FDF2F8", "tag": "#F9A8D4"},
    {"bg": "#111111", "a1": "#1C1C1C", "a2": "#F59E0B", "txt": "#FFFBEB", "tag": "#FCD34D"},
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def h2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def blend(c1, c2, t):
    return tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3))

def wrap_px(draw, text, font, max_w):
    lines = []
    for hard in text.split("\n"):
        words, cur = hard.split(), ""
        for w in words:
            test = (cur+" "+w).strip()
            if draw.textbbox((0,0),test,font=font)[2] > max_w and cur:
                lines.append(cur); cur = w
            else:
                cur = test
        if cur: lines.append(cur)
    return lines

# ── Génération citation Gemini ─────────────────────────────────────────────────

def generate_quote() -> str:
    from google import genai

    prompt = """Tu es créateur de contenu Instagram pour @afder.recovery (pair-aidance, addiction, rétablissement).
Génère UNE citation percutante et bienveillante en français.
Thèmes : courage, fierté du chemin, douceur envers soi, rechute ≠ échec, espoir, liberté, pair-aidance.
Maximum 15 mots, français correct avec accents, direct et chaleureux.
Zéro mot anglais. Pas de guillemets ni hashtags.
Pour un saut de ligne entre deux idées utilise | (pipe).
Réponds UNIQUEMENT avec la citation."""

    client = genai.Client(api_key=GEMINI_API_KEY)
    for model in GEMINI_MODELS:
        try:
            print(f"Gemini : essai {model}…")
            r = client.models.generate_content(model=model, contents=prompt)
            raw = r.text.strip()
            return raw.replace(" | ", "\n").replace("|", "\n")
        except Exception as e:
            print(f"  ✗ {model} : {e}")

    # Fallback citations AFDER
    return random.choice([
        "Chaque jour sans rechute est une victoire.\nSois fier de toi.",
        "Tu n'es pas ton passé.\nTu es ton courage d'aujourd'hui.",
        "La rechute n'est pas la fin.\nC'est un détour vers ta liberté.",
        "Doux avec toi-même, fort dans ta démarche.",
        "Un jour à la fois, tu bâtis une vie nouvelle.",
        "Le rétablissement n'est pas une ligne droite.\nC'est un chemin qui t'appartient.",
        "Tu mérites de guérir.\nPas seulement de survivre.",
    ])

# ── Dessin d'une frame ─────────────────────────────────────────────────────────

def draw_frame(quote: str, palette: dict, progress: float) -> np.ndarray:
    bg  = h2rgb(palette["bg"])
    a1  = h2rgb(palette["a1"])
    a2  = h2rgb(palette["a2"])
    txt = h2rgb(palette["txt"])
    tag = h2rgb(palette["tag"])

    # Fond dégradé
    pixels = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for y in range(HEIGHT):
        pixels[y, :] = blend(bg, a1, (y/HEIGHT)*0.32)
    img  = Image.fromarray(pixels)
    draw = ImageDraw.Draw(img, "RGBA")
    t    = progress * math.pi * 2

    # Formes décoratives
    draw.ellipse([WIDTH*.75-480, HEIGHT*.75-480, WIDTH*.75+480, HEIGHT*.75+480],
                 fill=(*a1, int(55+20*math.sin(t))))
    draw.ellipse([-80, -80, 420, 420],
                 fill=(*a2, int(35+15*math.sin(t+1.5))))
    for i in range(-HEIGHT, WIDTH+HEIGHT, 120):
        draw.line([(i,0),(i+HEIGHT,HEIGHT)], fill=(*a2,12), width=1)

    # Losange décoratif bas droite
    sq, sx, sy = 80, WIDTH-110, HEIGHT-320
    draw.polygon([(sx,sy-sq),(sx+sq,sy),(sx,sy+sq),(sx-sq,sy)], fill=(*a1,80))

    # Arc décoratif bas
    arc_r = 180; axc, ayc = WIDTH//2, HEIGHT-180
    draw.arc([axc-arc_r, ayc-70, axc+arc_r, ayc+70],
             start=0, end=180, fill=(*a2,100), width=5)

    # Ligne accent en haut
    draw.rectangle([SAFE_MARGIN+10, HEIGHT//2-260, SAFE_MARGIN+140, HEIGHT//2-256],
                   fill=(*a2, 220))

    # Polices
    try:
        font_q = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", FONT_SIZE_Q)
        font_g = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 145)
        font_t = ImageFont.truetype("/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf", 36)
        font_h = ImageFont.truetype("/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf", 42)
    except Exception:
        font_q = font_g = font_t = font_h = ImageFont.load_default()

    safe_w    = WIDTH - 2*SAFE_MARGIN
    all_lines = wrap_px(draw, quote, font_q, safe_w)
    total_h   = len(all_lines) * LINE_HEIGHT
    start_y   = (HEIGHT - total_h) // 2

    # Guillemet ouvrant
    draw.text((SAFE_MARGIN-10, start_y-130), "\u201c", font=font_g,
              fill=(*a2, 90))

    # Texte machine à écrire
    TYPING_END  = 0.72
    typing_prog = min(1.0, progress/TYPING_END)
    vis_chars   = math.ceil(typing_prog * len(quote))
    vis_lines   = wrap_px(draw, quote[:vis_chars].rstrip(), font_q, safe_w)

    for i, line in enumerate(vis_lines):
        y = start_y + i*LINE_HEIGHT
        draw.text((SAFE_MARGIN+3, y+3), line, font=font_q, fill=(*bg, 115))
        draw.text((SAFE_MARGIN, y),     line, font=font_q, fill=(*txt, 255))

    # Curseur clignotant
    if typing_prog < 1.0 and vis_lines:
        if (int(progress*DURATION*FPS)//18) % 2 == 0:
            lw    = draw.textbbox((0,0), vis_lines[-1], font=font_q)[2]
            cur_x = SAFE_MARGIN + lw + 7
            cur_y = start_y + (len(vis_lines)-1)*LINE_HEIGHT
            draw.rectangle([cur_x, cur_y+5, cur_x+5, cur_y+FONT_SIZE_Q+5],
                           fill=(*a2, 240))

    # Tags et handle en fondu
    if progress > TYPING_END:
        fade = int(min(210, (progress-TYPING_END)/(1-TYPING_END)*210))
        tag_txt = "#pairaidance  #rétablissement  #sobriété"
        tw = draw.textbbox((0,0), tag_txt, font=font_t)[2]
        draw.text(((WIDTH-tw)//2, HEIGHT-220), tag_txt, font=font_t,
                  fill=(*tag, fade))
        handle = "@AFDER.RECOVERY"
        hw = draw.textbbox((0,0), handle, font=font_h)[2]
        draw.text(((WIDTH-hw)//2, HEIGHT-160), handle, font=font_h,
                  fill=(*txt, fade))

    return np.array(img)

# ── Génération vidéo ───────────────────────────────────────────────────────────

def make_video(quote: str, output_path: str):
    palette = random.choice(PALETTES)
    print(f"Palette : {palette['bg']} → {palette['a2']}")

    def make_frame(t):
        return draw_frame(quote, palette, t/DURATION)

    clip = VideoClip(make_frame, duration=DURATION).set_fps(FPS)

    # Musique optionnelle (dossier assets/music/)
    music_dir = os.path.join(os.path.dirname(__file__), "assets/music")
    mp3s = [f for f in os.listdir(music_dir) if f.endswith(".mp3")] \
           if os.path.isdir(music_dir) else []
    if mp3s:
        audio = AudioFileClip(os.path.join(music_dir, random.choice(mp3s))) \
                    .subclip(0, DURATION).volumex(0.28)
        clip = clip.set_audio(audio)

    clip.write_videofile(output_path, fps=FPS, codec="libx264",
                         audio_codec="aac", logger=None)
    print(f"Vidéo générée : {output_path}")

# ── Publication Instagram Reels ────────────────────────────────────────────────

def publish_reel(video_url: str, caption: str) -> str:
    """Publie un Reel via l'Instagram Graph API."""

    # 1. Créer le container média
    r = requests.post(
        f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media",
        data={
            "media_type":  "REELS",
            "video_url":   video_url,
            "caption":     caption,
            "share_to_feed": "true",
            "access_token": IG_TOKEN,
        },
    )
    resp = r.json()
    print(f"Container Reel : {resp}")
    if "id" not in resp:
        raise Exception(f"Container Reel échoué : {resp}")
    container_id = resp["id"]

    # 2. Attendre que le container soit prêt (polling)
    import time
    for attempt in range(20):
        time.sleep(8)
        status_r = requests.get(
            f"https://graph.instagram.com/v19.0/{container_id}",
            params={"fields": "status_code,status", "access_token": IG_TOKEN},
        )
        status = status_r.json()
        code   = status.get("status_code", "")
        print(f"  Status [{attempt+1}] : {code}")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise Exception(f"Encodage Reel échoué : {status}")

    # 3. Publier
    pub_r = requests.post(
        f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": IG_TOKEN},
    )
    pub = pub_r.json()
    if "id" not in pub:
        raise Exception(f"Publication Reel échouée : {pub}")
    print(f"Reel publié ✓  ID : {pub['id']}")
    return pub["id"]

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("="*52)
    print(f"AFDER Reels — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Générer la citation
    quote = generate_quote()
    print(f"Citation : {quote!r}")

    # 2. Générer la vidéo
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        video_path = tmp.name
    make_video(quote, video_path)

    # 3. Upload sur Cloudinary (vidéo)
    print("Upload Cloudinary…")
    res = cloudinary.uploader.upload(
        video_path,
        resource_type = "video",
        folder        = "afder_reels",
        access_mode   = "public",
    )
    video_url = res["secure_url"]
    print(f"Upload ✓  {video_url}")

    # 4. Caption Instagram
    caption_quote = quote.replace("\n", " ")
    caption = (
        f"{caption_quote}\n\n"
        f"━━━━━━━━━━\n"
        f"@AFDER.RECOVERY · Pair-aidance & Rétablissement\n"
        f"afder.org\n\n"
        f"#pairaidance #rétablissement #addiction #sobriété "
        f"#santémentale #AFDER #courage #guérison"
    )

    # 5. Publier le Reel
    publish_reel(video_url, caption)

    # Nettoyage
    os.unlink(video_path)
    print("="*52)

if __name__ == "__main__":
    main()
