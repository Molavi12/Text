#!/usr/bin/env bash
# ============================================================================
#  balevpn-server.sh — مدیر سمت سرور BaleVPN
#  ---------------------------------------------------------------------
#  اسکریپت مدیریت گیت‌وی BaleVPN روی سرور لینوکس (VPS خارج از ایران):
#    - نصب باینری headless از Release رسمی پروژه (یا فایل محلی)
#    - اجرا به‌صورت systemd service (یا nohup در محیط بدون systemd)
#    - ثبت‌نام/ورود با حساب بله (SMS OTP یا توکن دستی)
#    - مدیریت لیست مجاز/مسدود، سقف کلاینت، درخواست‌های در انتظار
#    - آماده‌سازی NAT کرنلی (setcap + sysctl + iptables)
#    - مانیتورینگ کلاینت‌های متصل و لاگ‌ها
#
#  نیازمندی: bash 4+، curl، jq (نصب خودکار در «install»)
#  استفاده:  ./balevpn-server.sh <command> [args]
#  راهنما:   ./balevpn-server.sh help
# ============================================================================
set -euo pipefail

# ----------------------------- تنظیمات عمومی -------------------------------
BALEVPN_VERSION="${BALEVPN_VERSION:-}"
BALEVPN_DIR="${BALEVPN_DIR:-}"
BALEVPN_PORT="${BALEVPN_PORT:-3001}"
BALEVPN_NAT_MODE="${BALEVPN_NAT_MODE:-userspace}"

REPO="kookoo1sabzy/BaleVPN"
BIN_NAME="bale-vpn-headless-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
SCRIPT_SELF="$(readlink -f "${BASH_SOURCE[0]}")"

# اگر از مسیر نصب‌شده اجرا می‌شود، همان دایرکتوری را نگه دار
if [ -z "$BALEVPN_DIR" ] && [ -f "$(dirname "$SCRIPT_SELF")/bale-vpn-headless-linux-x86_64" ]; then
    BALEVPN_DIR="$(dirname "$SCRIPT_SELF")"
fi
if [ -z "$BALEVPN_DIR" ]; then
    # ریشه / قابل نوشتن (با sudo) → /opt/balevpn، وگرنه دایرکتوری خانگی
    if sudo -n true 2>/dev/null; then
        BALEVPN_DIR="/opt/balevpn"
    else
        BALEVPN_DIR="$HOME/balevpn"
    fi
fi

BIN="$BALEVPN_DIR/$BIN_NAME"
CFG="$BALEVPN_DIR/.bale-vpn_config.json"
API="http://127.0.0.1:$BALEVPN_PORT"
TXN_FILE="$BALEVPN_DIR/.auth_txn"
PID_FILE="$BALEVPN_DIR/balevpn.pid"
LOG_FILE="$BALEVPN_DIR/balevpn.log"
UNIT_FILE="/etc/systemd/system/balevpn.service"

C_G='\033[0;32m'; C_Y='\033[0;33m'; C_R='\033[0;31m'; C_B='\033[1;36m'; C_0='\033[0m'
info()  { printf "${C_G}[✓]${C_0} %s\n" "$*"; }
warn()  { printf "${C_Y}[!]${C_0} %s\n" "$*"; }
err()   { printf "${C_R}[✗]${C_0} %s\n" "$*" >&2; }
hdr()   { printf "\n${C_B}── %s ──${C_0}\n" "$*"; }

# ----------------------------- ابزارهای کمکی -------------------------------
have()      { command -v "$1" >/dev/null 2>&1; }

daemon_pid() {
    pgrep -f "bale-vpn-headless.*server" 2>/dev/null | head -1 || true
}

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null && return 0
    [ -n "$(daemon_pid)" ] && return 0
    return 1
}

api() { # GET/POST endpoint [json]
    local method="$1" ep="$2" data="${3:-}"
    if [ "$method" = "GET" ]; then
        curl -fsS --max-time 5 "$API$ep"
    else
        curl -fsS --max-time 8 -X POST "$API$ep" -H 'Content-Type: application/json' -d "${data:-{}}"
    fi
}

daemon_running_msg() {
    if is_running; then
        return 0
    else
        warn "دیمون در حال اجرا نیست. ابتدا: $0 service start"
        return 1
    fi
}

# ویرایش فایل کانفیگ با jq — فقط وقتی دیمون متوقف است (دیمون در حافظه‌اش را
# بازنویسی می‌کند). هنگام اجرای دیمون از HTTP API استفاده کنید.
cfg_edit() { # jq expression
    [ -f "$CFG" ] || { echo '{}' > "$CFG"; }
    local tmp; tmp="$(mktemp)"
    jq "$1" "$CFG" > "$tmp" && mv "$tmp" "$CFG" && chmod 600 "$CFG"
}

ensure_sysd() {
    if systemctl is-system-running >/dev/null 2>&1 || systemctl status >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

# ----------------------------- help ----------------------------------------
cmd_help() {
cat <<'EOF'
BaleVPN Server Manager — مدیریت گیت‌وی تونل تماس بله

  install    [--dir DIR] [--from FILE] [--version vX.Y.Z]   نصب باینری و وابستگی‌ها
  service    install|uninstall|start|stop|restart|status    مدیریت سرویس (systemd یا nohup)
  auth       phone <شماره> | verify <کد> [نام] | token <JWT> | status
             ثبت‌نام/ورود حساب بله (SMS OTP) یا نصب دستی توکن
  nat        userspace|kernel                               انتخاب حالت forwarding سرور
  admission  list | allow <peerId> | disallow <peerId>      لیست مجاز (پذیرش خودکار تماس)
  block      list | add <peerId> | remove <peerId>          لیست مسدود
  maxclients <1-253>                                        سقف کلاینت همزمان
  pending                                                   درخواست‌های تماس در انتظار
  pending    accept <peerId> | reject <peerId>              پذیرش/رد درخواست
  clients                                                   کلاینت‌های متصل + ترافیک
  status                                                    وضعیت کلی دیمون
  logs       [تعداد خط]                                     نمایش لاگ
  ui                                                        راهنمای دسترسی به رابط وب
  update                                                    به‌روزرسانی به آخرین Release
  uninstall                                                 حذف کامل

متغیرهای محیطی:
  BALEVPN_DIR=/path    مسیر نصب (پیش‌فرض: /opt/balevpn یا ~/balevpn)
  BALEVPN_PORT=3001    پورت رابط وب محلی
  BALEVPN_NAT_MODE=userspace|kernel

مثال:
  sudo ./balevpn-server.sh install
  ./balevpn-server.sh service start
  ./balevpn-server.sh auth phone +98912xxxxxxx
  ./balevpn-server.sh auth verify 12345
  ./balevpn-server.sh admission allow 1234567890
  ./balevpn-server.sh clients
EOF
}

# ----------------------------- install -------------------------------------
cmd_install() {
    local from="" dlver="latest"
    while [ $# -gt 0 ]; do
        case "$1" in
            --dir)    BALEVPN_DIR="$2"; BIN="$BALEVPN_DIR/$BIN_NAME"; CFG="$BALEVPN_DIR/.bale-vpn_config.json"; shift 2 ;;
            --from)   from="$2"; shift 2 ;;
            --version) BALEVPN_VERSION="$2"; dlver="$2"; shift 2 ;;
            *) err "آرگومان ناشناخته: $1"; return 1 ;;
        esac
    done

    hdr "نصب BaleVPN (سمت سرور)"
    mkdir -p "$BALEVPN_DIR"

    # وابستگی‌ها
    if ! have curl; then
        if have apt-get; then sudo apt-get update -qq && sudo apt-get install -y -qq curl ca-certificates;
        elif have dnf; then sudo dnf install -y -q curl;
        elif have yum; then sudo yum install -y -q curl; fi
    fi
    if ! have jq; then
        if have apt-get; then sudo apt-get install -y -qq jq;
        elif have dnf; then sudo dnf install -y -q jq;
        elif have yum; then sudo yum install -y -q jq; fi
    fi
    have curl || { err "curl نصب نشد"; return 1; }
    have jq    || { err "jq نصب نشد"; return 1; }
    info "وابستگی‌ها آماده است (curl, jq)"

    # باینری
    if [ -n "$from" ]; then
        cp -f "$from" "$BIN"
        info "باینری از فایل محلی کپی شد: $from"
    else
        local url="https://github.com/$REPO/releases"
        if [ "$dlver" = "latest" ]; then
            url="$url/latest/download/$BIN_NAME"
        else
            url="$url/download/$dlver/$BIN_NAME"
        fi
        info "دانلود: $url"
        curl -fSL --progress-bar -o "$BIN" "$url"
    fi
    chmod +x "$BIN"

    [ -f "$CFG" ] || { echo '{}' > "$CFG"; chmod 600 "$CFG"; }

    info "نصب در: $BALEVPN_DIR"
    warn "قدم بعدی:  $0 service start   و سپس   $0 auth phone <شماره>"
}

# ----------------------------- service -------------------------------------
cmd_service() {
    local action="${1:-status}"
    case "$action" in
        install)
            if ensure_sysd; then
                sudo tee "$UNIT_FILE" >/dev/null <<EOF
[Unit]
Description=BaleVPN gateway (call-tunnel over Bale messenger)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BALEVPN_DIR
ExecStart=$BIN --config-dir $BALEVPN_DIR --port $BALEVPN_PORT server --nat-mode $BALEVPN_NAT_MODE
Restart=on-failure
RestartSec=5
User=$(whoami)

[Install]
WantedBy=multi-user.target
EOF
                sudo systemctl daemon-reload
                sudo systemctl enable balevpn.service
                info "سرویس systemd نصب شد → start با: $0 service start"
            else
                warn "systemd در دسترس نیست؛ از nohup استفاده خواهد شد (service start)"
            fi
            ;;
        uninstall)
            if ensure_sysd && [ -f "$UNIT_FILE" ]; then
                sudo systemctl disable --now balevpn.service 2>/dev/null || true
                sudo rm -f "$UNIT_FILE"
                sudo systemctl daemon-reload
                info "سرویس systemd حذف شد"
            else
                cmd_service stop
                rm -f "$PID_FILE"
            fi
            ;;
        start)
            if is_running; then warn "از قبل در حال اجراست (pid=$(daemon_pid))"; return 0; fi
            if ensure_sysd && [ -f "$UNIT_FILE" ]; then
                sudo systemctl start balevpn.service
            else
                ( cd "$BALEVPN_DIR" && nohup "$BIN" --config-dir "$BALEVPN_DIR" --port "$BALEVPN_PORT" \
                    server --nat-mode "$BALEVPN_NAT_MODE" >> "$LOG_FILE" 2>&1 & echo $! > "$PID_FILE" )
            fi
            sleep 2
            if is_running; then info "دیمون روشن شد (pid=$(daemon_pid)) — UI: $API"; else err "راه‌اندازی ناموفق — $0 logs"; return 1; fi
            ;;
        stop)
            if ensure_sysd && [ -f "$UNIT_FILE" ]; then
                sudo systemctl stop balevpn.service 2>/dev/null || true
            fi
            if [ -f "$PID_FILE" ]; then kill "$(cat "$PID_FILE")" 2>/dev/null || true; rm -f "$PID_FILE"; fi
            pkill -f "bale-vpn-headless" 2>/dev/null || true
            sleep 1
            info "دیمون متوقف شد"
            ;;
        restart) cmd_service stop; sleep 1; cmd_service start ;;
        status)
            if is_running; then
                info "در حال اجرا (pid=$(daemon_pid))"
                curl -fsS --max-time 5 "$API/state" 2>/dev/null | jq . 2>/dev/null || true
            else
                warn "متوقف است"
            fi
            ;;
        *) err "unknown: $action"; return 1 ;;
    esac
}

# ----------------------------- auth ----------------------------------------
cmd_auth() {
    local sub="${1:-status}"
    case "$sub" in
        phone)
            daemon_running_msg || return 1
            local phone="$2" reply
            [ -n "$phone" ] || { err "استفاده: auth phone <+989xxxxxxxxx>"; return 1; }
            reply="$(api POST /auth/start "{\"phone\":\"$phone\"}")"
            echo "$reply" | jq . > /dev/null && echo "$reply" > "$TXN_FILE"
            local hash reg
            hash="$(echo "$reply" | jq -r '.transaction_hash // .transactionHash // empty')"
            reg="$(echo "$reply" | jq -r '.is_registered // false')"
            [ -n "$hash" ] || { err "شروع ثبت‌نام ناموفق: $reply"; return 1; }
            info "کد ارسال شد به $phone (hash ذخیره شد)"
            [ "$reg" = "true" ] && info "این شماره ثبت‌نام‌شده است" || warn "شماره جدید است — بعد از verify نام هم می‌گیریم"
            printf "قدم بعدی: %s auth verify <کد پیامک‌شده>\n" "$0"
            ;;
        verify)
            daemon_running_msg || return 1
            local code="$2" name="${3:-}"
            [ -f "$TXN_FILE" ] || { err "اول auth phone بزنید"; return 1; }
            local hash reg
            hash="$(jq -r '.transaction_hash // .transactionHash // empty' "$TXN_FILE")"
            reg="$(jq -r '.is_registered // false' "$TXN_FILE")"
            [ -n "$hash" ] || { err "transaction hash پیدا نشد — دوباره auth phone"; return 1; }
            local reply
            reply="$(api POST /auth/verify "{\"transaction_hash\":\"$hash\",\"code\":\"$code\",\"is_registered\":$reg}")"
            local ok ns
            ok="$(echo "$reply" | jq -r '.ok')"
            ns="$(echo "$reply" | jq -r '.needs_signup')"
            if [ "$ok" = "true" ]; then
                info "ورود موفق — توکن ذخیره شد"
                rm -f "$TXN_FILE"
                $0 auth status || true
            elif [ "$ns" = "true" ]; then
                warn "ثبت‌نام جدید — نام نمایشی لازم است"
                if [ -z "$name" ]; then
                    printf "نام نمایشی را وارد کنید: "; read -r name
                fi
                api POST /auth/signup "{\"transaction_hash\":\"$hash\",\"name\":\"$name\"}" >/dev/null
                info "ثبت‌نام کامل شد"
                rm -f "$TXN_FILE"
                $0 auth status || true
            else
                err "خطا: $(echo "$reply" | jq -r '.error // "unknown"')"
                return 1
            fi
            ;;
        token)
            local jwt="$2"
            [ -n "$jwt" ] || { err "استفاده: auth token <access_token JWT>"; return 1; }
            if is_running; then
                warn "دیمون روشن است — برای اعمال توکن، توقف و شروع مجدد لازم است"
                cmd_service stop
            fi
            cfg_edit ".token = \"$jwt\""
            info "توکن در کانفیگ ذخیره شد (chmod 600)"
            cmd_service start
            ;;
        status)
            hdr "وضعیت احراز هویت"
            if is_running; then
                api GET /state | jq '{tokenSet, sessionExpired, self, wsReady, wsPaused}'
            elif [ -f "$CFG" ] && jq -e '.token | length > 0' "$CFG" >/dev/null 2>&1; then
                info "توکن در کانفیگ موجود است (دیمون خاموش)"
            else
                warn "هیچ توکنی موجود نیست — $0 auth phone <شماره>"
            fi
            ;;
        *) err "unknown: $sub"; return 1 ;;
    esac
}

# ----------------------------- nat -----------------------------------------
cmd_nat() {
    local mode="${1:-}"
    case "$mode" in
        userspace)
            BALEVPN_NAT_MODE="userspace"
            cfg_edit '.nat_mode = "userspace"' 2>/dev/null || true
            info "حالت userspace (بدون نیاز به دسترسی روت) — برای اعمال: service restart"
            ;;
        kernel)
            hdr "آماده‌سازی NAT کرنلی (یک‌بار مصرف، نیازمند sudo)"
            sudo setcap cap_net_admin+eip "$BIN"
            sudo sysctl -w net.ipv4.ip_forward=1
            echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-bale-vpn.conf >/dev/null
            sudo iptables -t nat -C POSTROUTING -s 10.8.0.0/16 -j MASQUERADE 2>/dev/null || \
                sudo iptables -t nat -A POSTROUTING -s 10.8.0.0/16 -j MASQUERADE
            info "setcap + ip_forward + MASQUERADE (10.8.0.0/16) انجام شد"
            BALEVPN_NAT_MODE="kernel"
            cfg_edit '.nat_mode = "kernel"' 2>/dev/null || true
            warn "برای اعمال: service restart"
            ;;
        *) err "استفاده: nat userspace|kernel"; return 1 ;;
    esac
}

# ----------------------------- admission/block/maxclients/pending/clients ---
cmd_admission() {
    local sub="${1:-list}"
    case "$sub" in
        list)
            if is_running; then api GET /server/admission | jq .; else jq '.admission' "$CFG"; fi ;;
        allow)
            local id="$2"; [ -n "$id" ] || { err "استفاده: admission allow <peerId>"; return 1; }
            if is_running; then api POST /server/admission "{\"callerId\":\"$id\"}" >/dev/null && info "allow شد: $id"
            else cfg_edit ".admission = ((.admission // []) | if index(\"$id\") then . else . + [\"$id\"] end)"; info "allow شد (فایل): $id"; fi ;;
        disallow)
            local id="$2"; [ -n "$id" ] || { err "استفاده: admission disallow <peerId>"; return 1; }
            if is_running; then api DELETE "/server/admission/$id" >/dev/null && info "حذف شد: $id"
            else cfg_edit ".admission = ((.admission // []) | map(select(. != \"$id\")))"; info "حذف شد (فایل): $id"; fi ;;
        *) err "unknown: $sub"; return 1 ;;
    esac
}

cmd_block() {
    local sub="${1:-list}"
    case "$sub" in
        list)
            if is_running; then api GET /server/blacklist | jq .; else jq '.blacklist' "$CFG"; fi ;;
        add)
            local id="$2"; [ -n "$id" ] || { err "استفاده: block add <peerId>"; return 1; }
            if is_running; then api POST /server/blacklist "{\"callerId\":\"$id\"}" >/dev/null && info "block شد: $id"
            else cfg_edit ".blacklist = ((.blacklist // []) | if index(\"$id\") then . else . + [\"$id\"] end)"; info "block شد (فایل): $id"; fi ;;
        remove)
            local id="$2"; [ -n "$id" ] || { err "استفاده: block remove <peerId>"; return 1; }
            if is_running; then api DELETE "/server/blacklist/$id" >/dev/null && info "آن‌بلاک شد: $id"
            else cfg_edit ".blacklist = ((.blacklist // []) | map(select(. != \"$id\")))"; info "آن‌بلاک شد (فایل): $id"; fi ;;
        *) err "unknown: $sub"; return 1 ;;
    esac
}

cmd_maxclients() {
    local n="$1"
    [ -n "$n" ] || { if is_running; then api GET /server/max-clients | jq .; else jq '.maxClients' "$CFG"; fi; return 0; }
    if is_running; then api POST /server/max-clients "{\"value\":$n}" >/dev/null && info "سقف کلاینت: $n"
    else cfg_edit ".maxClients = $n"; info "سقف کلاینت (فایل): $n"; fi
}

cmd_pending() {
    local sub="${1:-}"
    case "$sub" in
        "") daemon_running_msg && api GET /server/pending | jq . ;;
        accept) api POST "/server/pending/$2/accept" >/dev/null && info "پذیرفته شد: $2" ;;
        reject) api POST "/server/pending/$2/reject" >/dev/null && info "رد شد: $2" ;;
        *) err "استفاده: pending [accept <id>|reject <id>]"; return 1 ;;
    esac
}

cmd_clients() {
    daemon_running_msg || return 1
    hdr "کلاینت‌های متصل"
    api GET /tunnel/clients | jq .
    hdr "وضعیت تونل"
    api GET /tunnel/status | jq .
}

# ----------------------------- status/logs/ui/update/uninstall --------------
cmd_status() {
    if ! is_running; then warn "دیمون متوقف است"; exit 1; fi
    hdr "state"
    api GET /state | jq '{tokenSet, sessionExpired, mode, wsReady, wsPaused, lkActive, sessions, cliTxBytes, cliRxBytes}'
    hdr "config"
    api GET /config | jq .
    hdr "max-clients"
    api GET /server/max-clients | jq .
}

cmd_logs() {
    local n="${1:-50}"
    if ensure_sysd && [ -f "$UNIT_FILE" ]; then
        journalctl -u balevpn.service -n "$n" --no-pager
    else
        tail -n "$n" "$LOG_FILE" 2>/dev/null || { warn "لاگی موجود نیست"; return 0; }
    fi
}

cmd_ui() {
cat <<EOF
رابط وب روی 127.0.0.1:$BALEVPN_PORT بایند شده و از اینترنت قابل دسترس نیست.
برای دسترسی از لپ‌تاپ خودتان:

    ssh -L $BALEVPN_PORT:127.0.0.1:$BALEVPN_PORT user@server

سپس در مرورگر:  http://localhost:$BALEVPN_PORT
(ثبت‌نام SMS، مدیریت لیست مجاز، دیدن کلاینت‌ها از همین UI هم ممکن است)
EOF
}

cmd_update() {
    hdr "به‌روزرسانی"
    local was=0; is_running && was=1 && cmd_service stop
    curl -fSL --progress-bar -o "$BIN.new" \
        "https://github.com/$REPO/releases/latest/download/$BIN_NAME"
    mv -f "$BIN.new" "$BIN" && chmod +x "$BIN"
    info "باینری جدید جایگزین شد"
    [ "$was" = "1" ] && cmd_service start
}

cmd_uninstall() {
    warn "حذف کامل BaleVPN از این سرور؟ [y/N]"; read -r ans
    [ "$ans" = "y" ] || { info "لغو شد"; return 0; }
    cmd_service stop || true
    cmd_service uninstall || true
    rm -rf "$BALEVPN_DIR"
    sudo iptables -t nat -D POSTROUTING -s 10.8.0.0/16 -j MASQUERADE 2>/dev/null || true
    info "حذف شد"
}

# ----------------------------- router --------------------------------------
case "${1:-help}" in
    help|-h|--help)  cmd_help ;;
    install)         shift; cmd_install "$@" ;;
    service)         shift; cmd_service "$@" ;;
    auth)            shift; cmd_auth "$@" ;;
    nat)             shift; cmd_nat "$@" ;;
    admission)       shift; cmd_admission "$@" ;;
    block)           shift; cmd_block "$@" ;;
    maxclients)      shift; cmd_maxclients "$@" ;;
    pending)         shift; cmd_pending "$@" ;;
    clients)         cmd_clients ;;
    status)          cmd_status ;;
    logs)            shift; cmd_logs "$@" ;;
    ui)              cmd_ui ;;
    update)          cmd_update ;;
    uninstall)       cmd_uninstall ;;
    *) err "دستور ناشناخته: $1"; cmd_help; exit 1 ;;
esac
