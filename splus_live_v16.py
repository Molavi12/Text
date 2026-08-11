#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  SPlus 24/7 Live Stream Manager - v16
  سروش+ لایو ۲۴/۷ - نسخه ۱۶
================================================================================
  تغییرات کلیدی v16:
  ۱. حذف کامل route interception — باعث خرابی پاسخ‌ها می‌شد
     (content-encoding دوبل → SyntaxError)
  ۲. اتکا به Chrome flags برای CSP bypass:
     --disable-web-security + --disable-features=...+ContentSecurityPolicy
  ۳. enableWorker: false در HLS.js — دیگر نیازی به blob Workers نیست
  ۴. ناوبری هوشمند به تماس:
     - ابتدا hash navigation
     - سپس pushState + hashchange event
     - سپس location.replace
     - fallback: باز کردن لندینگ پیج
  ۵. دیباگ کامل: dump تمام دکمه‌ها وقتی رابط ورود پیدا نشد
  ۶. lk-user-choices در localStorage
  ۷. بررسی واقعی جریان مدیا بعد از تزریق HLS
================================================================================
"""
import os, sys, time, json, re, zlib, base64, traceback, signal, subprocess
import urllib.request
from pathlib import Path

SPLUS_WEB_URL = "https://web.splus.ir"
DEFAULT_GROUP_ID = "-10023429631"
DEFAULT_CALL_TITLE = "تماس لایو"
DEFAULT_HLS_URL = "https://dev-live.livetvstream.co.uk/LS-63503-4/index.m3u8"

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE = SCRIPT_DIR / "splus_v16.log"
PID_FILE = SCRIPT_DIR / "splus_v16.pid"
DEBUG_DIR = SCRIPT_DIR / "splus_v16_debug"

BROWSER_STATE_REPO_RAW_URLS = [
    "https://raw.githubusercontent.com/Molavi12/Text/main/BROWSER_STATE_B64.txt",
    "https://raw.githubusercontent.com/Molavi12/Text/master/BROWSER_STATE_B64.txt",
]
BROWSER_STATE_FALLBACK_FILE = SCRIPT_DIR / "BROWSER_STATE_B64.local.txt"

def _log_fetch(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass
    print(msg, flush=True)

def fetch_browser_state_b64():
    last_err = None
    for url in BROWSER_STATE_REPO_RAW_URLS:
        try:
            _log_fetch(f"[browser-state] downloading from {url} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "splus-live-v16/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                data = resp.read().decode("utf-8", errors="replace").strip()
            if not data or len(data) < 1000:
                raise RuntimeError(f"too short: {len(data)}")
            try:
                BROWSER_STATE_FALLBACK_FILE.write_text(data, encoding="utf-8")
            except Exception:
                pass
            _log_fetch(f"[browser-state] OK: {len(data)} chars")
            return data
        except Exception as e:
            last_err = e
            _log_fetch(f"[browser-state] FAIL {url}: {e}")
    if BROWSER_STATE_FALLBACK_FILE.exists():
        cached = BROWSER_STATE_FALLBACK_FILE.read_text(encoding="utf-8").strip()
        if cached:
            _log_fetch(f"[browser-state] Using LOCAL cache ({len(cached)} chars)")
            return cached
    raise RuntimeError(f"BROWSER_STATE_B64 unavailable. Last error: {last_err}")

BROWSER_STATE_B64 = fetch_browser_state_b64()
MEDIA_PATCH_B64 = """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"""
HLS_INJECT_B64 = """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"""

def _decode_b64zlib(b64_str):
    return zlib.decompress(base64.b64decode(b64_str.strip()))

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
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page.content())
    except Exception:
        pass

def load_browser_state():
    try:
        data = json.loads(_decode_b64zlib(BROWSER_STATE_B64).decode('utf-8'))
        log(f"وضعیت مرورگر: {len(data.get('origins',[]))} origins, {len(data.get('cookies',[]))} cookies")
        return data
    except Exception as e:
        log(f"خطا در بارگذاری وضعیت: {e}", "ERROR")
        return None

def load_media_patch_js():
    try:
        js = _decode_b64zlib(MEDIA_PATCH_B64).decode('utf-8')
        log(f"media_patch_js: {len(js)} bytes")
        return js
    except Exception as e:
        log(f"خطا در media_patch: {e}", "ERROR")
        return None

def load_hls_inject_js():
    try:
        js = _decode_b64zlib(HLS_INJECT_B64).decode('utf-8')
        log(f"hls_inject_js: {len(js)} bytes")
        return js
    except Exception as e:
        log(f"خطا در hls_inject: {e}", "ERROR")
        return None

# Xvfb
_xvfb_process = None
def start_xvfb():
    global _xvfb_process
    display = os.environ.get('DISPLAY', '')
    if display and display.startswith(':'):
        log(f"X Server: DISPLAY={display}")
        return True
    try:
        if subprocess.run(['which', 'Xvfb'], capture_output=True).returncode != 0:
            return False
    except Exception:
        return False
    try:
        _xvfb_process = subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1280x720x24', '-ac'],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        if _xvfb_process.poll() is not None:
            return False
        os.environ['DISPLAY'] = ':99'
        log("Xvfb راه‌اندازی شد: :99")
        return True
    except Exception:
        return False

def stop_xvfb():
    global _xvfb_process
    if _xvfb_process:
        try: _xvfb_process.terminate(); _xvfb_process.wait(timeout=5)
        except Exception:
            try: _xvfb_process.kill()
            except Exception: pass
        _xvfb_process = None

# Signal
_shutdown = False
def _signal_handler(signum, frame):
    global _shutdown
    _shutdown = True
def install_signal_handlers():
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
def is_shutdown_requested():
    return _shutdown

# ============================================================================
# SPA & Navigation
# ============================================================================
def wait_for_spa_load(page, timeout_sec=60):
    for i in range(timeout_sec // 2):
        if is_shutdown_requested():
            return False
        time.sleep(2)
        try:
            has = page.evaluate("() => !!document.querySelector('.chat-list, .ListItem.Chat, .ChatList, .lk-join-button, [class*=livekit])")
            if has:
                log(f"  SPA بارگذاری شد بعد از {(i+1)*2} ثانیه")
                return True
            if i % 5 == 0:
                log(f"  منتظر SPA... {(i+1)*2} ثانیه")
        except Exception as e:
            if i % 5 == 0:
                log(f"  خطا SPA: {e}", "WARN")
    log("  SPA بارگذاری نشد!", "WARN")
    return False

def click_group(page, group_id):
    try:
        gl = page.locator(f'a[href*="{group_id}"]')
        if gl.count() > 0:
            gl.first.click()
            log(f"  گروه کلیک شد: {group_id}")
            try:
                page.wait_for_selector('.Composer, .MessageList', timeout=30000)
                log("  پنل چت بارگذاری شد")
            except Exception:
                log("  پنل چت بارگذاری نشد، ادامه...", "WARN")
            return True
        log(f"  گروه {group_id} یافت نشد!", "ERROR")
        return False
    except Exception as e:
        log(f"  خطا گروه: {e}", "ERROR")
        return False

def find_existing_meet_link(page):
    try:
        links_info = page.evaluate(r"""() => {
            const links = document.querySelectorAll('a[href*="meet"]');
            const result = [];
            for (const link of links) {
                const href = link.href;
                const m = href.match(/\/meet\/([a-z0-9-]+)/);
                if (!m) continue;
                result.push({code: m[1], href: href});
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
        log(f"  خطا جستجوی meet: {e}", "WARN")
        return None

def wait_for_peer_connections(page, timeout_sec=60, min_pc_count=1):
    log(f"  منتظر WebRTC peer connections (حداقل {min_pc_count})...")
    for i in range(timeout_sec // 2):
        if is_shutdown_requested():
            return 0
        time.sleep(2)
        try:
            pc_count = page.evaluate("() => window._allPCs ? window._allPCs.size : 0")
            if pc_count >= min_pc_count:
                log(f"  ★ {pc_count} peer connection بعد از {(i+1)*2} ثانیه")
                return pc_count
            if i % 5 == 0:
                log(f"  منتظر PC... {(i+1)*2}s (count={pc_count})")
        except Exception:
            pass
    log(f"  هیچ peer connection بعد از {timeout_sec}s", "WARN")
    return 0

def check_sender_status(page):
    try:
        return page.evaluate(r"""() => {
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
    except Exception as e:
        log(f"  خطا sender status: {e}", "WARN")
        return None

# ============================================================================
# v16: Smart Navigation to Meet Page
# ============================================================================
def navigate_to_meet(page, meet_code):
    """
    ناوبری هوشمند به صفحه تماس. چندین روش امتحان می‌کند.
    """
    meet_hash = f"#/im?meet={meet_code}"
    meet_url = f"{SPLUS_WEB_URL}/{meet_hash}"
    
    # روش ۱: goto مستقیم
    log(f"  روش ۱: goto مستقیم به {meet_url}")
    try:
        page.goto(meet_url, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        log(f"  goto خطا: {e}", "WARN")
    
    time.sleep(3)
    
    # بررسی hash
    try:
        current_hash = page.evaluate("() => window.location.hash")
        log(f"  hash فعلی: {current_hash}")
        if meet_hash in current_hash:
            log("  ✓ hash درست تنظیم شد")
            return True
    except Exception:
        pass
    
    # روش ۲: pushState + hashchange
    log(f"  روش ۲: pushState به {meet_hash}")
    try:
        page.evaluate(f"""() => {{
            history.pushState({{}}, '', '{meet_hash}');
            window.dispatchEvent(new HashChangeEvent('hashchange'));
        }}""")
        time.sleep(3)
        current_hash = page.evaluate("() => window.location.hash")
        if meet_hash in current_hash:
            log("  ✓ pushState موفق")
            return True
    except Exception as e:
        log(f"  pushState خطا: {e}", "WARN")
    
    # روش ۳: location.hash مستقیم
    log(f"  روش ۳: location.hash")
    try:
        page.evaluate(f"window.location.hash = '{meet_hash}'")
        time.sleep(3)
        current_hash = page.evaluate("() => window.location.hash")
        if meet_hash in current_hash:
            log("  ✓ location.hash موفق")
            return True
    except Exception as e:
        log(f"  location.hash خطا: {e}", "WARN")
    
    # روش ۴: location.replace
    log(f"  روش ۴: location.replace")
    try:
        page.evaluate(f"window.location.replace('{meet_url}')")
        time.sleep(5)
        current_hash = page.evaluate("() => window.location.hash")
        if meet_hash in current_hash:
            log("  ✓ location.replace موفق")
            return True
    except Exception as e:
        log(f"  location.replace خطا: {e}", "WARN")
    
    log("  هیچ روش ناوبری موفق نبود!", "WARN")
    return False


def dump_all_buttons(page):
    """دیباگ: dump تمام دکمه‌ها در صفحه."""
    try:
        all_btns = page.evaluate(r"""() => {
            const btns = document.querySelectorAll('button, [role="button"], a, .lk-button, .lk-join-button');
            const result = [];
            for (const b of btns) {
                const t = (b.textContent || '').trim().substring(0, 60);
                const cls = (b.className || '').substring(0, 60);
                const href = b.href || '';
                const ariaLabel = b.getAttribute('aria-label') || '';
                if (t || ariaLabel) {
                    result.push({text: t, cls: cls, href: href.substring(0, 80), aria: ariaLabel});
                }
            }
            return result.slice(0, 50);
        }""")
        log(f"  === تمام دکمه‌ها ({len(all_btns)}) ===")
        for b in all_btns:
            log(f"    text='{b.get('text','')}' cls='{b.get('cls','')}' aria='{b.get('aria','')}' href='{b.get('href','')}'")
    except Exception as e:
        log(f"  خطا در dump دکمه‌ها: {e}", "WARN")


def find_join_buttons(page):
    """یافتن دکمه‌های ورود به تماس — selectors بسیار گسترده."""
    try:
        return page.evaluate(r"""() => {
            const btns = document.querySelectorAll('button, [role="button"], .lk-button, .lk-join-button, a');
            const result = [];
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                const cls = b.className || '';
                const ariaLabel = b.getAttribute('aria-label') || '';
                const title = b.getAttribute('title') || '';
                const id = b.id || '';
                
                // Persian buttons
                if (t.includes('ورود به تماس') || t.includes('شروع ویدیو') || 
                    t.includes('ورود') || t.includes('شروع') ||
                    t.includes('اتصال') || t.includes('تماس')) {
                    result.push({text: t.substring(0, 80), cls: cls.substring(0, 80), how: 'text-fa'});
                    continue;
                }
                // English buttons
                if (t.includes('Join') || t.includes('Start Video') || t.includes('Start with Video') ||
                    t.includes('Connect') || t.includes('Enter') || t.includes('Join Call')) {
                    result.push({text: t.substring(0, 80), cls: cls.substring(0, 80), how: 'text-en'});
                    continue;
                }
                // CSS classes
                if (cls.includes('lk-join-button') || cls.includes('lk-button') || 
                    cls.includes('join') || cls.includes('start')) {
                    result.push({text: t.substring(0, 80), cls: cls.substring(0, 80), how: 'class'});
                    continue;
                }
                // Aria labels
                if (ariaLabel.includes('Join') || ariaLabel.includes('Start') || 
                    ariaLabel.includes('ورود') || ariaLabel.includes('شروع') ||
                    ariaLabel.includes('Camera') || ariaLabel.includes('Video')) {
                    result.push({text: (ariaLabel || t).substring(0, 80), cls: cls.substring(0, 80), how: 'aria'});
                    continue;
                }
                // Title attributes
                if (title.includes('Join') || title.includes('Start') || 
                    title.includes('ورود') || title.includes('شروع')) {
                    result.push({text: (title || t).substring(0, 80), cls: cls.substring(0, 80), how: 'title'});
                    continue;
                }
            }
            return result;
        }""")
    except Exception as e:
        log(f"  خطا در یافتن دکمه‌ها: {e}", "WARN")
        return []


def join_call(page, meet_code):
    """
    ورود به تماس — روش هوشمند با fallback.
    """
    # ناوبری به صفحه تماس
    navigate_to_meet(page, meet_code)
    
    # منتظر SPA
    log("  منتظر بارگذاری SPA...")
    wait_for_spa_load(page, timeout_sec=40)
    time.sleep(3)
    save_screenshot(page, "after_nav_spa")
    
    # منتظر رابط ورود
    log("  منتظر رابط ورود به تماس (حداکثر 60 ثانیه)...")
    join_btns = []
    for i in range(30):
        if is_shutdown_requested():
            return False
        time.sleep(2)
        join_btns = find_join_buttons(page)
        if join_btns:
            log(f"  ★ دکمه‌های ورود یافت شد بعد از {(i+1)*2} ثانیه:")
            for b in join_btns[:5]:
                log(f"    text='{b['text']}' cls='{b['cls']}' how='{b['how']}'")
            break
        if i % 5 == 0:
            log(f"  منتظر ورود... {(i+1)*2}s")
    
    if not join_btns:
        log("  دکمه ورود یافت نشد! — dump تمام دکمه‌ها:", "ERROR")
        dump_all_buttons(page)
        save_screenshot(page, "no_join_buttons")
        save_html(page, "no_join_buttons")
        return False
    
    save_screenshot(page, "join_interface_ready")
    
    # کلیک «شروع ویدیو» اول
    log("  کلیک 'شروع ویدیو'...")
    try:
        vr = page.evaluate(r"""() => {
            const btns = document.querySelectorAll('button, [role="button"], .lk-button');
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                if (t.includes('شروع ویدیو') || t.includes('Start Video') || t.includes('Start with Video')) {
                    b.click();
                    return {text: t, clicked: true};
                }
            }
            return null;
        }""")
        if vr:
            log(f"  ✓ ویدیو کلیک شد: {vr}")
        else:
            log("  'شروع ویدیو' یافت نشد — ادامه", "WARN")
    except Exception as e:
        log(f"  خطا ویدیو: {e}", "WARN")
    
    time.sleep(3)
    save_screenshot(page, "after_video_click")
    
    # کلیک «ورود به تماس»
    log("  کلیک 'ورود به تماس'...")
    try:
        jr = page.evaluate(r"""() => {
            const btns = document.querySelectorAll('button, [role="button"], .lk-button, .lk-join-button');
            // اول: ورود به تماس
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                const cls = b.className || '';
                if (t.includes('ورود به تماس') || cls.includes('lk-join-button')) {
                    b.click();
                    return {text: t, clicked: true};
                }
            }
            // دوم: Join
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                if (t === 'Join' || t.includes('Join Call') || t.includes('Join Now')) {
                    b.click();
                    return {text: t, clicked: true};
                }
            }
            // سوم: هر دکمه ورود
            for (const b of btns) {
                const t = (b.textContent || '').trim();
                if (t.includes('ورود') || t.includes('Join') || t.includes('Enter')) {
                    b.click();
                    return {text: t, clicked: true};
                }
            }
            return null;
        }""")
        if jr:
            log(f"  ✓ ورود کلیک شد: {jr}")
        else:
            log("  دکمه ورود یافت نشد!", "ERROR")
            save_screenshot(page, "no_join_btn")
            return False
    except Exception as e:
        log(f"  خطا ورود: {e}", "ERROR")
        return False
    
    time.sleep(5)
    save_screenshot(page, "after_join_click")
    
    # منتظر WebRTC
    log("  منتظر اتصال WebRTC...")
    pc_count = wait_for_peer_connections(page, timeout_sec=90, min_pc_count=1)
    if pc_count == 0:
        log("  هیچ peer connection!", "ERROR")
        save_screenshot(page, "no_pc")
        return False
    
    # بررسی senders
    status = check_sender_status(page)
    if status:
        log(f"  senders: {json.dumps(status, ensure_ascii=False)}")
        if not any(s.get('kind') == 'video' for s in status.get('senders', [])):
            log("  بدون video sender — فعال‌سازی ویدیو...")
            try:
                page.evaluate(r"""() => {
                    const btns = document.querySelectorAll('button, [role="button"]');
                    for (const b of btns) {
                        const t = (b.textContent || '').trim();
                        const a = b.getAttribute('aria-label') || '';
                        if (t.includes('دوربین') || t.includes('Camera') || a.includes('Camera')) {
                            b.click(); return;
                        }
                    }
                }""")
            except Exception:
                pass
            time.sleep(3)
    
    return True


def create_new_call(page, context, call_title):
    """ایجاد تماس گروهی جدید."""
    existing = find_existing_meet_link(page)
    log("  کلیک 'فعالیت های بیشتر'...")
    try:
        mb = page.locator('[aria-label="فعالیت های بیشتر"]')
        if mb.count() > 0:
            mb.first.click()
            time.sleep(2)
        else:
            log("  دکمه فعالیت یافت نشد!", "ERROR")
            return None
    except Exception as e:
        log(f"  خطا: {e}", "ERROR")
        return None

    log("  انتخاب 'تماس گروهی جدید'...")
    try:
        clicked = page.evaluate(r"""() => {
            const items = document.querySelectorAll('[role="menuitem"], .MenuItem, [class*="MenuItem"]');
            for (const item of items) {
                const t = (item.textContent || '').trim();
                if (t.includes('تماس گروهی جدید') || t.includes('New Group Call')) {
                    item.click(); return t;
                }
            }
            return null;
        }""")
        if not clicked:
            log("  منو آیتم یافت نشد!", "ERROR")
            return None
    except Exception as e:
        log(f"  خطا: {e}", "ERROR")
        return None

    log("  انتظار modal...")
    for i in range(15):
        time.sleep(2)
        try:
            if page.evaluate("""() => {
                const m = document.querySelector('[role="dialog"], .Modal');
                return m && m.textContent.includes('نام تماس');
            }"""):
                log(f"  modal ظاهر شد ({(i+1)*2}s)")
                break
        except Exception:
            pass
    else:
        log("  modal ظاهر نشد!", "ERROR")
        return None

    time.sleep(2)
    try:
        ni = page.locator('[role="dialog"] input, .Modal input').first
        ni.wait_for(state='visible', timeout=5000)
        ni.click(); time.sleep(0.5)
        ni.fill(call_title); time.sleep(1)
    except Exception as e:
        log(f"  خطا نام: {e}", "WARN")

    log("  کلیک 'ساخت لینک'...")
    try:
        cb = page.locator('button:has-text("ساخت لینک")').first
        cb.wait_for(state='visible', timeout=5000)
        cb.click(force=True)
    except Exception as e:
        log(f"  خطا: {e}", "ERROR")
        return None

    log("  انتظار لینک تماس...")
    for i in range(15):
        if is_shutdown_requested():
            return None
        time.sleep(2)
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
            if meet_code:
                log(f"  ★ تماس ایجاد شد: {meet_code}")
                return meet_code
        except Exception:
            pass

    # Fallback: find in chat
    time.sleep(10)
    new_code = find_existing_meet_link(page)
    if new_code and new_code != existing:
        log(f"  ★ تماس جدید در چت: {new_code}")
        return new_code
    return None


def inject_media_patch(page, js):
    try:
        if page.evaluate("() => !!window._mediaPatched"):
            return True
        page.evaluate(js)
        return True
    except Exception as e:
        log(f"  خطا media patch: {e}", "WARN")
        return False

def inject_hls(page, js, hls_url):
    try:
        if page.evaluate("() => !!window._hlsInstance"):
            return True
        page.evaluate(f"window._HLS_URL = {json.dumps(hls_url)}")
        result = page.evaluate(js)
        log(f"  HLS نتیجه: {result}")
        return True
    except Exception as e:
        log(f"  خطا HLS: {e}", "WARN")
        return False

def verify_media_flow(page, timeout_sec=30):
    log("  بررسی جریان مدیا...")
    for i in range(timeout_sec // 3):
        if is_shutdown_requested():
            return False
        time.sleep(3)
        try:
            s = page.evaluate(r"""() => {
                const v = document.getElementById('streamPlayer');
                const hlsOk = !!window._hlsInstance && !window._hlsInstance.destroyed;
                const playing = v && !v.paused && v.readyState >= 2;
                const hasData = v && v.videoWidth > 0;
                let liveSenders = 0;
                if (window._allPCs) {
                    for (const pc of window._allPCs) {
                        for (const s of pc.getSenders()) {
                            if (s.track && (s.track.id === (window._liveVideoTrack ? window._liveVideoTrack.id : null) ||
                                           s.track.id === (window._liveAudioTrack ? window._liveAudioTrack.id : null))) {
                                liveSenders++;
                            }
                        }
                    }
                }
                return {hlsOk, playing, hasData, vw: v?v.videoWidth:0, vh: v?v.videoHeight:0, liveSenders,
                        lv: window._liveVideoTrack?window._liveVideoTrack.id:null,
                        la: window._liveAudioTrack?window._liveAudioTrack.id:null};
            }""")
            if i % 3 == 0:
                log(f"  مدیا ({(i+1)*3}s): {json.dumps(s, ensure_ascii=False)}")
            if s.get('hlsOk') and s.get('playing') and s.get('liveSenders', 0) >= 1:
                log("  ★ جریان مدیا تأیید شد!")
                return True
        except Exception:
            pass
    log("  جریان مدیا تأیید نشد", "WARN")
    return False


def start_live(args):
    from playwright.sync_api import sync_playwright
    page = None
    context = None
    browser = None
    pw = None
    success = False

    try:
        log("=" * 70)
        log("شروع لایو سروش+ ۲۴/۷ (v16)")
        log("=" * 70)
        log(f"HLS: {args.hls_url} | گروه: {args.group_id} | headed: {args.headed}")

        state = load_browser_state()
        if not state:
            return False
        media_patch_js = load_media_patch_js()
        hls_inject_js = load_hls_inject_js()
        if not media_patch_js or not hls_inject_js:
            return False

        # مرحله ۱: مرورگر
        log("مرحله ۱/۶: راه‌اندازی مرورگر...")
        launch_args = [
            '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
            '--autoplay-policy=no-user-gesture-required',
            '--use-fake-ui-for-media-stream',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=AudioServiceOutOfProcess',
            '--mute-audio=false',
            # v16: CSP bypass از طریق Chrome flags
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
        ]

        use_headed = args.headed
        if use_headed and not start_xvfb():
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

        # مرحله ۲: تزریق وضعیت
        log("مرحله ۲/۶: تزریق وضعیت مرورگر...")
        cookies = [c for c in state.get('cookies', []) if 'splus.ir' in c.get('domain', '')]
        if cookies:
            try:
                context.add_cookies(cookies)
                log(f"  {len(cookies)} کوکی تزریق شد")
            except Exception as e:
                log(f"  خطا کوکی: {e}", "WARN")

        ls_items = []
        for od in state.get('origins', []):
            if 'splus.ir' not in od.get('origin', ''):
                continue
            for item in od.get('localStorage', []):
                ls_items.append((item['name'], item['value']))

        if ls_items:
            parts = [f"localStorage.setItem({json.dumps(n)}, {json.dumps(v)});" for n, v in ls_items]
            context.add_init_script("try { " + " ".join(parts) + " } catch(e) {}")
            log(f"  {len(ls_items)} کلید localStorage تزریق شد")

        # lk-user-choices
        context.add_init_script("""try {
            if (!localStorage.getItem('lk-user-choices')) {
                localStorage.setItem('lk-user-choices', JSON.stringify({videoEnabled:true,audioEnabled:true,videoDeviceId:'',audioDeviceId:''}));
            }
        } catch(e) {}""")
        log("  lk-user-choices ثبت شد")

        # media patch از init_script
        context.add_init_script(media_patch_js)
        log("  media patch ثبت شد")

        # مرحله ۳: باز کردن سروش+
        log("مرحله ۳/۶: باز کردن سروش+ و یافتن تماس...")
        page = context.new_page()
        page.goto(SPLUS_WEB_URL, wait_until='domcontentloaded', timeout=60000)

        if not wait_for_spa_load(page, timeout_sec=60):
            log("  SPA بارگذاری نشد!", "WARN")
            save_screenshot(page, "spa_fail")

        time.sleep(3)

        if not click_group(page, args.group_id):
            log("  ورود به گروه ناموفق!", "ERROR")
            return False

        time.sleep(5)
        try:
            page.evaluate("() => { const m = document.querySelector('.MessageList, .chat-list'); if (m) m.scrollTop = m.scrollHeight; }")
            time.sleep(2)
        except Exception:
            pass

        # یافتن/ایجاد تماس
        existing_meet = find_existing_meet_link(page)
        meet_code = None

        if existing_meet:
            log(f"  ★ تماس موجود: {existing_meet}")
            meet_code = existing_meet
        else:
            log("  ایجاد تماس جدید...")
            meet_code = create_new_call(page, context, args.call_title)
            if not meet_code:
                log("  ایجاد تماس ناموفق!", "ERROR")
                return False

        # مرحله ۴: ورود به تماس
        log(f"مرحله ۴/۶: ورود به تماس ({meet_code})...")
        if not join_call(page, meet_code):
            log("  ورود ناموفق!", "ERROR")
            save_screenshot(page, "join_fail")
            return False

        # مرحله ۵: تزریق HLS
        log("مرحله ۵/۶: تزریق HLS...")
        pc_count = wait_for_peer_connections(page, timeout_sec=30, min_pc_count=1)
        log(f"  peer connections: {pc_count}")

        status = check_sender_status(page)
        if status:
            log(f"  senders قبل: {json.dumps(status, ensure_ascii=False)}")

        inject_media_patch(page, media_patch_js)
        time.sleep(1)
        inject_hls(page, hls_inject_js, args.hls_url)
        time.sleep(10)

        # مرحله ۶: تأیید
        log("مرحله ۶/۶: تأیید اتصال...")
        for i in range(30):
            if is_shutdown_requested():
                break
            time.sleep(2)
            try:
                hs = page.evaluate(r"""() => {
                    let liveCount = 0;
                    if (window._allPCs) {
                        for (const pc of window._allPCs) {
                            for (const s of pc.getSenders()) {
                                const tid = s.track ? s.track.id : null;
                                if (tid === (window._liveVideoTrack?window._liveVideoTrack.id:null) ||
                                    tid === (window._liveAudioTrack?window._liveAudioTrack.id:null)) liveCount++;
                            }
                        }
                    }
                    return {pcCount: window._allPCs?window._allPCs.size:0, hlsReady:!!window._hlsInstance, liveCount};
                }""")
                if i % 5 == 0:
                    log(f"  {(i+1)*2}s: {json.dumps(hs, ensure_ascii=False)}")
                if hs.get('liveCount', 0) >= 2:
                    log("  ★ هر دو tracks متصل!")
                    break
                if hs.get('liveCount', 0) >= 1 and i > 10:
                    log("  ★ حداقل یک track متصل")
                    break
            except Exception:
                pass

        verify_media_flow(page, timeout_sec=30)
        save_screenshot(page, "live_started")

        # وضعیت نهایی
        try:
            fs = page.evaluate(r"""() => {
                const r = [];
                r.push('videos:' + document.querySelectorAll('video').length);
                r.push('patched:' + (window._mediaPatched||false));
                r.push('hls:' + !!window._hlsInstance);
                let aS=0,vS=0,lS=0;
                if (window._allPCs) for (const pc of window._allPCs) for (const s of pc.getSenders()) {
                    if(s.track&&s.track.kind==='audio')aS++;
                    if(s.track&&s.track.kind==='video')vS++;
                    if(s.track&&(s.track.id===(window._liveVideoTrack?window._liveVideoTrack.id:null)||s.track.id===(window._liveAudioTrack?window._liveAudioTrack.id:null)))lS++;
                }
                r.push('aS:'+aS); r.push('vS:'+vS); r.push('lS:'+lS);
                const v = document.getElementById('streamPlayer');
                r.push('playing:'+(v&&!v.paused)); r.push('size:'+(v?v.videoWidth+'x'+v.videoHeight:'0x0'));
                return r.join('|');
            }""")
            log(f"  وضعیت نهایی: {fs}")
        except Exception:
            pass

        log("=" * 70)
        log("=== لایو فعال شد ===")
        log(f"PID: {os.getpid()} | HLS: {args.hls_url} | گروه: {args.group_id}")
        log("=" * 70)

        success = True

        if not args.once:
            log("شروع لوپ نگهداری ۲۴/۷...")
            cc = 0
            cf = 0
            while not is_shutdown_requested():
                time.sleep(30)
                cc += 1
                try:
                    if page.is_closed():
                        cf += 1
                        if cf >= 3: break
                        continue
                    alive = page.evaluate("() => !!window._hlsInstance && !window._hlsInstance.destroyed")
                    if not alive:
                        inject_hls(page, hls_inject_js, args.hls_url)
                        time.sleep(5)
                    page.evaluate("() => { if (window._replaceAllPCTracks) window._replaceAllPCTracks(); }")
                    page.evaluate("""() => {
                        try{if(window._audioCtx&&window._audioCtx.state==='suspended')window._audioCtx.resume();}catch(e){}
                        try{if(window._placeholderAudioCtx&&window._placeholderAudioCtx.state==='suspended')window._placeholderAudioCtx.resume();}catch(e){}
                    }""")
                    if cc % 10 == 0:
                        log(f"  بررسی #{cc}: فعال")
                    cf = 0
                except Exception as e:
                    log(f"  خطا نگهداری: {e}", "WARN")
                    cf += 1
                    if cf >= 3: break

        return True

    except Exception as e:
        log(f"خطای کلی: {e}", "ERROR")
        log(traceback.format_exc(), "ERROR")
        return False
    finally:
        if not success or args.once:
            for p in ([page] if page else []):
                try:
                    if not p.is_closed(): p.close()
                except Exception:
                    pass
            for obj in [context, browser]:
                try:
                    if obj: obj.close()
                except Exception:
                    pass
            try:
                if pw: pw.stop()
            except Exception:
                pass
            stop_xvfb()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SPlus 24/7 Live v16')
    parser.add_argument('--headed', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--hls-url', default=DEFAULT_HLS_URL)
    parser.add_argument('--group-id', default=DEFAULT_GROUP_ID)
    parser.add_argument('--call-title', default=DEFAULT_CALL_TITLE)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    install_signal_handlers()
    _init_logger()
    _ensure_debug_dir()

    if args.check:
        try:
            from playwright.sync_api import sync_playwright
            log("✓ Playwright OK")
        except ImportError:
            log("✗ Playwright نصب نیست!", "ERROR")
            return 1
        if load_browser_state():
            log("✓ وضعیت مرورگر OK")
        else:
            return 1
        if load_media_patch_js() and load_hls_inject_js():
            log("✓ JS payloads OK")
        else:
            return 1
        return 0

    for attempt in range(1, 4):
        log(f"=== تلاش {attempt}/3 ===")
        if start_live(args):
            log("✓ لایو موفق")
            return 0
        if attempt < 3:
            time.sleep(10 * attempt)
    log("همه تلاش‌ها ناموفق", "ERROR")
    return 1

if __name__ == '__main__':
    sys.exit(main())
