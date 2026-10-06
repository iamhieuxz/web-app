import urllib.request
import json

try:
    req = urllib.request.urlopen('http://127.0.0.1:8000/api/db/accounts')
    data = json.loads(req.read().decode())
    
    print('Total accounts:', len(data))
    
    ig = [x for x in data if x.get('platform') == 'instagram']
    x = [x for x in data if x.get('platform') == 'twitter']
    
    print('IG count:', len(ig))
    print('X count:', len(x))
    
    print('\nFirst 3 records:')
    for a in data[:3]:
        print('  ', a)
        
except Exception as e:
    print('Error:', e)
