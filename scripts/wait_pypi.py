import time, urllib.request, json, sys

target = "1.4.0"
for i in range(12):
    try:
        d = json.loads(urllib.request.urlopen("https://pypi.org/pypi/chatwire/json", timeout=10).read())
        v = d["info"]["version"]
        if v == target:
            print(f"PyPI {target} is live!")
            sys.exit(0)
        print(f"attempt {i+1}: PyPI shows {v}, waiting...")
    except Exception as e:
        print(f"attempt {i+1}: error: {e}")
    time.sleep(20)

print("Timed out waiting for PyPI 1.4.0")
sys.exit(1)
