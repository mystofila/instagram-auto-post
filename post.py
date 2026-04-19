import os
import json
import time
import random
import requests
import textwrap
from PIL import Image, ImageDraw, ImageFont
from google import genai
import cloudinary
import cloudinary.uploader

# Config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
IG_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID = os.environ["INSTAGRAM_USER_ID"]

cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ["CLOUDINARY_API_SECRET"]
)

# Générer le contenu avec Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

themes = [
    "les erreurs qui font jeter un CV en 10 secondes",
    "comment réussir un entretien d'embauche",
    "rédiger une lettre de motivation percutante",
    "optimiser son profil LinkedIn pour être recruté",
    "répondre à parlez-moi de vous en entretien",
    "les mots à bannir de son CV",
    "négocier son salaire sans stress",
    "se démarquer sans expérience professionnelle",
    "relancer un recruteur après un entretien",
    "changer de secteur et convaincre les recruteurs",
]
theme = random.choice(themes)

prompt = f"""Tu es un expert en recrutement et coach carrière français.
Génère le contenu pour un carrousel Instagram de 5 slides sur : {theme}

IMPORTANT :
- N'utilise AUCUN emoji et AUCUN caractère spécial
- Texte uniquement en français simple
- Le contenu de chaque slide doit faire maximum 12 mots

Réponds UNIQUEMENT en JSON valide, sans markdown, sans commentaire :
{{
  "accroche": "titre choc max 35 caractères sans emoji",
  "slides": [
    {{"titre": "point 1 max 5 mots", "contenu": "UNE phrase courte et complète, 15 mots maximum, qui se termine toujours par un point"}},
    {{"titre": "point 2 max 5 mots", "contenu": "UNE phrase courte et complète, 15 mots maximum, qui se termine toujours par un point"}},
    {{"titre": "point 3 max 5 mots", "contenu": "UNE phrase courte et complète, 15 mots maximum, qui se termine toujours par un point"}}
  ],
  "cta": "call to action max 30 caractères sans emoji",
  "caption": "texte Instagram avec 5 hashtags français, max 200 caractères sans emoji"
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
print(f"Contenu généré : {data}")

# Palettes sombres et contrastées
palettes = [
    [(15, 32, 78), (30, 90, 180)],
    [(78, 15, 60), (180, 30, 140)],
    [(15, 78, 40), (30, 180, 90)],
    [(78, 30, 15), (200, 80, 20)],
    [(20, 60, 78), (30, 160, 180)],
]

def create_slide(text_title, text_body, filename, index=1):
    W, H = 1080, 1080
    c1, c2 = palettes[index % len(palettes)]

    # Dégradé vertical
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        ratio = y / H
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Overlay diagonal sombre à gauche
    overlay = Image.new("RGB", (W, H), c1)
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.polygon([(0, 0), (W//2, 0), (0, H)], fill=120)
    img = Image.composite(overlay, img, mask)
    draw = ImageDraw.Draw(img)

    # Cercles décoratifs
    draw.ellipse([800, -100, 1180, 280], outline=(255, 255, 255), width=3)
    draw.ellipse([830, -70, 1150, 250], outline=(255, 255, 255), width=1)
    draw.ellipse([-100, 800, 280, 1180], outline=(255, 255, 255), width=3)

    # Bande gauche
    draw.rectangle([0, 0, 8, H], fill="white")

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 76)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    except:
        font_title = ImageFont.load_default()
        font_body = font_title
        font_small = font_title
        font_brand = font_title

    # Numéro slide en haut à droite
    num_text = f"{index} / 5"
    bbox = draw.textbbox((0, 0), num_text, font=font_small)
    draw.text((W - (bbox[2] - bbox[0]) - 50, 45), num_text, font=font_small, fill="white")

    # Titre centré
    wrapped_title = textwrap.wrap(text_title, width=16)
    y_pos = 320 if text_body else 430
    for line in wrapped_title:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) / 2, y_pos), line, font=font_title, fill="white")
        y_pos += 95

    # Ligne déco sous titre
    draw.rectangle([(W - 140) / 2, y_pos + 10, (W + 140) / 2, y_pos + 18], fill="white")
    y_pos += 55

    # Corps — max 3 lignes
    if text_body:
        wrapped_body = textwrap.wrap(text_body, width=26)[:3]
        y_pos += 20
        for line in wrapped_body:
            bbox = draw.textbbox((0, 0), line, font=font_body)
            w = bbox[2] - bbox[0]
            draw.text(((W - w) / 2, y_pos), line, font=font_body, fill=(200, 220, 255))
            y_pos += 60

    # Ligne et branding en bas
    draw.rectangle([60, H - 110, W - 60, H - 104], fill="white")
    brand = "@mystofila"
    bbox = draw.textbbox((0, 0), brand, font=font_brand)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, H - 90), brand, font=font_brand, fill="white")

    img.save(filename, quality=95)
    print(f"Slide créée : {filename}")

# Créer les 5 slides
slides_files = []

create_slide(data["accroche"], "", "slide_1.jpg", 1)
slides_files.append("slide_1.jpg")

for i, slide in enumerate(data["slides"][:3]):
    fname = f"slide_{i+2}.jpg"
    create_slide(slide["titre"], slide["contenu"], fname, i+2)
    slides_files.append(fname)

create_slide(data["cta"], "Sauvegarde ce post !", "slide_5.jpg", 5)
slides_files.append("slide_5.jpg")

print(f"Slides créées : {slides_files}")

# Uploader sur Cloudinary
image_urls = []
for fname in slides_files:
    result = cloudinary.uploader.upload(fname)
    url = result["secure_url"]
    image_urls.append(url)
    print(f"Image uploadée : {url}")

# Publier le carrousel sur Instagram
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
print(f"Carrousel créé : {carousel_r.json()}")

time.sleep(10)

publish_r = requests.post(
    f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media_publish",
    data={
        "creation_id": carousel_id,
        "access_token": IG_TOKEN
    }
)
print(f"Publication : {publish_r.json()}")
