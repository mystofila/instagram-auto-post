import os
import json
import time
import random
import requests
import textwrap
import base64
import datetime
from PIL import Image, ImageDraw, ImageFont
from google import genai
import cloudinary
import cloudinary.uploader
 
# ── Config ─────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
IG_TOKEN       = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID     = os.environ["INSTAGRAM_USER_ID"]
GH_TOKEN       = os.environ["GH_TOKEN"]
REPO           = "mystofila/instagram-auto-post"
HISTORIQUE_FILE = "historique.json"
 
cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ["CLOUDINARY_API_SECRET"]
)
 
# ── Liste des sujets ────────────────────────────────────────────────────────
SUJETS = [
    "CV : erreurs qui tuent ta candidature",
    "Lettre de motivation : l'intro parfaite",
    "Entretien : les 3 questions pièges",
    "LinkedIn : optimise ton profil en 10 min",
    "Relance après entretien : le bon timing",
    "CV : comment quantifier tes résultats",
    "Lettre de motivation : évite les clichés",
    "Entretien : comment parler de tes défauts",
    "CV : la photo, oui ou non ?",
    "Négocier son salaire : les mots exacts",
    "Entretien : les 5 minutes qui font tout",
    "CV trou : comment l'expliquer",
    "Lettre spontanée : est-ce que ça marche ?",
    "Entretien en anglais : survivre sans stress",
    "ATS : comment passer les robots RH",
    "CV une page ou deux : la vraie règle",
    "Entretien : les questions à poser au recruteur",
    "Reconversion : comment le présenter en entretien",
    "Stage vs alternance : que mettre sur le CV",
    "Entretien vidéo : les erreurs classiques",
    "Mail de candidature : objet qui fait ouvrir",
    "Portfolio : quand et comment l'utiliser",
    "Références professionnelles : qui mettre",
    "Entretien collectif : comment se démarquer",
    "CV : les mots-clés qui attirent les recruteurs",
    "Lettre de motivation : structure en 3 paragraphes",
    "Entretien : gérer le stress en direct",
    "Réseau professionnel : comment l'activer",
    "Job board : lesquels utiliser vraiment",
    "Période d'essai : comment la réussir",
]
 
# ── Historique GitHub ───────────────────────────────────────────────────────
def get_historique_from_github():
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{HISTORIQUE_FILE}",
        headers={"Authorization": f"token {GH_TOKEN}"}
    )
    if r.status_code == 404:
        return [], None
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]
 
def save_historique_to_github(historique, sha):
    content = json.dumps(historique, ensure_ascii=False, indent=2)
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": f"Historique mis à jour - {datetime.date.today()}",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{HISTORIQUE_FILE}",
        headers={"Authorization": f"token {GH_TOKEN}"},
        json=payload
    )
    print(f"Historique sauvegardé sur GitHub : {r.status_code}")
 
# ── Refresh token Instagram ─────────────────────────────────────────────────
def refresh_instagram_token(current_token):
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": current_token}
    )
    data = r.json()
    if "access_token" not in data:
        print(f"Impossible de rafraichir le token : {data}")
        return current_token
    new_token = data["access_token"]
    print("Token rafraichi avec succes !")
    pub_r = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}"}
    )
    pub_data = pub_r.json()
    from nacl import encoding, public
    public_key_obj = public.PublicKey(pub_data["key"].encode(), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(new_token.encode())
    encrypted_b64 = base64.b64encode(encrypted).decode()
    update_r = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/INSTAGRAM_ACCESS_TOKEN",
        headers={"Authorization": f"token {GH_TOKEN}"},
        json={"encrypted_value": encrypted_b64, "key_id": pub_data["key_id"]}
    )
    print(f"Secret GitHub mis a jour : {update_r.status_code}")
    return new_token
 
IG_TOKEN = refresh_instagram_token(IG_TOKEN)
 
# ── Sélection du sujet (file d'attente infinie, sans doublon consécutif) ───
historique, historique_sha = get_historique_from_github()
 
sujets_deja_traites = [h["sujet"] for h in historique]
sujets_neufs = [s for s in SUJETS if s not in sujets_deja_traites]
 
if sujets_neufs:
    # Il reste des sujets jamais traités → on pioche dedans
    sujet_du_jour = random.choice(sujets_neufs)
else:
    # Tous les sujets ont été faits au moins une fois
    # → on reprend le plus ancien (premier de l'historique)
    sujet_du_jour = sujets_deja_traites[0]
    # On le retire de l'historique pour qu'il repasse comme "neuf"
    historique = [h for h in historique if h["sujet"] != sujet_du_jour]
 
print(f"Sujet choisi : {sujet_du_jour}")
 
# ── Génération du contenu avec Gemini ──────────────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY)
today = datetime.date.today().strftime("%Y-%m-%d")
 
prompt = f"""Tu es un expert en recrutement et coach carriere francais.
 
Redige un carrousel Instagram sur ce sujet PRECIS : "{sujet_du_jour}"
 
Reponds UNIQUEMENT en JSON valide sans markdown sans commentaire :
{{
  "accroche": "titre choc max 35 caracteres sans emoji",
  "slides": [
    {{"titre": "point 1 max 5 mots", "contenu": "phrase complete max 20 mots avec point final"}},
    {{"titre": "point 2 max 5 mots", "contenu": "phrase complete max 20 mots avec point final"}},
    {{"titre": "point 3 max 5 mots", "contenu": "phrase complete max 20 mots avec point final"}}
  ],
  "cta": "call to action max 30 caracteres sans emoji",
  "caption": "texte Instagram avec 5 hashtags francais max 200 caracteres sans emoji"
}}"""
 
response = client.models.generate_content(
    model="gemma-3-27b-it",
    contents=prompt
)
 
raw = response.text.strip()
if "```" in raw:
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
data = json.loads(raw.strip())
print(f"Contenu genere : {data}")
 
# ── Sauvegarder le sujet dans l'historique ─────────────────────────────────
historique.append({
    "date": today,
    "sujet": sujet_du_jour
})
save_historique_to_github(historique, historique_sha)
 
# ── Palettes ────────────────────────────────────────────────────────────────
palettes = [
    [(15, 32, 78),  (30, 90, 180)],
    [(78, 15, 60),  (180, 30, 140)],
    [(15, 78, 40),  (30, 180, 90)],
    [(78, 30, 15),  (200, 80, 20)],
    [(20, 60, 78),  (30, 160, 180)],
]
 
# ── Création des slides ─────────────────────────────────────────────────────
def create_slide(text_title, text_body, filename, index=1):
    W, H = 1080, 1080
    c1, c2 = palettes[(index + random.randint(0, 4)) % len(palettes)]
 
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        ratio = y / H
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
 
    overlay = Image.new("RGB", (W, H), c1)
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.polygon([(0, 0), (W//2, 0), (0, H)], fill=120)
    img = Image.composite(overlay, img, mask)
    draw = ImageDraw.Draw(img)
 
    draw.ellipse([800, -100, 1180, 280], outline=(255, 255, 255), width=3)
    draw.ellipse([830, -70, 1150, 250],  outline=(255, 255, 255), width=1)
    draw.ellipse([-100, 800, 280, 1180], outline=(255, 255, 255), width=3)
    draw.rectangle([0, 0, 8, H], fill="white")
 
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 76)
        font_body  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 46)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    except:
        font_title = ImageFont.load_default()
        font_body  = font_title
        font_small = font_title
        font_brand = font_title
 
    num_text = f"{index} / 5"
    bbox = draw.textbbox((0, 0), num_text, font=font_small)
    draw.text((W - (bbox[2] - bbox[0]) - 50, 45), num_text, font=font_small, fill="white")
 
    wrapped_title = textwrap.wrap(text_title, width=20, break_long_words=False, break_on_hyphens=False)
    y_pos = 320 if text_body else 430
    for line in wrapped_title:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) / 2, y_pos), line, font=font_title, fill="white")
        y_pos += 95
 
    draw.rectangle([(W - 140) / 2, y_pos + 10, (W + 140) / 2, y_pos + 18], fill="white")
    y_pos += 55
 
    if text_body:
        wrapped_body = textwrap.wrap(text_body, width=26)[:5]
        y_pos += 20
        for line in wrapped_body:
            bbox = draw.textbbox((0, 0), line, font=font_body)
            w = bbox[2] - bbox[0]
            draw.text(((W - w) / 2, y_pos), line, font=font_body, fill=(200, 220, 255))
            y_pos += 62
 
    draw.rectangle([60, H - 110, W - 60, H - 104], fill="white")
    brand = "@mystofila"
    bbox = draw.textbbox((0, 0), brand, font=font_brand)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, H - 90), brand, font=font_brand, fill="white")
 
    img.save(filename, quality=95)
    print(f"Slide creee : {filename}")
 
# ── Générer les 5 slides ────────────────────────────────────────────────────
slides_files = []
 
create_slide(data["accroche"], "", "slide_1.jpg", 1)
slides_files.append("slide_1.jpg")
 
for i, slide in enumerate(data["slides"][:3]):
    fname = f"slide_{i+2}.jpg"
    create_slide(slide["titre"], slide["contenu"], fname, i + 2)
    slides_files.append(fname)
 
create_slide(data["cta"], "Sauvegarde ce post !", "slide_5.jpg", 5)
slides_files.append("slide_5.jpg")
 
print(f"Slides creees : {slides_files}")
 
# ── Upload Cloudinary ───────────────────────────────────────────────────────
image_urls = []
for fname in slides_files:
    result = cloudinary.uploader.upload(fname)
    url = result["secure_url"]
    image_urls.append(url)
    print(f"Image uploadee : {url}")
 
# ── Publication carrousel Instagram ────────────────────────────────────────
children_ids = []
for url in image_urls:
    r = requests.post(
        f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media",
        data={
            "image_url": url,
            "is_carousel_item": "true",
            "access_token": IG_TOKEN
        }
    )
    children_ids.append(r.json()["id"])
    print(f"Conteneur enfant : {r.json()}")
 
carousel_r = requests.post(
    f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media",
    data={
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": data["caption"],
        "access_token": IG_TOKEN
    }
)
carousel_id = carousel_r.json()["id"]
print(f"Carrousel cree : {carousel_r.json()}")
 
time.sleep(10)
 
publish_r = requests.post(
    f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media_publish",
    data={
        "creation_id": carousel_id,
        "access_token": IG_TOKEN
    }
)
print(f"Publication : {publish_r.json()}")
 
