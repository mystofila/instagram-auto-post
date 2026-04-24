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

# Config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
IG_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID = os.environ["INSTAGRAM_USER_ID"]

cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ["CLOUDINARY_API_SECRET"]
)

# Refresh token Instagram
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
    gh_token = os.environ["GH_TOKEN"]
    repo = "mystofila/instagram-auto-post"
    pub_r = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers={"Authorization": f"token {gh_token}"}
    )
    pub_data = pub_r.json()
    from nacl import encoding, public
    public_key_obj = public.PublicKey(pub_data["key"].encode(), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(new_token.encode())
    encrypted_b64 = base64.b64encode(encrypted).decode()
    update_r = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/INSTAGRAM_ACCESS_TOKEN",
        headers={"Authorization": f"token {gh_token}"},
        json={"encrypted_value": encrypted_b64, "key_id": pub_data["key_id"]}
    )
    print(f"Secret GitHub mis a jour : {update_r.status_code}")
    return new_token

IG_TOKEN = refresh_instagram_token(IG_TOKEN)

# Générer le contenu avec Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

today = datetime.date.today().strftime("%Y-%m-%d")
seed = random.randint(1, 9999)

prompt = f"""Tu es un expert en recrutement et coach carriere francais.
Aujourd hui c est le {today} et ta graine aleatoire est {seed}.

Choisis toi-meme un sujet DIFFERENT et ORIGINAL sur la recherche d emploi, le CV, la lettre de motivation ou les entretiens.
Ne repete jamais un sujet deja traite.

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

# Palettes
palettes = [
    [(15, 32, 78), (30, 90, 180)],
    [(78, 15, 60), (180, 30, 140)],
    [(15, 78, 40), (30, 180, 90)],
    [(78, 30, 15), (200, 80, 20)],
    [(20, 60, 78), (30, 160, 180)],
]

def create_slide(text_title, text_body, filename, index=1):
    W, H = 1080, 1080
    c1, c2 = palettes[(index + random.randint(0, 4)) % len(palettes)]

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img
