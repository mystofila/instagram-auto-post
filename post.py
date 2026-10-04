"""
AFDER.RECOVERY — Carrousel Instagram automatique
Groq      : génère le texte (JSON)
Together  : génère l'image de couverture (FLUX.1-schnell)
Slides    : 1080x1080px PNG — Open Sans
"""

import os, re, json, math, time, random, base64, datetime, io
import requests
from PIL import Image, ImageDraw, ImageFont
import cloudinary, cloudinary.uploader
from groq import Groq

# ── Config ─────────────────────────────────────────────────────────────────────
GROQ_API_KEY     = os.environ["GROQ_API_KEY"]
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
IG_TOKEN         = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID       = os.environ["INSTAGRAM_USER_ID"]
GH_TOKEN         = os.environ["GH_TOKEN"]
REPO             = "mystofila/instagram-auto-post"
HISTORIQUE_FILE  = "historique_afder.json"
GROQ_MODEL       = "openai/gpt-oss-120b"
IG_API           = "https://graph.instagram.com/v19.0"

cloudinary.config(
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key    = os.environ["CLOUDINARY_API_KEY"],
    api_secret = os.environ["CLOUDINARY_API_SECRET"],
)

# ── Polices ────────────────────────────────────────────────────────────────────
_OSD = "/usr/share/fonts/truetype/open-sans/"
_FB  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def F(name, size):
    try:
        return ImageFont.truetype(_OSD + name, size)
    except Exception:
        return ImageFont.truetype(_FB, size)

# ── Couleurs ───────────────────────────────────────────────────────────────────
WHITE      = (255, 255, 255)
BG_COVER   = (240, 241, 245)
BG_CONTENT = (243, 244, 247)
DARK       = (15,  15,  15)
TEXT_CLR   = (28,  28,  28)
MID_GREY   = (90,  90,  90)
RULE       = (205, 208, 215)
RED        = (240, 80,  80)
SIZE       = 1080

# ── Sujets ─────────────────────────────────────────────────────────────────────
SUJETS = [
    # Codépendance & relations
    "La co-dépendance, c'est quoi ?",
    "Codépendance : quand aider devient épuisant",
    "Aimer quelqu'un en addiction sans se perdre",
    "Comment poser des limites bienveillantes",
    "Quand l'amour devient contrôle : reconnaître la codépendance",
    # Rechute & rétablissement
    "Rechute : ce n'est pas un échec, c'est une information",
    "Le rétablissement n'est pas une ligne droite",
    "Après une rechute : comment se relever sans se juger",
    "Les petites victoires qui comptent dans le rétablissement",
    "Rétablissement : pourquoi comparer son chemin est dangereux",
    # Émotions & santé mentale
    "La honte en addiction : comment s'en libérer",
    "Colère, tristesse, peur : les émotions cachées de l'addiction",
    "Santé mentale et addiction : le lien qu'on n'explique pas",
    "Comment gérer l'anxiété sans substance",
    "Apprendre à se faire confiance à nouveau",
    # Pair-aidance
    "Pair-aidance : la force de l'expérience vécue",
    "Pair-aidant : ce que ça change d'être compris par quelqu'un qui a vécu",
    "Comment soutenir sans donner de conseils",
    "L'écoute active : l'outil le plus puissant du pair-aidant",
    "Pair-aidance : prendre soin de soi pour prendre soin des autres",
    # Famille & entourage
    "Famille et addiction : briser le silence",
    "Ce que vivent les proches : les émotions qu'on tait",
    "Comment parler de l'addiction à ses enfants",
    "Pardon et réconciliation : est-ce toujours possible ?",
    "L'entourage aussi a besoin de soutien",
    # Identité & reconstruction
    "Le deuil de la personne qu'on était avant",
    "Qui suis-je sans ma dépendance ?",
    "Reconstruire l'estime de soi après l'addiction",
    "Trouver un sens à son histoire de vie",
    "Les forces cachées dans ton parcours de rétablissement",
    # Pratique & quotidien
    "Les signes que tu prends soin de toi malgré tout",
    "Routine et rétablissement : pourquoi la structure aide",
    "Sommeil, alimentation, mouvement : les bases du rétablissement",
    "Comment gérer les triggers au quotidien",
    "Célébrer ses progrès : un acte révolutionnaire",
]

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — HISTORIQUE GITHUB
# ═══════════════════════════════════════════════════════════════════════════════

def get_historique():
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{HISTORIQUE_FILE}",
        headers={"Authorization": f"token {GH_TOKEN}"},
        timeout=30,
    )
    if r.status_code == 404:
        return [], None
    r.raise_for_status()
    data = r.json()
    return json.loads(base64.b64decode(data["content"]).decode()), data["sha"]


def save_historique(hist, sha):
    encoded = base64.b64encode(
        json.dumps(hist, ensure_ascii=False, indent=2).encode()
    ).decode()
    payload = {"message": f"Historique AFDER — {datetime.date.today()}", "content": encoded}
    if sha:
        payload["sha"] = sha
    r = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{HISTORIQUE_FILE}",
        headers={"Authorization": f"token {GH_TOKEN}"},
        json=payload,
        timeout=30,
    )
    print(f"Historique sauvegardé : {r.status_code}")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — GROQ : TEXTE
# ═══════════════════════════════════════════════════════════════════════════════

def _groq_call(client, system, user, max_tok=1000):
    """
    Appel Groq avec retry.
    gpt-oss-120b est un modèle de raisonnement : une partie des tokens part dans
    la « réflexion ». On ajoute donc une marge et on réessaie si la réponse est vide.
    """
    extra = {"reasoning_effort": "low", "include_reasoning": False}

    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.6,
                max_tokens=max_tok + 3000,
                **extra,
            )
            choice  = resp.choices[0]
            content = (choice.message.content or "").strip()
            if not content:
                raise ValueError(f"réponse vide (finish_reason={choice.finish_reason})")
            return content

        except Exception as e:
            msg = str(e).lower()

            # SDK / modèle qui refuse les paramètres de raisonnement → on les retire
            if extra and ("reasoning" in msg or "unexpected keyword" in msg):
                print(f"Paramètres de raisonnement refusés ({e}) → retry sans")
                extra = {}
                continue

            if any(x in msg for x in ["rate_limit", "rate limit", "503", "500", "vide", "timeout"]):
                wait = 10 * (attempt + 1)
                print(f"Groq problème ({e}), retry dans {wait}s… ({attempt+1}/4)")
                time.sleep(wait)
            else:
                raise

    raise Exception("Groq indisponible après plusieurs tentatives")


def generate_text(client, sujet):
    system = (
        "Tu es expert en santé mentale, addiction et pair-aidance. "
        "Tu réponds UNIQUEMENT en JSON valide sur une seule ligne, "
        "sans markdown, sans backticks, sans commentaire. "
        "Tout le texte en FRANÇAIS CORRECT avec accents. "
        "Zéro mot anglais. Orthographe parfaite."
    )
    user = (
        f'Carrousel Instagram @afder.recovery sur : "{sujet}"\n\n'
        'JSON sur UNE SEULE LIGNE :\n'
        '{"accroche":"TITRE FRANÇAIS MAX 5 MOTS MAJUSCULES",'
        '"slides":[{"contenu":"2-3 phrases bienveillantes max 180 chars tutoiement"},'
        '{"contenu":"Suite concrète max 180 chars"}],'
        '"cta":"PHRASE FORTE MAJUSCULES max 25 chars",'
        '"cta_sous":"phrase bienveillante max 75 chars",'
        '"caption":"texte Instagram 5 hashtags français max 180 chars"}'
    )
    return _groq_call(client, system, user, max_tok=1000)


def parse_groq_response(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Réponse Groq vide")

    # Retire les éventuels blocs markdown
    if "```" in text:
        for part in text.split("```")[1:]:
            c = part.strip()
            if c.lower().startswith("json"):
                c = c[4:].strip()
            if c.startswith("{"):
                text = c
                break

    # Extrait le plus grand bloc JSON
    blocks = list(re.finditer(r'\{[\s\S]*\}', text))
    if not blocks:
        raise ValueError(f"Pas de JSON : {text[:200]}")
    text = max((m.group() for m in blocks), key=len)

    # Guillemets typographiques → droits
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        fixed = text.strip()
        open_braces   = max(0, fixed.count("{") - fixed.count("}"))
        open_brackets = max(0, fixed.count("[") - fixed.count("]"))
        fixed += "]" * open_brackets + "}" * open_braces
        try:
            data = json.loads(fixed)
            print("JSON réparé manuellement")
        except json.JSONDecodeError:
            data = {}
            for key in ["accroche", "cta", "cta_sous", "caption"]:
                m = re.search(r'"' + key + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', fixed)
                if m:
                    data[key] = m.group(1)
            slides_raw = re.findall(r'"contenu"\s*:\s*"((?:[^"\\]|\\.)*)"', fixed)
            if slides_raw:
                data["slides"] = [{"contenu": s} for s in slides_raw]
            if not data.get("accroche") or not data.get("slides"):
                raise ValueError(f"JSON invalide : {text[:300]}")
            print("JSON extrait par regex")

    for key in ["accroche", "slides", "cta", "cta_sous", "caption"]:
        if key not in data:
            raise ValueError(f"Clé manquante : '{key}'")
    if not isinstance(data["slides"], list) or len(data["slides"]) < 2:
        raise ValueError("slides doit avoir au moins 2 éléments")
    for s in data["slides"][:2]:
        if not isinstance(s, dict) or not s.get("contenu"):
            raise ValueError("Slide sans 'contenu'")

    # Vérification du titre
    MOTS_ANGLAIS = {"mental", "health", "recovery", "self", "care", "mind", "body",
                    "soul", "help", "support", "heal", "feel", "free", "hope",
                    "strong", "safe", "you", "we"}
    mots = data["accroche"].split()
    if len(mots) > 6:
        print(f"⚠ Titre trop long ({len(mots)} mots) → tronqué")
        data["accroche"] = " ".join(mots[:5])
    mots_en = [m for m in mots if m.lower().strip(".,!?") in MOTS_ANGLAIS]
    if mots_en:
        print(f"⚠ Mots anglais détectés : {mots_en}")

    return data

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — UTILITAIRES DESSIN
# ═══════════════════════════════════════════════════════════════════════════════

def _blob(img, cx, cy, rx, ry, color=(195, 205, 215), alpha=55):
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=(*color, alpha))
    base = img.convert("RGBA")
    base.paste(ov, mask=ov)
    return base.convert("RGB")


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textbbox((0, 0), t, font=font)[2] <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _arrow_btn(draw, cx, cy, r=56):
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=RED)
    draw.line([(cx-15, cy), (cx+13, cy)], fill=WHITE, width=5)
    draw.polygon([(cx+5, cy-10), (cx+21, cy), (cx+5, cy+10)], fill=WHITE)


def _prev_btn(draw, cy):
    draw.ellipse([18, cy-44, 82, cy+44], fill=(222, 223, 228))
    draw.polygon([(58, cy-16), (40, cy), (58, cy+16)], fill=(145, 145, 155))


def _nav_dots(draw, total, active):
    gap = 20
    sx  = (SIZE - (total-1)*gap) // 2
    cy  = SIZE - 30
    for i in range(total):
        x = sx + i*gap
        if i == active:
            draw.ellipse([x-5, cy-5, x+5, cy+5], fill=DARK)
        else:
            draw.ellipse([x-4, cy-4, x+4, cy+4], fill=RULE)


def _sep(draw, y=SIZE-102):
    draw.line([(55, y), (SIZE-192, y)], fill=RULE, width=2)


def _heart_shape(draw, cx, cy, sz, color):
    pts = []
    for i in range(360):
        a  = math.radians(i)
        sc = sz / 100
        pts.append((
            cx + int(sz*(16*math.sin(a)**3)*sc*0.56),
            cy - int(sz*(13*math.cos(a) - 5*math.cos(2*a) - 2*math.cos(3*a) - math.cos(4*a))*sc*0.56),
        ))
    draw.polygon(pts, fill=color)

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — CRÉATION DES SLIDES
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_cover_image(sujet: str) -> Image.Image:
    """Génère l'illustration de couverture via Together.ai FLUX.1-schnell."""
    if not TOGETHER_API_KEY:
        raise ValueError("TOGETHER_API_KEY manquante")

    prompt = (
        f"Minimal modern editorial illustration, theme: {sujet}. "
        "Single abstract human figure, neutral posture, subtle sense of struggle "
        "without dramatization, no facial expression, no smile, no cartoon style. "
        "Soft muted tones, calm neutral background, clean composition with strong "
        "negative space for typography overlay. Professional public health style, "
        "restrained emotional tone, focus on resilience and continuity. "
        "Soft lighting, simple shapes, hybrid flat-to-soft 3D aesthetic, "
        "centered subject, no text, no symbols, no exaggerated emotion. "
        "Instagram carousel cover, prevention and awareness campaign."
    )
    print("Together.ai : appel API (FLUX.1-schnell)…")
    resp = requests.post(
        "https://api.together.xyz/v1/images/generations",
        headers={
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type":  "application/json",
        },
        json={
            "model":           "black-forest-labs/FLUX.1-schnell",
            "prompt":          prompt,
            "width":           1024,
            "height":          1024,
            "steps":           4,
            "n":               1,
            "response_format": "b64_json",
        },
        timeout=90,
    )
    print(f"Together.ai : status {resp.status_code}")
    if resp.status_code != 200:
        print(f"Together.ai erreur : {resp.text[:300]}")
        resp.raise_for_status()
    b64 = resp.json()["data"][0]["b64_json"]
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    print(f"Together.ai : image reçue {img.size}")
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def make_cover(titre: str, sujet: str, total: int) -> str:
    """Cover : image IA plein fond + dégradé sombre en haut + titre blanc."""
    try:
        img = fetch_cover_image(sujet)
        dark_text_bg = True
    except Exception as e:
        print(f"Together.ai indisponible ({e}) → fond uni")
        img = Image.new("RGB", (SIZE, SIZE), BG_COVER)
        dark_text_bg = False

    # Dégradé sombre du haut vers le transparent (seulement si image IA)
    if dark_text_bg:
        overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for i in range(600):
            alpha = int((1 - i/600) ** 1.4 * 210)
            od.line([(0, i), (SIZE, i)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    d = ImageDraw.Draw(img)
    text_color = WHITE if dark_text_bg else DARK

    margin = 55
    max_w  = SIZE - margin * 2
    f, lines = None, []
    for font_size in [108, 92, 78, 66, 54]:
        f     = F("OpenSans-ExtraBold.ttf", font_size)
        lines = _wrap(d, titre.upper(), f, max_w)
        if len(lines) * int(font_size * 1.1) <= 420:
            break

    y = 70
    for line in lines:
        if dark_text_bg:
            d.text((margin+3, y+3), line, font=f, fill=(0, 0, 0))
        d.text((margin, y), line, font=f, fill=text_color)
        y += int(f.size * 1.1)

    _sep(d)
    _arrow_btn(d, SIZE-100, SIZE-100)
    _nav_dots(d, total, 0)
    path = "/tmp/afder_slide_1.png"
    img.save(path, format="PNG")
    return path


def make_content(texte: str, slide_idx: int, total: int) -> str:
    img = Image.new("RGB", (SIZE, SIZE), BG_CONTENT)
    img = _blob(img, SIZE-40, SIZE//2+200, 280, 320, (188, 200, 215), alpha=40)

    d      = ImageDraw.Draw(img)
    f_reg  = F("OpenSans-Regular.ttf", 66)
    f_bold = F("OpenSans-Bold.ttf",    66)
    margin = 72
    max_w  = SIZE - margin*2
    lh     = int(f_reg.size * 1.50)
    sp     = d.textbbox((0, 0), " ", font=f_reg)[2]

    tokens = re.split(r'(\*\*[^*]+\*\*)', texte)
    wf = []
    for tok in tokens:
        if tok.startswith("**") and tok.endswith("**"):
            for w in tok[2:-2].split():
                wf.append((w, f_bold))
        else:
            for w in tok.split():
                wf.append((w, f_reg))

    lines_wf, cur_l, cur_w = [], [], 0
    for word, font in wf:
        ww   = d.textbbox((0, 0), word, font=font)[2]
        need = ww + (sp if cur_l else 0)
        if cur_w + need <= max_w:
            cur_l.append((word, font))
            cur_w += need
        else:
            if cur_l:
                lines_wf.append(cur_l)
            cur_l, cur_w = [(word, font)], ww
    if cur_l:
        lines_wf.append(cur_l)

    total_h = len(lines_wf) * lh
    y = 90 + (SIZE - 148 - 90 - total_h) // 2
    for wfline in lines_wf:
        lx = margin
        for word, font in wfline:
            d.text((lx, y), word, font=font, fill=TEXT_CLR)
            lx += d.textbbox((0, 0), word, font=font)[2] + sp
        y += lh

    _sep(d)
    _arrow_btn(d, SIZE-100, SIZE-100)
    _prev_btn(d, SIZE//2)
    _nav_dots(d, total, slide_idx-1)
    path = f"/tmp/afder_slide_{slide_idx}.png"
    img.save(path, format="PNG")
    return path


def make_cta(cta_titre: str, cta_sous: str, total: int) -> str:
    img = Image.new("RGB", (SIZE, SIZE), BG_CONTENT)
    img = _blob(img, SIZE//2, SIZE-60, 440, 220, (188, 200, 215), alpha=62)
    img = _blob(img, 45, 175, 155, 155, (188, 200, 215), alpha=40)

    d   = ImageDraw.Draw(img)
    hcy = 138
    d.ellipse([SIZE//2-60, hcy-60, SIZE//2+60, hcy+60], fill=RED)
    _heart_shape(d, SIZE//2, hcy, 44, WHITE)
    d.line([(62, hcy-76), (SIZE//2-88, hcy-76)], fill=RULE, width=2)
    d.line([(SIZE//2+88, hcy-76), (SIZE-62, hcy-76)], fill=RULE, width=2)

    f_cta = F("OpenSans-ExtraBold.ttf", 106)
    lines = _wrap(d, cta_titre, f_cta, SIZE-130)
    if len(lines) > 2:
        f_cta = F("OpenSans-ExtraBold.ttf", 88)
        lines = _wrap(d, cta_titre, f_cta, SIZE-130)
    y = 255
    for line in lines:
        bb = d.textbbox((0, 0), line, font=f_cta)
        d.text(((SIZE-(bb[2]-bb[0]))//2, y), line, font=f_cta, fill=DARK)
        y += int(f_cta.size * 1.08)

    y += 34
    f_sub = F("OpenSans-Regular.ttf", 50)
    for line in _wrap(d, cta_sous, f_sub, SIZE-175):
        bb = d.textbbox((0, 0), line, font=f_sub)
        d.text(((SIZE-(bb[2]-bb[0]))//2, y), line, font=f_sub, fill=MID_GREY)
        y += int(f_sub.size * 1.48)

    f_h    = F("OpenSans-Semibold.ttf", 46)
    handle = "@AFDER.RECOVERY"
    bb     = d.textbbox((0, 0), handle, font=f_h)
    d.text(((SIZE-(bb[2]-bb[0]))//2, SIZE-130), handle, font=f_h, fill=DARK)
    _sep(d, SIZE-172)
    _prev_btn(d, SIZE//2)
    _nav_dots(d, total, total-1)
    path = f"/tmp/afder_slide_{total}.png"
    img.save(path, format="PNG")
    return path

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — PUBLICATION INSTAGRAM
# ═══════════════════════════════════════════════════════════════════════════════

def _ig_post(endpoint, data):
    data = {**data, "access_token": IG_TOKEN}
    r = requests.post(f"{IG_API}/{endpoint}", data=data, timeout=60)
    return r.json()


def ig_child(url):
    resp = _ig_post(f"{IG_USER_ID}/media", {"image_url": url, "is_carousel_item": "true"})
    if "id" not in resp:
        raise Exception(f"Child failed: {resp}")
    return resp["id"]


def ig_carousel(ids, caption):
    resp = _ig_post(f"{IG_USER_ID}/media", {
        "media_type": "CAROUSEL",
        "children":   ",".join(ids),
        "caption":    caption,
    })
    if "id" not in resp:
        raise Exception(f"Carousel failed: {resp}")
    return resp["id"]


def ig_wait_ready(container_id, max_wait=120):
    """Attend que le conteneur soit FINISHED avant de publier."""
    waited = 0
    while waited < max_wait:
        r = requests.get(
            f"{IG_API}/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN},
            timeout=30,
        ).json()
        status = r.get("status_code")
        print(f"Statut conteneur : {status}")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise Exception(f"Conteneur en échec : {r}")
        time.sleep(5)
        waited += 5
    raise Exception("Timeout : conteneur pas prêt")


def ig_publish(cid):
    resp = _ig_post(f"{IG_USER_ID}/media_publish", {"creation_id": cid})
    if "id" not in resp:
        raise Exception(f"Publish failed: {resp}")
    return resp

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # Token Facebook longue durée → utilisé tel quel (pas de refresh automatique)
    print("Token utilisé tel quel (token longue durée)")

    # Historique & choix du sujet
    hist, hist_sha = get_historique()
    today    = datetime.date.today().strftime("%Y-%m-%d")
    deja_vus = [h.get("sujet", "") for h in hist]
    neufs    = [s for s in SUJETS if s not in deja_vus]
    sujet    = random.choice(neufs) if neufs else random.choice(SUJETS)
    print(f"Sujet : {sujet}")

    # Texte via Groq
    client = Groq(api_key=GROQ_API_KEY)
    print("Génération Groq…")
    raw  = generate_text(client, sujet)
    data = parse_groq_response(raw)
    print(f"Titre : {data['accroche']}")

    # Slides
    total  = 4
    slides = [
        make_cover(data["accroche"], sujet, total),
        make_content(data["slides"][0]["contenu"], 2, total),
        make_content(data["slides"][1]["contenu"], 3, total),
        make_cta(data["cta"], data["cta_sous"], total),
    ]
    print(f"Slides : {slides}")

    # Upload Cloudinary
    urls = []
    for path in slides:
        res = cloudinary.uploader.upload(
            path,
            folder="afder_carousel",
            format="png",
            resource_type="image",
            access_mode="public",
        )
        urls.append(res["secure_url"])
        print(f"Upload ✓  {res['secure_url']}")

    # Instagram
    child_ids = []
    for u in urls:
        print(f"Container : {u}")
        child_ids.append(ig_child(u))
        time.sleep(3)

    carousel_id = ig_carousel(child_ids, data["caption"])
    print(f"Carrousel : {carousel_id}")
    ig_wait_ready(carousel_id)
    pub = ig_publish(carousel_id)
    print(f"Publié ✓  {pub}")

    # Historique sauvegardé SEULEMENT après publication réussie
    hist.append({"date": today, "sujet": sujet})
    save_historique(hist, hist_sha)


if __name__ == "__main__":
    main()
