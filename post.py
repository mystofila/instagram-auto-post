import os
import json
import requests
import textwrap
from PIL import Image, ImageDraw, ImageFont
from google import genai

# Config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
IG_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID = os.environ["INSTAGRAM_USER_ID"]

# Générer le contenu avec Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

import random
themes = [
    "les erreurs qui font jeter un CV en 10 secondes",
    "comment réussir un entretien d'embauche",
    "rédiger une lettre de motivation percutante",
    "optimiser son profil LinkedIn pour être recruté",
    "répondre à 'parlez-moi de vous' en entretien",
    "les mots à bannir de son CV",
    "négocier son salaire sans stress",
    "se démarquer sans expérience professionnelle",
    "relancer un recruteur après un entretien",
    "changer de secteur et convaincre les recruteurs",
]
theme = random.choice(themes)

prompt = f"""Tu es un expert en recrutement et coach carrière français.
Génère le contenu pour un carrousel Instagram de 5 slides sur : {theme}

Réponds UNIQUEMENT en JSON valide, sans markdown, sans commentaire, exactement ce format :
{{
  "accroche": "titre choc de la slide 1, max 50 caractères, avec 1 emoji",
  "slides": [
    {{"titre": "point 1 court", "contenu": "explication en 1-2 phrases max, concrète"}},
    {{"titre": "point 2 court", "contenu": "explication en 1-2 phrases max, concrète"}},
    {{"titre": "point 3 court", "contenu": "explication en 1-2 phrases max, concrète"}}
  ],
  "cta": "phrase call to action courte pour la slide 5, avec emoji",
  "caption": "texte du post Instagram avec 5 hashtags français pertinents, max 200 caractères"
}}"""

response = client.models.generate_content(
    model="gemma-3-27b-it",
    contents=prompt
)

# Parser le JSON
raw = response.text.strip()
if "```" in raw:
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
data = json.loads(raw.strip())
print(f"Contenu généré : {data}")

# Générer les slides avec Pillow
def create_slide(text_title, text_body, filename, slide_type="content", index=1):
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Dégradé
    colors = [
        [(41, 128, 185), (109, 213, 237)],   # Bleu
        [(142, 68, 173), (210, 143, 234)],   # Violet
        [(39, 174, 96), (109, 237, 153)],    # Vert
        [(231, 76, 60), (237, 143, 109)],    # Rouge
        [(243, 156, 18), (237, 213, 109)],   # Orange
    ]
    c1, c2 = colors[index % len(colors)]

    for y in range(H):
        ratio = y / H
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Overlay sombre pour lisibilité
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 80))
    img.paste(Image.new("RGB", (W, H), (0,0,0)), mask=overlay.split()[3])

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Titre
    wrapped_title = textwrap.wrap(text_title, width=20)
    y_pos = 300
    for line in wrapped_title:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) / 2, y_pos), line, font=font_title, fill="white")
        y_pos += 90

    # Corps
    if text_body:
        wrapped_body = textwrap.wrap(text_body, width=30)
        y_pos += 40
        for line in wrapped_body:
            bbox = draw.textbbox((0, 0), line, font=font_body)
            w = bbox[2] - bbox[0]
            draw.text(((W - w) / 2, y_pos), line, font=font_body, fill=(255, 255, 255, 200))
            y_pos += 65

    # Numéro de slide
    draw.text((50, 50), f"{index}/5", font=font_small, fill=(255,255,255,150))

    img.save(filename)
    print(f"Slide créée : {filename}")

# Créer les 5 slides
slides_files = []

# Slide 1 - Accroche
create_slide(data["accroche"], "", "slide_1.jpg", "accroche", 0)
slides_files.append("slide_1.jpg")

# Slides 2-4 - Contenu
for i, slide in enumerate(data["slides"]):
    fname = f"slide_{i+2}.jpg"
    create_slide(slide["titre"], slide["contenu"], fname, "content", i+1)
    slides_files.append(fname)

# Slide 5 - CTA
create_slide(data["cta"], "Sauvegarde ce post 💾", "slide_5.jpg", "cta", 4)
slides_files.append("slide_5.jpg")

print(f"Slides créées : {slides_files}")

# Uploader les images sur imgbb (gratuit, sans CB)
IMGBB_API_KEY = os.environ["IMGBB_API_KEY"]

image_urls = []
for fname in slides_files:
    with open(fname, "rb") as f:
        import base64
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    r = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY, "image": img_b64}
    )
    url = r.json()["data"]["url"]
    image_urls.append(url)
    print(f"Image uploadée : {url}")

# Publier le carrousel sur Instagram
# Étape 1 : créer les conteneurs pour chaque image
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

# Étape 2 : créer le conteneur carrousel
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

# Étape 3 : publier
publish_r = requests.post(
    f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media_publish",
    data={
        "creation_id": carousel_id,
        "access_token": IG_TOKEN
    }
)
print(f"Publication : {publish_r.json()}")
