#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  SPlus 24/7 Live Stream Manager - v14 (Remote BROWSER_STATE)
  سروش+ لایو ۲۴/۷ - نسخه ۱۴ — BROWSER_STATE از راه دور
================================================================================
  تغییرات کلیدی نسخه ۱۴:
  ۱. حذف BROWSER_STATE_B64 توکار از داخل اسکریپت — اکنون در هر اجرا
     از ریپو Molavi12/Text روی GitHub دریافت می‌شود
     (raw.githubusercontent.com/Molavi12/Text/main/BROWSER_STATE_B64.txt)
  ۲. کش محلی BROWSER_STATE_B64.local.txt برای بازیابی در صورت قطع اینترنت
  ۳. پیام خطای واضح اگر فایل در ریپو موجود نباشد
  ۴. سایر بخش‌ها بدون تغییر نسبت به v13
  —
  تغییرات کلیدی نسخه ۱۳:
  ۱. رفع مشکل صدا — مشکل اصلی: Object.defineProperty روی sender.track باعث
     می‌شد replaceTrack واقعی هرگز فراخوانی نشود
  ۲. media_patch v13: حذف getter override، استفاده از WeakMap برای رهگیری
     track واقعی داخلی، فراخوانی مستقیم origReplaceTrack
  ۳. hls_inject v13: استراتژی اول createMediaElementSource (Web Audio API)
     به جای captureStream — مطمئن‌تر در حالت headless
  ۴. حذف --use-fake-device-for-media-stream و اضافه کردن
     --disable-features=AudioServiceOutOfProcess
  ۵. سشن و تمام داده‌ها مستقیماً در اسکریپت جاسازی شده
  ۶. لاگ‌گذاری دقیق و اسکرین‌شات در هر مرحله
================================================================================
"""
import os, sys, time, json, re, zlib, base64, traceback, signal, subprocess
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
LOG_FILE = SCRIPT_DIR / "splus_v14.log"
PID_FILE = SCRIPT_DIR / "splus_v14.pid"
DEBUG_DIR = SCRIPT_DIR / "splus_v14_debug"

# ============================================================================
# دریافت BROWSER_STATE_B64 از ریپو Molavi12/Text در زمان اجرا
# ============================================================================
# (تعریف تابع fetch_browser_state_b64 و مقداردهی BROWSER_STATE_B64 در ادامه‌ی
#  همین بخش می‌آید — پس از تعریف ثابت‌های مربوط به URL و فایل کش)

# ============================================================================
# داده‌های جاسازی‌شده
# ============================================================================
# این داده‌ها از فایل splus-auth-state.json استخراج شده‌اند
# و شامل تمام اطلاعات سشن برای اتصال بدون کد تأیید هستند
# ----------------------------------------------------------------------------
# BROWSER_STATE_B64 از ریپو Molavi12/Text روی GitHub گرفته می‌شود.
# داخل خود اسکریپت دیگر متن BROWSER_STATE وجود ندارد؛ در هر اجرا از این
# آدرس دانلود می‌شود:
#     https://raw.githubusercontent.com/Molavi12/Text/main/BROWSER_STATE_B64.txt
# اگر شاخه main نبود، master هم امتحان می‌شود.
# ----------------------------------------------------------------------------
BROWSER_STATE_REPO_RAW_URLS = [
    "https://raw.githubusercontent.com/Molavi12/Text/main/BROWSER_STATE_B64.txt",
    "https://raw.githubusercontent.com/Molavi12/Text/master/BROWSER_STATE_B64.txt",
]
BROWSER_STATE_FALLBACK_FILE = SCRIPT_DIR / "BROWSER_STATE_B64.local.txt"


def _log_fetch(msg: str) -> None:
    """لاگ ساده برای مرحله‌ی fetch — چون LOG_FILE هنوز باز نشده ممکن است."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass
    print(msg, flush=True)


def fetch_browser_state_b64() -> str:
    """
    BROWSER_STATE_B64 را از ریپو Molavi12/Text می‌گیرد.
    در صورت شکست، نسخه‌ی کش‌شده‌ی محلی (BROWSER_STATE_B64.local.txt)
    را در صورت وجود استفاده می‌کند.
    """
    last_err = None
    for url in BROWSER_STATE_REPO_RAW_URLS:
        try:
            _log_fetch(f"[browser-state] downloading from {url} ...")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "splus-live-v14/1.0 (+python urllib)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                data = resp.read().decode("utf-8", errors="replace").strip()
            if not data or len(data) < 1000:
                raise RuntimeError(f"response too short: {len(data)} chars")
            # کش محلی برای بازیابی در صورت قطع اینترنت در اجراهای بعدی
            try:
                BROWSER_STATE_FALLBACK_FILE.write_text(data, encoding="utf-8")
            except Exception as e:
                _log_fetch(f"[browser-state] WARN: cannot write local cache: {e}")
            _log_fetch(
                f"[browser-state] OK: {len(data)} chars from {url}"
            )
            return data
        except Exception as e:
            last_err = e
            _log_fetch(f"[browser-state] FAIL {url}: {e}")

    # اگر همه URLها شکست خوردند، نسخه‌ی کش‌شده‌ی محلی را استفاده کن
    if BROWSER_STATE_FALLBACK_FILE.exists():
        cached = BROWSER_STATE_FALLBACK_FILE.read_text(encoding="utf-8").strip()
        if cached:
            _log_fetch(
                f"[browser-state] Using LOCAL cache: "
                f"{BROWSER_STATE_FALLBACK_FILE} ({len(cached)} chars)"
            )
            return cached

    # شکست کامل
    raise RuntimeError(
        "BROWSER_STATE_B64 از ریپو Molavi12/Text قابل دریافت نیست. "
        f"آخرین خطا: {last_err}. "
        "لطفاً مطمئن شو فایل BROWSER_STATE_B64.txt در ریپو "
        "https://github.com/Molavi12/Text وجود دارد."
    )

# فراخوانی تابع در زمان import — مقدار BROWSER_STATE_B64 را از ریپو می‌گیرد
BROWSER_STATE_B64 = fetch_browser_state_b64()
MEDIA_PATCH_B64 = """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"""
HLS_INJECT_B64 = """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"""

# ============================================================================
# توابع کمکی
# ============================================================================
def _decode_b64zlib(b64_str):
    """دیکد base64 + zlib."""
    raw = base64.b64decode(b64_str.strip())
    return zlib.decompress(raw)

def _init_logger():
    """راه‌اندازی لاگر."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Clear log file
    with open(LOG_FILE, 'w') as f:
        f.write('')

def log(msg, level="INFO"):
    """لاگ پیام."""
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

def _ensure_debug_dir():
    """ایجاد پوشه دیباگ."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

def save_screenshot(page, name):
    """ذخیره اسکرین‌شات."""
    _ensure_debug_dir()
    try:
        path = DEBUG_DIR / f"splus_{name}.png"
        page.screenshot(path=str(path))
        log(f"  اسکرین‌شات ذخیره شد: {path}")
    except Exception as e:
        log(f"  خطا در اسکرین‌شات: {e}", "WARN")

def save_html(page, name):
    """ذخیره HTML صفحه."""
    _ensure_debug_dir()
    try:
        path = DEBUG_DIR / f"splus_{name}.html"
        content = page.content()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        log(f"  خطا در ذخیره HTML: {e}", "WARN")

def load_browser_state():
    """بارگذاری وضعیت مرورگر از ثابت جاسازی‌شده."""
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
    """بارگذاری اسکریپت پچ مدیا."""
    b64 = MEDIA_PATCH_B64
    if not b64 or b64.startswith('__'):
        log("هیچ داده MEDIA_PATCH جاسازی نشده!", "ERROR")
        return None
    try:
        raw = _decode_b64zlib(b64)
        js = raw.decode('utf-8')
        log(f"media_patch_js بارگذاری شد ({len(js)} bytes)")
        return js
    except Exception as e:
        log(f"خطا در دیکد MEDIA_PATCH: {e}", "ERROR")
        return None

def load_hls_inject_js():
    """بارگذاری اسکریپت تزریق HLS."""
    b64 = HLS_INJECT_B64
    if not b64 or b64.startswith('__'):
        log("هیچ داده HLS_INJECT جاسازی نشده!", "ERROR")
        return None
    try:
        raw = _decode_b64zlib(b64)
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
    """راه‌اندازی Xvfb برای اجرای headed browser."""
    global _xvfb_process
    # Check if Xvfb is already running
    display = os.environ.get('DISPLAY', '')
    if display and display.startswith(':'):
        log(f"X Server در حال اجرا: DISPLAY={display}")
        return True

    # Check if Xvfb is available
    try:
        result = subprocess.run(['which', 'Xvfb'], capture_output=True, text=True)
        if result.returncode != 0:
            log("Xvfb یافت نشد — استفاده از حالت headless", "WARN")
            return False
    except Exception:
        log("Xvfb یافت نشد — استفاده از حالت headless", "WARN")
        return False

    # Start Xvfb
    try:
        display_num = 99
        _xvfb_process = subprocess.Popen(
            ['Xvfb', f':{display_num}', '-screen', '0', '1280x720x24', '-ac'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        if _xvfb_process.poll() is not None:
            log("Xvfb شروع نشد!", "WARN")
            return False
        os.environ['DISPLAY'] = f':{display_num}'
        log(f"Xvfb راه‌اندازی شد: DISPLAY=:{display_num}")
        return True
    except Exception as e:
        log(f"خطا در راه‌اندازی Xvfb: {e}", "WARN")
        return False

def stop_xvfb():
    """توقف Xvfb."""
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
# Main Logic
# ============================================================================
def wait_for_spa_load(page, timeout_sec=60):
    """منتظر بارگذاری SPA (chat list ظاهر شود)."""
    for i in range(timeout_sec // 2):
        if is_shutdown_requested():
            return False
        time.sleep(2)
        try:
            has_chat = page.evaluate("() => !!document.querySelector('.chat-list, .ListItem.Chat')")
            if has_chat:
                log(f"  SPA بارگذاری شد بعد از {(i+1)*2} ثانیه")
                return True
            if i % 5 == 0:
                log(f"  منتظر SPA... {(i+1)*2} ثانیه")
        except Exception as e:
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
                return True
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
                let parent = link;
                let timestamp = null;
                for (let i = 0; i < 5 && parent; i++) {
                    const timeEl = parent.querySelector('.message-time, .time');
                    if (timeEl) {
                        timestamp = timeEl.textContent.trim();
                        break;
                    }
                    parent = parent.parentElement;
                }
                result.push({code: code, timestamp: timestamp, href: href});
            }
            return result;
        }""")
        if not links_info:
            return None
        valid = [l for l in links_info if re.match(r'^[a-z]{3}-[a-z]{3}-[a-z]{3}$', l.get('code', ''))]
        if not valid:
            return None
        last = valid[-1]
        log(f"  آخرین meet code یافت شده: {last['code']}")
        return last['code']
    except Exception as e:
        log(f"  خطا در جستجوی meet link: {e}", "WARN")
        return None

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
            if i % 5 == 0:
                log(f"  منتظر peer connections... {(i+1)*2} ثانیه (pc_count={pc_count})")
        except Exception:
            pass
    log(f"  هیچ peer connection یافت نشد بعد از {timeout_sec} ثانیه", "WARN")
    return 0

def click_camera_button(page):
    """کلیک روی دکمه دوربین/ویدیو در تماس برای فعال‌سازی ویدیو."""
    log("  تلاش برای کلیک دکمه دوربین/ویدیو در تماس...")
    try:
        # Try multiple selectors for camera/video button
        result = page.evaluate(r"""() => {
            // Look for camera/video toggle buttons
            const btns = document.querySelectorAll('button, [role="button"]');
            for (const btn of btns) {
                const t = (btn.textContent || '').trim();
                const ariaLabel = btn.getAttribute('aria-label') || '';
                const cls = btn.className || '';
                const title = btn.getAttribute('title') || '';
                // Check for camera/video related text
                if (t.includes('دوربین') || t.includes('ویدیو') || t.includes('Camera') || t.includes('Video') ||
                    ariaLabel.includes('دوربین') || ariaLabel.includes('ویدیو') || ariaLabel.includes('Camera') || ariaLabel.includes('Video') ||
                    title.includes('دوربین') || title.includes('ویدیو') || title.includes('Camera') || title.includes('Video')) {
                    // Check if it's not already active (muted)
                    const isMuted = cls.includes('muted') || cls.includes('disabled') || btn.getAttribute('aria-pressed') === 'false';
                    btn.click();
                    return {text: t, ariaLabel: ariaLabel, cls: cls.substring(0, 80), wasMuted: isMuted};
                }
            }
            // Also check for SVG icons (camera icon)
            const svgs = document.querySelectorAll('svg, [class*="icon"]');
            for (const svg of svgs) {
                const parent = svg.closest('button, [role="button"]');
                if (parent) {
                    const ariaLabel = parent.getAttribute('aria-label') || '';
                    const title = parent.getAttribute('title') || '';
                    if (ariaLabel.includes('Camera') || ariaLabel.includes('Video') || 
                        ariaLabel.includes('دوربین') || ariaLabel.includes('ویدیو') ||
                        title.includes('Camera') || title.includes('Video')) {
                        parent.click();
                        return {text: ariaLabel || title, cls: 'svg-icon-button', wasMuted: false};
                    }
                }
            }
            return null;
        }""")
        if result:
            log(f"  دکمه دوربین/ویدیو کلیک شد: {result}")
            return True
        else:
            log("  دکمه دوربین/ویدیو یافت نشد", "WARN")
            return False
    except Exception as e:
        log(f"  خطا در کلیک دکمه دوربین: {e}", "WARN")
        return False

def add_video_transceiver(page):
    """اضافه کردن video transceiver به peer connection در صورت نبود video sender."""
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
                            const sender = pc.addTrack(videoTrack, new MediaStream([videoTrack]));
                            if (window._patchSender) window._patchSender(sender, 'video');
                            added++;
                        } else {
                            // Add transceiver without track
                            const transceiver = pc.addTransceiver('video', {direction: 'sendrecv'});
                            if (transceiver.sender && window._patchSender) {
                                window._patchSender(transceiver.sender, 'video');
                            }
                            added++;
                        }
                    } catch(e) {
                        // Try addTransceiver
                        try {
                            const transceiver = pc.addTransceiver('video', {direction: 'sendrecv'});
                            if (transceiver.sender && window._patchSender) {
                                window._patchSender(transceiver.sender, 'video');
                            }
                            added++;
                        } catch(e2) {}
                    }
                }
            }
            return {added: added, pcCount: window._allPCs.size};
        }""")
        log(f"  نتیجه add_video_transceiver: {result}")
        return result.get('added', 0) > 0
    except Exception as e:
        log(f"  خطا در add_video_transceiver: {e}", "WARN")
        return False

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

def create_new_call(page, context, call_title):
    """ایجاد تماس گروهی جدید."""
    existing_meet_code_before_create = find_existing_meet_link(page)
    log("  کلیک روی 'فعالیت های بیشتر'...")
    try:
        more_btn = page.locator('[aria-label="فعالیت های بیشتر"]')
        if more_btn.count() > 0:
            more_btn.first.click()
            time.sleep(2)
            log("  دکمه فعالیت کلیک شد")
        else:
            log("  دکمه 'فعالیت های بیشتر' یافت نشد!", "ERROR")
            save_screenshot(page, "no_more_button")
            return None
    except Exception as e:
        log(f"  خطا در کلیک دکمه فعالیت: {e}", "ERROR")
        return None

    # کلیک روی "تماس گروهی جدید"
    log("  انتخاب 'تماس گروهی جدید' از منو...")
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
            log("  منو آیتم 'تماس گروهی جدید' یافت نشد!", "ERROR")
            save_screenshot(page, "no_call_menuitem")
            return None
    except Exception as e:
        log(f"  خطا در کلیک منو آیتم: {e}", "ERROR")
        return None

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
                log(f"  modal 'نام تماس' ظاهر شد بعد از {(i+1)*2} ثانیه")
                modal_appeared = True
                break
        except Exception:
            pass

    if not modal_appeared:
        log("  modal 'نام تماس' ظاهر نشد!", "ERROR")
        save_screenshot(page, "no_name_modal")
        return None

    time.sleep(2)

    # پر کردن فیلد نام تماس
    log(f"  پر کردن فیلد نام تماس با '{call_title}'...")
    try:
        name_input = page.locator('[role="dialog"] input, .Modal input').first
        name_input.wait_for(state='visible', timeout=5000)
        name_input.click()
        time.sleep(0.5)
        name_input.fill(call_title)
        time.sleep(1)
        log("  نام تماس پر شد")
    except Exception as e:
        log(f"  خطا در پر کردن نام: {e}", "WARN")

    # کلیک روی "ساخت لینک"
    log("  کلیک روی 'ساخت لینک'...")
    try:
        create_btn = page.locator('button:has-text("ساخت لینک")').first
        create_btn.wait_for(state='visible', timeout=5000)
        create_btn.click(force=True)
        log("  دکمه 'ساخت لینک' کلیک شد")
    except Exception as e:
        log(f"  خطا در کلیک 'ساخت لینک': {e}", "ERROR")
        save_screenshot(page, "no_create_button")
        return None

    # انتظار برای modal "لینک تماس"
    log("  انتظار برای modal 'لینک تماس'...")
    link_modal_appeared = False
    for i in range(15):
        if is_shutdown_requested():
            return None
        time.sleep(2)
        try:
            has_link_modal = page.evaluate("""() => {
                const m = document.querySelector('[role="dialog"], .Modal');
                if (!m) return false;
                const txt = m.textContent || '';
                return txt.includes('لینک تماس') || txt.includes('توجه') || txt.includes('Call Link');
            }""")
            if has_link_modal:
                log(f"  modal 'لینک تماس' ظاهر شد بعد از {(i+1)*2} ثانیه")
                link_modal_appeared = True
                break
        except Exception:
            pass

    if not link_modal_appeared:
        log("  modal 'لینک تماس' ظاهر نشد!", "WARN")
        save_screenshot(page, "no_link_modal")
        # Fallback: check if meet link appeared in chat
        time.sleep(10)
        try:
            page.evaluate("""() => {
                const msgList = document.querySelector('.MessageList, .chat-list');
                if (msgList) msgList.scrollTop = msgList.scrollHeight;
            }""")
            time.sleep(3)
        except Exception:
            pass
        new_meet_code = find_existing_meet_link(page)
        if new_meet_code and new_meet_code != existing_meet_code_before_create:
            log(f"  ★ تماس جدید ایجاد شد با کد: {new_meet_code}")
            return join_existing_call(page, context, new_meet_code)
        return None

    # انتظار برای دکمه "ورود"
    log("  انتظار برای رندر شدن دکمه 'ورود' در modal...")
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
                log(f"  دکمه 'ورود' ظاهر شد بعد از {(i+1)*2} ثانیه")
                break
        except Exception:
            pass

    time.sleep(2)
    save_screenshot(page, "before_join_click")

    # کلیک روی دکمه "ورود"
    log("  کلیک روی دکمه 'ورود'...")
    join_btn = page.locator('button:has-text("ورود")')
    if join_btn.count() == 0:
        log("  دکمه 'ورود' یافت نشد!", "ERROR")
        save_screenshot(page, "no_join_button")
        return None

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
        log("  هیچ popup جدیدی باز نشد — انتظار Call UI در همان صفحه...")
        popup_page = None

    target_page = popup_page if popup_page is not None else page
    save_screenshot(target_page, "after_join_click")

    # ========== v13 KEY CHANGE: Wait for WebRTC peer connections ==========
    # Instead of just checking for call UI, wait for actual WebRTC connections
    log("  v13: منتظر اتصال WebRTC...")
    pc_count = wait_for_peer_connections(target_page, timeout_sec=60, min_pc_count=1)
    
    if pc_count > 0:
        log(f"  ✓ {pc_count} peer connection برقرار شد")
        # Check if we have video senders
        status = check_sender_status(target_page)
        if status:
            log(f"  وضعیت senders: {json.dumps(status, ensure_ascii=False)}")
            has_video_sender = any(s.get('kind') == 'video' for s in status.get('senders', []))
            if not has_video_sender:
                log("  هیچ video sender یافت نشد — تلاش برای فعال‌سازی ویدیو...")
                # Try clicking camera button
                click_camera_button(target_page)
                time.sleep(3)
                # Try adding video transceiver
                add_video_transceiver(target_page)
                time.sleep(2)
        return target_page
    
    # Fallback: try join_existing_call
    log("  WebRTC peer connection برقرار نشد — تلاش fallback...")
    meet_code = find_existing_meet_link(page)
    if meet_code:
        log(f"  تلاش ورود به تماس با کد: {meet_code}")
        fallback_page = join_existing_call(page, context, meet_code)
        if fallback_page is not None:
            return fallback_page

    log("  ایجاد تماس ناموفق بود", "ERROR")
    save_screenshot(page, "create_call_failed_final")
    return None


def join_existing_call(page, context, meet_code):
    """ورود به تماس موجود از طریق landing page."""
    log(f"  ورود به تماس موجود با کد: {meet_code}")
    target_meet_url = f"https://web.splus.ir/#/im?meet={meet_code}"

    # باز کردن صفحه لندینگ
    log("  باز کردن صفحه لندینگ meet...")
    landing_page = None
    try:
        with context.expect_page(timeout=15000) as lp_info:
            page.evaluate(f"window.open('https://splus.ir/meet/{meet_code}', '_blank')")
        landing_page = lp_info.value
        landing_page.wait_for_load_state('domcontentloaded', timeout=30000)
        log(f"  صفحه لندینگ باز شد: {landing_page.url}")
    except Exception as e:
        log(f"  خطا در باز کردن صفحه لندینگ: {e}", "ERROR")
        return None

    time.sleep(3)
    save_screenshot(landing_page, "landing_page")

    # کلیک روی "ورود به تماس در نسخه وب"
    log("  کلیک روی 'ورود به تماس در نسخه وب'...")
    call_page = None
    try:
        web_btn = landing_page.locator('a:has-text("ورود به تماس در نسخه وب"), a:has-text("نسخه وب"), a[href*="web.splus.ir"]')
        if web_btn.count() == 0:
            log("  دکمه 'ورود به تماس در نسخه وب' یافت نشد!", "ERROR")
            save_screenshot(landing_page, "no_web_button")
            try:
                landing_page.close()
            except Exception:
                pass
            return None
        with context.expect_page(timeout=20000) as cp_info:
            web_btn.first.click()
        call_page = cp_info.value
        call_page.wait_for_load_state('domcontentloaded', timeout=30000)
        log(f"  صفحه تماس باز شد: {call_page.url}")
    except Exception as e:
        log(f"  خطا در کلیک دکمه وب: {e}", "ERROR")
        save_screenshot(landing_page, "web_button_click_failed")
        try:
            landing_page.close()
        except Exception:
            pass
        return None

    # بستن صفحه لندینگ
    try:
        landing_page.close()
    except Exception:
        pass

    # اطمینان از hash URL
    try:
        current_hash = call_page.evaluate("() => window.location.hash")
        log(f"  بررسی hash: {current_hash}")
        if not current_hash or 'meet=' not in current_hash:
            log(f"  hash موجود نیست — navigate به {target_meet_url}")
            # روش ۱: goto
            try:
                call_page.goto(target_meet_url, wait_until='domcontentloaded', timeout=30000)
                time.sleep(2)
            except Exception:
                pass
            # روش ۲: pushState
            current_hash = call_page.evaluate("() => window.location.hash")
            if not current_hash or 'meet=' not in current_hash:
                try:
                    call_page.evaluate(f"""() => {{
                        history.pushState({{}}, '', '#/im?meet={meet_code}');
                        window.dispatchEvent(new HashChangeEvent('hashchange'));
                    }}""")
                    time.sleep(3)
                except Exception:
                    pass
            # روش ۳: location.replace
            current_hash = call_page.evaluate("() => window.location.hash")
            if not current_hash or 'meet=' not in current_hash:
                try:
                    call_page.evaluate(f"window.location.replace({json.dumps(target_meet_url)})")
                    time.sleep(3)
                except Exception:
                    pass
    except Exception as e:
        log(f"  خطا در navigate: {e}", "WARN")

    # انتظار برای بارگذاری SPA
    log("  انتظار برای بارگذاری SPA در صفحه تماس...")
    if not wait_for_spa_load(call_page, timeout_sec=40):
        log("  SPA در صفحه تماس بارگذاری نشد", "WARN")

    # دوباره hash را بررسی کن
    try:
        current_hash = call_page.evaluate("() => window.location.hash")
        if not current_hash or 'meet=' not in current_hash:
            log("  hash بعد از SPA load از دست رفت — تلاش با pushState")
            try:
                call_page.evaluate(f"""() => {{
                    history.pushState({{}}, '', '#/im?meet={meet_code}');
                    window.dispatchEvent(new HashChangeEvent('hashchange'));
                    window.location.hash = '#/im?meet={meet_code}';
                }}""")
                time.sleep(5)
            except Exception:
                pass
    except Exception:
        pass

    save_screenshot(call_page, "call_page_after_spa")

    # انتظار برای دکمه "ورود به تماس"
    log("  انتظار برای دکمه 'ورود به تماس' (lk-join-button)...")
    join_btn_appeared = False
    join_btn_text = None
    for i in range(15):
        if is_shutdown_requested():
            return None
        time.sleep(2)
        try:
            btn_info = call_page.evaluate(r"""() => {
                const btns = document.querySelectorAll('.lk-join-button, .lk-button, button');
                const result = [];
                for (const b of btns) {
                    const t = (b.textContent || '').trim();
                    const cls = b.className || '';
                    if (t.includes('ورود به تماس') || t.includes('شروع ویدیو') ||
                        t.includes('Join') || t.includes('Start Video') ||
                        cls.includes('lk-join-button')) {
                        result.push({text: t.substring(0, 60), cls: cls.substring(0, 80)});
                    }
                }
                return result;
            }""")
            if btn_info:
                log(f"  ★ دکمه ورود ظاهر شد بعد از {(i+1)*2} ثانیه:")
                for b in btn_info[:5]:
                    log(f"    text='{b['text']}' cls='{b['cls']}'")
                join_btn_appeared = True
                for b in btn_info:
                    if 'ورود به تماس' in b['text'] or 'lk-join-button' in b['cls']:
                        join_btn_text = b['text']
                        break
                if not join_btn_text and btn_info:
                    join_btn_text = btn_info[0]['text']
                break
            if i % 5 == 0:
                log(f"  منتظر دکمه ورود... {(i+1)*2} ثانیه")
        except Exception:
            pass

    if not join_btn_appeared:
        log("  دکمه 'ورود به تماس' ظاهر نشد", "WARN")
        save_screenshot(call_page, "no_join_btn_existing")
        try:
            call_page.close()
        except Exception:
            pass
        return None

    # کلیک روی دکمه "ورود به تماس"
    log(f"  کلیک روی دکمه '{join_btn_text}'...")
    try:
        clicked = call_page.evaluate(r"""() => {
            let btn = document.querySelector('.lk-join-button');
            if (btn) {
                btn.click();
                return btn.textContent.trim();
            }
            const btns = document.querySelectorAll('.lk-button, button');
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                if (t.includes('ورود به تماس') || t.includes('Join')) {
                    b.click();
                    return t;
                }
            }
            btn = document.querySelector('.lk-button');
            if (btn) {
                btn.click();
                return btn.textContent.trim();
            }
            return null;
        }""")
        if clicked:
            log(f"  دکمه کلیک شد: {clicked}")
        else:
            log("  هیچ دکمه‌ای یافت نشد!", "ERROR")
            try:
                call_page.close()
            except Exception:
                pass
            return None
    except Exception as e:
        log(f"  خطا در کلیک دکمه ورود: {e}", "ERROR")
        try:
            call_page.close()
        except Exception:
            pass
        return None

    save_screenshot(call_page, "after_join_btn_click")

    # ========== v13 KEY CHANGE: Wait for WebRTC peer connections ==========
    log("  v13: منتظر اتصال WebRTC...")
    pc_count = wait_for_peer_connections(call_page, timeout_sec=60, min_pc_count=1)

    if pc_count > 0:
        log(f"  ✓ {pc_count} peer connection برقرار شد")
        # Check sender status
        status = check_sender_status(call_page)
        if status:
            log(f"  وضعیت senders: {json.dumps(status, ensure_ascii=False)}")
            has_video_sender = any(s.get('kind') == 'video' for s in status.get('senders', []))
            if not has_video_sender:
                log("  هیچ video sender یافت نشد — تلاش برای فعال‌سازی ویدیو...")
                # Click camera button
                click_camera_button(call_page)
                time.sleep(3)
                # Add video transceiver
                add_video_transceiver(call_page)
                time.sleep(2)
        return call_page

    log("  Call UI در صفحه تماس ظاهر نشد!", "ERROR")
    save_screenshot(call_page, "no_call_ui_existing")
    try:
        call_page.close()
    except Exception:
        pass
    return None


def inject_media_patch(page, media_patch_js):
    """تزریق پچ مدیا."""
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
    """تزریق استریم HLS."""
    try:
        already = page.evaluate("() => !!window._hlsInstance")
        if already:
            log("  استریم HLS قبلاً تزریق شده")
            return True
        page.evaluate(f"window._HLS_URL = {json.dumps(hls_url)}")
        result = page.evaluate(hls_inject_js)
        log(f"  نتیجه تزریق HLS: {result}")
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
        log("شروع لایو سروش+ ۲۴/۷ (v13)")
        log("=" * 70)
        log(f"HLS URL: {args.hls_url}")
        log(f"Group ID: {args.group_id}")
        log(f"Call Title: {args.call_title}")
        log(f"Headed: {args.headed}")
        log(f"Once: {args.once}")

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
        log("مرحله ۱/۷: راه‌اندازی مرورگر...")
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
            # Try Xvfb
            if not start_xvfb():
                log("  Xvfb در دسترس نیست — استفاده از حالت headless", "WARN")
                use_headed = False

        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=not use_headed,
            args=launch_args,
        )
        log("  مرورگر راه‌اندازی شد")

        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            locale='fa-IR',
            permissions=['camera', 'microphone'],
        )

        # تزریق وضعیت مرورگر
        log("مرحله ۲/۷: تزریق وضعیت مرورگر...")
        cookies = state.get('cookies', [])
        splus_cookies = [c for c in cookies if 'splus.ir' in c.get('domain', '')]
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
            if 'splus.ir' not in origin:
                continue
            for item in origin_data.get('localStorage', []):
                ls_items.append((item['name'], item['value']))

        if ls_items:
            ls_script_parts = []
            for name, value in ls_items:
                ls_script_parts.append(
                    f"localStorage.setItem({json.dumps(name)}, {json.dumps(value)});"
                )
            ls_script = "try { " + " ".join(ls_script_parts) + " } catch(e) {}"
            context.add_init_script(ls_script)
            log(f"  {len(ls_items)} کلید localStorage تزریق شد")
        else:
            log("  هشدار: هیچ کلید localStorage یافت نشد!", "WARN")

        # تزریق media patch از init_script
        context.add_init_script(media_patch_js)
        log("  init_script برای media patch ثبت شد")

        # باز کردن سروش+
        log("مرحله ۳/۷: باز کردن سروش+...")
        page = context.new_page()
        opened_pages.append(page)
        page.goto(SPLUS_WEB_URL, wait_until='domcontentloaded', timeout=60000)

        log("مرحله ۴/۷: منتظر بارگذاری SPA...")
        if not wait_for_spa_load(page, timeout_sec=60):
            log("  SPA بارگذاری نشد، ادامه...", "WARN")
            save_screenshot(page, "spa_not_loaded")

        time.sleep(3)

        # ورود به گروه
        log("مرحله ۵/۷: ورود به گروه...")
        if not click_group(page, args.group_id):
            log("  ورود به گروه ناموفق بود", "ERROR")
            return False

        time.sleep(5)
        # scroll down
        try:
            page.evaluate("""() => {
                const msgList = document.querySelector('.MessageList, .chat-list');
                if (msgList) msgList.scrollTop = msgList.scrollHeight;
            }""")
            time.sleep(2)
        except Exception:
            pass

        # ایجاد یا ورود به تماس
        log("مرحله ۶/۷: ایجاد یا ورود به تماس...")
        existing_meet_code = find_existing_meet_link(page)
        call_page = None

        if existing_meet_code:
            log(f"  ★ تماس موجود یافت شد: {existing_meet_code}")
            log("  تلاش برای ورود به تماس موجود...")
            call_page = join_existing_call(page, context, existing_meet_code)
            if call_page is None:
                log("  ورود به تماس موجود ناموفق بود — ایجاد تماس جدید...", "WARN")
                call_page = create_new_call(page, context, args.call_title)
                if call_page is None:
                    log("  ایجاد تماس جدید هم ناموفق بود", "ERROR")
                    save_screenshot(page, "create_call_failed")
                    return False
        else:
            log("  تماس موجود یافت نشد، ایجاد تماس جدید...")
            call_page = create_new_call(page, context, args.call_title)
            if call_page is None:
                log("  ایجاد تماس ناموفق بود", "ERROR")
                save_screenshot(page, "create_call_failed")
                return False

        if call_page is not page and call_page not in opened_pages:
            opened_pages.append(call_page)

        # ========== v13 KEY: Wait for WebRTC + Video Sender ==========
        log("مرحله ۷/۷: تزریق HLS و فعال‌سازی لایو...")
        
        # First, wait for peer connections to be established
        pc_count = wait_for_peer_connections(call_page, timeout_sec=30, min_pc_count=1)
        log(f"  وضعیت peer connections: {pc_count}")
        
        # Check sender status
        status = check_sender_status(call_page)
        if status:
            log(f"  وضعیت senders قبل از تزریق: {json.dumps(status, ensure_ascii=False)}")
            has_video_sender = any(s.get('kind') == 'video' for s in status.get('senders', []))
            if not has_video_sender:
                log("  ★ هیچ video sender یافت نشد — تلاش برای فعال‌سازی ویدیو...")
                # Click camera button
                click_camera_button(call_page)
                time.sleep(5)
                # Check again
                status2 = check_sender_status(call_page)
                if status2:
                    log(f"  وضعیت senders بعد از کلیک دوربین: {json.dumps(status2, ensure_ascii=False)}")
                    has_video_sender2 = any(s.get('kind') == 'video' for s in status2.get('senders', []))
                    if not has_video_sender2:
                        log("  هنوز video sender وجود ندارد — اضافه کردن video transceiver...")
                        add_video_transceiver(call_page)
                        time.sleep(3)

        # تزریق media patch دوباره
        inject_media_patch(call_page, media_patch_js)
        time.sleep(1)

        # تزریق HLS
        inject_hls(call_page, hls_inject_js, args.hls_url)
        time.sleep(10)  # بیشتر صبر کنیم تا HLS آماده شود

        # ========== v13: Wait for HLS to connect to PCs ==========
        log("  منتظر اتصال HLS به peer connections...")
        for i in range(30):  # 60 seconds
            if is_shutdown_requested():
                break
            time.sleep(2)
            try:
                hls_status = call_page.evaluate(r"""() => {
                    const pcCount = window._allPCs ? window._allPCs.size : 0;
                    let senderInfo = [];
                    let patchedCount = 0;
                    let liveCount = 0;
                    if (window._allPCs) {
                        for (const pc of window._allPCs) {
                            for (const s of pc.getSenders()) {
                                const trackId = s.track ? s.track.id : null;
                                const liveVideoId = window._liveVideoTrack ? window._liveVideoTrack.id : null;
                                const liveAudioId = window._liveAudioTrack ? window._liveAudioTrack.id : null;
                                const isLive = trackId === liveVideoId || trackId === liveAudioId;
                                if (isLive) liveCount++;
                                if (window._patchedSenders && window._patchedSenders.has(s)) patchedCount++;
                                senderInfo.push({
                                    kind: s.track ? s.track.kind : 'none',
                                    isLive: isLive,
                                    isPatched: window._patchedSenders ? window._patchedSenders.has(s) : false,
                                });
                            }
                        }
                    }
                    return {
                        pcCount: pcCount,
                        hlsReady: !!window._hlsInstance,
                        streamReady: !!window._m3u8Stream,
                        patchedCount: patchedCount,
                        liveCount: liveCount,
                        senderTotal: senderInfo.length,
                        senders: senderInfo.slice(0, 10),
                    };
                }""")
                if (i % 5 == 0):
                    log(f"  {(i+1)*2} ثانیه: {json.dumps(hls_status, ensure_ascii=False)}")
                if hls_status.get('liveCount', 0) >= 2:
                    log(f"  ★ هر دو audio و video tracks به peer connection متصل شدند!")
                    break
                if hls_status.get('liveCount', 0) >= 1 and i > 15:
                    log(f"  ★ حداقل یک track متصل شد — ادامه...")
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
                results.push('canvases:' + document.querySelectorAll('canvas').length);
                results.push('mediaPatched:' + (window._mediaPatched || false));
                results.push('hlsReady:' + !!window._hlsInstance);
                results.push('streamReady:' + !!window._m3u8Stream);
                results.push('pcCount:' + (window._allPCs ? window._allPCs.size : 0));
                // Check sender status
                let audioSender = 0, videoSender = 0, patchedSender = 0, liveSender = 0;
                if (window._allPCs) {
                    for (const pc of window._allPCs) {
                        for (const s of pc.getSenders()) {
                            if (s.track && s.track.kind === 'audio') audioSender++;
                            if (s.track && s.track.kind === 'video') videoSender++;
                            if (window._patchedSenders && window._patchedSenders.has(s)) patchedSender++;
                            const liveVideoId = window._liveVideoTrack ? window._liveVideoTrack.id : null;
                            const liveAudioId = window._liveAudioTrack ? window._liveAudioTrack.id : null;
                            if (s.track && (s.track.id === liveVideoId || s.track.id === liveAudioId)) liveSender++;
                        }
                    }
                }
                results.push('audioSenders:' + audioSender);
                results.push('videoSenders:' + videoSender);
                results.push('patchedSenders:' + patchedSender);
                results.push('liveSenders:' + liveSender);
                results.push('url:' + window.location.href);
                results.push('hash:' + window.location.hash);
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
                    # Check if call page is still alive
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
    parser = argparse.ArgumentParser(description='SPlus 24/7 Live Stream Manager v13')
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
            log("✓ Playwright قابل ایمپورت است")
        except ImportError:
            log("✗ Playwright نصب نیست!", "ERROR")
            return 1
        
        state = load_browser_state()
        if state:
            log(f"✓ وضعیت مرورگر بارگذاری شد")
        else:
            log("✗ وضعیت مرورگر بارگذاری نشد!", "ERROR")
            return 1
        
        mp = load_media_patch_js()
        if mp:
            log(f"✓ media_patch_js بارگذاری شد")
        else:
            log("✗ media_patch_js بارگذاری نشد!", "ERROR")
            return 1
        
        hi = load_hls_inject_js()
        if hi:
            log(f"✓ hls_inject_js بارگذاری شد")
        else:
            log("✗ hls_inject_js بارگذاری نشد!", "ERROR")
            return 1
        
        log("✓ همه بررسی‌ها با موفقیت انجام شد")
        return 0

    # Run with retry
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        log(f"=== تلاش {attempt}/{max_attempts} ===")
        if start_live(args):
            log("✓ لایو با موفقیت اجرا شد")
            return 0
        if attempt < max_attempts:
            wait_time = 10 * attempt
            log(f"تلاش ناموفق. صبر {wait_time} ثانیه قبل از تلاش مجدد...")
            time.sleep(wait_time)
    
    log(f"همه {max_attempts} تلاش ناموفق بود", "ERROR")
    return 1


if __name__ == '__main__':
    sys.exit(main())
