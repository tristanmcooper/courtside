import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("OURA_TOKEN")

if not TOKEN:
    raise ValueError("Missing OURA_TOKEN in .env")

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

url = "https://api.ouraring.com/v2/usercollection/personal_info"

response = requests.get(url, headers=headers)

print("Status:", response.status_code)
print(response.text)