#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  SPlus 24/7 Live Stream Manager - v15 (CSP Fix + Direct Nav + Robust Join)
  سروش+ لایو ۲۴/۷ - نسخه ۱۵ — رفع CSP + ناوبری مستقیم + ورود مقاوم
================================================================================
  تغییرات کلیدی نسخه ۱۵ نسبت به v14:
  ۱. رفع مشکل CSP — توقیف و تعدیل هدر Content-Security-Policy با route
     interception در Playwright تا blob: Workers اجازه کار بگیرند
  ۲. غیرفعال کردن enableWorker در HLS.js (چون CSP blob: را مسدود می‌کند)
     و استفاده از setInterval به جای Worker برای keep-alive
  ۳. ناوبری مستقیم به hash URL تماس (#/im?meet=...) به جای لندینگ پیج
  ۴. پر کردن lk-user-choices در localStorage (رفع هشدار LiveKit)
  ۵. فلو ورود مقاوم‌تر: کلیک «شروع ویدیو» سپس «ورود به تماس»
  ۶. بررسی واقعی جریان مدیا بعد از تزریق HLS
  ۷. زمان‌بندی بهتر بین مراحل
  ۸. رفع مشکل ویدیو — اطمینان از فعال بودن video track قبل از ورود
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
LOG_FILE = SCRIPT_DIR / "splus_v15.log"
PID_FILE = SCRIPT_DIR / "splus_v15.pid"
DEBUG_DIR = SCRIPT_DIR / "splus_v15_debug"

# ============================================================================
# دریافت BROWSER_STATE_B64 از ریپو Molavi12/Text در زمان اجرا
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
MEDIA_PATCH_B64 = """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"""
HLS_INJECT_B64 = """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"""

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
        log("Xvfb یافت نشد — استفاده از حالت headless", "WARN")
        return False
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
# v15 NEW: CSP Bypass via Route Interception
# ============================================================================
def install_csp_bypass(context):
    """
    توقیف فقط پاسخ‌های HTML (document) از splus.ir و تعدیل هدر CSP.
    فقط navigation/document requests توقیف می‌شوند؛
    JS/CSS/images بدون تغییر pass-through می‌شوند.
    بدون این، HLS.js نمی‌تواند Web Worker بسازد و استریم کار نمی‌کند.
    """
    def _csp_handler(route):
        request = route.request
        resource_type = request.resource_type
        
        # فقط HTML document requests توقیف شود — JS/CSS/images بدون تغییر عبور کنند
        if resource_type != 'document':
            try:
                route.continue_()
            except Exception:
                pass
            return
        
        try:
            response = route.fetch()
            headers = dict(response.headers)
            
            # Modify CSP to allow blob: workers and inline scripts
            csp = headers.get('content-security-policy', '')
            if csp:
                # Add blob: to script-src
                csp = re.sub(
                    r"script-src([^;]+)",
                    r"script-src\1 blob: data: 'unsafe-inline' 'unsafe-eval'",
                    csp
                )
                # Add blob: to worker-src if exists
                if 'worker-src' in csp:
                    csp = re.sub(
                        r"worker-src([^;]+)",
                        r"worker-src\1 blob: data:",
                        csp
                    )
                else:
                    # Add worker-src directive
                    csp += "; worker-src 'self' blob: data:"
                headers['content-security-policy'] = csp
            
            # Also handle CSP report-only
            csp_ro = headers.get('content-security-policy-report-only', '')
            if csp_ro:
                csp_ro = re.sub(
                    r"script-src([^;]+)",
                    r"script-src\1 blob: data: 'unsafe-inline' 'unsafe-eval'",
                    csp_ro
                )
                headers['content-security-policy-report-only'] = csp_ro
            
            route.fulfill(
                status=response.status,
                headers=headers,
                body=response.body,
            )
        except Exception as e:
            # If interception fails, just continue normally
            try:
                route.continue_()
            except Exception:
                pass
    
    # Intercept only splus.ir requests (not external CDNs)
    context.route("https://web.splus.ir/**", _csp_handler)
    log("  CSP bypass نصب شد (فقط HTML documents از web.splus.ir)")
    return True


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
            has_chat = page.evaluate("() => !!document.querySelector('.chat-list, .ListItem.Chat, .ChatList')")
            if has_chat:
                log(f"  SPA بارگذاری شد بعد از {(i+1)*2} ثانیه")
                return True
            # Also check for call UI (we might be on the meet page)
            has_call_ui = page.evaluate("() => !!document.querySelector('.lk-join-button, .lk-button, [class*=livekit], [class*=call])")
            if has_call_ui:
                log(f"  SPA بارگذاری شد (call UI یافت شد) بعد از {(i+1)*2} ثانیه")
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
                const m = href.match(/\/meet\/([a-z0-9-]+)/);
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
        log(f"  آخرین meet code: {last['code']}")
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


def click_camera_button(page):
    """کلیک روی دکمه دوربین/ویدیو در تماس."""
    log("  تلاش برای کلیک دکمه دوربین/ویدیو در تماس...")
    try:
        result = page.evaluate(r"""() => {
            const btns = document.querySelectorAll('button, [role="button"]');
            for (const btn of btns) {
                const t = (btn.textContent || '').trim();
                const ariaLabel = btn.getAttribute('aria-label') || '';
                const cls = btn.className || '';
                const title = btn.getAttribute('title') || '';
                if (t.includes('دوربین') || t.includes('ویدیو') || t.includes('Camera') || t.includes('Video') ||
                    ariaLabel.includes('دوربین') || ariaLabel.includes('ویدیو') || ariaLabel.includes('Camera') || ariaLabel.includes('Video') ||
                    title.includes('دوربین') || title.includes('ویدیو') || title.includes('Camera') || title.includes('Video')) {
                    const isMuted = cls.includes('muted') || cls.includes('disabled') || btn.getAttribute('aria-pressed') === 'false';
                    btn.click();
                    return {text: t, ariaLabel: ariaLabel, cls: cls.substring(0, 80), wasMuted: isMuted};
                }
            }
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
    """اضافه کردن video transceiver به peer connection."""
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
                            const transceiver = pc.addTransceiver('video', {direction: 'sendrecv'});
                            if (transceiver.sender && window._patchSender) {
                                window._patchSender(transceiver.sender, 'video');
                            }
                            added++;
                        }
                    } catch(e) {
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


# ============================================================================
# v15: Direct Navigation Join Flow
# ============================================================================
def join_call_direct_navigation(page, meet_code):
    """
    ورود به تماس با ناوبری مستقیم به hash URL.
    این روش مستقیم‌تر و مقاوم‌تر از لندینگ پیج است.
    """
    meet_url = f"{SPLUS_WEB_URL}/#/im?meet={meet_code}"
    log(f"  ناوبری مستقیم به: {meet_url}")
    
    # Navigate directly to the meet URL
    try:
        page.goto(meet_url, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        log(f"  خطا در ناوبری: {e}", "WARN")
    
    time.sleep(2)
    
    # Wait for SPA to load
    log("  منتظر بارگذاری SPA...")
    if not wait_for_spa_load(page, timeout_sec=40):
        log("  SPA بارگذاری نشد، ادامه...", "WARN")
        save_screenshot(page, "spa_not_loaded_direct_nav")
    
    time.sleep(3)
    save_screenshot(page, "after_direct_nav_spa")
    
    # v15: Wait for the join interface to appear
    log("  منتظر رابط ورود به تماس (حداکثر 90 ثانیه)...")
    join_interface_found = False
    for i in range(45):  # 90 seconds
        if is_shutdown_requested():
            return False
        time.sleep(2)
        try:
            # Check for join-related buttons
            btn_info = page.evaluate(r"""() => {
                const btns = document.querySelectorAll('button, [role="button"], .lk-button, .lk-join-button');
                const result = [];
                for (const b of btns) {
                    const t = (b.textContent || '').trim();
                    const cls = b.className || '';
                    if (t.includes('ورود به تماس') || t.includes('شروع ویدیو') || 
                        t.includes('Join') || t.includes('Start Video') ||
                        t.includes('Camera') || t.includes('Video') ||
                        cls.includes('lk-join-button') || cls.includes('lk-button')) {
                        result.push({text: t.substring(0, 80), cls: cls.substring(0, 80)});
                    }
                }
                // Also check for any video/camera toggle
                const allBtns = document.querySelectorAll('button');
                for (const b of allBtns) {
                    const ariaLabel = b.getAttribute('aria-label') || '';
                    const title = b.getAttribute('title') || '';
                    if (ariaLabel.includes('Camera') || ariaLabel.includes('Video') || 
                        title.includes('Camera') || title.includes('Video')) {
                        result.push({text: ariaLabel || title, cls: 'aria-btn'});
                    }
                }
                return result;
            }""")
            if btn_info:
                log(f"  ★ رابط ورود به تماس ظاهر شد بعد از {(i+1)*2} ثانیه")
                for b in btn_info[:5]:
                    log(f"    text='{b['text']}' cls='{b['cls']}'")
                join_interface_found = True
                break
            if i % 5 == 0:
                log(f"  منتظر رابط ورود... {(i+1)*2} ثانیه")
        except Exception as e:
            if i % 5 == 0:
                log(f"  خطا در بررسی رابط ورود: {e}", "WARN")
    
    if not join_interface_found:
        log("  رابط ورود به تماس ظاهر نشد!", "ERROR")
        save_screenshot(page, "no_join_interface")
        return False
    
    save_screenshot(page, "join_interface_ready")
    
    # v15: Click "شروع ویدیو" / "Start Video" button first (to enable camera)
    log("  تلاش برای کلیک دکمه 'شروع ویدیو'...")
    try:
        video_start_result = page.evaluate(r"""() => {
            // Priority: look for "شروع ویدیو" / "Start Video" / "Start with Video"
            const btns = document.querySelectorAll('button, [role="button"], .lk-button');
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                if (t === 'شروع ویدیو' || t === 'Start Video' || t === 'Start with Video' ||
                    t.includes('شروع ویدیو') || t.includes('Start Video')) {
                    b.click();
                    return {text: t, clicked: true};
                }
            }
            // Fallback: look for camera toggle
            const allBtns = document.querySelectorAll('button, [role="button"]');
            for (const b of allBtns) {
                const ariaLabel = b.getAttribute('aria-label') || '';
                const title = b.getAttribute('title') || '';
                if (ariaLabel.includes('Camera') || ariaLabel.includes('Video') ||
                    title.includes('Camera') || title.includes('Video')) {
                    b.click();
                    return {text: ariaLabel || title, clicked: true};
                }
            }
            return null;
        }""")
        if video_start_result:
            log(f"  ✓ دکمه ویدیو کلیک شد: {video_start_result}")
        else:
            log("  دکمه 'شروع ویدیو' یافت نشد — ادامه بدون آن", "WARN")
    except Exception as e:
        log(f"  خطا در کلیک دکمه ویدیو: {e}", "WARN")
    
    time.sleep(3)
    save_screenshot(page, "after_video_start_click")
    
    # v15: Click "ورود به تماس" / "Join" button
    log("  کلیک روی دکمه 'ورود به تماس'...")
    try:
        join_result = page.evaluate(r"""() => {
            // Priority: look for "ورود به تماس" / "Join"
            const btns = document.querySelectorAll('button, [role="button"], .lk-button, .lk-join-button');
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                const cls = b.className || '';
                if (t.includes('ورود به تماس') || t === 'Join' || 
                    cls.includes('lk-join-button')) {
                    b.click();
                    return {text: t, clicked: true};
                }
            }
            // Fallback: any button with "ورود" or "Join"
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                if (t.includes('ورود') || t.includes('Join')) {
                    b.click();
                    return {text: t, clicked: true};
                }
            }
            return null;
        }""")
        if join_result:
            log(f"  ✓ دکمه ورود کلیک شد: {join_result}")
        else:
            log("  دکمه 'ورود به تماس' یافت نشد!", "ERROR")
            save_screenshot(page, "no_join_button")
            return False
    except Exception as e:
        log(f"  خطا در کلیک دکمه ورود: {e}", "ERROR")
        return False
    
    time.sleep(5)
    save_screenshot(page, "after_join_click")
    
    # v15: Wait for WebRTC peer connections to be established
    log("  منتظر اتصال WebRTC...")
    pc_count = wait_for_peer_connections(page, timeout_sec=90, min_pc_count=1)
    log(f"  وضعیت peer connections: {pc_count}")
    
    if pc_count == 0:
        log("  هیچ peer connection یافت نشد!", "ERROR")
        save_screenshot(page, "no_peer_connections")
        return False
    
    # Check sender status
    status = check_sender_status(page)
    if status:
        log(f"  وضعیت senders: {json.dumps(status, ensure_ascii=False)}")
        has_video_sender = any(s.get('kind') == 'video' for s in status.get('senders', []))
        if not has_video_sender:
            log("  ★ هیچ video sender یافت نشد — تلاش برای فعال‌سازی ویدیو...")
            click_camera_button(page)
            time.sleep(3)
            add_video_transceiver(page)
            time.sleep(2)
    
    return True


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
        time.sleep(10)
        new_meet_code = find_existing_meet_link(page)
        if new_meet_code and new_meet_code != existing_meet_code_before_create:
            log(f"  ★ تماس جدید ایجاد شد با کد: {new_meet_code}")
            return new_meet_code
        return None

    # Get the meet code from the link in the modal
    time.sleep(3)
    meet_code = None
    try:
        meet_code = page.evaluate(r"""() => {
            const m = document.querySelector('[role="dialog"], .Modal');
            if (!m) return null;
            const links = m.querySelectorAll('a[href*="meet"]');
            for (const link of links) {
                const m2 = link.href.match(/\/meet\/([a-z0-9-]+)/);
                if (m2) return m2[1];
            }
            return null;
        }""")
    except Exception:
        pass
    
    if meet_code:
        log(f"  ★ تماس ایجاد شد با کد: {meet_code}")
        return meet_code
    
    # Close the modal and find the meet code in chat
    try:
        close_btn = page.locator('[role="dialog"] button:has-text("بستن"), [role="dialog"] button:has-text("Close")')
        if close_btn.count() > 0:
            close_btn.first.click()
            time.sleep(3)
    except Exception:
        pass
    
    new_meet_code = find_existing_meet_link(page)
    if new_meet_code and new_meet_code != existing_meet_code_before_create:
        log(f"  ★ تماس جدید ایجاد شد با کد: {new_meet_code}")
        return new_meet_code
    
    log("  ایجاد تماس ناموفق بود", "ERROR")
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


# ============================================================================
# v15: Verify actual media flow
# ============================================================================
def verify_media_flow(page, timeout_sec=30):
    """
    بررسی واقعی جریان مدیا — نه فقط وجود tracks.
    بررسی می‌کند که HLS در حال پخش است و video element داده دارد.
    """
    log("  بررسی جریان واقعی مدیا...")
    for i in range(timeout_sec // 3):
        if is_shutdown_requested():
            return False
        time.sleep(3)
        try:
            flow_status = page.evaluate(r"""() => {
                const video = document.getElementById('streamPlayer');
                const hlsOk = !!window._hlsInstance && !window._hlsInstance.destroyed;
                const videoPlaying = video && !video.paused && video.readyState >= 2;
                const videoHasData = video && (video.videoWidth > 0 || video.videoHeight > 0);
                const liveV = window._liveVideoTrack;
                const liveA = window._liveAudioTrack;
                const liveVReady = liveV && liveV.readyState === 'live';
                const liveAReady = liveA && liveA.readyState === 'live';
                
                // Check sender tracks are actually live tracks
                let liveSenderCount = 0;
                let totalSenders = 0;
                if (window._allPCs) {
                    for (const pc of window._allPCs) {
                        for (const s of pc.getSenders()) {
                            totalSenders++;
                            if (s.track && (s.track.id === (liveV ? liveV.id : null) || 
                                           s.track.id === (liveA ? liveA.id : null))) {
                                liveSenderCount++;
                            }
                        }
                    }
                }
                
                return {
                    hlsOk: hlsOk,
                    videoPlaying: videoPlaying,
                    videoHasData: videoHasData,
                    videoWidth: video ? video.videoWidth : 0,
                    videoHeight: video ? video.videoHeight : 0,
                    liveVideoReady: liveVReady,
                    liveAudioReady: liveAReady,
                    liveVideoId: liveV ? liveV.id : null,
                    liveAudioId: liveA ? liveA.id : null,
                    liveSenderCount: liveSenderCount,
                    totalSenders: totalSenders,
                    allGood: hlsOk && videoPlaying && videoHasData && liveVReady && liveAReady && liveSenderCount >= 2,
                };
            }""")
            if i % 3 == 0:
                log(f"  جریان مدیا ({(i+1)*3}s): {json.dumps(flow_status, ensure_ascii=False)}")
            if flow_status.get('allGood'):
                log("  ★ جریان مدیا تأیید شد — HLS پخش می‌کند و tracks متصل هستند")
                return True
            # Partial success: HLS is playing but not all tracks are live yet
            if flow_status.get('hlsOk') and flow_status.get('videoPlaying') and flow_status.get('liveSenderCount', 0) >= 1:
                log("  ★ جریان مدیا جزئی تأیید شد — حداقل یک track متصل است")
                return True
        except Exception as e:
            log(f"  خطا در بررسی جریان مدیا: {e}", "WARN")
    
    log("  جریان مدیا تأیید نشد!", "WARN")
    return False


def start_live(args):
    """اجرای کامل فلو لایو ۲۴/۷."""
    from playwright.sync_api import sync_playwright

    page = None
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

        # مرحله ۱: راه‌اندازی مرورگر
        log("مرحله ۱/۶: راه‌اندازی مرورگر...")
        launch_args = [
            '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
            '--autoplay-policy=no-user-gesture-required',
            '--use-fake-ui-for-media-stream',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=AudioServiceOutOfProcess',
            '--mute-audio=false',
            # v15: Add flags to help with CSP and media
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process,ContentSecurityPolicy',
        ]

        use_headed = args.headed
        if use_headed:
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

        # v15: نصب CSP bypass (CRITICAL FIX)
        log("  نصب CSP bypass...")
        install_csp_bypass(context)

        # مرحله ۲: تزریق وضعیت مرورگر
        log("مرحله ۲/۶: تزریق وضعیت مرورگر...")
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

        # v15: Pre-populate lk-user-choices (fixes LiveKit warning)
        lk_init_script = """try {
            if (!localStorage.getItem('lk-user-choices')) {
                localStorage.setItem('lk-user-choices', JSON.stringify({
                    videoEnabled: true,
                    audioEnabled: true,
                    videoDeviceId: '',
                    audioDeviceId: '',
                }));
            }
        } catch(e) {}"""
        context.add_init_script(lk_init_script)
        log("  init_script برای lk-user-choices ثبت شد")

        # تزریق media patch از init_script
        context.add_init_script(media_patch_js)
        log("  init_script برای media patch ثبت شد")

        # مرحله ۳: باز کردن سروش+ و یافتن تماس
        log("مرحله ۳/۶: باز کردن سروش+ و یافتن تماس...")
        page = context.new_page()
        page.goto(SPLUS_WEB_URL, wait_until='domcontentloaded', timeout=60000)

        if not wait_for_spa_load(page, timeout_sec=60):
            log("  SPA بارگذاری نشد، ادامه...", "WARN")
            save_screenshot(page, "spa_not_loaded")

        time.sleep(3)

        # ورود به گروه
        log("  ورود به گروه...")
        if not click_group(page, args.group_id):
            log("  ورود به گروه ناموفق بود", "ERROR")
            return False

        time.sleep(5)
        # scroll down to find meet links
        try:
            page.evaluate("""() => {
                const msgList = document.querySelector('.MessageList, .chat-list');
                if (msgList) msgList.scrollTop = msgList.scrollHeight;
            }""")
            time.sleep(2)
        except Exception:
            pass

        # یافتن یا ایجاد تماس
        existing_meet_code = find_existing_meet_link(page)
        meet_code = None

        if existing_meet_code:
            log(f"  ★ تماس موجود یافت شد: {existing_meet_code}")
            meet_code = existing_meet_code
        else:
            log("  تماس موجود یافت نشد، ایجاد تماس جدید...")
            meet_code = create_new_call(page, context, args.call_title)
            if meet_code is None:
                log("  ایجاد تماس ناموفق بود", "ERROR")
                save_screenshot(page, "create_call_failed")
                return False

        # مرحله ۴: ورود به تماس با ناوبری مستقیم
        log(f"مرحله ۴/۶: ورود به تماس با ناوبری مستقیم ({meet_code})...")
        if not join_call_direct_navigation(page, meet_code):
            log("  ورود به تماس ناموفق بود!", "ERROR")
            save_screenshot(page, "join_call_failed")
            return False

        # مرحله ۵: تزریق HLS و فعال‌سازی لایو
        log("مرحله ۵/۶: تزریق HLS و فعال‌سازی لایو...")
        
        # First, wait for peer connections
        pc_count = wait_for_peer_connections(page, timeout_sec=30, min_pc_count=1)
        log(f"  وضعیت peer connections: {pc_count}")
        
        # Check sender status before injection
        status = check_sender_status(page)
        if status:
            log(f"  وضعیت senders قبل از تزریق: {json.dumps(status, ensure_ascii=False)}")
            has_video_sender = any(s.get('kind') == 'video' for s in status.get('senders', []))
            if not has_video_sender:
                log("  ★ هیچ video sender یافت نشد — تلاش برای فعال‌سازی ویدیو...")
                click_camera_button(page)
                time.sleep(5)
                status2 = check_sender_status(page)
                if status2:
                    log(f"  وضعیت senders بعد از کلیک دوربین: {json.dumps(status2, ensure_ascii=False)}")
                    has_video_sender2 = any(s.get('kind') == 'video' for s in status2.get('senders', []))
                    if not has_video_sender2:
                        log("  هنوز video sender وجود ندارد — اضافه کردن video transceiver...")
                        add_video_transceiver(page)
                        time.sleep(3)

        # تزریق media patch دوباره
        inject_media_patch(page, media_patch_js)
        time.sleep(1)

        # تزریق HLS
        inject_hls(page, hls_inject_js, args.hls_url)
        time.sleep(10)

        # مرحله ۶: منتظر اتصال HLS و تأیید جریان مدیا
        log("مرحله ۶/۶: منتظر اتصال HLS...")
        for i in range(30):
            if is_shutdown_requested():
                break
            time.sleep(2)
            try:
                hls_status = page.evaluate(r"""() => {
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
                    log(f"  ★ هر دو audio و video tracks متصل شدند!")
                    break
                if hls_status.get('liveCount', 0) >= 1 and i > 15:
                    log(f"  ★ حداقل یک track متصل شد — ادامه...")
                    break
            except Exception:
                pass

        # v15: Verify actual media flow
        media_ok = verify_media_flow(page, timeout_sec=30)
        if not media_ok:
            log("  هشدار: جریان مدیا تأیید نشد — ادامه...", "WARN")
            # Try re-injecting HLS
            log("  تلاش مجدد تزریق HLS...")
            try:
                page.evaluate("() => { if (window._hlsInstance) { try { window._hlsInstance.destroy(); } catch(e) {} } window._hlsInstance = null; }")
                time.sleep(2)
                inject_hls(page, hls_inject_js, args.hls_url)
                time.sleep(10)
                media_ok = verify_media_flow(page, timeout_sec=20)
                if media_ok:
                    log("  ★ تزریق مجدد HLS موفق بود")
            except Exception as e:
                log(f"  خطا در تزریق مجدد HLS: {e}", "WARN")

        # ذخیره اسکرین‌شات نهایی
        save_screenshot(page, "live_started")
        save_html(page, "live_started")

        # بررسی وضعیت نهایی
        try:
            final_status = page.evaluate(r"""() => {
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
                results.push('audioSenders:' + audioSender);
                results.push('videoSenders:' + videoSender);
                results.push('liveSenders:' + liveSender);
                
                // v15: Check actual video playback
                const video = document.getElementById('streamPlayer');
                results.push('hlsPlaying:' + (video && !video.paused));
                results.push('videoSize:' + (video ? video.videoWidth + 'x' + video.videoHeight : '0x0'));
                
                return results.join('|');
            }""")
            log(f"  وضعیت نهایی: {final_status}")
        except Exception as e:
            log(f"  خطا در بررسی وضعیت: {e}", "WARN")

        pid = os.getpid()
        log("=" * 70)
        log("=== لایو فعال شد ===")
        log(f"PID: {pid} | HLS: {args.hls_url} | گروه: {args.group_id}")
        log(f"صفحه تماس: {page.url}")
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
                    if page.is_closed():
                        log("  صفحه تماس بسته شد!", "WARN")
                        consecutive_failures += 1
                        if consecutive_failures >= 3:
                            break
                        continue
                    
                    # Re-inject HLS if needed
                    hls_alive = page.evaluate("() => !!window._hlsInstance && !window._hlsInstance.destroyed")
                    if not hls_alive:
                        log("  HLS از بین رفته — تزریق مجدد...")
                        inject_hls(page, hls_inject_js, args.hls_url)
                        time.sleep(5)
                    
                    # Replace tracks
                    page.evaluate("() => { if (window._replaceAllPCTracks) window._replaceAllPCTracks(); }")
                    
                    # v15: Aggressive AudioContext resume
                    page.evaluate("""() => {
                        try { if (window._audioCtx && window._audioCtx.state === 'suspended') window._audioCtx.resume(); } catch(e) {}
                        try { if (window._placeholderAudioCtx && window._placeholderAudioCtx.state === 'suspended') window._placeholderAudioCtx.resume(); } catch(e) {}
                    }""")
                    
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
            if page:
                try:
                    if not page.is_closed():
                        page.close()
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
