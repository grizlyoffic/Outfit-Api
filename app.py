from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import os
import base64

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)
session = requests.Session()

# --- XOR Secret and Encrypted API key ---
SECRET = "mysecret123"            # Ye secret aapke paas safe rahe
ENCRYPTED_KEY = "PRgBFwIaAAw="    # Ye aapka encrypted key (Parrahex)

def decrypt_key(enc_key: str, secret: str) -> str:
    data = base64.b64decode(enc_key)
    return "".join([chr(b ^ ord(secret[i % len(secret)])) for i, b in enumerate(data)])

# --- Decrypt at runtime ---
API_KEY = decrypt_key(ENCRYPTED_KEY, SECRET)

# --- Configuration ---
BACKGROUND_FILENAME = "outfit.png"
IMAGE_TIMEOUT = 8
CANVAS_SIZE = (800, 800)

# ---- Outfit slot rules ----
required_starts = ["211", "214", "211", "203", "204", "205", "203"]

# ---- Default IDs for missing outfit slots ----
fallback_ids = [
    "211000000",  # Slot 1 default
    "214000000",  # Slot 2 default
    "208000000",  # Slot 3 default
    "203000000",  # Slot 4 default
    "204000000",  # Slot 5 default
    "205000000",  # Slot 6 default
    "212000000"   # Slot 7 default
]

# ---- Default weapon ID ----
DEFAULT_WEAPON_ID = "909852001"


def fetch_player_info(uid: str):
    try:
        url = f"https://info-canze1.vercel.app/player-info?uid={uid}"
        resp = session.get(url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except:
        return None


def fetch_image(url):
    try:
        r = session.get(url, timeout=IMAGE_TIMEOUT)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except:
        return None


@app.route('/outfit-image', methods=['GET'])
def outfit_image():
    uid = request.args.get('uid')
    key = request.args.get('key')

    # --- Check encrypted API key ---
    if key != API_KEY:
        return jsonify({'error': 'Invalid API key'}), 401
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    data = fetch_player_info(uid)
    if not data:
        return jsonify({'error': 'Player not found'}), 500

    # --- Get outfit IDs ---
    clothes_ids = data.get("profileInfo", {}).get("clothes", []) or []
    weapon_ids = data.get("basicInfo", {}).get("weaponSkinShows", []) or []

    used_ids = set()

    # ---- Helper: get outfit image with fallback ----
    def get_outfit(idx, code):
        matched = None
        for cid in clothes_ids:
            s = str(cid)
            if s.startswith(code) and s not in used_ids:
                matched = s
                used_ids.add(s)
                break
        if not matched:
            matched = fallback_ids[idx]   # fallback
        return fetch_image(f"https://item-info-ldp1.vercel.app/icon?item_id={matched}")

    # ---- Fetch outfit images concurrently ----
    futures = [executor.submit(get_outfit, i, c) for i, c in enumerate(required_starts)]

    # ---- Background ----
    bg_path = os.path.join(os.path.dirname(__file__), BACKGROUND_FILENAME)
    bg = Image.open(bg_path).convert("RGBA")

    bg_w, bg_h = bg.size
    canvas_w, canvas_h = CANVAS_SIZE
    scale = max(canvas_w / bg_w, canvas_h / bg_h)

    bg = bg.resize((int(bg_w * scale), int(bg_h * scale)), Image.LANCZOS)

    offset_x = (canvas_w - bg.width) // 2
    offset_y = (canvas_h - bg.height) // 2

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
    canvas.paste(bg, (offset_x, offset_y), bg)

    # ---- Outfit positions ----
    positions = [
        {'x': 350, 'y': 30},
        {'x': 575, 'y': 130},
        {'x': 665, 'y': 350},
        {'x': 575, 'y': 560},
        {'x': 358, 'y': 654},
        {'x': 135, 'y': 570},
        {'x': 135, 'y': 130},
    ]

    # ---- Paste outfits ----
    for idx, future in enumerate(futures):
        img = future.result()
        if not img:
            continue
        size = int(150 * scale)
        img = img.resize((size, size), Image.LANCZOS)

        paste_x = offset_x + int(positions[idx]['x'] * scale)
        paste_y = offset_y + int(positions[idx]['y'] * scale)

        canvas.paste(img, (paste_x, paste_y), img)

    # ---- Weapon with default fallback and maintain aspect ratio (corner aligned) ----
    weapon_id = str(weapon_ids[0]) if weapon_ids else DEFAULT_WEAPON_ID
    weapon_img = fetch_image(f"https://iconapi.wasmer.app/{weapon_id}")

    if weapon_img:
        # Slightly bigger box for weapon
        max_width = int(200 * scale)
        max_height = int(200 * scale)

        w, h = weapon_img.size
        factor = min(max_width / w, max_height / h)
        new_w = int(w * factor)
        new_h = int(h * factor)

        weapon_img = weapon_img.resize((new_w, new_h), Image.LANCZOS)

        # Paste position (left middle corner aligned)
        weapon_x = offset_x + int(22 * scale)
        weapon_y = offset_y + int(395 * scale)

        canvas.paste(weapon_img, (weapon_x, weapon_y), weapon_img)

    # ---- Return as PNG ----
    output = BytesIO()
    canvas.save(output, format='PNG')
    output.seek(0)

    return send_file(output, mimetype='image/png')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
