import os
import requests
from dotenv import load_dotenv

load_dotenv()

JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID")
print("JAMENDO_CLIENT_ID:", JAMENDO_CLIENT_ID)

if not JAMENDO_CLIENT_ID:
    raise RuntimeError("JAMENDO_CLIENT_ID is not set in environment")

def fetch_jamendo_track(tag="lofi"):
    try:
        base_url = "https://api.jamendo.com/v3.0/tracks/"
        params = {
            "client_id": JAMENDO_CLIENT_ID,
            "format": "json",
            "limit": "1",
            "tags": tag,
            "audioformat": "mp32",
        }

        response = requests.get(base_url, params=params)
        print("Request URL:", response.url)
        print("Status code:", response.status_code)
        data = response.json()
        print("Response JSON:", data)
        if data["headers"]["results_count"] > 0:
            track = data["results"][0]
            return track["audio"], track["name"], track["artist_name"]
        return None, None, None
    except Exception as e:
        print(f"❌ Jamendo API error: {e}")
        return None, None, None

audio, name, artist = fetch_jamendo_track()
print("Track:", audio, name, artist)
