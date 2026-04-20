import requests
import json
login_res = requests.post("http://localhost:8000/v1/auth/login", data={"username":"test@yamabun.com","password":"test1234"})
token = login_res.json()["access_token"]
res = requests.get("http://localhost:8000/v1/templates", headers={"Authorization":f"Bearer {token}"})
print(res.status_code, res.text)
