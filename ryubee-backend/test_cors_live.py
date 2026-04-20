import urllib.request
import time
import sys

url = "https://ryubee-api-new.onrender.com/v1/health"
headers = {"Origin": "https://spitarmy.github.io"}

for i in range(30):
    try:
        req = urllib.request.Request(url, headers=headers)
        res = urllib.request.urlopen(req)
        acao = res.headers.get("access-control-allow-origin", "")
        if acao == "https://spitarmy.github.io":
            print(f"SUCCESS: Render deployed the fix! (ACAO={acao})")
            sys.exit(0)
        else:
            print(f"Still deploying... ACAO is '{acao}'")
    except Exception as e:
        print(f"Error checking: {e}")
    time.sleep(5)

print("Timeout waiting for deploy.")
