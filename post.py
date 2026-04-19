import os
import requests
from google import genai

# Config
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
IG_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID = os.environ["INSTAGRAM_USER_ID"]

# Générer le texte avec Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

prompt = """Génère un post Instagram court et engageant sur le thème de l'emploi et du CV.
Le post doit contenir :
- Un conseil pratique sur la recherche d'emploi, la rédaction de CV ou les entretiens
- 3 à 5 hashtags pertinents en français
- Un ton bienveillant et motivant
- Maximum 300 caractères
Réponds uniquement avec le texte du post, sans commentaire."""

response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=prompt
)
caption = response.text
print(f"Caption générée : {caption}")

# Image publique
image_url = "https://images.unsplash.com/photo-1586281380349-632531db7ed4?w=1080"

# Étape 1 : Créer le conteneur média
container_url = f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media"
container_response = requests.post(container_url, data={
    "image_url": image_url,
    "caption": caption,
    "access_token": IG_TOKEN
})
container_data = container_response.json()
print(f"Conteneur : {container_data}")

# Étape 2 : Publier
if "id" in container_data:
    publish_url = f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media_publish"
    publish_response = requests.post(publish_url, data={
        "creation_id": container_data["id"],
        "access_token": IG_TOKEN
    })
    print(f"Publication : {publish_response.json()}")
else:
    print("Erreur lors de la création du conteneur")
