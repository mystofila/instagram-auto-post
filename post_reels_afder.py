"""
AFDER.RECOVERY — Reels Instagram automatique
Scrape JFT (Just For Today - NA) → adapte en français via DeepSeek
Crée une vidéo 9:16 1080x1920 avec animation machine à écrire
Publie sur Instagram via Cloudinary + Graph API
"""

import os, math, tempfile, time, requests, datetime, base64, json
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import VideoClip
import cloudinary, cloudinary.uploader
from openai import OpenAI

# ── Config ─────────────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
IG_TOKEN        = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID      = os.environ["INSTAGRAM_USER_ID"]
GH_TOKEN        = os.environ["GH_TOKEN"]
REPO            = "mystofila/instagram-auto-post"
JFT_URL         = "https://www.jftna.org/jft/"

cloudinary.config(
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key    = os.environ["CLOUDINARY_API_KEY"],
    api_secret = os.environ["CLOUDINARY_API_SECRET"],
)

# ── Vidéo ──────────────────────────────────────────────────────────────────────
WIDTH, HEIGHT  = 1080, 1920
DURATION       = 13
FPS            = 30
FONT_SIZE      = 58
FONT_SIZE_TAG  = 32
SAFE_MARGIN    = 90
LINE_HEIGHT    = 84

# ── Palettes (1 par jour) ──────────────────────────────────────────────────────
PALETTES = [
    {"bg":"#0D0D1A","a1":"#7B2FBE","a2":"#E040FB","text":"#F5F0FF","tag":"#9E7BC4"},
    {"bg":"#0A1628","a1":"#1565C0","a2":"#00E5FF","text":"#E3F2FD","tag":"#6EB3D4"},
    {"bg":"#0F1F0F","a1":"#1B5E20","a2":"#69F0AE","text":"#F1F8E9","tag":"#7AB88A"},
    {"bg":"#1A0A00","a1":"#BF360C","a2":"#FF6D00","text":"#FFF8F1","tag":"#C4906A"},
    {"bg":"#1A0010","a1":"#880E4F","a2":"#F06292","text":"#FCE4EC","tag":"#C47A95"},
    {"bg":"#0A0A0A","a1":"#1a1a1a","a2":"#FFD600","text":"#FFFFFF", "tag":"#B8A800"},
    {"bg":"#001A1A","a1":"#004D4D","a2":"#00E5FF","text":"#FFFFFF", "tag":"#00BCD4"},
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def blend(c1, c2, t):
    return tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3))

def wrap_text(draw, text, font, max_w):
    lines = []
    for hard in text.split("\n"):
        words, cur = hard.split(), ""
        for w in words:
            test = (cur + " " + w).strip()
            bb = draw.textbbox((0,0), test, font=font)
            if (bb[2]-bb[0]) > max_w and cur:
                lines.append(cur); cur = w
            else:
                cur = test
        if cur: lines.append(cur)
    return lines

# ── Scraping JFT ───────────────────────────────────────────────────────────────

def scrape_jft():
    r = requests.get(JFT_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    cells = [td.get_text(separator=" ", strip=True) for td in soup.find_all("td")]
    cells = [c for c in cells if c]
    if len(cells) < 5:
        raise ValueError(f"Structure JFT inattendue : {len(cells)} cellules")
    titre = cells[1]
    jft   = next((c for c in reversed(cells) if c.lower().startswith("just for today")), cells[-1])
    print(f"JFT titre : {titre}")
    print(f"JFT pensée : {jft}")
    return {"titre": titre, "jft": jft}

# ── Génération citation DeepSeek ───────────────────────────────────────────────

def generate_quote():
    jft = scrape_jft()
    client = OpenAI(
        api_key  = DEEPSEEK_API_KEY,
        base_url = "https://api.deepseek.com",
    )
    prompt = (
        "Tu es un créateur de contenu Instagram bienveillant spécialisé en addiction et rétablissement.\n"
        "Voici la pensée du jour en anglais :\n\n"
        f"TITRE : {jft['titre']}\n"
        f"PENSÉE : {jft['jft']}\n\n"
        "Ta mission : traduire et adapter cette pensée en français pour Instagram Reels.\n\n"
        "RÈGLES OBLIGATOIRES :\n"
        "1. Commence TOUJOURS par 'Juste pour aujourd'hui :'\n"
        "2. Maximum 15 mots après les deux points\n"
        "3. Phrase COMPLÈTE avec point final\n"
        "4. Remplace NA / Narcotics Anonymous par 'notre communauté'\n"
        "5. Remplace Dieu / God / Higher Power / spiritual par 'la force du collectif' ou 'l'entraide'\n"
        "6. Style : chaleureux, direct, inspirant\n"
        "7. Si tu veux un saut de ligne utilise | (pipe)\n"
        "8. Réponds UNIQUEMENT avec la phrase, rien d'autre"
    )
    resp = client.chat.completions.create(
        model       = "deepseek-chat",
        messages    = [{"role": "user", "content": prompt}],
        max_tokens  = 256,
        temperature = 0.7,
    )
    raw = resp.choices[0].message.content.strip()
    return raw.replace(" | ", "\n").replace("|", "\n")

# ── Dessin d'une frame ─────────────────────────────────────────────────────────

def draw_frame(quote, palette, progress):
    bg  = hex_rgb(palette["bg"])
    a1  = hex_rgb(palette["a1"])
    a2  = hex_rgb(palette["a2"])
    txt = hex_rgb(palette["text"])
    tag = hex_rgb(palette["tag"])

    pixels = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for y in range(HEIGHT):
        pixels[y, :] = blend(bg, a1, (y/HEIGHT)*0.28)
    img  = Image.fromarray(pixels)
    draw = ImageDraw.Draw(img, "RGBA")
    t    = progress * math.pi * 2

    # Blobs de fond
    bx, by = int(WIDTH*.88), int(HEIGHT*.80)
    draw.ellipse([bx-520,by-520,bx+520,by+520], fill=(*a1, int(55+22*math.sin(t))))
    bx2,by2 = int(WIDTH*.08), int(HEIGHT*.12)
    draw.ellipse([bx2-360,by2-360,bx2+360,by2+360], fill=(*a2, int(35+16*math.sin(t+1.5))))

    # Lignes diagonales
    for i in range(-HEIGHT, WIDTH+HEIGHT, 100):
        draw.line([(i,0),(i+HEIGHT,HEIGHT)], fill=(*a2,15), width=1)

    # Triangle haut-droit
    off = int(math.sin(t*.9)*14)
    draw.polygon([(WIDTH-60+off,100),(WIDTH-220+off,310),(WIDTH-10+off,310)], fill=(*a2,50))

    # Losange bas-gauche
    sq,sx,sy = 78, 100, HEIGHT-270
    draw.polygon([(sx,sy-sq),(sx+sq,sy),(sx,sy+sq),(sx-sq,sy)], fill=(*a1,72))

    # Cercle accent
    draw.ellipse([WIDTH-155,65,WIDTH-55,165], fill=(*a2,40))

    # Arc bas
    ar=160; axc,ayc = WIDTH//2, HEIGHT-160
    draw.arc([axc-ar,ayc-60,axc+ar,ayc+60], start=0, end=180, fill=(*a2,110), width=4)

    # Polices
    try:
        font_q = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", FONT_SIZE)
        font_g = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 130)
        font_t = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", FONT_SIZE_TAG)
    except Exception:
        font_q = font_g = font_t = ImageFont.load_default()

    safe_w      = WIDTH - 2*SAFE_MARGIN
    all_lines   = wrap_text(draw, quote, font_q, safe_w)
    total_h     = len(all_lines) * LINE_HEIGHT
    text_start  = (HEIGHT - total_h) // 2

    # Barre séparateur
    bar_y = text_start - 52
    draw.rectangle([SAFE_MARGIN+10, bar_y, SAFE_MARGIN+130, bar_y+3], fill=(*a2,200))

    # Guillemet ouvrant
    draw.text((SAFE_MARGIN-8, text_start-105), "\u201c", font=font_g, fill=(*a2,85))

    # Animation machine à écrire
    TYPING_END  = 0.72
    typing_prog = min(1.0, progress/TYPING_END)
    vis_chars   = math.ceil(typing_prog * len(quote))
    vis_lines   = wrap_text(draw, quote[:vis_chars].rstrip(), font_q, safe_w)

    for i, line in enumerate(vis_lines):
        y = text_start + i*LINE_HEIGHT
        draw.text((SAFE_MARGIN+3, y+3), line, font=font_q, fill=(*bg,120))
        draw.text((SAFE_MARGIN,   y),   line, font=font_q, fill=(*txt,255))

    # Curseur clignotant
    if typing_prog < 1.0 and vis_lines:
        if (int(progress*DURATION*FPS)//18) % 2 == 0:
            lw    = draw.textbbox((0,0), vis_lines[-1], font=font_q)[2]
            cur_x = SAFE_MARGIN + lw + 6
            cur_y = text_start + (len(vis_lines)-1)*LINE_HEIGHT
            draw.rectangle([cur_x,cur_y+5,cur_x+4,cur_y+FONT_SIZE+5], fill=(*a2,240))

    # Hashtags en fondu
    if progress > TYPING_END:
        alpha    = int(min(200, (progress-TYPING_END)/(1-TYPING_END)*200))
        tag_text = "#rétablissement  #addiction  #sobriété"
        tw       = draw.textbbox((0,0), tag_text, font=font_t)[2]
        draw.text(((WIDTH-tw)//2, HEIGHT-130), tag_text, font=font_t, fill=(*tag,alpha))

    # Handle AFDER
    try:
        font_h = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    except Exception:
        font_h = ImageFont.load_default()
    handle = "@AFDER.RECOVERY"
    hw = draw.textbbox((0,0), handle, font=font_h)[2]
    draw.text(((WIDTH-hw)//2, HEIGHT-80), handle, font=font_h, fill=(*tag,180))

    return np.array(img)

# ── Génération vidéo ───────────────────────────────────────────────────────────

def make_video(quote, output_path):
    palette = PALETTES[datetime.datetime.now().weekday()]
    print(f"Palette : {palette['bg']} → {palette['a2']}")

    def make_frame(t):
        return draw_frame(quote, palette, t/DURATION)

    clip = VideoClip(make_frame, duration=DURATION).set_fps(FPS)
    clip.write_videofile(output_path, fps=FPS, codec="libx264",
                         audio=False, logger=None)
    print(f"Vidéo générée : {output_path}")

# ── Refresh token Instagram ────────────────────────────────────────────────────

def refresh_instagram_token(token):
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
    )
    data = r.json()
    if "access_token" not in data:
        print(f"Token non rafraîchi : {data}")
        return token
    new_token = data["access_token"]
    print("Token Instagram rafraîchi ✓")
    pub = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}"},
    ).json()
    from nacl import encoding, public as nacl_pub
    pk  = nacl_pub.PublicKey(pub["key"].encode(), encoding.Base64Encoder())
    enc = base64.b64encode(nacl_pub.SealedBox(pk).encrypt(new_token.encode())).decode()
    requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/INSTAGRAM_ACCESS_TOKEN",
        headers={"Authorization": f"token {GH_TOKEN}"},
        json={"encrypted_value": enc, "key_id": pub["key_id"]},
    )
    return new_token

# ── Publication Instagram ──────────────────────────────────────────────────────

def publish_reel(video_url, caption):
    # Étape 1 — créer le container (avec retry sur erreurs transitoires)
    resp = None
    for attempt in range(5):
        r = requests.post(
            f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media",
            data={
                "media_type":  "REELS",
                "video_url":   video_url,
                "caption":     caption,
                "access_token": IG_TOKEN,
            },
        )
        resp = r.json()
        if "id" in resp:
            break
        is_transient = resp.get("error", {}).get("is_transient", False)
        print(f"Container creation failed (attempt {attempt+1}/5) : {resp}")
        if is_transient and attempt < 4:
            wait = 20 * (attempt + 1)
            print(f"Erreur transitoire, retry dans {wait}s…")
            time.sleep(wait)
        else:
            raise Exception(f"Container Reel failed: {resp}")
    container_id = resp["id"]
    print(f"Container créé : {container_id}")

    # Étape 2 — attendre que le container soit prêt
    for attempt in range(20):
        time.sleep(10)
        status = requests.get(
            f"https://graph.instagram.com/v19.0/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN},
        ).json()
        print(f"Status container ({attempt+1}/20) : {status.get('status_code')}")
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise Exception(f"Container en erreur : {status}")
    else:
        raise Exception("Container jamais prêt après 200s")

    # Étape 3 — publier
    r2 = requests.post(
        f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": IG_TOKEN},
    )
    result = r2.json()
    print(f"Publié ✓ {result}")
    return result

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global IG_TOKEN
    print("="*52)
    print(f"AFDER Reels — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

    IG_TOKEN = refresh_instagram_token(IG_TOKEN)

    # Citation
    quote = generate_quote()
    print(f"Citation : {quote!r}")

    # Vidéo
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        video_path = tmp.name
    make_video(quote, video_path)

    # Upload Cloudinary
    print("Upload Cloudinary…")
    res = cloudinary.uploader.upload(
        video_path,
        resource_type = "video",
        folder        = "afder_reels",
        access_mode   = "public",
    )
    video_url = res["secure_url"]
    print(f"Cloudinary ✓ {video_url}")

    os.unlink(video_path)

    # Caption
    caption = quote.replace("\n", " ") + "\n\n#rétablissement #addiction #sobriété #pairaidance #afder"

    # Publication
    publish_reel(video_url, caption)
    print("="*52)

if __name__ == "__main__":
    main()
