"""
AFDER.RECOVERY — Carrousel Instagram automatique
Infra  : Groq (llama-3.3-70b) · Cloudinary · Instagram Graph API · historique GitHub
Visuel : fond blanc/gris, Open Sans ExtraBold, blobs décoratifs, bouton rouge, illustrations Pillow
"""

import os
import re
import json
import math
import time
import random
import base64
import datetime
import requests
import textwrap

from PIL import Image, ImageDraw, ImageFont
import cloudinary
import cloudinary.uploader
from groq import Groq

# ── Config ─────────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.environ["GROQ_API_KEY"]
IG_TOKEN        = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID      = os.environ["INSTAGRAM_USER_ID"]
GH_TOKEN        = os.environ["GH_TOKEN"]
REPO            = "mystofila/instagram-auto-post"   # ← adapte si besoin
HISTORIQUE_FILE = "historique_afder.json"
GROQ_MODEL      = "llama-3.3-70b-versatile"

cloudinary.config(
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key    = os.environ["CLOUDINARY_API_KEY"],
    api_secret = os.environ["CLOUDINARY_API_SECRET"],
)

# ── Polices ────────────────────────────────────────────────────────────────────
_FONT_DIR    = "/usr/share/fonts/truetype/open-sans/"
_FONT_XBOLD  = _FONT_DIR + "OpenSans-ExtraBold.ttf"
_FONT_BOLD   = _FONT_DIR + "OpenSans-Bold.ttf"
_FONT_SEMI   = _FONT_DIR + "OpenSans-Semibold.ttf"
_FONT_REG    = _FONT_DIR + "OpenSans-Regular.ttf"
# Fallback si la police n'est pas installée
_FALLBACK    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def _F(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(_FALLBACK, size)

# ── Couleurs ───────────────────────────────────────────────────────────────────
WHITE      = (255, 255, 255)
BG_GREY    = (237, 239, 243)   # fond cover
LIGHT_GREY = (243, 244, 247)   # fond slides contenu/cta
DARK       = (18,  18,  18)    # texte principal
MID_GREY   = (95,  95,  95)    # texte secondaire
RULE_CLR   = (200, 205, 212)   # lignes décoratives
RED        = (237, 78,  78)    # bouton / icône rouge
BLUE_L     = (168, 213, 235)
BLUE_M     = (95,  165, 215)
YELLOW     = (255, 200,  72)
PINK_SOFT  = (255, 145, 145)
SAGE       = (130, 190, 140)

SIZE = 1080   # 1080 × 1080 px (carré Instagram)

# ── Sujets AFDER ──────────────────────────────────────────────────────────────
SUJETS = [
    "La co-dépendance, c'est quoi ?",
    "Rechute ≠ échec : ce que disent les neurosciences",
    "La honte en addiction : comment s'en libérer",
    "Pair-aidance : pourquoi l'expérience vécue change tout",
    "Frontières saines : c'est quoi et comment les poser",
    "Santé mentale & addiction : le lien invisible",
    "Famille & addiction : briser le silence",
    "Le rétablissement n'est pas linéaire — et c'est normal",
    "Les signes que tu prends soin de toi malgré tout",
    "Codépendance : quand aider devient épuisant",
    "Vivre avec quelqu'un en addiction : les émotions qu'on n'ose pas nommer",
    "Le deuil de la personne qu'on était avant",
    "Soutenir sans se perdre : trouver l'équilibre",
    "Les rechutes comme partie intégrante du chemin",
    "Pair-aidant : un métier qui part du vécu",
]

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — HISTORIQUE GITHUB
# ═══════════════════════════════════════════════════════════════════════════════

def get_historique():
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{HISTORIQUE_FILE}",
        headers={"Authorization": f"token {GH_TOKEN}"},
    )
    if r.status_code == 404:
        return [], None
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]

def save_historique(historique, sha):
    content = json.dumps(historique, ensure_ascii=False, indent=2)
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": f"Historique AFDER — {datetime.date.today()}",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{HISTORIQUE_FILE}",
        headers={"Authorization": f"token {GH_TOKEN}"},
        json=payload,
    )
    print(f"Historique sauvegardé : {r.status_code}")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — REFRESH TOKEN INSTAGRAM
# ═══════════════════════════════════════════════════════════════════════════════

def refresh_instagram_token(current_token):
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
    )
    data = r.json()
    if "access_token" not in data:
        print(f"Impossible de rafraîchir le token : {data}")
        return current_token
    new_token = data["access_token"]
    print("Token rafraîchi ✓")
    # Mise à jour du secret GitHub
    pub_r = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}"},
    )
    pub = pub_r.json()
    from nacl import encoding, public as nacl_public
    pk  = nacl_public.PublicKey(pub["key"].encode(), encoding.Base64Encoder())
    box = nacl_public.SealedBox(pk)
    enc = base64.b64encode(box.encrypt(new_token.encode())).decode()
    upd = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/INSTAGRAM_ACCESS_TOKEN",
        headers={"Authorization": f"token {GH_TOKEN}"},
        json={"encrypted_value": enc, "key_id": pub["key_id"]},
    )
    print(f"Secret GitHub mis à jour : {upd.status_code}")
    return new_token

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GÉNÉRATION GROQ
# ═══════════════════════════════════════════════════════════════════════════════

def generate_with_retry(client, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es expert en santé mentale, addiction et pair-aidance. "
                            "Tu crées du contenu Instagram bienveillant pour @afder.recovery. "
                            "Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans backticks, "
                            "sans commentaire, sans texte avant ou après. "
                            "Vérifie que chaque tableau est fermé par ] et chaque objet par }."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.75,
                max_tokens=900,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            es = str(e)
            if any(x in es.lower() for x in ["rate_limit", "503", "500"]):
                wait = 15 * (attempt + 1)
                print(f"Groq rate-limit, retry dans {wait}s… ({attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                print(f"Erreur Groq non récupérable : {es}")
                raise
    raise Exception(f"Groq indisponible après {max_retries} tentatives")


def parse_json_robust(raw: str, client=None) -> dict:
    text = raw.strip()
    if "```" in text:
        for part in text.split("```")[1:]:
            c = part.strip().lstrip("json").strip()
            if c.startswith("{"):
                text = c
                break
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"Pas de JSON trouvé : {text[:200]}")
    text = text[s:e+1]
    text = text.replace("\u2019","'").replace("\u2018","'")
    text = text.replace("\u201c",'"').replace("\u201d",'"')

    # Tentative 1 : direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Tentative 2 : ] parasites avant } ou ,
    try:
        return json.loads(re.sub(r'\]\s*(?=[},])', '', text))
    except json.JSONDecodeError:
        pass

    # Tentative 3 : json-repair
    try:
        from json_repair import repair_json
        result = json.loads(repair_json(text))
        print("JSON réparé via json-repair.")
        return result
    except Exception:
        pass

    # Tentative 4 : re-demander à Groq
    if client:
        print("JSON invalide, correction via Groq…")
        fix = (
            "Corrige uniquement les erreurs de syntaxe JSON et renvoie UNIQUEMENT "
            f"le JSON valide, sans markdown, sans backticks :\n\n{text}"
        )
        try:
            raw2 = generate_with_retry(client, fix, max_retries=2)
            s2, e2 = raw2.find("{"), raw2.rfind("}")
            if s2 != -1 and e2 != -1:
                return json.loads(raw2[s2:e2+1])
        except Exception as ex:
            print(f"Correction Groq échouée : {ex}")

    raise ValueError("JSON invalide après toutes les tentatives.")


def validate_content(data: dict):
    for key in ["accroche", "illustration_type", "slides", "cta", "cta_sous", "caption"]:
        if key not in data:
            raise ValueError(f"Clé manquante : '{key}'")
    if not isinstance(data["slides"], list) or len(data["slides"]) < 2:
        raise ValueError("'slides' doit contenir au moins 2 éléments")
    for i, sl in enumerate(data["slides"][:2]):
        if "contenu" not in sl:
            raise ValueError(f"Slide {i+1} sans 'contenu'")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — UTILITAIRES DESSIN
# ═══════════════════════════════════════════════════════════════════════════════

def _wrap(draw, text, font, max_w):
    words  = text.split()
    lines, cur = [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textbbox((0,0), test, font=font)[2] <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def _draw_wrapped(draw, text, font, color, x, y, max_w, gap=1.42):
    lh = int(font.size * gap)
    for line in _wrap(draw, text, font, max_w):
        draw.text((x, y), line, font=font, fill=color)
        y += lh
    return y

def _blob(img, cx, cy, rx, ry, color, alpha=62):
    ov = Image.new("RGBA", img.size, (0,0,0,0))
    ImageDraw.Draw(ov).ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=(*color, alpha))
    base = img.convert("RGBA")
    base.paste(ov, mask=ov)
    return base.convert("RGB")

def _arrow_btn(draw, cx, cy, r=54):
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=RED)
    draw.line([(cx-14, cy), (cx+12, cy)], fill=WHITE, width=5)
    draw.polygon([(cx+4, cy-10), (cx+20, cy), (cx+4, cy+10)], fill=WHITE)

def _nav_dots(draw, total, active, cy):
    gap = 20
    sx  = (SIZE - (total-1)*gap) // 2
    for i in range(total):
        x = sx + i*gap
        if i == active:
            draw.ellipse([x-5,cy-5,x+5,cy+5], fill=DARK)
        else:
            draw.ellipse([x-4,cy-4,x+4,cy+4], fill=RULE_CLR)

def _bottom_rule(draw, y):
    draw.line([(60, y), (SIZE-185, y)], fill=RULE_CLR, width=2)

def _rrect(draw, x0, y0, x1, y1, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle([x0,y0,x1,y1], radius=r, fill=fill, outline=outline, width=width)

# ── Illustrations ──────────────────────────────────────────────────────────────

def _person(draw, cx, cy, color, s=1.0):
    rh = int(40*s)
    draw.rounded_rectangle(
        [cx-int(44*s), cy-int(5*s), cx+int(44*s), cy+int(115*s)],
        radius=int(28*s), fill=color)
    draw.ellipse([cx-rh, cy-int(108*s), cx+rh, cy-int(8*s)], fill=color)

def _heart(draw, cx, cy, size, color):
    sc = size/100
    pts = []
    for i in range(360):
        a = math.radians(i)
        pts.append((
            cx + int(size*(16*math.sin(a)**3)*sc*0.58),
            cy - int(size*(13*math.cos(a)-5*math.cos(2*a)-2*math.cos(3*a)-math.cos(4*a))*sc*0.58),
        ))
    draw.polygon(pts, fill=color)

def _chain_link(draw, cx, cy, w, h, color, horiz=True):
    if horiz:
        draw.ellipse([cx-w,cy-h,cx+w,cy+h], outline=color, width=5)
    else:
        draw.ellipse([cx-h,cy-w,cx+h,cy+w], outline=color, width=5)

def illus_chain(img, cx, cy, s=1.0):
    d = ImageDraw.Draw(img)
    _person(d, int(cx-130*s), cy, YELLOW, s)
    _person(d, int(cx+130*s), cy, PINK_SOFT, s)
    for i in range(5):
        t = (i+0.5)/5
        lx = int((cx-70*s) + 140*s*t)
        _chain_link(d, lx, int(cy-50*s), int(22*s), int(13*s), BLUE_M, horiz=(i%2==0))

def illus_heart(img, cx, cy, s=1.0):
    d = ImageDraw.Draw(img)
    _heart(d, cx, int(cy-20*s), int(115*s), (255,210,210))
    _heart(d, cx, int(cy-20*s), int(80*s),  RED)
    skin = (220,185,155)
    d.rounded_rectangle([cx-int(90*s), int(cy+60*s), cx-int(20*s), int(cy+100*s)], radius=15, fill=skin)
    d.rounded_rectangle([cx+int(20*s), int(cy+60*s), cx+int(90*s), int(cy+100*s)], radius=15, fill=skin)

def illus_brain(img, cx, cy, s=1.0):
    d = ImageDraw.Draw(img)
    r = int(105*s)
    d.ellipse([cx-r, int(cy-r*0.82), cx+r, int(cy+r*0.82)], fill=(255,195,195), outline=(210,100,100), width=3)
    d.line([(cx, int(cy-r*0.78)), (cx, int(cy+r*0.78))], fill=(210,100,100), width=3)
    for i in range(-2, 3):
        ox = abs(i)*8
        d.arc([cx-r+ox, int(cy-r//2+i*18), cx+r-ox, int(cy+r//2+i*18)], start=200, end=340, fill=(210,100,100), width=2)

def illus_family(img, cx, cy, s=1.0):
    d = ImageDraw.Draw(img)
    _person(d, int(cx-120*s), cy, YELLOW, s)
    _person(d, int(cx+120*s), cy, PINK_SOFT, s)
    _person(d, cx, int(cy+28*s), BLUE_L, s*0.72)

def illus_door(img, cx, cy, s=1.0):
    d = ImageDraw.Draw(img)
    w, h = int(120*s), int(195*s)
    _rrect(d, cx-w, cy-h, cx+w, cy+h, r=int(18*s), fill=(220,200,175), outline=(155,125,95), width=5)
    _rrect(d, cx-w+12, cy-h+12, cx+14, cy+h-12, r=10, fill=(185,160,135))
    d.ellipse([cx+int(30*s), cy-8, cx+int(52*s), cy+14], fill=YELLOW)

def illus_tree(img, cx, cy, s=1.0):
    d = ImageDraw.Draw(img)
    _rrect(d, cx-int(18*s), int(cy+25), cx+int(18*s), cy+int(125*s), r=8, fill=(155,115,75))
    d.ellipse([cx-int(82*s), cy-75,  cx+int(82*s), cy+65],  fill=(120,190,100))
    d.ellipse([cx-int(62*s), cy-128, cx+int(62*s), cy+22],  fill=(92,172,82))
    d.ellipse([cx-int(45*s), cy-168, cx+int(45*s), cy-32],  fill=(72,152,62))

def illus_hands(img, cx, cy, s=1.0):
    d = ImageDraw.Draw(img)
    skin = (220,185,155)
    _rrect(d, cx-int(88*s), cy-int(35*s), cx-int(18*s), cy+int(45*s), r=int(22*s), fill=skin)
    _rrect(d, cx+int(18*s), cy-int(35*s), cx+int(88*s), cy+int(45*s), r=int(22*s), fill=skin)
    for i in range(4):
        ox = i*int(18*s)
        d.ellipse([cx-int(88*s)+ox, cy-int(78*s), cx-int(68*s)+ox, cy-int(38*s)], fill=skin)
        d.ellipse([cx+int(20*s)+ox, cy-int(78*s), cx+int(40*s)+ox, cy-int(38*s)], fill=skin)

def illus_mirror(img, cx, cy, s=1.0):
    d = ImageDraw.Draw(img)
    _rrect(d, cx-int(82*s), cy-int(115*s), cx+int(82*s), cy+int(115*s),
           r=42, fill=(228,228,250), outline=(175,175,218), width=5)
    _person(d, cx, int(cy+12*s), (155,155,198), s*0.78)

_ILLUS = {
    "chain":  illus_chain,
    "heart":  illus_heart,
    "brain":  illus_brain,
    "family": illus_family,
    "door":   illus_door,
    "tree":   illus_tree,
    "hands":  illus_hands,
    "mirror": illus_mirror,
}

def draw_illus(img, kind, cx, cy, s=1.0):
    _ILLUS.get(kind, illus_chain)(img, cx, cy, s)

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — CRÉATION DES SLIDES
# ═══════════════════════════════════════════════════════════════════════════════

def make_cover(titre: str, illus_type: str, total: int) -> str:
    """Slide 1 — titre imposant + illustration thématique."""
    img = Image.new("RGB", (SIZE, SIZE), BG_GREY)
    img = _blob(img, SIZE-90,  SIZE//2,    360, 420, (190,205,218))
    img = _blob(img, SIZE+20,  SIZE-30,    195, 195, (182,200,215))
    img = _blob(img, 60,       SIZE-80,    140, 140, (195,210,220))

    # Illustration centrée bas
    draw_illus(img, illus_type, SIZE//2+95, 660, s=1.08)

    d = ImageDraw.Draw(img)
    # Brackets autour de l'illustration
    bx, by, bw, bh = SIZE//2+95, 555, 225, 165
    for (x0,y0),(x1,y1) in [
        ((bx-bw, by-bh),(bx-bw, by-bh+55)), ((bx-bw, by-bh),(bx-bw+55, by-bh)),
        ((bx+bw, by-bh),(bx+bw, by-bh+55)), ((bx+bw, by-bh),(bx+bw-55, by-bh)),
    ]:
        d.line([(x0,y0),(x1,y1)], fill=RULE_CLR, width=3)

    # Titre principal (en haut à gauche, très grand)
    f_titre = _F(_FONT_XBOLD, 112)
    margin  = 62
    lines   = _wrap(d, titre, f_titre, SIZE - margin - 55)
    y = 70
    for line in lines:
        d.text((margin, y), line, font=f_titre, fill=DARK)
        y += int(112 * 1.08)

    _bottom_rule(d, SIZE-98)
    _arrow_btn(d, SIZE-98, SIZE-98)
    _nav_dots(d, total, 0, SIZE-28)

    path = "/tmp/afder_slide_1.jpg"
    img.save(path, quality=95)
    return path


def make_content(texte: str, slide_idx: int, total: int) -> str:
    """Slides 2-3 — corps de texte, fond gris clair."""
    img = Image.new("RGB", (SIZE, SIZE), LIGHT_GREY)
    img = _blob(img, 80,      SIZE//2+120, 295, 345, (192,207,218), alpha=55)
    img = _blob(img, SIZE-80, 120,         180, 180, (195,210,220), alpha=45)

    d  = ImageDraw.Draw(img)
    f  = _F(_FONT_REG, 58)
    margin = 72
    max_w  = SIZE - margin*2
    y = 172
    for para in (texte.split("\n\n") if "\n\n" in texte else [texte]):
        y = _draw_wrapped(d, para, f, DARK, margin, y, max_w, gap=1.48)
        y += 52

    _bottom_rule(d, SIZE-98)
    _arrow_btn(d, SIZE-98, SIZE-98)
    # Flèche gauche
    d.ellipse([18, SIZE//2-42, 80, SIZE//2+42], fill=(225,225,230))
    d.polygon([(56,SIZE//2-15),(38,SIZE//2),(56,SIZE//2+15)], fill=(148,148,158))
    _nav_dots(d, total, slide_idx-1, SIZE-28)

    path = f"/tmp/afder_slide_{slide_idx}.jpg"
    img.save(path, quality=95)
    return path


def make_cta(cta_titre: str, cta_sous: str, total: int) -> str:
    """Slide finale — icône cœur + CTA bold + @AFDER.RECOVERY."""
    img = Image.new("RGB", (SIZE, SIZE), LIGHT_GREY)
    img = _blob(img, SIZE//2, SIZE-75, 420, 210, (192,207,218), alpha=60)
    img = _blob(img, 55,      180,     165, 165, (192,207,218), alpha=42)

    d = ImageDraw.Draw(img)
    # Icône cœur en haut centré
    hcy = 130
    d.ellipse([SIZE//2-58, hcy-58, SIZE//2+58, hcy+58], fill=RED)
    _heart(d, SIZE//2, hcy, 42, WHITE)
    d.line([(62, hcy-74),(SIZE//2-82, hcy-74)], fill=RULE_CLR, width=2)
    d.line([(SIZE//2+82, hcy-74),(SIZE-62, hcy-74)], fill=RULE_CLR, width=2)

    # Titre CTA (centré, très bold)
    f_cta = _F(_FONT_XBOLD, 102)
    lines = _wrap(d, cta_titre, f_cta, SIZE-128)
    y = 240
    for line in lines:
        bb = d.textbbox((0,0), line, font=f_cta)
        d.text(((SIZE-(bb[2]-bb[0]))//2, y), line, font=f_cta, fill=DARK)
        y += int(102*1.1)

    # Sous-titre
    y += 28
    f_sub  = _F(_FONT_REG, 50)
    for line in _wrap(d, cta_sous, f_sub, SIZE-168):
        bb = d.textbbox((0,0), line, font=f_sub)
        d.text(((SIZE-(bb[2]-bb[0]))//2, y), line, font=f_sub, fill=MID_GREY)
        y += int(50*1.45)

    # Handle
    f_handle = _F(_FONT_SEMI, 44)
    handle   = "@AFDER.RECOVERY"
    bb = d.textbbox((0,0), handle, font=f_handle)
    d.text(((SIZE-(bb[2]-bb[0]))//2, SIZE-122), handle, font=f_handle, fill=DARK)

    _bottom_rule(d, SIZE-168)
    d.ellipse([18, SIZE//2-42, 80, SIZE//2+42], fill=(225,225,230))
    d.polygon([(56,SIZE//2-15),(38,SIZE//2),(56,SIZE//2+15)], fill=(148,148,158))
    _nav_dots(d, total, total-1, SIZE-28)

    path = f"/tmp/afder_slide_{total}.jpg"
    img.save(path, quality=95)
    return path

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — PUBLICATION INSTAGRAM
# ═══════════════════════════════════════════════════════════════════════════════

def _ig_child(url, token, user_id):
    r = requests.post(
        f"https://graph.instagram.com/v19.0/{user_id}/media",
        data={"image_url": url, "is_carousel_item": "true", "access_token": token},
    )
    resp = r.json()
    if "id" not in resp:
        raise Exception(f"Conteneur enfant échoué : {resp}")
    return resp["id"]

def _ig_carousel(child_ids, caption, token, user_id):
    r = requests.post(
        f"https://graph.instagram.com/v19.0/{user_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children":    ",".join(child_ids),
            "caption":     caption,
            "access_token": token,
        },
    )
    resp = r.json()
    if "id" not in resp:
        raise Exception(f"Carrousel échoué : {resp}")
    return resp["id"]

def _ig_publish(carousel_id, token, user_id):
    r = requests.post(
        f"https://graph.instagram.com/v19.0/{user_id}/media_publish",
        data={"creation_id": carousel_id, "access_token": token},
    )
    return r.json()

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — MAIN
# ═══════════════════════════════════════════════════════════════════════════════

# 1. Refresh token
IG_TOKEN = refresh_instagram_token(IG_TOKEN)

# 2. Choix du sujet (anti-doublon via historique GitHub)
historique, hist_sha = get_historique()
today = datetime.date.today().strftime("%Y-%m-%d")
deja_vus   = [h.get("sujet","") for h in historique]
sujets_neufs = [s for s in SUJETS if s not in deja_vus]

if sujets_neufs:
    sujet = random.choice(sujets_neufs)
else:
    sujet = deja_vus[0]
    historique = [h for h in historique if h.get("sujet","") != sujet]

print(f"Sujet : {sujet}")

# 3. Génération du contenu via Groq
client = Groq(api_key=GROQ_API_KEY)

prompt = f"""Crée un carrousel Instagram pour @afder.recovery sur ce sujet PRÉCIS : "{sujet}"

Réponds UNIQUEMENT en JSON valide, sans markdown, sans backticks, sans commentaire.
Chaque objet dans slides doit être fermé par }}, le tableau par ].

{{
  "accroche": "TITRE EN MAJUSCULES percutant, max 35 caractères, sans emoji",
  "illustration_type": "UNE valeur parmi : chain, heart, brain, family, door, tree, hands, mirror",
  "slides": [
    {{"contenu": "Paragraphe bienveillant 2-3 phrases, max 220 caractères, ton direct, tutoiement"}},
    {{"contenu": "Suite du propos, 2-3 phrases, max 220 caractères, concret et actionnable"}}
  ],
  "cta": "PHRASE FORTE EN MAJUSCULES, max 30 caractères",
  "cta_sous": "1 phrase bienveillante, max 90 caractères",
  "caption": "Texte Instagram avec 5 hashtags français, max 220 caractères, sans emoji"
}}"""

raw  = generate_with_retry(client, prompt)
print(f"Raw Groq : {repr(raw[:120])}…")

data = parse_json_robust(raw, client=client)
validate_content(data)
print(f"Contenu validé ✓  |  Titre : {data['accroche']}  |  Illus : {data['illustration_type']}")

# 4. Sauvegarde historique
historique.append({"date": today, "sujet": sujet})
save_historique(historique, hist_sha)

# 5. Création des slides (4 slides : cover + 2 contenu + cta)
total  = 4
slides = [
    make_cover(data["accroche"], data["illustration_type"], total),
    make_content(data["slides"][0]["contenu"], 2, total),
    make_content(data["slides"][1]["contenu"], 3, total),
    make_cta(data["cta"], data["cta_sous"], total),
]
print(f"Slides créées : {slides}")

# 6. Upload Cloudinary
urls = []
for path in slides:
    result = cloudinary.uploader.upload(path, folder="afder_carousel")
    urls.append(result["secure_url"])
    print(f"Upload ✓  {result['secure_url']}")

# 7. Publication Instagram
child_ids  = [_ig_child(u, IG_TOKEN, IG_USER_ID) for u in urls]
carousel_id = _ig_carousel(child_ids, data["caption"], IG_TOKEN, IG_USER_ID)
print(f"Carrousel créé : {carousel_id}")

time.sleep(10)

pub = _ig_publish(carousel_id, IG_TOKEN, IG_USER_ID)
print(f"Publication : {pub}")
