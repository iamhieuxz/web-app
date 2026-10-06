import urllib.request
import json

# Test with error body
try:
    req = urllib.request.urlopen('http://127.0.0.1:8000/api/storage/stats')
    raw = req.read().decode()
    print('Raw:', raw[:2000])
except urllib.error.HTTPError as e:
    print('HTTP Error:', e.code)
    body = e.read().decode()
    print('Error body:', body[:2000])
except Exception as e:
    print('Error:', type(e).__name__, str(e))
