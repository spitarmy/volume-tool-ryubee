import urllib.request
import json
import sys
sys.path.append("/Users/spitarmy/Ryubee/volume-tool-ryubee/ryubee-backend")
from app.auth import create_access_token

token = create_access_token({"sub": "koji.yamabun@outlook.jp"})
req = urllib.request.Request("http://127.0.0.1:8000/v1/settings", method="PUT")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", f"Bearer {token}")
data = json.dumps({"smtp_port": 465}).encode("utf-8")

try:
    resp = urllib.request.urlopen(req, data=data)
    print("SUCCESS", resp.status)
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
