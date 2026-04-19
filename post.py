import os
import json
import time
import random
import requests
import textwrap
import subprocess
from PIL import Image, ImageDraw, ImageFont
from google import genai
import cloudinary
import cloudinary.uploader
import base64

# Installer la police emoji
subprocess.run(["sudo", "apt-get", "install", "-y", "fonts-noto-color-emoji"], capture_output=True)

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

IMPORTANT : N'utilise AUCUN emoji et AUCUN caractère spécial. Uniquement du texte simple.

Réponds UNIQUEMENT en JSON valide, sans markdown, sans commentaire, exactement ce format :
{{
  "accroche": "titre choc de la slide 1, max 40 caractères, sans emoji",
  "slides": [
    {{"titre": "point 1 court sans emoji", "contenu": "explication en 1-2 phrases max, concrète, sans emoji"}},
    {{"titre": "point 2 court sans emoji", "contenu": "explication en 1-2 phrases max, concrète, sans emoji"}},
    {{"titre": "point 3 court sans emoji", "contenu": "explication en 1-2 phrases max, concrète, sans emoji"}}
  ],
  "cta": "phrase call to action courte pour la slide 5, sans emoji",
  "caption": "texte du post Instagram avec 5 hashtags français pertinents, max 200 caractères, sans emoji"
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

# Générer les slides
def create_slide(text_title, text_body, filename, index=1):
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Dégradé vertical
    gradients = [
        [(41, 128, 185), (109, 213, 237)],
        [(142, 68, 173), (210, 143, 234)],
        [(39, 174, 96), (109, 237, 153)],
        [(231, 76, 60), (237, 143, 109)],
        [(243, 156, 18), (237, 213, 109)],
    ]
    c1, c2 = gradients[index % len(gradients)]
    for y in range(H):
        ratio = y / H
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Overlay sombre
    overlay = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.blend(img, overlay, alpha=0.3)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 46)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Numéro de slide
    draw.text((50, 40), f"{index}/5", font=font_small, fill=(255, 255, 255))

    # Titre centré
    wrapped_title = textwrap.wrap(text_title, width=18)
    y_pos = 350 if not text_body else 280
    for line in wrapped_title:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) / 2, y_pos), line, font=font_title, fill="white")
        y_pos += 90

    # Corps centré
    if text_body:
        wrapped_body = textwrap.wrap(text_body, width=28)
        y_pos += 50
        for line in wrapped_body:
            bbox = draw.textbbox((0, 0), line, font=font_body)
            w = bbox[2] - bbox[0]
            draw.text(((W - w) / 2, y_pos), line, font=font_body, fill=(230, 230, 230))
            y_pos += 62

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
