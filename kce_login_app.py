"""
KCE Lab — Agent Login App v3 (kce_login_app.py)
================================================
• Claude-design UI with custom cursor effect
• Opens in browser automatically on Windows login
• Idle 15 min → beautiful alert: "Hi {name}, I see you've been inactive..."
• Idle 50 min → auto logout
• Tracks sessions in backend DB

Run:     python kce_login_app.py
Install: python kce_login_app.py --install
Remove:  python kce_login_app.py --uninstall
"""

import sys, os, time, json, socket, threading, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import urllib.request, urllib.error

# ── Load .env ─────────────────────────────────────────────────────────────────
_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env):
    with open(_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().split('#')[0].strip())

LAB_ID         = os.getenv('LAB_ID', 'cc1').lower()
SERVER_IP      = os.getenv('SERVER_IP', 'localhost')
SERVER_PORT    = os.getenv('SERVER_PORT', '5000')
MACHINE_LABEL  = os.getenv('MACHINE_LABEL', '').strip() or socket.gethostname()
BASE_URL = "https://kce-lab-backend.onrender.com"
LOCAL_PORT     = 8765
IDLE_WARN_SEC  = 15 * 60   # 15 min
IDLE_LOGOFF_SEC= 50 * 60   # 50 min

state = {
    'session_id':    None,
    'username':      None,
    'login_time':    None,
    'login_ts':      None,
    'last_activity': time.time(),
    'idle_warned':   False,
    'status':        'login',
}

def api_post(path, data):
    url  = f"{BASE_URL}/api{path}"
    body = json.dumps(data).encode()
    req  = urllib.request.Request(url, body, {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:    return json.loads(e.read()), e.code
        except: return {'error': str(e)}, e.code
    except Exception as e:
        return {'error': str(e)}, 0

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return '127.0.0.1'

def idle_checker():
    while True:
        time.sleep(20)
        if not state['session_id']: continue
        idle = time.time() - state['last_activity']
        if idle >= IDLE_LOGOFF_SEC:
            do_auto_logout()
        elif idle >= IDLE_WARN_SEC and not state['idle_warned']:
            state['idle_warned'] = True
            state['status'] = 'warning'
            api_post('/system/idle-alert', {
                'session_id': state['session_id'],
                'idle_minutes': int(idle / 60),
                'alert_type': 'WARNING'
            })

def heartbeat():
    while True:
        time.sleep(60)
        if state['session_id']:
            api_post('/system/heartbeat', {'session_id': state['session_id']})

def do_auto_logout():
    sid = state['session_id']
    state.update({'session_id': None, 'username': None, 'status': 'loggedout', 'idle_warned': False})
    if sid:
        idle_min = int((time.time() - state['last_activity']) / 60)
        api_post('/system/idle-alert', {'session_id': sid, 'idle_minutes': idle_min, 'alert_type': 'AUTO_SHUTDOWN'})
        api_post('/system/logout', {'session_id': sid})

def do_logout():
    sid = state['session_id']
    state.update({'session_id': None, 'username': None, 'status': 'login', 'idle_warned': False})
    if sid:
        api_post('/system/logout', {'session_id': sid})


# ══════════════════════════════════════════════════════════════════════════════
# HTML PAGES — Claude design system
# ══════════════════════════════════════════════════════════════════════════════

CURSOR_JS = """
(function(){
  const dot=document.createElement('div');
  dot.id='kce-dot';
  Object.assign(dot.style,{position:'fixed',top:0,left:0,width:'8px',height:'8px',
    borderRadius:'50%',background:'#1a1917',pointerEvents:'none',zIndex:'99999',
    marginLeft:'-4px',marginTop:'-4px',transform:'translate(-200px,-200px)',
    willChange:'transform',transition:'none'});
  const ring=document.createElement('div');
  ring.id='kce-ring';
  Object.assign(ring.style,{position:'fixed',top:0,left:0,width:'28px',height:'28px',
    borderRadius:'50%',border:'1.5px solid rgba(0,0,0,0.22)',pointerEvents:'none',
    zIndex:'99998',marginLeft:'-14px',marginTop:'-14px',
    transform:'translate(-200px,-200px)',willChange:'transform',
    transition:'width .2s,height .2s,border-color .2s,background .2s'});
  document.body.appendChild(dot);
  document.body.appendChild(ring);
  let rx=-200,ry=-200,mx=-200,my=-200,raf;
  document.addEventListener('mousemove',e=>{
    mx=e.clientX;my=e.clientY;
    dot.style.transform='translate('+mx+'px,'+my+'px)';
  },{passive:true});
  document.addEventListener('mouseover',e=>{
    const el=e.target.closest('button,a,input,select,[role="button"],label');
    if(el){Object.assign(ring.style,{width:'38px',height:'38px',borderColor:'rgba(0,0,0,0.35)',background:'rgba(0,0,0,0.04)'});}
    else{Object.assign(ring.style,{width:'28px',height:'28px',borderColor:'rgba(0,0,0,0.22)',background:'transparent'});}
  },{passive:true});
  (function animate(){
    rx+=(mx-rx)*0.13;ry+=(my-ry)*0.13;
    ring.style.transform='translate('+rx+'px,'+ry+'px)';
    raf=requestAnimationFrame(animate);
  })();
})();
"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>KCE Lab — Sign In</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
*,*::before,*::after{cursor:none!important}
body{font-family:'Inter',sans-serif;background:#f9f9f8;color:#1a1917;min-height:100vh;display:flex;-webkit-font-smoothing:antialiased;font-size:14px;overflow:hidden}
.left{width:320px;flex-shrink:0;background:#fff;border-right:0.5px solid rgba(0,0,0,0.1);padding:36px 30px;display:flex;flex-direction:column;gap:0}
.logo{display:flex;align-items:center;gap:10px;margin-bottom:40px}
.li{width:30px;height:30px;background:#1a1917;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.right{flex:1;display:flex;align-items:center;justify-content:center;padding:36px;background:#f9f9f8}
.card{width:100%;max-width:330px}
.status-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:5px;background:#f0fdf4;border:0.5px solid #bbf7d0;font-size:11px;font-weight:500;color:#16a34a;margin-bottom:22px}
.pulse{width:6px;height:6px;border-radius:50%;background:#16a34a;animation:pa 2s infinite;display:inline-block;flex-shrink:0}
@keyframes pa{0%,100%{opacity:1}50%{opacity:.35}}
h1{font-size:22px;font-weight:500;letter-spacing:-0.4px;margin-bottom:4px;color:#1a1917}
.sub{font-size:13px;color:#9c9a92;margin-bottom:24px;line-height:1.5}
label{display:block;font-size:11px;font-weight:500;color:#5c5b57;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.06em}
.iw{position:relative;margin-bottom:14px}
input{width:100%;height:38px;padding:0 12px;background:#fff;border:0.5px solid rgba(0,0,0,0.18);border-radius:8px;font-size:13.5px;font-family:inherit;color:#1a1917;outline:none;transition:border-color .12s,box-shadow .12s}
input:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,0.09)}
input::placeholder{color:#b4b2a9}
.eye{position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;color:#9c9a92;display:flex;padding:4px}
.forg{text-align:right;margin-bottom:16px}
.forg a{font-size:12px;color:#2563eb;text-decoration:none;font-weight:500}
.forg a:hover{text-decoration:underline}
.err{background:#fef2f2;border:0.5px solid #fecaca;border-radius:8px;padding:9px 12px;color:#dc2626;font-size:12.5px;margin-bottom:13px;display:none;line-height:1.5}
.btn{width:100%;height:40px;background:#1a1917;color:#fff;border:none;border-radius:8px;font-size:13.5px;font-weight:500;font-family:inherit;display:flex;align-items:center;justify-content:center;gap:8px;transition:opacity .15s}
.btn:hover{opacity:.86}
.btn:disabled{opacity:.5}
.sp{width:13px;height:13px;border:1.5px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:none}
@keyframes spin{to{transform:rotate(360deg)}}
.feat{display:flex;align-items:flex-start;gap:9px;padding:9px 11px;background:#f9f9f8;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12px;color:#5c5b57;margin-bottom:6px}
.fd{width:5px;height:5px;border-radius:50%;background:#9c9a92;flex-shrink:0;margin-top:4px}
.foot{margin-top:20px;text-align:center;font-size:11px;color:#b4b2a9}
.info-box{margin-top:18px;padding:11px 13px;background:#fffbeb;border:0.5px solid #fde68a;border-radius:8px;font-size:12px;color:#92400e;line-height:1.75}
</style>
</head>
<body>
<div class="left">
  <div class="logo">
    <div class="li"><svg width="15" height="15" fill="none" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2" stroke="white" stroke-width="2"/><path d="M8 21h8M12 17v4" stroke="white" stroke-width="2" stroke-linecap="round"/></svg></div>
    <div>
      <div style="font-weight:600;font-size:13px;color:#1a1917">KCE Lab Tracker</div>
      <div style="font-size:10.5px;color:#9c9a92;margin-top:1px">Cognentrz Platform</div>
    </div>
  </div>
  <div style="flex:1;display:flex;flex-direction:column;justify-content:center">
    <div style="font-size:22px;font-weight:500;line-height:1.3;letter-spacing:-0.4px;color:#1a1917;margin-bottom:10px">Lab Computer<br>Access Portal</div>
    <div style="font-size:13px;color:#5c5b57;line-height:1.7;margin-bottom:28px">Sign in with your credentials to begin your tracked lab session.</div>
    <div class="feat"><span class="fd"></span><div><div style="font-weight:500;color:#1a1917;margin-bottom:1px">Session tracking</div><div>Login time, duration, machine recorded</div></div></div>
    <div class="feat"><span class="fd"></span><div><div style="font-weight:500;color:#1a1917;margin-bottom:1px">15 min idle alert</div><div>Gentle reminder to stay active</div></div></div>
    <div class="feat"><span class="fd"></span><div><div style="font-weight:500;color:#1a1917;margin-bottom:1px">50 min auto-logout</div><div>Protects your account automatically</div></div></div>
  </div>
  <div style="font-size:10.5px;color:#b4b2a9;font-family:monospace">{LAB_ID_UPPER} &middot; {MACHINE_LABEL}</div>
</div>
<div class="right">
  <div class="card">
    <div class="status-chip"><span class="pulse"></span> System online</div>
    <h1>Sign in</h1>
    <p class="sub">Enter your lab credentials below</p>
    <form onsubmit="doLogin(event)">
      <label>Username</label>
      <div class="iw"><input id="un" type="text" placeholder="your_username" autocomplete="username" required/></div>
      <label>Password</label>
      <div class="iw">
        <input id="pw" type="password" placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;" autocomplete="current-password" required style="padding-right:36px"/>
        <button class="eye" type="button" onclick="togglePwd()"><svg width="14" height="14" fill="none" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/></svg></button>
      </div>
      <div class="forg"><a href="/forgot-password">Forgot password?</a></div>
      <div id="err" class="err"></div>
      <button type="submit" id="btn" class="btn">
        <div class="sp" id="sp"></div><span id="bt">Sign in &rarr;</span>
      </button>
    </form>
    <div class="info-box">&#9888;&#65039; Idle 15 min &rarr; reminder alert<br>&#128274; Idle 50 min &rarr; session auto-ends</div>
    <div class="foot">Developed by <strong style="color:#1a1917">Logesh</strong> &middot; Cognentrz</div>
  </div>
</div>
<script>
function togglePwd(){const p=document.getElementById('pw');p.type=p.type==='password'?'text':'password'}
function setErr(m){const e=document.getElementById('err');e.textContent=m;e.style.display=m?'block':'none'}
function setLoading(v){document.getElementById('sp').style.display=v?'block':'none';document.getElementById('bt').style.display=v?'none':'inline';document.getElementById('btn').disabled=v}
async function doLogin(e){
  e.preventDefault();setErr('');setLoading(true)
  const u=document.getElementById('un').value.trim(),p=document.getElementById('pw').value
  try{
    const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})})
    const d=await r.json()
    if(d.ok){window.location.href='/session'}
    else{setErr(d.error||'Login failed');setLoading(false)}
  }catch{setErr('Cannot connect to server. Check your connection.');setLoading(false)}
}
</script>
<script>CURSOR_PLACEHOLDER</script>
</body>
</html>"""

SESSION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>KCE Lab — Session Active</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
*,*::before,*::after{cursor:none!important}
body{font-family:'Inter',sans-serif;background:#f9f9f8;color:#1a1917;min-height:100vh;-webkit-font-smoothing:antialiased;font-size:14px}

/* ── Idle alert overlay ── */
#idleOverlay{display:none;position:fixed;inset:0;z-index:9000;align-items:center;justify-content:center;background:rgba(249,249,248,0.82);backdrop-filter:blur(4px)}
#idleOverlay.show{display:flex;animation:fadeIn .25s ease}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.alert-card{background:#fff;border:0.5px solid rgba(0,0,0,0.12);border-radius:16px;padding:36px 32px;max-width:400px;width:90%;text-align:center;box-shadow:0 8px 40px rgba(0,0,0,0.08);animation:slideUp .3s ease}
@keyframes slideUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.alert-icon{width:60px;height:60px;border-radius:16px;background:#fffbeb;border:0.5px solid #fde68a;display:flex;align-items:center;justify-content:center;margin:0 auto 18px;font-size:28px}
.alert-title{font-size:19px;font-weight:500;color:#1a1917;letter-spacing:-0.3px;margin-bottom:8px;line-height:1.3}
.alert-sub{font-size:13px;color:#5c5b57;line-height:1.65;margin-bottom:24px}
.countdown-ring{width:72px;height:72px;margin:0 auto 20px;position:relative}
.countdown-ring svg{transform:rotate(-90deg)}
.ring-bg{fill:none;stroke:#f3f4f6;stroke-width:5}
.ring-fill{fill:none;stroke:#d97706;stroke-width:5;stroke-linecap:round;stroke-dasharray:188;stroke-dashoffset:0;transition:stroke-dashoffset 1s linear}
.ring-text{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:500;color:#1a1917;font-family:'JetBrains Mono',monospace}
.alert-btn{width:100%;height:42px;background:#1a1917;color:#fff;border:none;border-radius:9px;font-size:13.5px;font-weight:500;font-family:inherit;display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:10px}
.alert-btn:hover{opacity:.86}
.alert-btn-sec{width:100%;height:38px;background:#fff;color:#5c5b57;border:0.5px solid rgba(0,0,0,0.15);border-radius:9px;font-size:13px;font-weight:400;font-family:inherit}
.alert-btn-sec:hover{background:#f9f9f8}

/* ── Auto-logout overlay ── */
#logoutOverlay{display:none;position:fixed;inset:0;z-index:9999;align-items:center;justify-content:center;background:#f9f9f8}
#logoutOverlay.show{display:flex;animation:fadeIn .3s ease}
.logout-card{text-align:center;max-width:360px;padding:20px}
.logout-icon{width:64px;height:64px;border-radius:16px;background:#fef2f2;border:0.5px solid #fecaca;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;font-size:28px}
.logout-btn{padding:11px 32px;background:#1a1917;color:#fff;border:none;border-radius:9px;font-size:13.5px;font-weight:500;font-family:inherit;margin-top:20px}
.logout-btn:hover{opacity:.86}

/* ── Main session UI ── */
.wrap{max-width:560px;margin:0 auto;padding:28px 20px}
.hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px;padding-bottom:18px;border-bottom:0.5px solid rgba(0,0,0,0.08)}
.logo{display:flex;align-items:center;gap:8px}
.li{width:28px;height:28px;background:#1a1917;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.dot{width:6px;height:6px;border-radius:50%;background:#16a34a;animation:pa 2s infinite;display:inline-block}
@keyframes pa{0%,100%{opacity:1}50%{opacity:.35}}
.logout-link{padding:7px 14px;background:#fef2f2;border:0.5px solid #fecaca;color:#dc2626;border-radius:7px;font-size:12.5px;font-weight:500;font-family:inherit}
.logout-link:hover{background:#fee2e2}
.card{background:#fff;border:0.5px solid rgba(0,0,0,0.1);border-radius:12px;padding:22px;margin-bottom:12px}
.avatar{width:46px;height:46px;border-radius:10px;background:#f9f9f8;border:0.5px solid rgba(0,0,0,0.1);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:600;color:#1a1917;flex-shrink:0}
.timer{font-family:'JetBrains Mono',monospace;font-size:32px;font-weight:500;color:#1a1917;text-align:center;margin:18px 0;letter-spacing:2px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}
.cell{background:#f9f9f8;border:0.5px solid rgba(0,0,0,0.07);border-radius:8px;padding:11px 13px}
.cl{font-size:10px;font-weight:500;color:#9c9a92;text-transform:uppercase;letter-spacing:0.07em;margin-bottom:3px}
.cv{font-size:13px;font-weight:500;color:#1a1917;font-family:'JetBrains Mono',monospace}
.active-btn{width:100%;height:37px;border:0.5px solid rgba(0,0,0,0.12);border-radius:8px;font-size:13px;font-weight:500;font-family:inherit;background:#fff;color:#5c5b57;margin-bottom:8px}
.active-btn:hover{background:#f9f9f8;border-color:rgba(0,0,0,0.2)}
.idle-info{padding:10px 13px;background:#fffbeb;border:0.5px solid #fde68a;border-radius:8px;font-size:12px;color:#92400e;line-height:1.75}
.foot{text-align:center;margin-top:18px;font-size:11px;color:#b4b2a9}
</style>
</head>
<body>

<!-- Idle Alert Overlay -->
<div id="idleOverlay">
  <div class="alert-card">
    <div class="alert-icon">&#128075;</div>
    <div class="alert-title">Hi <span id="alertName">there</span>,<br>are you still there?</div>
    <div class="alert-sub">I've noticed you've been inactive for a while.<br>Your session will auto-end in:</div>
    <div class="countdown-ring">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle class="ring-bg" cx="36" cy="36" r="30"/>
        <circle class="ring-fill" id="ringFill" cx="36" cy="36" r="30"/>
      </svg>
      <div class="ring-text" id="ringText">35</div>
    </div>
    <button class="alert-btn" onclick="iAmHere()">
      <svg width="14" height="14" fill="none" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      I'm here! &mdash; Cognentrz is active
    </button>
    <button class="alert-btn-sec" onclick="doLogout()">Log out now</button>
  </div>
</div>

<!-- Auto-logout Overlay -->
<div id="logoutOverlay">
  <div class="logout-card">
    <div class="logout-icon">&#128274;</div>
    <div style="font-size:22px;font-weight:500;color:#1a1917;margin-bottom:6px;letter-spacing:-0.4px">Session ended</div>
    <div style="font-size:13px;color:#9c9a92;line-height:1.65">Automatically logged out after 50 minutes of inactivity. This session has been recorded.</div>
    <button class="logout-btn" onclick="window.location.href='/'">Sign in again &rarr;</button>
  </div>
</div>

<!-- Main UI -->
<div class="wrap">
  <div class="hd">
    <div class="logo">
      <div class="li"><svg width="14" height="14" fill="none" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2" stroke="white" stroke-width="2"/><path d="M8 21h8M12 17v4" stroke="white" stroke-width="2" stroke-linecap="round"/></svg></div>
      <div>
        <div style="font-weight:600;font-size:13px;color:#1a1917">KCE Lab Tracker</div>
        <div style="font-size:10.5px;color:#9c9a92">Cognentrz Platform</div>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:10px">
      <div style="display:flex;align-items:center;gap:5px;font-size:11.5px;font-weight:500;color:#16a34a"><span class="dot"></span>Session active</div>
      <button class="logout-link" onclick="doLogout()">&#9167; Logout</button>
    </div>
  </div>

  <div class="card">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px;padding-bottom:16px;border-bottom:0.5px solid rgba(0,0,0,0.06)">
      <div class="avatar" id="av">?</div>
      <div>
        <div style="font-size:17px;font-weight:500;color:#1a1917;letter-spacing:-0.3px" id="welcome">Welcome!</div>
        <div style="font-size:11.5px;color:#9c9a92;margin-top:2px">Lab session in progress</div>
      </div>
    </div>
    <div class="timer" id="timerVal">00:00:00</div>
    <div class="grid">
      <div class="cell"><div class="cl">Machine</div><div class="cv">{MACHINE_LABEL}</div></div>
      <div class="cell"><div class="cl">Lab</div><div class="cv">{LAB_ID_UPPER}</div></div>
      <div class="cell"><div class="cl">Login time</div><div class="cv" id="loginTimeVal">—</div></div>
      <div class="cell"><div class="cl">Duration</div><div class="cv" style="color:#2563eb" id="durText">0m</div></div>
    </div>
    <button class="active-btn" onclick="iAmHere()">&#10003; I'm active — reset idle timer</button>
    <div class="idle-info">&#9888;&#65039; Idle 15 min &rarr; alert appears &nbsp;&nbsp;&nbsp; &#128274; Idle 50 min &rarr; auto logout</div>
  </div>
  <div class="foot">Developed by <strong style="color:#1a1917">Logesh</strong> &middot; Cognentrz</div>
</div>

<script>
const WARN_MS={IDLE_WARN_MS}, LOGOFF_MS={IDLE_LOGOFF_MS};
let lastActivity=Date.now(), warned=false, loginTs=Date.now(), alive=true;

['mousemove','keydown','click','scroll','touchstart'].forEach(ev=>
  window.addEventListener(ev,()=>{
    lastActivity=Date.now();
    if(warned){iAmHere();}
  },{passive:true})
);

function checkIdle(){
  if(!alive)return;
  const idle=Date.now()-lastActivity;
  const remaining=Math.max(0,Math.ceil((LOGOFF_MS-idle)/60000));
  // Update countdown ring
  const pct=Math.max(0,(LOGOFF_MS-idle)/LOGOFF_MS);
  document.getElementById('ringFill').style.strokeDashoffset=188*(1-pct);
  document.getElementById('ringText').textContent=remaining+'m';
  if(idle>=LOGOFF_MS && alive){
    alive=false;
    fetch('/auto-logout',{method:'POST'}).catch(()=>{});
    document.getElementById('idleOverlay').classList.remove('show');
    document.getElementById('logoutOverlay').classList.add('show');
  } else if(idle>=WARN_MS && !warned){
    warned=true;
    document.getElementById('idleOverlay').classList.add('show');
    fetch('/warn',{method:'POST'}).catch(()=>{});
  }
}
setInterval(checkIdle,10000);

function updateTimer(){
  const secs=Math.floor((Date.now()-loginTs)/1000);
  const h=Math.floor(secs/3600), m=Math.floor(secs%3600/60), s=secs%60;
  document.getElementById('timerVal').textContent=
    String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
  const mins=Math.floor(secs/60);
  document.getElementById('durText').textContent=h>0?`${h}h ${m}m`:`${mins}m`;
}
setInterval(updateTimer,1000);

function iAmHere(){
  lastActivity=Date.now(); warned=false;
  document.getElementById('idleOverlay').classList.remove('show');
  fetch('/active',{method:'POST'}).catch(()=>{});
}

function doLogout(){
  if(!confirm('Log out of your lab session now?'))return;
  fetch('/logout',{method:'POST'}).then(()=>window.location.href='/');
}

fetch('/state').then(r=>r.json()).then(d=>{
  if(!d.username){window.location.href='/';return;}
  document.getElementById('welcome').textContent='Welcome, '+d.username;
  document.getElementById('av').textContent=d.username[0].toUpperCase();
  document.getElementById('alertName').textContent=d.username;
  document.getElementById('loginTimeVal').textContent=d.login_time||'—';
  if(d.login_ts) loginTs=d.login_ts*1000;
});
</script>
<script>CURSOR_PLACEHOLDER</script>
</body>
</html>"""

FORGOT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>KCE Lab — Reset Password</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
*,*::before,*::after{cursor:none!important}
body{font-family:'Inter',sans-serif;background:#f9f9f8;color:#1a1917;min-height:100vh;display:flex;align-items:center;justify-content:center;-webkit-font-smoothing:antialiased;padding:20px}
.card{background:#fff;border:0.5px solid rgba(0,0,0,0.1);border-radius:12px;padding:30px;width:100%;max-width:370px}
.back{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:#9c9a92;text-decoration:none;margin-bottom:22px;font-weight:500}
.back:hover{color:#1a1917}
h1{font-size:20px;font-weight:500;margin-bottom:4px;letter-spacing:-0.3px}
.sub{font-size:12.5px;color:#9c9a92;margin-bottom:22px;line-height:1.6}
label{display:block;font-size:11px;font-weight:500;color:#5c5b57;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.06em}
.iw{position:relative;margin-bottom:14px}
input{width:100%;height:38px;padding:0 12px;background:#fff;border:0.5px solid rgba(0,0,0,0.18);border-radius:8px;font-size:13.5px;font-family:inherit;color:#1a1917;outline:none;transition:border-color .12s,box-shadow .12s}
input:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,0.09)}
input::placeholder{color:#b4b2a9}
.eye{position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;color:#9c9a92;display:flex;padding:4px}
.err{background:#fef2f2;border:0.5px solid #fecaca;border-radius:8px;padding:9px 12px;color:#dc2626;font-size:12.5px;margin-bottom:13px;display:none}
.ok{background:#f0fdf4;border:0.5px solid #bbf7d0;border-radius:8px;padding:16px;font-size:13px;color:#16a34a;text-align:center;display:none}
.btn{width:100%;height:40px;background:#1a1917;color:#fff;border:none;border-radius:8px;font-size:13.5px;font-weight:500;font-family:inherit;display:flex;align-items:center;justify-content:center;gap:8px;margin-top:4px}
.btn:hover{opacity:.86}
.btn:disabled{opacity:.5}
.sp{width:13px;height:13px;border:1.5px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:none}
@keyframes spin{to{transform:rotate(360deg)}}
.foot{margin-top:18px;text-align:center;font-size:11px;color:#b4b2a9}
</style>
</head>
<body>
<div class="card">
  <a href="/" class="back">
    <svg width="12" height="12" fill="none" viewBox="0 0 24 24"><path d="M19 12H5M12 5l-7 7 7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    Back to login
  </a>
  <h1>Reset password</h1>
  <p class="sub">Enter your username and a new password. No email needed — updates instantly.</p>
  <div id="okBox" class="ok" style="margin-bottom:16px">
    <div style="font-size:22px;margin-bottom:8px">&#9989;</div>
    <div style="font-weight:500;font-size:15px;margin-bottom:4px">Password updated!</div>
    <div style="font-size:12.5px;margin-bottom:14px">You can now sign in with your new password.</div>
    <a href="/" style="display:inline-block;padding:9px 22px;background:#1a1917;color:#fff;border-radius:8px;font-size:13px;font-weight:500;text-decoration:none">Login now &rarr;</a>
  </div>
  <div id="formArea">
    <label>Username</label>
    <div class="iw"><input id="un" type="text" placeholder="Enter your username" autocomplete="username"/></div>
    <label>New password</label>
    <div class="iw">
      <input id="np" type="password" placeholder="Min. 4 characters" style="padding-right:36px"/>
      <button class="eye" type="button" onclick="toggle('np')"><svg width="14" height="14" fill="none" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/></svg></button>
    </div>
    <label>Confirm password</label>
    <div class="iw">
      <input id="cp" type="password" placeholder="Re-enter new password" style="padding-right:36px"/>
      <button class="eye" type="button" onclick="toggle('cp')"><svg width="14" height="14" fill="none" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/></svg></button>
    </div>
    <div id="err" class="err"></div>
    <button id="btn" class="btn" onclick="doReset()">
      <div class="sp" id="sp"></div><span id="bt">Update password &rarr;</span>
    </button>
  </div>
  <div class="foot">Developed by <strong style="color:#1a1917">Logesh</strong> &middot; Cognentrz</div>
</div>
<script>
function toggle(id){const f=document.getElementById(id);f.type=f.type==='password'?'text':'password'}
function setErr(m){const e=document.getElementById('err');e.textContent=m;e.style.display=m?'block':'none'}
function setLoading(v){document.getElementById('sp').style.display=v?'block':'none';document.getElementById('bt').style.display=v?'none':'inline';document.getElementById('btn').disabled=v}
async function doReset(){
  setErr('');
  const u=document.getElementById('un').value.trim(),n=document.getElementById('np').value,c=document.getElementById('cp').value;
  if(!u){setErr('Enter your username');return}
  if(!n||n.length<4){setErr('Password must be at least 4 characters');return}
  if(n!==c){setErr('Passwords do not match');return}
  setLoading(true);
  try{
    const r=await fetch('/forgot-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,new_password:n})});
    const d=await r.json();
    if(d.ok){document.getElementById('formArea').style.display='none';document.getElementById('okBox').style.display='block'}
    else{setErr(d.error||'Reset failed — check your username');setLoading(false)}
  }catch{setErr('Connection error — is the server running?');setLoading(false)}
}
document.addEventListener('keydown',e=>{if(e.key==='Enter')doReset()});
</script>
<script>CURSOR_PLACEHOLDER</script>
</body>
</html>"""


# ── HTTP Handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_html(self, html, code=200):
        html = html.replace('CURSOR_PLACEHOLDER', CURSOR_JS)
        b = html.encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(b))
        self.end_headers()
        self.wfile.write(b)

    def send_json(self, data, code=200):
        b = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(b))
        self.end_headers()
        self.wfile.write(b)

    def read_json(self):
        n = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/login'):
            if state['session_id']:
                self.send_response(302); self.send_header('Location', '/session'); self.end_headers()
            else:
                html = LOGIN_HTML.replace('{LAB_ID_UPPER}', LAB_ID.upper()).replace('{MACHINE_LABEL}', MACHINE_LABEL)
                self.send_html(html)
        elif path in ('/forgot-password', '/reset-password'):
            self.send_html(FORGOT_HTML)
        elif path == '/session':
            if not state['session_id']:
                self.send_response(302); self.send_header('Location', '/'); self.end_headers()
            else:
                html = SESSION_HTML \
                    .replace('{MACHINE_LABEL}', MACHINE_LABEL) \
                    .replace('{LAB_ID_UPPER}', LAB_ID.upper()) \
                    .replace('{IDLE_WARN_MS}', str(IDLE_WARN_SEC * 1000)) \
                    .replace('{IDLE_LOGOFF_MS}', str(IDLE_LOGOFF_SEC * 1000))
                self.send_html(html)
        elif path == '/state':
            self.send_json({
                'username':   state['username'],
                'login_time': state['login_time'],
                'login_ts':   state.get('login_ts') or time.time(),
                'status':     state['status'],
            })
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        d    = self.read_json()

        if path == '/login':
            uname = d.get('username', '').strip()
            pwd   = d.get('password', '').strip()
            data, status = api_post('/system/login', {
                'username': uname, 'password': pwd,
                'lab_id': LAB_ID, 'machine_label': MACHINE_LABEL,
                'ip_address': get_ip(),
            })
            if status in (200, 201) and (data.get('ok') or data.get('token')):
                state.update({
                    'session_id':    data.get('session_id'),
                    'username':      uname,
                    'login_time':    time.strftime('%I:%M:%S %p'),
                    'login_ts':      time.time(),
                    'last_activity': time.time(),
                    'idle_warned':   False,
                    'status':        'active',
                })
                self.send_json({'ok': True})
            else:
                err = data.get('error', 'Login failed')
                if status == 401: err = 'Invalid username or password.'
                elif status == 403: err = 'Account disabled. Contact your lab admin.'
                elif status == 0: err = 'Cannot reach server. Check your network connection.'
                self.send_json({'ok': False, 'error': err}, 401)

        elif path in ('/forgot-password', '/reset-password'):
            data, status = api_post('/system/forgot-password', {
                'username': d.get('username', '').strip(),
                'new_password': d.get('new_password', '').strip()
            })
            self.send_json(data, status or 200)

        elif path == '/logout':
            do_logout(); self.send_json({'ok': True})

        elif path == '/auto-logout':
            do_auto_logout(); self.send_json({'ok': True})

        elif path == '/warn':
            state['status'] = 'warning'; state['idle_warned'] = True
            self.send_json({'ok': True})

        elif path == '/active':
            state['last_activity'] = time.time()
            state['idle_warned']   = False
            state['status']        = 'active'
            self.send_json({'ok': True})

        else:
            self.send_response(404); self.end_headers()


# ── Windows startup installer ──────────────────────────────────────────────────
def install_startup():
    try:
        import winreg
        script = os.path.abspath(__file__)
        cmd    = f'"{sys.executable}" "{script}"'
        key    = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                     r'Software\Microsoft\Windows\CurrentVersion\Run',
                     0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'KCELabLogin', 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        print(f'Installed to Windows startup: {cmd}')
    except Exception as e:
        print(f'Install failed: {e}')

def uninstall_startup():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                 r'Software\Microsoft\Windows\CurrentVersion\Run',
                 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, 'KCELabLogin')
        winreg.CloseKey(key)
        print('Removed from Windows startup.')
    except Exception as e:
        print(f'Uninstall failed: {e}')


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if '--install'   in sys.argv: install_startup();   sys.exit()
    if '--uninstall' in sys.argv: uninstall_startup(); sys.exit()

    print(f'KCE Login App v3  |  http://localhost:{LOCAL_PORT}')
    print(f'Lab: {LAB_ID.upper()}  |  Machine: {MACHINE_LABEL}')
    print(f'Backend: {BASE_URL}')
    print()

    threading.Thread(target=idle_checker, daemon=True).start()
    threading.Thread(target=heartbeat,    daemon=True).start()

    server     = HTTPServer(('127.0.0.1', LOCAL_PORT), Handler)
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    time.sleep(0.4)
    webbrowser.open(f'http://localhost:{LOCAL_PORT}/')

    print('Browser opened. Minimize this window — tracking continues in background.')
    print('Press Ctrl+C to stop.')
    print()

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print('Stopping...')
        if state['session_id']: do_logout()
        server.shutdown()
