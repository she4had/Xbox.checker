import requests,random,time
import json
def check3(user):
    f=open('file.txt','a')
    
    head={
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate',
        'authorization':'make a spam account and put the auth'
        'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
        'Connection': 'keep-alive',
        'Content-Length': '87',
        'Content-Type': 'application/json',
        'Host': 'gamertag.xboxlive.com',
        'MS-CV': 'MBpWDBGYojgOFrF3UZLDXo.0',
        'Origin': 'https://social.xbox.com',
        'Referer': 'https://social.xbox.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36',
        'x-xbl-contract-version': '1'
    }
    data={
    'gamertag': f'{user}',
    'reservationId': "2535457297763414",
    'targetGamertagFields': "gamertag"
    }
    url="https://gamertag.xboxlive.com/gamertags/reserve"
    time.sleep(5)
    req=requests.post(url=url,headers=head,json=data,timeout=5)
    print(req.text)
    if   '#' not in req.text and '"gamertagSuffix":""' in req.text:
        print(f'{user}')
        f.write(f'{user} \n')    
    main()

def main():
    letters='qwertyuiopasdfghjklzxcvbnm'
    leandnum='qwertyuiopasdfghjklzxcvbnm0123456789'
    user=random.choice(letters)
    user+=''.join(random.choice(leandnum) for _ in range(3))
    found=True
    while found:
        time.sleep(5)
        check3(user=user)
main()
