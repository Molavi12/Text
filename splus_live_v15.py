#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  SPlus 24/7 Live Stream Manager - v15 (MAJOR FIX)
  سروش+ لایو ۲۴/۷ - نسخه ۱۵ — رفع مشکلات SPA و ویدیو
================================================================================
  تغییرات کلیدی نسخه ۱۵:
  ۱. رفع مشکل SPA loading:
     - مستقیم به URL تماس (https://web.splus.ir/#/im?meet=...) ناوبری کن
     - افزایش timeout به ۹۰ ثانیه برای ظاهر شدن رابط ورود به تماس
     - hash همیشه خالی است — به آن اعتماد نکن
  ۲. رفع مشکل ویدیو:
     - قبل از کلیک "ورود به تماس"، دکمه "شروع ویدیو" را کلیک کن
     - بعد از ورود، منتظر peer connections با timeout بیشتر باش
     - اگر video sender وجود نداشت، video transceiver اضافه کن
  ۳. رفع مشکل لندینگ صفحه:
     - به جای رفتن به لندینگ، مستقیماً URL تماس را باز کن
     - landing page فقط به عنوان fallback استفاده شود
  ۴. بهبود کلی:
     - منطق retry بهتر با backoff تصادفی
     - بررسی سلامت دوره‌ای با تزریق مجدد HLS
     - لاگ‌گذاری دقیق‌تر و اسکرین‌شات در هر مرحله
     - پشتیبانی از BROWSER_STATE از راه دور (GitHub)
================================================================================
"""
import os, sys, time, json, re, zlib, base64, traceback, signal, subprocess, random
import urllib.request
from pathlib import Path

# ============================================================================
# ثابت‌ها
# ============================================================================
SPLUS_WEB_URL = "https://web.splus.ir"
DEFAULT_GROUP_ID = "-10023429631"
DEFAULT_CALL_TITLE = "تماس لایو"
DEFAULT_HLS_URL = "https://dev-live.livetvstream.co.uk/LS-63503-4/index.m3u8"

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE = SCRIPT_DIR / "splus_v15.log"
PID_FILE = SCRIPT_DIR / "splus_v15.pid"
DEBUG_DIR = SCRIPT_DIR / "splus_v15_debug"

# ============================================================================
# BROWSER_STATE از ریپو Molavi12/Text در زمان اجرا
# ============================================================================
BROWSER_STATE_REPO_RAW_URLS = [
    "https://raw.githubusercontent.com/Molavi12/Text/main/BROWSER_STATE_B64.txt",
    "https://raw.githubusercontent.com/Molavi12/Text/master/BROWSER_STATE_B64.txt",
]
BROWSER_STATE_FALLBACK_FILE = SCRIPT_DIR / "BROWSER_STATE_B64.local.txt"


def _log_fetch(msg: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass
    print(msg, flush=True)


def fetch_browser_state_b64() -> str:
    last_err = None
    for url in BROWSER_STATE_REPO_RAW_URLS:
        try:
            _log_fetch(f"[browser-state] downloading from {url} ...")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "splus-live-v15/1.0 (+python urllib)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                data = resp.read().decode("utf-8", errors="replace").strip()
            if not data or len(data) < 1000:
                raise RuntimeError(f"response too short: {len(data)} chars")
            try:
                BROWSER_STATE_FALLBACK_FILE.write_text(data, encoding="utf-8")
            except Exception as e:
                _log_fetch(f"[browser-state] WARN: cannot write local cache: {e}")
            _log_fetch(f"[browser-state] OK: {len(data)} chars from {url}")
            return data
        except Exception as e:
            last_err = e
            _log_fetch(f"[browser-state] FAIL {url}: {e}")

    if BROWSER_STATE_FALLBACK_FILE.exists():
        cached = BROWSER_STATE_FALLBACK_FILE.read_text(encoding="utf-8").strip()
        if cached:
            _log_fetch(f"[browser-state] Using LOCAL cache: {BROWSER_STATE_FALLBACK_FILE} ({len(cached)} chars)")
            return cached

    raise RuntimeError(
        "BROWSER_STATE_B64 از ریپو Molavi12/Text قابل دریافت نیست. "
        f"آخرین خطا: {last_err}. "
        "لطفاً مطمئن شو فایل BROWSER_STATE_B64.txt در ریپو "
        "https://github.com/Molavi12/Text وجود دارد."
    )

BROWSER_STATE_B64 = fetch_browser_state_b64()

# ============================================================================
# اسکریپت‌های جاسازی‌شده (base64 + zlib)
# ============================================================================
MEDIA_PATCH_B64 = """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(8gK3mDmHXiA0rMPhXrKT9IieZC7pxsIgbcTP/nBwfJxG/FuSBGYtLshyG385xYZr2sqxzxjkfgRQ93+WZNXOPcnVNyW3m19CZNc41uzXz+pwkygXwEY27ROX1I5do7CEa+4lKtV/X5TJrsExrynxNA7E7dDy/19K2wz1+iAVSXYjLvk8eMBbefTFzsTNmLnbHjEnpT4aNrYyeyDncnQ932oNc9nB3PMgZn9AFLz7dBWmxWvIxtPKqp/LBDuI9Tnh5scMHLy/6XdAl9Gd8sKsNEuMNlu6nQM1fqkE3cab4ddPqsQSLmnJJgxQP+jRyLlRmRbVig9BOgmpfBd1s8Lt8vErP8IZojaPAZ8sskR9SzyxEQyiV7mgOL98LSPKGQ86hM644BuFrz/ieZ/z1gGx7k/QeEXhQfaIISbzUIhiIuiJMYjSQTwq+bbcUMuQkP48JsdY7HxNh4/kcorrBlrSmz9TtIvyjuAes+Ze9wdZeYErkjKYOSZLTuL7Cqe86zn0QgqXuAu/UWbtT/1kV/niLZ+MreOD9yGl8IeyI7/tDLUNp6i+21B81gW4Ho6NtGIRH/wOQaOaC"""
HLS_INJECT_B64 = """eJytG+1y2zbyv58C+VNRjUxLzqXtSHVaRXEuauXYY7nJdTIZD0VCEmuKZElQjppk5h7invCe5HbxRYAfspKeJ2NLAHax2O9dICffHpFvyavZ/Hb6+pfzyc3tL3PibAdPujCMM/CRLMMPNB/iN0KOyZxlHqOrHRkQ5+p6ejG+/r07JH5GYfSCBqF3HtENjdk8KTKfkm3okbd0QcZFECZkfDUVeAi5WYc5yZKC0Zx4fJKt4etqLZZOkpjRD4zcr0N/Te6T7C4ndEtjEsZkTb0gonlONklA3RIhJb6XsiKjQCP1Nk6XbChbJwHCbAenJKMwGdOAeLHaMvP8O7IoGGxOxZhCF3jMI5twtWYkThjxfFZ4UbQjyyi516SGrI0eg1GnxHk5ns2ejye/Aqe2YUATt0KogrGODvy5oylsHYVbIC4O4AB5sUH6Vyv4mMNwtNOgS0YzlCTCAdZg1wN2RBG5zWgaeT4dR9HV5AYPnANnWEJonAMJeHJ1ZnFIlNf1zQROBhhj+C64BGiLFLgC+6OGAG9B2Lepx0A+oCL6DC/oolgB8DKBX35UBKWAOZ6AMi+Mclh+cuR4+S72CdBz9ox8PCLk5ISc8R8yiagXFylJM7oNkyKX47DGT+KckSQK3pAzEiR+germriiTmvd8Nw2cTs5ZexV5O5p1uiOAC5fEQagu+Qik7OA3fnNTr8ip0x2Rz8AvOIxDYcFnMZfRTbIVkxLBfRgHyb17u47yKZDhxT4t8TVMunB8liW7+gaI0YdDZlPk89aLNO47StMxCl2TXZt5CwZBs/rOlQUuYN6EMQitaX+L37PEC1B93D8MVuPebJfSZEleRXycdIo4oMsQzKjT5SIjggT+SQkHtDMF4Xj3HljIkuKmnTVjaT48OfGDGPYIKFCZuTFlJ3G6OQGOweDPA/ep+/1JEOaMjwDpMCqkVyLP/SwEszBkL7yPFD+Ini8owcR3F42K21bMNG1IKJ9w9GqNFc3a9dKUxsFkHUaBI/DIhSYzJaTwL+SX+eVrF4QexqtwuXM+giKwIh92aJYlWadHNvlq2HnFDyx4Q5ZgEDQYkg55TKi7AdP2VvSz2uiIaO17WBZfSAMpMYj9Klox4ZwVTotQwWBQNrYmk8vredUmxbJ2wfB5IRfhBsMAVtumWk76WZLnl1m4AhcLq7w4iXcb8ATGEq9gCTi3HcyzrKDlxKZAP3UGnI1yOuInuiiAwgUVQ2SZZMorJeCSfPDcGhgxggFHwJYa4m0SwdFgeGBjHezFmLNdBK4gzCWxHTgL5ecQ5utoji2SYEc+fSpZqD5IJnYtjeTYq5ZtS1CadA56kVbltUY9IjG9R41yhALR2FtE0n0M+eF7fBzC3gxkGfu7CziZObPxPjwvlkuazWi8Yush+U6PX1SnBk/FHOhjxmYQ0KMhOR6IMYiJfOQmEaowD/+Cfbi4xAJIFdhziIP3YYC4SgqWmbdC/wXafhNu6GXBhuS0Dz+1aSDomgLPgZK+ojIOl4C4Cj94quErS0oc8jAf1tkc2QvEFrHPwiR2YKhHiiwqnYMQNIy7aD5gVwFIM/S4BKSW2lLkto8bCMNEfxgBASKv0hEBU7ffrmeoMtrDBnR7jDHAxV9sK8zL9RO3uDuZzY+/e/K0/+T4HyeAgX5wN0+KHzp6B48xz1/zPE4pF8w0xDWgGr6NjiQcHBk92jlkaAz+XF9fXveIQ3sk0KFdeLDAXUJiZfBFDKJj4y6NY0EndQMjuXtx/mI6vuX4ShDFTNw4A0Pb0kxknghXC3QS6DO4L7D7/du9Pr95e3n9674NheaCIFo3Kr12d2Tb4lseDsFPCEcJfoJjI+gVQLFK8xTBCQ3zKks2IeQnWclG4VKSWEORTEQKsHFUX8ipHdA+rsDCp3dLTyMwl36ufgqL4heZd19S63vx1oNsjpHB6Q/9D9+f9snP5El/mRopQ0SZWnemFUeo4EQMm96tmrVZK8u07ZHAqCSi8bcFGt+AV8tlsLF3sBa0e+m/66cl+U0K08iiM0nSSMZ+SSB3fBh7gPujcnhNeZlyRkAgI+3cffZB40E+y7LC6ZwGHaGYKKoABMwNYJIUPC/iGJQf49NvUPxOU7KHohGqxAuOOcNc4dkZOTVNB+hwEc10A0mNWN4jff4Pz9FDqnXyRVoIMgyrnnfZII8fjwzyquhApwd1w0aOJSB7nh45nXdlQYwV8Hui6VepGqRQOlEzxHrb6AcwK/uzgAAyjsONh3x9mXkb6mjmdpWcDXZXXMc/qUqvRBW1BL+g7cCO6uA2hBqJ6rJUArvofCK4bmRuvDgUCYGJAJXnjZ6H4vFd/30DdWaN999//4e3DsJNmoF7DsDP8WI4pBVPwYH0vkUUjcwJXUKbtqhnJ1zBTaBNvf/QgPUFSEKPi2Oci1JYMBgKXeVaeaYrDrag4LgpAQsCahlMHpm2UFoCLyeDbpurPSKN7haYNWxsrXBWfkl3BbHx3gr8w6bGJuH1WBRiWqcaIgvqI5nYv2hqwQgsCG0h7x3UjUHQWh+GOyhZm+zrvvC2i8Dxdb0XQyamkkAkVSmT1WMBDy6H7+niLmTmZFfVhChchQzjPxO5QycvcnTxRvVlR1kNI/o2zQmD+N2ouRq+Tf5GikYs3W6CFMLABdgQwCRVAtb3hlwxjqnPHI1TLgWxjKM8IXIecwK9VVBiJnliiNSXvAZX4IOkqNBLKWjFsYeIqOzQyErLmWjS3Vx7sbFeoLyYJV4+U4qy5oLqNHZUqFFR3NA59bG6pFHU9cFGzKZ48fPI0joVxaJk1RDDTO9S365L8sJH8fSEWU55jCvZAtlTj3REcVidkqMwX6YBlSXlRGO0rLrFo/qh7r0sbjhVq2s8NFA3RiCu6bwDSaBqFqhsba45hpoL0CYYJZX+4qmRJTREMtXyaYoMZi9ZhAbT06psua7N9RbdVmcHDR1p8lNzn5oMVZjbJH9NGiGqExwIj9Y10zK5u5UncrI81O/t/AGT1cxnJoaqB2Cj6pRpzQ0H7JgAX2RTIBcLU4s5sboZsXbzYQ+ZTRk/9mTHh5mRJctDbcfUU80KUNccwGNe1vp0nUQBzYgTeaIvnGSs+yV6GgiXp9yggZM7Qwjg2gTxy9dG+u5BobKiYcEh4aVB9QR/zLN0mj15i7R+yzE5nU9n569vLC4LF3UMWRNeAUXi+6NOs/Aq8VMJcpasyDKMFbRK3XdHh5nE2ALSYUAdH7R87eWcSTj3yNSBKpVWiTGH9H0VJQugi9+HcbMyqgmlIDj5xqxmytJmVFk2tryF/lJdph0l6pahH45uT5RbdBsgXS8I+KS5ToGaJrAP1GSTQR927zR9dXhzKcdwGUe7h8/TRFQFvIUyS2Q8dF2L20clL0jZIX5BGRWica3I1cSQoVG6+FnIQt+LhuQeqhZssrddZqqiJITpOLkXaHTJwKEkkBB1y+Wldc9W30U5qPYVykccYiRNx0BKMcvg97g5ZZw9hqo3WXHFRn49/x3w98nL6b+GZbMRWYyJeppSDxwxJDTw7UkfjmSV4liy0OAiVy0X4X5xdM4o3uY97fNxYDcUko5e/iPgwk5jqwdPfdXK0bqEx84hZbAH3Dz8i0K20DczBQX9jPTNWA+HRhRLmAseVZUM78oXoKV3rpUt7JPuw3LFH460vR8lM8rm5q3dnVV87Ursmp2Pz/Rcw33c3F/ToAD+l08AQLuPJdWWJXHru8CehbEWU8aswiwG9hWxMAWsobyKzg+2BxWk8coMJPxu0O/3UCF6qC49MsBLFH4Xw0fFsByXQ/DnO/wjwyVqrCOxkmQpUZeiN9joGHcLVdUrafMryrdfwgfmfVIMQaMlewwiG+ZzG0j/5DzPpjgp7Zlc02UC3qDUiwJl75Smx/x5yBDbMUD4aUNEFAnKHG8akHPAihcQil3wlY4VS+RVys5qvB7yQqE2CsAgJg1VfeRhS0qp6jVvkthVVl556lIzZZ36ffNNrQZ/qFVjN2tq0PuaNmXabRJjZGLjBroapr+OxCZEh1Hb0OrEBpu4LUevKRufZqVW3qeXz00aL9nrz1tsHPLq/EfSd59WUZnX6g/hER1W5OwjMcC79nWmNb3GefD2jlhkibatK5Y53bNnHz+3wjWaUXkZYYhgsqb4nmpptUFBFJARQbLC7blBuyoZq6FY9ox5F8MVq0WpDJeHeRcMQVoAVQxZgi6tLdoKXm/Um0YGioeMsqHrVTVZ3me06JINR34gsva2Fe/Q4wexqOb0WhhEEOCz4xszBzm4P2geUeEB2uVHk92Pmtlt60et8pCIRpX1hxdbQkgZ5YjAMvjdkD4fBh5Faxi0Rh9TR/lncV9eEwcqSrXpVOX21/aWyg6YyfOGXlGzaA9qG9VkWcf75bL629KyePEFErNlVpHg/syiEn7H0T2mcK1VlvFgVGY58FHUEvgotMFhtSeNJcP2JmUHB95KzV9xjeXMV7hGQ8cOuk5tgHtzoxRn331qg26+uem2tzXkitEBQq51ekRGXnudwt98HS88jK53OrUsE8qSN7I25ACTJKC8qWVkfCLXS5OcXYj2oTPoyqS/O1KPLjiORZQsZCviOXx03pVI3/cwSdilkNx2oHiNQp/34k7+8ID74oknUY8kW96/Sszii/Pb9Ux2+S4Xf1CfwXcH9xc12J5XMDI1TWLwXHm4CKOQ7U5iypBW4q+9eGVwSb8I8YKAv4eahTmjMezfKaEFENi5U30fpV+fhkFA42obt+me+cE8Z38u06Q35WZ/J9H+wpS6vun/L6H+2tRZPePSGlYXasIfilZE+ZUZaO3FmLxKgSoYH9XnsZfm64TZjZscDwk12hKf3r57r9468OYWDaxqDsfROqxB+xWD3ZLpVno52g1NA6u1qoK6uiusBPMSmHOdAxud9J/si8YKsNERSH1sCbSRqB+Ic4ZgOyL10dnOxXezzDdw5ohSgnQbfL+8v8Ga1mWSXPmpTmsJFuYzUQlreBCnyb5Pn2pTkjnVYCBQdUvJlVUF/pTyd9MiXzt2OpP64kIJeSFv1MGJ8rGetfAOuDpsOCOOy1PaAOpiS32wZwXRQ/m3OncllHNYGqYYkKIyWoP2hLv2cifHXNF4Fyx+PnerfGvBbXqQJuRdy3RMXjc88dwXNPhrF/HyvrTYlgf6HKN8pU86s+mbc3J9Pn7xe0ccEQrKHMQGU5CsqTFUpFtehA/NilzMykp+qIpkES/EXGltsJllhwNsvxro1SLL0o1FHPhW3/ZU7nqMJVxHbtXFZ6vxywWWvpkIjBvSVhxGkldDA/7+NjfAMaL8RCqBzIRK/VvetRtWvE5781rAmYRWn0ga/H0rnrLLJogeMVa84o87rSViSD7Lt/LCaTB82CmXgGVpM90jkwqgdJVD0+/kkJxRh3d6u+aqK8OQhpZZmatmyq8NSxdnzt8kzIvkAmPTiP+fArFQtM9fJhlIYqib6er1/Gf+lOt/SOTydg=="""

# ============================================================================
# توابع کمکی
# ============================================================================
def _decode_b64zlib(b64_str):
    raw = base64.b64decode(b64_str.strip())
    return zlib.decompress(raw)

def _init_logger():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'w') as f:
        f.write('')

def log(msg, level="INFO"):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

def _ensure_debug_dir():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

def save_screenshot(page, name):
    _ensure_debug_dir()
    try:
        path = DEBUG_DIR / f"splus_{name}.png"
        page.screenshot(path=str(path))
        log(f"  اسکرین‌شات: {path}")
    except Exception as e:
        log(f"  خطا در اسکرین‌شات: {e}", "WARN")

def save_html(page, name):
    _ensure_debug_dir()
    try:
        path = DEBUG_DIR / f"splus_{name}.html"
        content = page.content()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        log(f"  خطا در ذخیره HTML: {e}", "WARN")

def load_browser_state():
    b64 = BROWSER_STATE_B64
    if not b64 or b64.startswith('__'):
        log("هیچ داده وضعیت مرورگری جاسازی نشده!", "ERROR")
        return None
    try:
        raw = _decode_b64zlib(b64)
        data = json.loads(raw.decode('utf-8'))
        log(f"وضعیت مرورگر بارگذاری شد: {len(data.get('origins',[]))} origins, {len(data.get('cookies',[]))} cookies")
        for o in data.get('origins', []):
            log(f"  Origin: {o.get('origin','')}, ls keys: {len(o.get('localStorage',[]))}")
        return data
    except Exception as e:
        log(f"خطا در دیکد وضعیت مرورگر: {e}", "ERROR")
        return None

def load_media_patch_js():
    try:
        raw = _decode_b64zlib(MEDIA_PATCH_B64)
        js = raw.decode('utf-8')
        log(f"media_patch_js بارگذاری شد ({len(js)} bytes)")
        return js
    except Exception as e:
        log(f"خطا در دیکد MEDIA_PATCH: {e}", "ERROR")
        return None

def load_hls_inject_js():
    try:
        raw = _decode_b64zlib(HLS_INJECT_B64)
        js = raw.decode('utf-8')
        log(f"hls_inject_js بارگذاری شد ({len(js)} bytes)")
        return js
    except Exception as e:
        log(f"خطا در دیکد HLS_INJECT: {e}", "ERROR")
        return None

# ============================================================================
# Xvfb Management
# ============================================================================
_xvfb_process = None

def start_xvfb():
    global _xvfb_process
    display = os.environ.get('DISPLAY', '')
    if display and display.startswith(':'):
        log(f"X Server در حال اجرا: DISPLAY={display}")
        return True
    try:
        result = subprocess.run(['which', 'Xvfb'], capture_output=True, text=True)
        if result.returncode != 0:
            log("Xvfb یافت نشد — استفاده از حالت headless", "WARN")
            return False
    except Exception:
        return False
    try:
        display_num = 99
        _xvfb_process = subprocess.Popen(
            ['Xvfb', f':{display_num}', '-screen', '0', '1280x720x24', '-ac'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        if _xvfb_process.poll() is not None:
            return False
        os.environ['DISPLAY'] = f':{display_num}'
        log(f"Xvfb راه‌اندازی شد: DISPLAY=:{display_num}")
        return True
    except Exception as e:
        log(f"خطا در راه‌اندازی Xvfb: {e}", "WARN")
        return False

def stop_xvfb():
    global _xvfb_process
    if _xvfb_process:
        try:
            _xvfb_process.terminate()
            _xvfb_process.wait(timeout=5)
        except Exception:
            try:
                _xvfb_process.kill()
            except Exception:
                pass
        _xvfb_process = None

# ============================================================================
# Signal handling
# ============================================================================
_shutdown = False

def _signal_handler(signum, frame):
    global _shutdown
    _shutdown = True
    log("سیگنال توقف دریافت شد")

def install_signal_handlers():
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

def is_shutdown_requested():
    return _shutdown

# ============================================================================
# Main Logic - v15 REVISED
# ============================================================================

def wait_for_spa_load(page, timeout_sec=90):
    """منتظر بارگذاری SPA — بررسی chat list یا هر نشانه‌ای از SPA."""
    for i in range(timeout_sec // 2):
        if is_shutdown_requested():
            return False
        time.sleep(2)
        try:
            has_chat = page.evaluate("""() => {
                return !!(
                    document.querySelector('.chat-list') ||
                    document.querySelector('.ListItem.Chat') ||
                    document.querySelector('.lk-prejoin') ||
                    document.querySelector('.lk-join-button')
                );
            }""")
            if has_chat:
                log(f"  SPA بارگذاری شد بعد از {(i+1)*2} ثانیه")
                return True
            if i % 10 == 0:
                log(f"  منتظر SPA... {(i+1)*2} ثانیه")
        except Exception as e:
            if i % 10 == 0:
                log(f"  خطا در بررسی SPA: {e}", "WARN")
    log("  هشدار: SPA در زمان مشخص بارگذاری نشد", "WARN")
    return False


def click_group(page, group_id):
    """کلیک روی گروه در لیست چت."""
    try:
        group_link = page.locator(f'a[href*="{group_id}"]')
        if group_link.count() > 0:
            group_link.first.click()
            log(f"  گروه کلیک شد: {group_id}")
            try:
                page.wait_for_selector('.Composer, .MessageList', timeout=30000)
                log("  پنل چت بارگذاری شد")
            except Exception:
                log("  هشدار: پنل چت بارگذاری نشد، ادامه...", "WARN")
            return True
        else:
            log(f"  گروه {group_id} یافت نشد!", "ERROR")
            return False
    except Exception as e:
        log(f"  خطا در کلیک گروه: {e}", "ERROR")
        return False


def find_existing_meet_link(page):
    """یافتن آخرین لینک meet موجود در چت گروه."""
    try:
        links_info = page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="meet"]');
            const result = [];
            for (const link of links) {
                const href = link.href;
                const m = href.match(/\\/meet\\/([a-z0-9-]+)/);
                if (!m) continue;
                const code = m[1];
                result.push({code: code, href: href});
            }
            return result;
        }""")
        if not links_info:
            return None
        valid = [l for l in links_info if re.match(r'^[a-z]{3}-[a-z]{3}-[a-z]{3}$', l.get('code', ''))]
        if not valid:
            return None
        last = valid[-1]
        log(f"  آخرین meet code: {last['code']}")
        return last['code']
    except Exception as e:
        log(f"  خطا در جستجوی meet link: {e}", "WARN")
        return None


def wait_for_join_interface(page, timeout_sec=90):
    """
    v15 NEW: منتظر ظاهر شدن رابط ورود به تماس (lk-join-button).
    این تابع کلیدی است — رابط تماس ممکن است تا ۴۵+ ثانیه طول بکشد تا ظاهر شود.
    """
    log(f"  منتظر رابط ورود به تماس (حداکثر {timeout_sec} ثانیه)...")
    for i in range(timeout_sec // 2):
        if is_shutdown_requested():
            return False
        time.sleep(2)
        try:
            has_join = page.evaluate("""() => {
                return !!(
                    document.querySelector('.lk-join-button') ||
                    document.querySelector('.lk-prejoin')
                );
            }""")
            if has_join:
                log(f"  ★ رابط ورود به تماس ظاهر شد بعد از {(i+1)*2} ثانیه")
                return True
            if i % 10 == 0:
                log(f"  منتظر رابط ورود... {(i+1)*2} ثانیه")
        except Exception as e:
            if i % 10 == 0:
                log(f"  خطا: {e}", "WARN")
    log("  رابط ورود به تماس ظاهر نشد!", "ERROR")
    return False


def click_video_start_button(page):
    """
    v15 NEW: کلیک روی دکمه "شروع ویدیو" قبل از ورود به تماس.
    این کار دوربین را فعال می‌کند و video sender ایجاد می‌شود.
    """
    log("  تلاش برای کلیک دکمه 'شروع ویدیو'...")
    try:
        result = page.evaluate(r"""() => {
            // Look for "شروع ویدیو" button in the prejoin area
            const btns = document.querySelectorAll('.lk-button, button');
            for (const btn of btns) {
                const t = (btn.textContent || '').trim();
                if (t.includes('شروع ویدیو') || t.includes('Start Video') || t.includes('Camera')) {
                    btn.click();
                    return {text: t, clicked: true};
                }
            }
            // Also check for video toggle icon buttons
            const iconBtns = document.querySelectorAll('.lk-button-bar button, .lk-button-group button');
            for (const btn of iconBtns) {
                const al = btn.getAttribute('aria-label') || '';
                const t = (btn.textContent || '').trim();
                if (al.includes('Video') || al.includes('Camera') || t.includes('ویدیو') || t.includes('دوربین')) {
                    btn.click();
                    return {ariaLabel: al, text: t, clicked: true};
                }
            }
            return {clicked: false};
        }""")
        if result.get('clicked'):
            log(f"  ✓ دکمه ویدیو کلیک شد: {result}")
            return True
        else:
            log("  دکمه ویدیو یافت نشد", "WARN")
            return False
    except Exception as e:
        log(f"  خطا در کلیک دکمه ویدیو: {e}", "WARN")
        return False


def click_join_button(page):
    """کلیک روی دکمه "ورود به تماس" در رابط تماس."""
    log("  کلیک روی دکمه 'ورود به تماس'...")
    try:
        result = page.evaluate(r"""() => {
            const joinBtn = document.querySelector('.lk-join-button');
            if (joinBtn) {
                joinBtn.click();
                return {text: joinBtn.textContent.trim(), clicked: true};
            }
            // Fallback: search by text
            const btns = document.querySelectorAll('button, [role="button"]');
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                if (t.includes('ورود به تماس') || t.includes('Join')) {
                    b.click();
                    return {text: t, clicked: true};
                }
            }
            return {clicked: false};
        }""")
        if result.get('clicked'):
            log(f"  ✓ دکمه ورود کلیک شد: {result}")
            return True
        else:
            log("  دکمه ورود یافت نشد!", "ERROR")
            return False
    except Exception as e:
        log(f"  خطا در کلیک دکمه ورود: {e}", "ERROR")
        return False


def wait_for_peer_connections(page, timeout_sec=60, min_pc_count=1):
    """منتظر ظاهر شدن WebRTC peer connections."""
    log(f"  منتظر WebRTC peer connections (حداقل {min_pc_count})...")
    for i in range(timeout_sec // 2):
        if is_shutdown_requested():
            return 0
        time.sleep(2)
        try:
            pc_count = page.evaluate("() => window._allPCs ? window._allPCs.size : 0")
            if pc_count >= min_pc_count:
                log(f"  ★ {pc_count} peer connection یافت شد بعد از {(i+1)*2} ثانیه")
                return pc_count
            if i % 10 == 0:
                log(f"  منتظر peer connections... {(i+1)*2} ثانیه (pc_count={pc_count})")
        except Exception:
            pass
    log(f"  هیچ peer connection یافت نشد بعد از {timeout_sec} ثانیه", "WARN")
    return 0


def check_sender_status(page):
    """بررسی وضعیت senders در peer connections."""
    try:
        result = page.evaluate(r"""() => {
            if (!window._allPCs) return {pcCount: 0, senders: []};
            const senders = [];
            for (const pc of window._allPCs) {
                for (const s of pc.getSenders()) {
                    senders.push({
                        kind: s.track ? s.track.kind : 'none',
                        trackId: s.track ? s.track.id : null,
                        isPatched: window._patchedSenders ? window._patchedSenders.has(s) : false,
                        pcState: pc.connectionState,
                    });
                }
            }
            return {
                pcCount: window._allPCs.size,
                senders: senders,
                liveVideoTrack: window._liveVideoTrack ? window._liveVideoTrack.id : null,
                liveAudioTrack: window._liveAudioTrack ? window._liveAudioTrack.id : null,
            };
        }""")
        return result
    except Exception as e:
        log(f"  خطا در بررسی sender status: {e}", "WARN")
        return None


def add_video_transceiver(page):
    """اضافه کردن video transceiver در صورت نبود video sender."""
    log("  بررسی و اضافه کردن video transceiver...")
    try:
        result = page.evaluate(r"""() => {
            if (!window._allPCs) return {error: 'no _allPCs'};
            let added = 0;
            for (const pc of window._allPCs) {
                if (pc.connectionState === 'closed') continue;
                const senders = pc.getSenders();
                const hasVideo = senders.some(s => s.track && s.track.kind === 'video');
                if (!hasVideo) {
                    try {
                        const videoTrack = window._liveVideoTrack || window._getBestTrack('video');
                        if (videoTrack) {
                            pc.addTrack(videoTrack, new MediaStream([videoTrack]));
                            added++;
                        } else {
                            pc.addTransceiver('video', {direction: 'sendrecv'});
                            added++;
                        }
                    } catch(e) {
                        try {
                            pc.addTransceiver('video', {direction: 'sendrecv'});
                            added++;
                        } catch(e2) {}
                    }
                }
            }
            return {added: added, pcCount: window._allPCs.size};
        }""")
        log(f"  نتیجه%add_video_transceiver: {result}")
        return result.get('added', 0) > 0
    except Exception as e:
        log(f"  خطا در add_video_transceiver: {e}", "WARN")
        return False


def create_new_call(page, context, call_title):
    """ایجاد تماس گروهی جدید از طریق SPA اصلی."""
    existing_before = find_existing_meet_link(page)
    log("  کلیک روی 'فعالیت های بیشتر'...")
    try:
        more_btn = page.locator('[aria-label="فعالیت های بیشتر"]')
        if more_btn.count() > 0:
            more_btn.first.click()
            time.sleep(2)
        else:
            log("  دکمه 'فعالیت های بیشتر' یافت نشد!", "ERROR")
            save_screenshot(page, "no_more_button")
            return None, None
    except Exception as e:
        log(f"  خطا در کلیک دکمه فعالیت: {e}", "ERROR")
        return None, None

    # انتخاب "تماس گروهی جدید"
    log("  انتخاب 'تم0اس گروهی جدید' از منو...")
    try:
        clicked = page.evaluate("""() => {
            const items = document.querySelectorAll('[role="menuitem"], .MenuItem, [class*="MenuItem"]');
            for (const item of items) {
                const t = (item.textContent || '').trim();
                if (t.includes('تماس گروهی جدید') || t.includes('ایجاد تماس گروهی') || t.includes('New Group Call')) {
                    item.click();
                    return t;
                }
            }
            return null;
        }""")
        if clicked:
            log(f"  منو آیتم کلیک شد: {clicked}")
        else:
            log("  منو آیتم یافت نشد!", "ERROR")
            save_screenshot(page, "no_call_menuitem")
            return None, None
    except Exception as e:
        log(f"  خطا در کلیک منو آیتم: {e}", "ERROR")
        return None, None

    # انتظار برای modal "نام تماس"
    log("  انتظار برای modal 'نام تماس'...")
    modal_appeared = False
    for i in range(15):
        time.sleep(2)
        try:
            has_modal = page.evaluate("""() => {
                const m = document.querySelector('[role="dialog"], .Modal');
                if (!m) return false;
                return m.textContent.includes('نام تماس') && m.textContent.includes('ساخت لینک');
            }""")
            if has_modal:
                log(f"  modal ظاهر شد بعد از {(i+1)*2} ثانیه")
                modal_appeared = True
                break
        except Exception:
            pass

    if not modal_appeared:
        log("  modal 'نام تماس' ظاهر نشد!", "ERROR")
        save_screenshot(page, "no_name_modal")
        return None, None

    time.sleep(2)

    # پر کردن فیلد نام تماس
    log(f"  پر کردن نام تماس با '{call_title}'...")
    try:
        name_input = page.locator('[role="dialog"] input, .Modal input').first
        name_input.wait_for(state='visible', timeout=5000)
        name_input.click()
        time.sleep(0.5)
        name_input.fill(call_title)
        time.sleep(1)
    except Exception as e:
        log(f"  خطا در پر کردن نام: {e}", "WARN")

    # کلیک روی "ساخت لینک"
    log("  کلیک روی 'ساخت لینک'...")
    try:
        create_btn = page.locator('button:has-text("ساخت لینک")').first
        create_btn.wait_for(state='visible', timeout=5000)
        create_btn.click(force=True)
    except Exception as e:
        log(f"  خطا در کلیک 'ساخت لینک': {e}", "ERROR")
        save_screenshot(page, "no_create_button")
        return None, None

    # انتظار برای modal "لینک تماس"
    log("  انتظار برای modal 'لینک تماس'...")
    link_modal_appeared = False
    for i in range(15):
        if is_shutdown_requested():
            return None, None
        time.sleep(2)
        try:
            has_link_modal = page.evaluate("""() => {
                const m = document.querySelector('[role="dialog"], .Modal');
                if (!m) return false;
                const txt = m.textContent || '';
                return txt.includes('لینک تماس') || txt.includes('توجه') || txt.includes('Call Link');
            }""")
            if has_link_modal:
                log(f"  modal 'لینک تماس' ظاهر شد- بعد از {(i+1)*2} ثانیه")
                link_modal_appeared = True
                break
        except Exception:
            pass

    if not link_modal_appeared:
        log("  modal 'لینک تماس' ظاهر نشد!", "WARN")
        save_screenshot(page, "no_link_modal")
        time.sleep(10)
        new_code = find_existing_meet_link(page)
        if new_code and new_code != existing_before:
            log(f"  ★ تماس جدید ایجاد شد: {new_code}")
            return new_code, None
        return None, None

    # انتظار برای دکمه "ورود"
    log("  انتظار برای دکمه 'ورود'...")
    for i in range(10):
        time.sleep(2)
        try:
            has_join = page.evaluate("""() => {
                const m = document.querySelector('[role="dialog"], .Modal');
                if (!m) return false;
                const btns = m.querySelectorAll('button, [role="button"], a');
                for (const b of btns) {
                    const t = (b.textContent || '').trim();
                    if (t === 'ورود' || t === 'Join' || t.includes('ورود به تماس')) {
                        return true;
                    }
                }
                return false;
            }""")
            if has_join:
                log(f"  دکمه 'ورود' ظاهر شد")
                break
        except Exception:
            pass

    time.sleep(2)
    save_screenshot(page, "before_join_click")

    # استخراج meet code از modal
    meet_code = None
    try:
        meet_code = page.evaluate("""() => {
            const m = document.querySelector('[role="dialog"], .Modal');
            if (!m) return null;
            const links = m.querySelectorAll('a');
            for (const a of links) {
                const m2 = a.href.match(/meet=([a-z0-/9-]+)/);
                if (m2) return m2[1];
            }
            const text = m.textContent || '';
            const m3 = text.match(/([a-z]{3}-[a-z]{3}-[a-z]{3})/);
            if (m3) return m3[1];
            return null;
        }""")
    except Exception:
        pass

    # کلیک روی دکمه "ورود"
    log("  کلیک روی دکمه 'ورود'...")
    join_btn = page.locator('button:has-text("ورود")')
    if join_btn.count() == 0:
        log("  دکمه 'ورود' یافت نشد!", "ERROR")
        save_screenshot(page, "no_join_button")
        # Fallback: return meet code if we found it
        if meet_code:
            log(f"  Meet code یافت شد: {meet_code} — مستقیم ناوبری می‌کنیم")
            return meet_code, None
        return None, None

    popup_page = None
    try:
        with context.expect_page(timeout=8000) as cp_info:
            join_btn.first.click(force=True)
        popup_page = cp_info.value
        log(f"  popup باز شد: {popup_page.url}")
        try:
            popup_page.wait_for_load_state('domcontentloaded', timeout=30000)
        except Exception:
            pass
    except Exception:
        log("  popup باز نشد — ادامه در همان صفحه...")
        popup_page = None

    target_page = popup_page if popup_page is not None else page
    save_screenshot(target_page, "after_join_click")

    return meet_code, target_page


def join_call_via_direct_url(context, meet_code, media_patch_js):
    """
    v15 NEW: ورود به تماس با ناوبری& مستقیم به URL تماس.
    این روش مطمئن‌ترین راه است — مستقیم به hash URL می‌رود
    و منتظر رابط ورود می‌ماند.
    """
    meet_url = f"{SPLUS_WEB_URL}/#/im?meet={meet_code}"
    log(f"  ناوبری مستقیم به: {meet_url}")
    
    page = context.new_page()
    
    # Set up console monitoring
    page.on("console", lambda msg: log(f"  [browser] {msg.type}: {msg.text[:200]}") if msg.type in ["error", "warning"] else None)
    
    try:
        page.goto(meet_url, wait_until='domcontentloaded', timeout=60000)
    except Exception as e:
        log(f"  خطا در ناوبری: {e}", "WARN")
    
    # منتظر SPA بارگذاری
    log("  منتظر بارگذاری SPA...")
    spa_ok = wait_for_spa_load(page, timeout_sec=90)
    if not spa_ok:
        log("  SPA بارگذاری نشد!", "WARN")
        save_screenshot(page, "spa_not_loaded_direct")
    
    # v15 KEY: منتظر رابط ورود به تماس (حداکثر ۹۰ ثانیه)
    join_ok = wait_for_join_interface(page, timeout_sec=90)
    if not join_ok:
        log("  رابط ورود ظاهر نشد!", "ERROR")
        save_screenshot(page, "no_join_interface")
        # Fallback: تلاش با hash تغییر
        log("  تلاش fallback: hash تغییر...")
        try:
            page.evaluate(f"""() => {{
                window.location.hash = '#/im?meet={meet_code}';
            }}""")
            time.sleep(10)
            join_ok = wait_for_join_interface(page, timeout_sec=30)
        except Exception:
            pass
        if not join_ok:
            try:
                page.close()
            except Exception:
                pass
            return None
    
    save_screenshot(page, "join_interface_ready")
    
    # v15 KEY: کلیک روی "شروع ویدیو" قبل از ورود
    click_video_start_button(page)
    time.sleep(3)
    save_screenshot(page, "after_video_start_click")
    
    # کلیک روی "ورود به تماس"
    if not click_join_button(page):
        log("  کلیک ورود ناموفق!", "ERROR")
        save_screenshot(page, "join_click_failed")
        try:
            page.close()
        except Exception:
            pass
        return None
    
    time.sleep(5)
    save_screenshot(page, "after_join_click")
    
    # منتظر WebRTC
    log("  منتظر اتصال WebRTC...")
    pc_count = wait_for_peer_connections(page, timeout_sec=60, min_pc_count=1)
    log(f"  وضعیت peer connections: {pc_count}")
    
    # بررسی sender status
    status = check_sender_status(page)
    if status:
        log(f"  وضعیت senders: {json.dumps(status, ensure_ascii=False)}")
        has_video_sender = any(s.get('kind') == 'video' for s in status.get('senders', []))
        if not has_video_sender:
            log("  هیچ video sender یافت نشد — تلاش برای فعال‌سازی ویدیو...")
            add_video_transceiver(page)
            time.sleep(3)
    
    return page


def inject_media_patch(page, media_patch_js):
    try:
        already = page.evaluate("() => !!window._mediaPatched")
        if already:
            return True
        page.evaluate(media_patch_js)
        return True
    except Exception as e:
        log(f"  خطا در تزریق media patch: {e}", "WARN")
        return False


def inject_hls(page, hls_inject_js, hls_url):
    try:
        already = page.evaluate("() => !!window._hlsInstance")
        if already:
            log("  HLS قبلاً تزریق شده")
            return True
        page.evaluate(f"window._HLS_URL = {json.dumps(hls_url)}")
        result = page.evaluate(hls_inject_js)
        log(f"  نتیجه تزریق HLS: {str(result)[:200]}")
        return True
    except Exception as e:
        log(f"  خطا در تزریق HLS: {e}", "WARN")
        return False


def start_live(args):
    """اجرای کامل فلو لایو ۲۴/۷."""
    from playwright.sync_api import sync_playwright

    opened_pages = []
    context = None
    browser = None
    pw = None
    success = False

    try:
        log("=" * 70)
        log("شروع لایو سروش+ ۲۴/۷ (v15)")
        log("=" * 70)
        log(f"HLS URL: {args.hls_url}")
        log(f"Group ID: {args.group_id}")
        log(f"Call Title: {args.call_title}")

        # بارگذاری داده‌ها
        state = load_browser_state()
        if not state:
            return False
        media_patch_js = load_media_patch_js()
        if not media_patch_js:
            return False
        hls_inject_js = load_hls_inject_js()
        if not hls_inject_js:
            return False

        # راه‌اندازی مرورگر
        log("مرحله ۱/۶: راه‌اندازی مرورگر...")
        launch_args = [
            '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
            '--autoplay-policy=no-user-gesture-required',
            '--use-fake-ui-for-media-stream',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=AudioServiceOutOfProcess',
            '--mute-audio=false',
        ]

        use_headed = args.headed
        if use_headed:
            if not start_xvfb():
                use_headed = False

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=not use_headed, args=launch_args)
        log("  مرورگر راه‌اندازی شد")

        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            locale='fa-IR',
            permissions=['camera', 'microphone'],
        )

        # تزریق وضعیت مرورگر
        log("مرحله ۲/۶: تزریق وضعیت مرورگر...")
        cookies = state.get('cookies', [])
        splus_cookies = [c for c in cookies if 'splus' in c.get('domain', '')]
        if splus_cookies:
            try:
                context.add_cookies(splus_cookies)
                log(f"  {len(splus_cookies)} کوکی تزریق شد")
            except Exception as e:
                log(f"  خطا در تزریق کوکی‌ها: {e}", "WARN")

        # localStorage
        ls_items = []
        for origin_data in state.get('origins', []):
            origin = origin_data.get('origin', '')
            if 'splus' not in origin:
                continue
            for item in origin_data.get('localStorage', []):
                ls_items.append((item['name'], item['value']))

        if ls_items:
            ls_parts = []
            for name, value in ls_items:
                ls_parts.append(f"localStorage.setItem({json.dumps(name)}, {json.dumps(value)});")
            ls_script = "try { " + " ".join(ls_parts) + " } catch(e) {}"
            context.add_init_script(ls_script)
            log(f"  {len(ls_items)} کلید localStorage تزریق شد")
        else:
            log("  هشدار: هیچ کلید localStorage یافت نشد!", "WARN")

        # تزریق media patch از init_script
        context.add_init_script(media_patch_js)
        log("  init_script برای media patch ثبت شد")

        # باز کردن سروش+ اصلی
        log("مرحله ۳/۶: باز کردن سروش+ و یافتن تماس...")
        main_page = context.new_page()
        opened_pages.append(main_page)
        main_page.goto(SPLUS_WEB_URL, wait_until='domcontentloaded', timeout=60000)

        # منتظر SPA
        if not wait_for_spa_load(main_page, timeout_sec=60):
            log("  SPA بارگذاری نشد، ادامه...", "WARN")
            save_screenshot(main_page, "spa_not_loaded")

        time.sleep(3)

        # ورود به گروه
        log("  ورود به گروه...")
        if not click_group(main_page, args.group_id):
            log("  ورود به گروه ناموفق بود", "ERROR")
            return False

        time.sleep(5)

        # scroll down
        try:
            main_page.evaluate("""() => {
                const msgList = document.querySelector('.MessageList, .chat-list');
                if (msgList) msgList.scrollTop = msgList.scrollHeight;
            }""")
            time.sleep(2)
        except Exception:
            pass

        # یافتن meet code موجود
        existing_meet_code = find_existing_meet_link(main_page)
        call_page = None
        meet_code = None

        if existing_meet_code:
            log(f"  ★ تماس موجود یافت شد: {existing_meet_code}")
            meet_code = existing_meet_code
        else:
            log("  تماس موجود یافت نشد — ایجاد تماس جدید...")
            # ایجاد تماس جدید
            new_meet_code, popup_page = create_new_call(main_page, context, args.call_title)
            if new_meet_code:
                meet_code = new_meet_code
                if popup_page:
                    call_page = popup_page
                    if call_page not in opened_pages:
                        opened_pages.append(call_page)
            else:
                log("  ایجاد تماس ناموفق بود", "ERROR")
                save_screenshot(main_page, "create_call_failed")
                return False

        # v15 KEY: ورود به تماس با ناوبری مستقیم
        if meet_code and call_page is None:
            log(f"مرحله ۴/۶: ورود به تماس با ناوبری مستقیم ({meet_code})...")
            call_page = join_call_via_direct_url(context, meet_code, media_patch_js)
            if call_page is None:
                log("  ورود به تماس ناموفق بود!", "ERROR")
                return False
            if call_page not in opened_pages:
                opened_pages.append(call_page)

        # اگر call_page از طریق popup به دست آمده
        if call_page is None:
            log("  هیچ صفحه تماسی ایجاد نشد!", "ERROR")
            return False

        # منتظر peer connections
        log("مرحله ۵/۶: تزریق HLS و فعال‌سازی لایو...")
        pc_count = wait_for_peer_connections(call_page, timeout_sec=30, min_pc_count=1)
        log(f"  وضعیت peer connections: {pc_count}")

        # بررسی و فعال‌سازی ویدیو
        status = check_sender_status(call_page)
        if status:
            log(f"  وضعیت senders قبل از تزریق: {json.dumps(status, ensure_ascii=False)}")
            has_video = any(s.get('kind') == 'video' for s in status.get('senders', []))
            if not has_video:
                log("  ★ هیچ video sender — تلاش فعال‌سازی...")
                add_video_transceiver(call_page)
                time.sleep(3)

        # تزریق media patch دوباره
        inject_media_patch(call_page, media_patch_js)
        time.sleep(1)

        # تزریق HLS
        inject_hls(call_page, hls_inject_js, args.hls_url)
        time.sleep(10)

        # منتظر اتصال HLS به peer connections
        log("مرحله ۶/۶: منتظر اتصال HLS...")
        for i in range(30):
            if is_shutdown_requested():
                break
            time.sleep(2)
            try:
                hls_status = call_page.evaluate(r"""() => {
                    const pcCount = window._allPCs ? window._allPCs.size : 0;
                    let liveCount = 0;
                    if (window._allPCs) {
                        for (const pc of window._allPCs) {
                            for (const s of pc.getSenders()) {
                                const trackId = s.track ? s.track.id : null;
                                const liveVideoId = window._liveVideoTrack ? window._liveVideoTrack.id : null;
                                const liveAudioId = window._liveAudioTrack ? window._liveAudioTrack.id : null;
                                if (trackId === liveVideoId || trackId === liveAudioId) liveCount++;
                            }
                        }
                    }
                    return {
                        pcCount: pcCount,
                        hlsReady: !!window._hlsInstance,
                        streamReady: !!window._m3u8Stream,
                        liveCount: liveCount,
                    };
                }""")
                if (i % 5 == 0):
                    log(f"  {(i+1)*2}s: {json.dumps(hls_status, ensure_ascii=False)}")
                if hls_status.get('liveCount', 0) >= 2:
                    log("  ★ هر دو audio و video tracks متصل شدند!")
                    break
                if hls_status.get('liveCount', 0) >= 1 and i > 15:
                    log("  ★ حداقل یک track متصل شد — ادامه...")
                    break
            except Exception:
                pass

        # ذخیره اسکرین‌شات نهایی
        save_screenshot(call_page, "live_started")
        save_html(call_page, "live_started")

        # بررسی وضعیت نهایی
        try:
            final_status = call_page.evaluate(r"""() => {
                const results = [];
                results.push('videos:' + document.querySelectorAll('video').length);
                results.push('mediaPatched:' + (window._mediaPatched || false));
                results.push('hlsReady:' + !!window._hlsInstance);
                results.push('streamReady:' + !!window._m3u8Stream);
                results.push('pcCount:' + (window._allPCs ? window._allPCs.size : 0));
                let audioSender = 0, videoSender = 0, liveSender = 0;
                if (window._allPCs) {
                    for (const pc of window._allPCs) {
                        for (const s of pc.getSenders()) {
                            if (s.track && s.track.kind === 'audio') audioSender++;
                            if (s.track && s.track.kind === 'video') videoSender++;
                            const liveVideoId = window._liveVideoTrack ? window._liveVideoTrack.id : null;
                            const liveAudioId = window._liveAudioTrack ? window._liveAudioTrack.id : null;
                            if (s.track && (s.track.id === liveVideoId || s.track.id === liveAudioId)) liveSender++;
                        }
                    }
                }
                results.push('audio$audioSenders:' + audioSender);
                results.push('videoSenders:' + videoSender);
                results.push('liveSenders:' + liveSender);
                return results.join('|');
            }""")
            log(f"  وضعیت نهایی: {final_status}")
        except Exception as e:
            log(f"  خطا در بررسی وضعیت: {e}", "WARN")

        pid = os.getpid()
        log("=" * 70)
        log("=== لایو فعال شد ===")
        log(f"PID: {pid} | HLS: {args.hls_url} | گروه: {args.group_id}")
        log(f"صفحه تماس: {call_page.url}")
        log("=" * 70)

        success = True

        if not args.once:
            # Keep alive loop
            log("شروع لوپ نگهداری ۲۴/۷...")
            check_count = 0
            consecutive_failures = 0
            while not is_shutdown_requested():
                time.sleep(30)
                check_count += 1
                try:
                    if call_page.is_closed():
                        log("  صفحه تماس بسته شد!", "WARN")
                        consecutive_failures += 1
                        if consecutive_failures >= 3:
                            break
                        continue

                    # Re-inject HLS if needed
                    hls_alive = call_page.evaluate("() => !!window._hlsInstance && !window._hlsInstance.destroyed")
                    if not hls_alive:
                        log("  HLS از بین رفته — تزریق مجدد...")
                        inject_hls(call_page, hls_inject_js, args.hls_url)
                        time.sleep(5)

                    # Replace tracks
                    call_page.evaluate("() => { if (window._replaceAllPCTracks) window._replaceAllPCTracks(); }")

                    if check_count % 10 == 0:
                        log(f"  بررسی #{check_count}: لایو فعال است")

                    consecutive_failures = 0
                except Exception as e:
                    log(f"  خطا در نگهداری: {e}", "WARN")
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        break

        return True

    except Exception as e:
        log(f"خطای کلی در start_live: {e}", "ERROR")
        log(traceback.format_exc(), "ERROR")
        return False

    finally:
        if not success or args.once:
            log("پاک‌سازی منابع...")
            for p in opened_pages:
                try:
                    if not p.is_closed():
                        p.close()
                except Exception:
                    pass
            try:
                if context:
                    context.close()
            except Exception:
                pass
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            try:
                if pw:
                    pw.stop()
            except Exception:
                pass
            stop_xvfb()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SPlus 24/7 Live Stream Manager v15')
    parser.add_argument('--headed', action='store_true', help='Run in headed mode')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--hls-url', default=DEFAULT_HLS_URL, help='HLS stream URL')
    parser.add_argument('--group-id', default=DEFAULT_GROUP_ID, help='Group ID')
    parser.add_argument('--call-title', default=DEFAULT_CALL_TITLE, help='Call title')
    parser.add_argument('--check', action='store_true', help='Check dependencies only')
    args = parser.parse_args()

    install_signal_handlers()
    _init_logger()
    _ensure_debug_dir()

    if args.check:
        log("بررسی وابستگی‌ها...")
        try:
            from playwright.sync_api import sync_playwright
            log("  Playwright OK")
        except ImportError:
            log("  Playwright نصب نیست!", "ERROR")
            return 1

        state = load_browser_state()
        if state:
            log("  وضعیت مرورگر OK")
        else:
            log("  وضعیت مرورگر نامعتبر!", "ERROR")
            return 1

        mp = load_media_patch_js()
        if mp:
            log("  media_patch_js OK")
        else:
            log("  media_patch_js نامعتبر!", "ERROR")
            return 1

        hi = load_hls_inject_js()
        if hi:
            log("  hls_inject_js OK")
        else:
            log("  hls_inject_js نامعتبر!", "ERROR")
            return 1

        log("  همه بررسی‌ها OK")
        return 0

    # Run with retry
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        log(f"=== تلاش {attempt}/{max_attempts} ===")
        if start_live(args):
            log("  لایو با موفقیت اجرا شد")
            return 0
        if attempt < max_attempts:
            wait_time = 10 * attempt + random.randint(0, 5)
            log(f"تلاش ناموفق. صبر {wait_time} ثانیه قبل از تلاش مجدد...")
            time.sleep(wait_time)

    log(f"همه {max_attempts} تلاش ناموفق بود", "ERROR")
    return 1


if __name__ == '__main__':
    sys.exit(main())
