import os
import cv2
import json
import time
import base64
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_from_directory, Response, session, redirect, url_for

app = Flask(__name__)
app.secret_key = "cyber_exhibit_secret_key"

# --- Configuration & Setup ---
CAUGHT_DIR = os.path.join(os.getcwd(), "caught_visitors")
if not os.path.exists(CAUGHT_DIR):
    os.makedirs(CAUGHT_DIR)

# Initialize Camera and Face Detector
camera = cv2.VideoCapture(0)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# --- Statistics Tracking ---
stats = {
    "total_visitors": 0,
    "emails_inspected": 0,
    "safe_clicks": 0,
    "phished_clicks": 0
}

def generate_frames():
    """Live video stream generator."""
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# --- Mock Inbox Data ---
EMAILS = [
    {
        "id": 1,
        "sender_name": "PayPal Security",
        "sender_email": "security@paypa1-support.com",
        "subject": "Action Required: Your account has been limited",
        "snippet": "We noticed an unusual login attempt from a new location.",
        "body_html": """
            <p>Dear Valued Customer,</p>
            <div style="background:#fef7f6; border-left:4px solid #d93025; padding:15px; margin:20px 0;">
                <strong>Security Alert:</strong> A login attempt was detected from Moscow, Russia.
            </div>
            <p>For your protection, we have temporarily limited your account. Please verify your identity now to restore access.</p>
            <button class="cta-btn">Verify Identity Now</button>
        """,
        "is_phish": True,
        "red_flags": "The sender domain is 'paypa1.com' (with a number '1'), and the message uses fear/urgency to bypass your critical thinking."
    },
    {
        "id": 2,
        "sender_name": "Discord Developer Team",
        "sender_email": "dev-alerts@discord-app-portal.com",
        "subject": "ACTION REQUIRED: Bot API Token Revocation",
        "snippet": "Your application 'GreashBot' is scheduled for deletion.",
        "body_html": """
            <p>Hello Developer,</p>
            <p>During a routine security audit, we detected that your Bot API Token for <strong>'GreashBot'</strong> has been leaked to a public repository.</p>
            <p>Failure to re-authenticate will result in the <strong>permanent deletion</strong> of your application within 12 hours.</p>
            <button class="cta-btn" style="background:#5865F2;">Authenticate Developer Portal</button>
        """,
        "is_phish": True,
        "red_flags": "Threatening to delete your work 'permanently' in a short timeframe is a classic tactic to induce panic."
    },
    {
        "id": 3,
        "sender_name": "Sri Desa Administration",
        "sender_email": "admin@sridesa-edu.my-portal.com",
        "subject": "URGENT: Missing Registration Document",
        "snippet": "Final notice regarding your student enrollment file.",
        "body_html": """
            <p>Attention Student,</p>
            <p>Our records indicate that your <strong>Form E-102 (Student Health Declaration)</strong> is missing from your enrollment file.</p>
            <p>Access the student portal immediately to upload the digital copy to avoid a late processing fee.</p>
            <button class="cta-btn" style="background:#800000;">Access Student Portal</button>
        """,
        "is_phish": True,
        "red_flags": "The sender email 'my-portal.com' is not a legitimate school domain. Always check the official '.edu' suffix."
    },
    {
        "id": 4,
        "sender_name": "Riot Games",
        "sender_email": "no-reply@riot-vct-beta.com",
        "subject": "You're Invited: Exclusive VCT Beta Access",
        "snippet": "You have been selected for the VALORANT Champions Tour Beta.",
        "body_html": """
            <p>AGENT,</p>
            <p>Congratulations! You have been randomly selected to participate in the <strong>Exclusive VCT Premier Beta</strong>.</p>
            <p>This invite includes exclusive player cards and early access to the new Shanghai map.</p>
            <button class="cta-btn" style="background:#ff4655;">Claim Your Access</button>
        """,
        "is_phish": True,
        "red_flags": "Phishers love 'Exclusive' scenarios. The domain 'riot-vct-beta.com' is not the official 'riotgames.com'."
    },
    {
        "id": 5,
        "sender_name": "Lens & Shutter Store",
        "sender_email": "receipts@lens-shutter.com",
        "subject": "Digital Receipt: Order #99102",
        "snippet": "Thank you for your purchase from Lens & Shutter.",
        "body_html": """
            <p>Thank you for shopping with us! Your order #99102 has been processed.</p>
            <table style="width:100%; margin:20px 0; border-top:1px solid #eee;">
                <tr><td style="padding:10px;">Accsoon CineView HE Wireless Transmitter</td><td style="text-align:right;">$349.00</td></tr>
            </table>
            <button class="cta-btn" style="background:#333;">Download PDF Invoice</button>
        """,
        "is_phish": False,
        "safe_reasons": "The sender domain lens-shutter.com is legitimate, the tone is routine, and the transaction details are specific to your activity."
    },
    {
        "id": 6,
        "sender_name": "Production Lead",
        "sender_email": "maya@indie-film-studio.com",
        "subject": "Re: Short Film Production Schedule - Draft 2",
        "snippet": "Updated call times for the Friday shoot.",
        "body_html": """
            <p>Hi all, I've updated the call times for Friday's shoot. We're starting at 06:00 to catch the morning light.</p>
            <p>Please check the latest script changes in the doc below.</p>
            <button class="cta-btn" style="background:#2ea44f;">View Google Doc Script</button>
        """,
        "is_phish": False,
        "safe_reasons": "This is a standard internal thread. The sender is a known contact, and the request for collaboration is expected."
    },
    {
        "id": 7,
        "sender_name": "WebDev Weekly",
        "sender_email": "newsletter@vite-react-news.dev",
        "subject": "Vite 6.0 & React 19: What you need to know",
        "snippet": "Deep dive into the new compiler features and performance...",
        "body_html": """
            <h3>Issue #142: The Future of Frontend</h3>
            <p>In this issue, we dive deep into the new compiler features and performance improvements in Vite 6.0.</p>
            <button class="cta-btn" style="background:#646cff;">Read Full Changelog</button>
        """,
        "is_phish": False,
        "safe_reasons": "Newsletter domains are common and informative. The content lacks urgency and doesn't ask for sensitive credentials."
    }
]

# --- Routes ---

@app.route("/")
def index():
    """Main interactive email client."""
    stats["total_visitors"] += 1
    return render_template_string(INDEX_HTML, emails=EMAILS, emails_json=json.dumps(EMAILS))

@app.route("/caught")
def caught():
    """Educational breakdown screen."""
    phish_id = session.get('last_email_id', 1)
    email = next((e for e in EMAILS if e['id'] == phish_id), EMAILS[0])
    return render_template_string(CAUGHT_HTML, email=email)

@app.route("/safe")
def safe():
    """Success feedback screen."""
    stats["safe_clicks"] += 1
    safe_id = session.get('last_email_id', 5)
    email = next((e for e in EMAILS if e['id'] == safe_id), EMAILS[4])
    return render_template_string(SAFE_HTML, email=email)

@app.route("/carousel")
def carousel():
    """Public 'Wall of Phished' live gallery."""
    return render_template_string(CAROUSEL_HTML)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Admin passcode entry."""
    if request.method == "POST":
        if request.form.get("passcode") == "4344":
            session["admin_auth"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template_string(LOGIN_HTML, error="Incorrect Passcode")
    return render_template_string(LOGIN_HTML)

@app.route("/admin")
def admin_dashboard():
    """Live monitor, statistics, and private gallery."""
    if not session.get("admin_auth"):
        return redirect(url_for("admin_login"))
    
    images = sorted(os.listdir(CAUGHT_DIR), reverse=True)
    images = [img for img in images if img.endswith(".jpg")]
    return render_template_string(ADMIN_HTML, images=images, stats=stats)

@app.route("/admin/delete/<filename>")
def delete_image(filename):
    """Delete a phished photo."""
    if not session.get("admin_auth"):
        return redirect(url_for("admin_login"))
    
    filepath = os.path.join(CAUGHT_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def logout():
    session.pop("admin_auth", None)
    return redirect(url_for("index"))

# --- API & Stream ---

@app.route("/video_feed")
def video_feed():
    """Live MJPEG stream for the admin monitor."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/api/images")
def get_images():
    """Returns a JSON list of all saved image URLs for the carousel."""
    images = sorted(os.listdir(CAUGHT_DIR), reverse=True)
    image_urls = [f"/images/{img}" for img in images if img.endswith(".jpg")]
    return jsonify(image_urls)

@app.route("/api/capture", methods=["POST"])
def capture():
    """Triggers server-side camera capture with face detection."""
    try:
        data = request.json
        session['last_email_id'] = data.get('id')
        stats["phished_clicks"] += 1
        
        success, frame = camera.read()
        if success:
            # Face Detection Logic (Strict Settings)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, 
                scaleFactor=1.2, 
                minNeighbors=6, 
                minSize=(100, 100)
            )
            
            # Draw green bounding boxes
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"phished_{timestamp}.jpg"
            filepath = os.path.join(CAUGHT_DIR, filename)
            cv2.imwrite(filepath, frame)
            
            return jsonify({"status": "success"}), 201
        return jsonify({"status": "error", "message": "Camera failure"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/track_inspect", methods=["POST"])
def track_inspect():
    """Logs when an email is viewed."""
    stats["emails_inspected"] += 1
    return jsonify({"status": "success"})

@app.route("/api/set_session", methods=["POST"])
def set_session():
    """Prepares session for safe interaction."""
    data = request.json
    session['last_email_id'] = data.get('id')
    return jsonify({"status": "success"})

@app.route("/images/<path:filename>")
def serve_image(filename):
    """Serves images from the caught_visitors directory."""
    return send_from_directory(CAUGHT_DIR, filename)

# --- Templates ---

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SecureMail - Educational Kiosk</title>
    <style>
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { margin: 0; background: #f6f8fc; display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 260px; background: white; border-right: 1px solid #ddd; padding: 20px 0; }
        .nav-item { padding: 10px 25px; color: #444; cursor: pointer; font-size: 14px; }
        .nav-item.active { background: #e8f0fe; color: #1a73e8; border-radius: 0 20px 20px 0; font-weight: bold; }
        .list-pane { width: 400px; background: white; border-right: 1px solid #ddd; overflow-y: auto; }
        .email-item { padding: 15px 20px; border-bottom: 1px solid #f1f1f1; cursor: pointer; }
        .email-item:hover { background: #f8f9fa; }
        .sender { font-size: 14px; margin-bottom: 4px; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .subject { font-size: 13px; color: #202124; margin-bottom: 4px; }
        .snippet { font-size: 12px; color: #5f6368; font-weight: normal; }
        .reading-pane { flex-grow: 1; background: white; padding: 40px 60px; overflow-y: auto; }
        .view-subject { font-size: 24px; color: #202124; margin-bottom: 25px; }
        .view-header { border-bottom: 1px solid #eee; padding-bottom: 20px; margin-bottom: 25px; display: flex; align-items: center; }
        .avatar { width: 45px; height: 45px; border-radius: 50%; background: #ccc; margin-right: 15px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 20px; }
        .view-body { line-height: 1.6; font-size: 15px; color: #3c4043; }
        .cta-btn { background: #1a73e8; color: white; border: none; padding: 12px 28px; border-radius: 4px; cursor: pointer; font-size: 15px; margin-top: 30px; font-weight: 500; }
        .cta-btn:hover { opacity: 0.9; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="nav-item active">Inbox ({{ emails|length }})</div>
        <div class="nav-item">Sent</div>
        <div class="nav-item">Drafts</div>
    </div>
    <div class="list-pane">
        {% for email in emails %}
        <div class="email-item" onclick="viewEmail({{ email.id }})">
            <span class="sender">{{ email.sender_name }}</span>
            <div class="subject">{{ email.subject }}</div>
            <div class="snippet">{{ email.snippet }}</div>
        </div>
        {% endfor %}
    </div>
    <div id="reading-pane" class="reading-pane">
        <div id="welcome-msg" style="height: 100%; display: flex; align-items: center; justify-content: center; color: #888;">Select an email to read</div>
        <div id="email-content" style="display: none;">
            <h1 id="view-subject" class="view-subject"></h1>
            <div class="view-header">
                <div id="view-avatar" class="avatar"></div>
                <div class="sender-details">
                    <strong id="view-sender-name"></strong> 
                    <span id="view-sender-email" style="color: #5f6368; font-size: 13px; margin-left: 5px;"></span>
                </div>
            </div>
            <div id="view-body" class="view-body"></div>
        </div>
    </div>

    <script>
        const emails = {{ emails_json | safe }};
        function viewEmail(id) {
            const email = emails.find(e => e.id === id);
            if (!email) return;

            // Track inspection
            fetch('/api/track_inspect', { method: 'POST' });

            document.getElementById('welcome-msg').style.display = 'none';
            document.getElementById('email-content').style.display = 'block';
            document.getElementById('view-subject').innerText = email.subject;
            document.getElementById('view-sender-name').innerText = email.sender_name;
            document.getElementById('view-sender-email').innerText = `<${email.sender_email}>`;
            document.getElementById('view-avatar').innerText = email.sender_name[0];
            document.getElementById('view-body').innerHTML = email.body_html;

            const btn = document.querySelector('#view-body .cta-btn');
            if (btn) {
                btn.onclick = async () => {
                    if (email.is_phish) {
                        await fetch('/api/capture', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ id: email.id })
                        });
                        window.location.href = '/caught';
                    } else {
                        await fetch('/api/set_session', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ id: email.id })
                        });
                        window.location.href = '/safe';
                    }
                };
            }
        }
    </script>
</body>
</html>
"""

CAUGHT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>YOU'VE BEEN PHISHED!</title>
    <style>
        body { background: #000; color: white; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
        .container { max-width: 700px; padding: 40px; border: 5px solid #ff4d4d; border-radius: 20px; background: #111; box-shadow: 0 0 50px rgba(255,77,77,0.3); }
        h1 { font-size: 50px; color: #ff4d4d; margin-top: 0; text-transform: uppercase; }
        p { font-size: 18px; line-height: 1.6; color: #ccc; }
        .fact-box { background: #222; padding: 25px; border-radius: 10px; text-align: left; margin: 30px 0; border-left: 5px solid #ff4d4d; }
        .btn { background: #ff4d4d; color: white; border: none; padding: 15px 40px; font-size: 18px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: 0.2s; }
        .btn:hover { background: #e60000; transform: scale(1.05); }
    </style>
</head>
<body>
    <div class="container">
        <h1>YOU'VE BEEN PHISHED!</h1>
        <p>You just clicked on a malicious link in the "{{ email.subject }}" email.</p>
        <div class="fact-box"><strong>WHY THIS WAS A TRAP:</strong><br><br>{{ email.red_flags }}</div>
        <button class="btn" onclick="window.location.href='/'">Return to Exhibit</button>
    </div>
</body>
</html>
"""

SAFE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SAFE - GOOD CATCH!</title>
    <style>
        body { background: #000; color: white; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }
        .container { max-width: 700px; padding: 40px; border: 5px solid #2ea44f; border-radius: 20px; background: #111; box-shadow: 0 0 50px rgba(46,164,79,0.3); }
        h1 { font-size: 50px; color: #2ea44f; margin-top: 0; text-transform: uppercase; }
        p { font-size: 18px; line-height: 1.6; color: #ccc; }
        .fact-box { background: #222; padding: 25px; border-radius: 10px; text-align: left; margin: 30px 0; border-left: 5px solid #2ea44f; }
        .btn { background: #2ea44f; color: white; border: none; padding: 15px 40px; font-size: 18px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: 0.2s; }
        .btn:hover { background: #288f44; transform: scale(1.05); }
    </style>
</head>
<body>
    <div class="container">
        <h1>SAFE - GOOD CATCH!</h1>
        <p>You correctly identified that "{{ email.subject }}" was a legitimate email.</p>
        <div class="fact-box"><strong>WHY THIS WAS SAFE:</strong><br><br>{{ email.safe_reasons }}</div>
        <button class="btn" onclick="window.location.href='/'">Return to Inbox</button>
    </div>
</body>
</html>
"""

CAROUSEL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CAUGHT BY THE PHISH</title>
    <style>
        body { background-color: #050505; color: white; font-family: sans-serif; margin: 0; overflow: hidden; }
        .header { background: linear-gradient(90deg, #ff4d4d, #000); padding: 20px; text-align: center; border-bottom: 2px solid #ff4d4d; }
        h1 { margin: 0; font-size: 2.5rem; color: #fff; }
        .grid { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; padding: 40px; overflow-y: auto; height: calc(100vh - 100px); }
        .card { width: 300px; height: 350px; background: #111; border: 1px solid #333; border-radius: 10px; overflow: hidden; transition: 0.5s; }
        .card img { width: 100%; height: 280px; object-fit: cover; }
        .card .info { padding: 15px; font-family: monospace; color: #ff4d4d; text-align: center; }
        .card:first-child { border: 2px solid #ff4d4d; transform: scale(1.05); }
    </style>
</head>
<body>
    <div class="header"><h1>CAUGHT BY THE PHISH - EXHIBIT</h1></div>
    <div id="image-grid" class="grid"></div>
    <script>
        let currentImages = [];
        async function updateImages() {
            try {
                const response = await fetch('/api/images');
                const images = await response.json();
                if (JSON.stringify(images) !== JSON.stringify(currentImages)) {
                    currentImages = images;
                    const grid = document.getElementById('image-grid');
                    grid.innerHTML = images.map(url => `
                        <div class="card"><img src="${url}"><div class="info">PHISHED VISITOR</div></div>
                    `).join('');
                }
            } catch (err) { console.error(err); }
        }
        setInterval(updateImages, 3000);
        updateImages();
    </script>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Admin Login</title></head>
<body style="font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; background:#eee;">
    <form method="POST" style="background:white; padding:40px; border-radius:10px; box-shadow:0 5px 15px rgba(0,0,0,0.1);">
        <h2>Admin Access</h2>
        {% if error %}<p style="color:red;">{{ error }}</p>{% endif %}
        <input type="password" name="passcode" placeholder="Enter Passcode" style="padding:10px; width:100%; margin-bottom:15px; border:1px solid #ddd;">
        <button type="submit" style="width:100%; padding:10px; background:#333; color:white; border:none; border-radius:4px; cursor:pointer;">Login</button>
    </form>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Dashboard</title>
    <style>
        body { font-family: sans-serif; margin: 0; background: #f0f2f5; }
        .header { background: #333; color: white; padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; }
        .container { padding: 30px; }
        
        /* Stats Styles */
        .stats-row { display: flex; gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; flex: 1; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-align: center; }
        .stat-card h4 { margin: 0; color: #666; font-size: 14px; text-transform: uppercase; }
        .stat-card p { margin: 10px 0 0; font-size: 28px; font-weight: bold; color: #1a73e8; }
        .stat-phished { color: #d93025 !important; }
        .stat-safe { color: #188038 !important; }

        .dashboard-content { display: flex; gap: 30px; }
        .monitor { background: white; padding: 20px; border-radius: 10px; flex: 1; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .gallery { flex: 2; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 15px; margin-top: 20px; }
        .photo-card { border: 1px solid #eee; border-radius: 8px; overflow: hidden; position: relative; }
        .photo-card img { width: 100%; height: 130px; object-fit: cover; }
        .delete-btn { position: absolute; top: 5px; right: 5px; background: rgba(255,0,0,0.8); color: white; border: none; border-radius: 4px; padding: 5px 10px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="header">
        <h1>EXHIBIT CONTROL CENTER</h1>
        <a href="/admin/logout" style="color:white; text-decoration:none;">Logout</a>
    </div>
    <div class="container">
        <!-- Statistics Section -->
        <div class="stats-row">
            <div class="stat-card"><h4>Total Visitors</h4><p>{{ stats.total_visitors }}</p></div>
            <div class="stat-card"><h4>Emails Read</h4><p>{{ stats.emails_inspected }}</p></div>
            <div class="stat-card"><h4>Safe Clicks</h4><p class="stat-safe">{{ stats.safe_clicks }}</p></div>
            <div class="stat-card"><h4>Phished</h4><p class="stat-phished">{{ stats.phished_clicks }}</p></div>
        </div>

        <div class="dashboard-content">
            <div class="monitor">
                <h3>Live Feed</h3>
                <img src="/video_feed" style="width:100%; border-radius:5px; background:#000;">
            </div>
            <div class="gallery">
                <h3>Captured Visitors ({{ images|length }})</h3>
                <div class="grid">
                    {% for img in images %}
                    <div class="photo-card">
                        <img src="/images/{{ img }}">
                        <button class="delete-btn" onclick="if(confirm('Delete?')) location.href='/admin/delete/{{ img }}'">X</button>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6767, debug=False)
