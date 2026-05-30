import requests, re
res = requests.get('https://ibb.co/GLy6j87', headers={'User-Agent': 'Mozilla/5.0'})
print('LINKS:', re.findall(r'https://i\.ibb\.co/[a-zA-Z0-9]+/[^"]+', res.text))
