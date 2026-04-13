import os
import json
import base64
import requests as req
from bs4 import BeautifulSoup
import anthropic
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ─── DATABASE ─────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"), cursor_factory=RealDictCursor)

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS match_stats (
                    id SERIAL PRIMARY KEY,
                    match VARCHAR(100) NOT NULL,
                    player VARCHAR(100) NOT NULL,
                    role VARCHAR(50),
                    runs INTEGER DEFAULT 0,
                    fours INTEGER DEFAULT 0,
                    sixes INTEGER DEFAULT 0,
                    wickets INTEGER DEFAULT 0,
                    catches INTEGER DEFAULT 0,
                    stumpings INTEGER DEFAULT 0,
                    maidens INTEGER DEFAULT 0,
                    dismissal VARCHAR(20) DEFAULT 'DNB',
                    mom INTEGER DEFAULT 0,
                    hattrick INTEGER DEFAULT 0,
                    pts REAL DEFAULT 0,
                    UNIQUE(match, player)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cvc_changes (
                    id SERIAL PRIMARY KEY,
                    team VARCHAR(100) NOT NULL,
                    type VARCHAR(5) NOT NULL,
                    from_player VARCHAR(100),
                    to_player VARCHAR(100),
                    date VARCHAR(20),
                    penalty INTEGER DEFAULT 0
                )
            """)
        conn.commit()

# Initialise DB on startup
try:
    init_db()
except Exception as e:
    print(f"DB init error: {e}")

def get_all_stats():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM match_stats ORDER BY id")
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"DB read error: {e}")
        return []

def get_all_cvc_changes():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM cvc_changes ORDER BY id")
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"DB read error: {e}")
        return []

def save_stats(entries):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                for e in entries:
                    cur.execute("""
                        INSERT INTO match_stats 
                        (match, player, role, runs, fours, sixes, wickets, catches, stumpings, maidens, dismissal, mom, hattrick, pts)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (match, player) DO UPDATE SET
                        runs=EXCLUDED.runs, fours=EXCLUDED.fours, sixes=EXCLUDED.sixes,
                        wickets=EXCLUDED.wickets, catches=EXCLUDED.catches, stumpings=EXCLUDED.stumpings,
                        maidens=EXCLUDED.maidens, dismissal=EXCLUDED.dismissal, mom=EXCLUDED.mom,
                        hattrick=EXCLUDED.hattrick, pts=EXCLUDED.pts, role=EXCLUDED.role
                    """, (e["match"], e["player"], e["role"], e["runs"], e["fours"], e["sixes"],
                          e["wickets"], e["catches"], e["stumpings"], e["maidens"],
                          e["dismissal"], e["mom"], e["hattrick"], e["pts"]))
            conn.commit()
    except Exception as ex:
        print(f"DB save error: {ex}")

def save_cvc_change(change):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO cvc_changes (team, type, from_player, to_player, date, penalty)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (change["team"], change["type"], change["from"], change["to"], change["date"], change["penalty"]))
            conn.commit()
    except Exception as ex:
        print(f"DB save error: {ex}")



TEAMS = {
    "Vijay": {"players": [
        {"name":"Virat Kohli","role":"Batsman","ipl":"RCB","cvc":"C"},
        {"name":"Sanju Samson","role":"Batsman","ipl":"CSK","cvc":"VC"},
        {"name":"Sai Sudharsan","role":"Batsman","ipl":"GT","cvc":None},
        {"name":"Ravindra Jadeja","role":"All-rounder","ipl":"RR","cvc":None},
        {"name":"Arshdeep Singh","role":"Bowler","ipl":"PK","cvc":None},
        {"name":"Yuzvendra Chahal","role":"Bowler","ipl":"PK","cvc":None},
        {"name":"Harpreet Brar","role":"Bowler","ipl":"PK","cvc":None},
        {"name":"Jasprit Bumrah","role":"Bowler","ipl":"MI","cvc":None},
        {"name":"Rachin Ravindra","role":"All-rounder","ipl":"KKR","cvc":None},
        {"name":"Finn Allen","role":"Batsman","ipl":"KKR","cvc":None},
        {"name":"Dewald Brewis","role":"Bowler","ipl":"CSK","cvc":None},
        {"name":"Deepak Chahar","role":"Bowler","ipl":"MI","cvc":None},
        {"name":"Tim David","role":"All-rounder","ipl":"RCB","cvc":None},
    ]},
    "Yash Shah": {"players": [
        {"name":"Abhishek Sharma","role":"All-rounder","ipl":"SRH","cvc":"C"},
        {"name":"Heinrich Klaasen","role":"Batsman","ipl":"SRH","cvc":"VC"},
        {"name":"Prabhsimran Singh","role":"Batsman","ipl":"PK","cvc":None},
        {"name":"Washington Sundar","role":"All-rounder","ipl":"GT","cvc":None},
        {"name":"Sunil Narine","role":"All-rounder","ipl":"KKR","cvc":None},
        {"name":"Jitesh Sharma","role":"Batsman","ipl":"RCB","cvc":None},
        {"name":"Shashank Singh","role":"All-rounder","ipl":"PK","cvc":None},
        {"name":"Nitish Kumar Reddy","role":"All-rounder","ipl":"SRH","cvc":None},
        {"name":"Rinku Singh","role":"Batsman","ipl":"KKR","cvc":None},
        {"name":"Angkrish Raghuvanshi","role":"Batsman","ipl":"KKR","cvc":None},
        {"name":"Azmatullah Omarzai","role":"All-rounder","ipl":"PK","cvc":None},
        {"name":"Devdutt Padikkal","role":"Batsman","ipl":"RCB","cvc":None},
        {"name":"Tushar Deshpande","role":"Bowler","ipl":"RR","cvc":None},
    ]},
    "Samay Maru": {"players": [
        {"name":"Shubman Gill","role":"Batsman","ipl":"GT","cvc":"C"},
        {"name":"Mitchell Marsh","role":"All-rounder","ipl":"LSG","cvc":"VC"},
        {"name":"Ruturaj Gaikwad","role":"Batsman","ipl":"CSK","cvc":None},
        {"name":"Krunal Pandya","role":"All-rounder","ipl":"RCB","cvc":None},
        {"name":"Ayush Mhatre","role":"Batsman","ipl":"CSK","cvc":None},
        {"name":"Jason Holder","role":"All-rounder","ipl":"GT","cvc":None},
        {"name":"Khaleel Ahmed","role":"Bowler","ipl":"CSK","cvc":None},
        {"name":"Bhuvneshwar Kumar","role":"Bowler","ipl":"RCB","cvc":None},
        {"name":"David Miller","role":"Batsman","ipl":"DC","cvc":None},
        {"name":"Riyan Parag","role":"All-rounder","ipl":"RR","cvc":None},
        {"name":"Marco Jansen","role":"All-rounder","ipl":"PK","cvc":None},
        {"name":"Nehal Wadhera","role":"Batsman","ipl":"PK","cvc":None},
        {"name":"Sherfane Rutherford","role":"All-rounder","ipl":"MI","cvc":None},
    ]},
    "Harsh Gupta": {"players": [
        {"name":"Rohit Sharma","role":"Batsman","ipl":"MI","cvc":"C"},
        {"name":"Ishan Kishan","role":"Batsman","ipl":"SRH","cvc":"VC"},
        {"name":"Travis Head","role":"Batsman","ipl":"SRH","cvc":None},
        {"name":"Rishabh Pant","role":"Batsman","ipl":"LSG","cvc":None},
        {"name":"Mohammed Siraj","role":"Bowler","ipl":"GT","cvc":None},
        {"name":"Pat Cummins","role":"Bowler","ipl":"SRH","cvc":None},
        {"name":"Dhruv Jurel","role":"Batsman","ipl":"RR","cvc":None},
        {"name":"Jacob Bethell","role":"All-rounder","ipl":"RCB","cvc":None},
        {"name":"Harshal Patel","role":"Bowler","ipl":"RCB","cvc":None},
        {"name":"Marcus Stoinis","role":"All-rounder","ipl":"PK","cvc":None},
        {"name":"Naman Dhir","role":"Batsman","ipl":"MI","cvc":None},
        {"name":"Shardul Thakur","role":"All-rounder","ipl":"MI","cvc":None},
        {"name":"Anrich Nortje","role":"Bowler","ipl":"LSG","cvc":None},
    ]},
    "Vikram Jumani": {"players": [
        {"name":"Yashasvi Jaiswal","role":"Batsman","ipl":"RR","cvc":"C"},
        {"name":"Nicholas Pooran","role":"Batsman","ipl":"LSG","cvc":"VC"},
        {"name":"Shreyas Iyer","role":"Batsman","ipl":"PK","cvc":None},
        {"name":"Priyansh Arya","role":"Batsman","ipl":"PK","cvc":None},
        {"name":"Shimron Hetmyer","role":"Batsman","ipl":"RR","cvc":None},
        {"name":"Ravi Bishnoi","role":"Bowler","ipl":"RR","cvc":None},
        {"name":"Pathum Nissanka","role":"Batsman","ipl":"DC","cvc":None},
        {"name":"Tristan Stubbs","role":"Batsman","ipl":"DC","cvc":None},
        {"name":"Mitchell Starc","role":"Bowler","ipl":"DC","cvc":None},
        {"name":"Suyash Sharma","role":"Bowler","ipl":"RCB","cvc":None},
        {"name":"Josh Inglis","role":"Batsman","ipl":"LSG","cvc":None},
        {"name":"Jofra Archer","role":"Bowler","ipl":"RR","cvc":None},
        {"name":"Prashant Veer","role":"Bowler","ipl":"CSK","cvc":None},
    ]},
    "Rishub Bubna": {"players": [
        {"name":"Hardik Pandya","role":"All-rounder","ipl":"MI","cvc":"C"},
        {"name":"Axar Patel","role":"All-rounder","ipl":"DC","cvc":"VC"},
        {"name":"Tilak Varma","role":"Batsman","ipl":"MI","cvc":None},
        {"name":"Kuldeep Yadav","role":"Bowler","ipl":"DC","cvc":None},
        {"name":"Cameron Green","role":"All-rounder","ipl":"KKR","cvc":None},
        {"name":"Rajat Patidar","role":"Batsman","ipl":"RCB","cvc":None},
        {"name":"Glenn Phillips","role":"All-rounder","ipl":"GT","cvc":None},
        {"name":"Mitchell Santner","role":"All-rounder","ipl":"MI","cvc":None},
        {"name":"Vaibhav Arora","role":"Bowler","ipl":"KKR","cvc":None},
        {"name":"Avesh Khan","role":"Bowler","ipl":"LSG","cvc":None},
        {"name":"Ryan Rickelton","role":"Batsman","ipl":"MI","cvc":None},
        {"name":"Quinton de Kock","role":"Batsman","ipl":"MI","cvc":None},
        {"name":"Rahul Tewatia","role":"All-rounder","ipl":"GT","cvc":None},
    ]},
    "Nihar Mehta": {"players": [
        {"name":"KL Rahul","role":"Batsman","ipl":"DC","cvc":"C"},
        {"name":"Aiden Markram","role":"All-rounder","ipl":"LSG","cvc":"VC"},
        {"name":"Vaibhav Suryavanshi","role":"Batsman","ipl":"RR","cvc":None},
        {"name":"Shivam Dube","role":"All-rounder","ipl":"CSK","cvc":None},
        {"name":"Ajinkya Rahane","role":"Batsman","ipl":"KKR","cvc":None},
        {"name":"Sarfaraz Khan","role":"Batsman","ipl":"CSK","cvc":None},
        {"name":"Sai Kishore","role":"Bowler","ipl":"GT","cvc":None},
        {"name":"Liam Livingstone","role":"All-rounder","ipl":"SRH","cvc":None},
        {"name":"Jacob Duffy","role":"Bowler","ipl":"RCB","cvc":None},
        {"name":"Digvesh Rathi","role":"Bowler","ipl":"LSG","cvc":None},
        {"name":"Prithvi Shaw","role":"Batsman","ipl":"DC","cvc":None},
        {"name":"Tim Seifert","role":"Batsman","ipl":"KKR","cvc":None},
        {"name":"Vignesh Puthur","role":"Bowler","ipl":"RR","cvc":None},
    ]},
    "Qais / Vaishali": {"players": [
        {"name":"Suryakumar Yadav","role":"Batsman","ipl":"MI","cvc":"C"},
        {"name":"Varun Chakravarthy","role":"Bowler","ipl":"KKR","cvc":"VC"},
        {"name":"Jos Buttler","role":"Batsman","ipl":"GT","cvc":None},
        {"name":"Phil Salt","role":"Batsman","ipl":"RCB","cvc":None},
        {"name":"Trent Boult","role":"Bowler","ipl":"MI","cvc":None},
        {"name":"Rashid Khan","role":"Bowler","ipl":"GT","cvc":None},
        {"name":"Will Jacks","role":"All-rounder","ipl":"MI","cvc":None},
        {"name":"Mohammad Shami","role":"Bowler","ipl":"LSG","cvc":None},
        {"name":"Rahul Tripathi","role":"Batsman","ipl":"KKR","cvc":None},
        {"name":"Noor Ahmad","role":"Bowler","ipl":"CSK","cvc":None},
        {"name":"Venkatesh Iyer","role":"All-rounder","ipl":"RCB","cvc":None},
        {"name":"Abhishek Porel","role":"Batsman","ipl":"DC","cvc":None},
        {"name":"Vyshak Vijaykumar","role":"Bowler","ipl":"PK","cvc":None},
    ]},
}

# ─── SCORING LOGIC ────────────────────────────────────────────────────────────

def calculate_points(player_data):
    """Calculate fantasy points for a player's match performance."""
    runs = player_data.get("runs", 0)
    fours = player_data.get("fours", 0)
    sixes = player_data.get("sixes", 0)
    wickets = player_data.get("wickets", 0)
    catches = player_data.get("catches", 0)
    stumpings = player_data.get("stumpings", 0)
    maidens = player_data.get("maidens", 0)
    dismissal = player_data.get("dismissal", "")
    mom = player_data.get("mom", 0)
    hattrick = player_data.get("hattrick", 0)
    role = player_data.get("role", "Batsman")

    pts = 0

    # Base points
    pts += runs * 1
    pts += fours * 1
    pts += sixes * 2
    pts += wickets * 25
    pts += catches * 3
    pts += stumpings * 5
    pts += maidens * 10

    # Duck penalty
    if runs == 0 and dismissal == "Out":
        if role == "Batsman":
            pts -= 6
        elif role == "All-rounder":
            pts -= 4
        elif role == "Bowler":
            pts -= 2

    # Not out bonus
    if dismissal == "Not Out":
        if role == "Batsman":
            pts += 6
        elif role == "All-rounder":
            pts += 4
        elif role == "Bowler":
            pts += 2

    # Milestone bonuses — batting
    if runs >= 100:
        pts += 30
    elif runs >= 75:
        pts += 20
    elif runs >= 50:
        pts += 10
    elif runs >= 30:
        pts += 5

    # Milestone bonuses — bowling
    if hattrick:
        pts += 30
    if wickets >= 5:
        pts += 30
    elif wickets == 4:
        pts += 20
    elif wickets == 3:
        pts += 10
    elif wickets == 2:
        pts += 5

    # MOM
    if mom:
        pts += 10

    return pts


def get_player_role(player_name):
    """Look up role from team data."""
    for team in TEAMS.values():
        for p in team["players"]:
            if p["name"] == player_name:
                return p["role"]
    return "Batsman"


def get_leaderboard():
    all_stats = get_all_stats()
    cvc_changes = get_all_cvc_changes()

    # Deduplicate: for same player+match, keep highest pts entry
    deduped = {}
    for stat in all_stats:
        key = f"{stat['player']}|{stat['match']}"
        if key not in deduped or stat["pts"] > deduped[key]["pts"]:
            deduped[key] = stat
    all_stats = list(deduped.values())

    matches_played = sorted(list(set(s["match"] for s in all_stats)))

    # Build per-owner per-match totals
    owner_match_pts = {owner: {} for owner in TEAMS}

    for stat in all_stats:
        player_name = stat["player"]
        match = stat["match"]
        raw_pts = stat["pts"]

        for owner, team in TEAMS.items():
            for p in team["players"]:
                if p["name"] == player_name:
                    mult = 2 if p["cvc"] == "C" else 1.5 if p["cvc"] == "VC" else 1
                    if match not in owner_match_pts[owner]:
                        owner_match_pts[owner][match] = 0
                    owner_match_pts[owner][match] += raw_pts * mult

    # Apply C/VC penalties
    for change in cvc_changes:
        owner = change["team"]
        if owner in owner_match_pts:
            penalty = -150 if change["type"] == "C" else -75
            if "__penalties__" not in owner_match_pts[owner]:
                owner_match_pts[owner]["__penalties__"] = 0
            owner_match_pts[owner]["__penalties__"] += penalty

    result = []
    for owner in TEAMS:
        match_pts = owner_match_pts[owner]
        penalty = match_pts.pop("__penalties__", 0)
        total = sum(match_pts.values()) + penalty
        result.append({
            "name": owner,
            "total": round(total, 1),
            "penalty": round(penalty, 1),
            "match_pts": {m: round(match_pts.get(m, 0), 1) for m in matches_played}
        })

    result.sort(key=lambda x: x["total"], reverse=True)
    for i, r in enumerate(result):
        r["rank"] = i + 1

    return result, matches_played, cvc_changes


# ─── API ENDPOINTS ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.route("/api/leaderboard")
def api_leaderboard():
    lb, matches, cvc_changes = get_leaderboard()
    return jsonify({"leaderboard": lb, "matches": matches, "cvc_changes": cvc_changes})

@app.route("/api/teams")
def api_teams():
    all_stats = get_all_stats()
    player_totals = {}
    for stat in all_stats:
        name = stat["player"]
        if name not in player_totals:
            player_totals[name] = {"name": name, "role": stat["role"], "total_pts": 0, "total_runs": 0, "total_wkts": 0, "matches": []}
        player_totals[name]["total_pts"] += stat["pts"]
        player_totals[name]["total_runs"] += stat.get("runs", 0)
        player_totals[name]["total_wkts"] += stat.get("wickets", 0)
        player_totals[name]["matches"].append({"match": stat["match"], "pts": stat["pts"], "runs": stat.get("runs", 0), "wkts": stat.get("wickets", 0), "mom": stat.get("mom", 0)})

    teams_out = {}
    for owner, team in TEAMS.items():
        players_out = []
        for p in team["players"]:
            name = p["name"]
            pt = player_totals.get(name, {"total_pts": 0, "total_runs": 0, "total_wkts": 0, "matches": []})
            mult = 2 if p["cvc"] == "C" else 1.5 if p["cvc"] == "VC" else 1
            players_out.append({
                "name": name,
                "role": p["role"],
                "ipl": p["ipl"],
                "cvc": p["cvc"],
                "raw_pts": round(pt["total_pts"], 1),
                "display_pts": round(pt["total_pts"] * mult, 1),
                "total_runs": pt["total_runs"],
                "total_wkts": pt["total_wkts"],
                "matches": pt["matches"],
            })
        teams_out[owner] = sorted(players_out, key=lambda x: x["display_pts"], reverse=True)

    return jsonify({"teams": teams_out})

@app.route("/api/players")
def api_players():
    all_stats = get_all_stats()

    # Deduplicate: for same player+match, keep the entry with highest pts
    deduped = {}
    for stat in all_stats:
        key = f"{stat['player']}|{stat['match']}"
        if key not in deduped or stat["pts"] > deduped[key]["pts"]:
            deduped[key] = stat

    player_totals = {}
    for stat in deduped.values():
        name = stat["player"]
        if name not in player_totals:
            player_totals[name] = {"name": name, "role": stat["role"], "total_pts": 0, "total_runs": 0, "total_wkts": 0, "matches": []}
        player_totals[name]["total_pts"] += stat["pts"]
        player_totals[name]["total_runs"] += stat.get("runs", 0)
        player_totals[name]["total_wkts"] += stat.get("wickets", 0)
        player_totals[name]["matches"].append({"match": stat["match"], "pts": stat["pts"], "runs": stat.get("runs", 0), "wkts": stat.get("wickets", 0), "mom": stat.get("mom", 0)})

    players = sorted(player_totals.values(), key=lambda x: x["total_pts"], reverse=True)
    for p in players:
        p["total_pts"] = round(p["total_pts"], 1)
    return jsonify({"players": players})

@app.route("/api/upload-scorecard-text", methods=["POST"])
def upload_scorecard_text():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    scorecard_text = data.get("text", "").strip()
    match_name = data.get("match_name", "").strip()
    mom_player = data.get("mom_player", "").strip()

    if not scorecard_text or not match_name:
        return jsonify({"error": "Scorecard text and match name required"}), 400

    all_players = []
    for team in TEAMS.values():
        for p in team["players"]:
            all_players.append(f"{p['name']} ({p['role']})")
    players_context = "\n".join(all_players)

    prompt = f"""You are reading an IPL cricket scorecard. Extract ALL player statistics from the text below.

Known fantasy league players (use for name matching):
{players_context}

Scorecard text:
{scorecard_text[:12000]}

CRITICAL: Return ONLY ONE entry per player. Never duplicate. For players who bat AND bowl, merge into one entry combining all their stats.

Return a JSON array with this exact structure:
[
  {{
    "player": "exact player name",
    "role": "Batsman" or "Bowler" or "All-rounder",
    "runs": number,
    "fours": number,
    "sixes": number,
    "wickets": number,
    "catches": number,
    "stumpings": number,
    "maidens": number,
    "dismissal": "Out" or "Not Out" or "DNB",
    "mom": 0,
    "hattrick": 0
  }}
]

Rules:
- ONE entry per player only — no duplicates whatsoever
- Include ALL players from both teams
- dismissal = "DNB" if did not bat, "Not Out" if not out, "Out" if dismissed
- catches = catches taken in the field by this player
- Return ONLY the JSON array, nothing else"""

    try:
        ai_response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = ai_response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        players_data = json.loads(raw)
        new_entries = process_players(players_data, match_name, mom_player)
        save_stats(new_entries)

        mom_entry = next((e for e in new_entries if e.get("mom") == 1), None)
        return jsonify({
            "success": True,
            "match": match_name,
            "players_processed": len(new_entries),
            "mom_applied_to": mom_entry["player"] if mom_entry else f"NOT APPLIED (received: '{mom_player}')",
            "entries": new_entries
        })

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Could not parse scorecard: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload-scorecard-url", methods=["POST"])
def upload_scorecard_url():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    url = data.get("url", "").strip()
    match_name = data.get("match_name", "").strip()
    mom_player = data.get("mom_player", "").strip()

    if not url or not match_name:
        return jsonify({"error": "URL and match name required"}), 400

    try:
        # Try multiple proxies to bypass ESPNcricinfo's bot protection
        proxies_to_try = [
            f"https://corsproxy.io/?{req.utils.quote(url, safe='')}",
            f"https://api.codetabs.com/v1/proxy?quest={req.utils.quote(url, safe='')}",
        ]
        html_content = None
        last_error = None
        for proxy_url in proxies_to_try:
            try:
                response = req.get(proxy_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if response.status_code == 200 and len(response.text) > 1000:
                    html_content = response.text
                    break
            except Exception as e:
                last_error = str(e)
                continue

        if not html_content:
            return jsonify({"error": f"Could not fetch scorecard. Try using screenshot upload instead. ({last_error})"}), 500

        soup = BeautifulSoup(html_content, "html.parser")
        scorecard_text = soup.get_text(separator="\n", strip=True)
        scorecard_text = scorecard_text[:12000]
    except Exception as e:
        return jsonify({"error": f"Could not fetch scorecard: {str(e)}"}), 500

    all_players = []
    for team in TEAMS.values():
        for p in team["players"]:
            all_players.append(f"{p['name']} ({p['role']})")
    players_context = "\n".join(all_players)

    prompt = f"""You are reading an IPL cricket scorecard from ESPNcricinfo. Extract ALL player statistics.

Known fantasy league players (use these for name matching):
{players_context}

Scorecard text:
{scorecard_text}

Return a JSON array with one entry per player. Use this exact structure:
[
  {{
    "player": "exact player name as shown",
    "role": "Batsman" or "Bowler" or "All-rounder",
    "runs": number,
    "fours": number,
    "sixes": number,
    "wickets": number,
    "catches": number,
    "stumpings": number,
    "maidens": number,
    "dismissal": "Out" or "Not Out" or "DNB",
    "mom": 0,
    "hattrick": 0
  }}
]

Rules:
- Include ALL batsmen and bowlers from BOTH innings
- dismissal = "DNB" if did not bat
- dismissal = "Not Out" if not out
- dismissal = "Out" if dismissed
- catches = catches taken in the field by this player
- Return ONLY the JSON array, nothing else"""

    try:
        ai_response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = ai_response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        players_data = json.loads(raw)
        new_entries = process_players(players_data, match_name, mom_player)
        save_stats(new_entries)

        return jsonify({
            "success": True,
            "match": match_name,
            "players_processed": len(new_entries),
            "entries": new_entries
        })

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Could not parse scorecard: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def process_players(players_data, match_name, mom_player):
    """Shared logic for processing player data from any source."""
    # Merge duplicate entries for the same player (batting + bowling combined)
    merged = {}
    for p in players_data:
        name = p["player"].strip()
        if name not in merged:
            merged[name] = {
                "player": name,
                "role": p.get("role") or get_player_role(name),
                "runs": p.get("runs", 0),
                "fours": p.get("fours", 0),
                "sixes": p.get("sixes", 0),
                "wickets": p.get("wickets", 0),
                "catches": p.get("catches", 0),
                "stumpings": p.get("stumpings", 0),
                "maidens": p.get("maidens", 0),
                "dismissal": p.get("dismissal", "DNB"),
                "mom": p.get("mom", 0),
                "hattrick": p.get("hattrick", 0),
            }
        else:
            # Merge — take the max of batting stats, add bowling stats
            m = merged[name]
            m["runs"] = max(m["runs"], p.get("runs", 0))
            m["fours"] = max(m["fours"], p.get("fours", 0))
            m["sixes"] = max(m["sixes"], p.get("sixes", 0))
            m["wickets"] = max(m["wickets"], p.get("wickets", 0))
            m["catches"] = max(m["catches"], p.get("catches", 0))
            m["stumpings"] = max(m["stumpings"], p.get("stumpings", 0))
            m["maidens"] = max(m["maidens"], p.get("maidens", 0))
            m["mom"] = max(m["mom"], p.get("mom", 0))
            m["hattrick"] = max(m["hattrick"], p.get("hattrick", 0))
            # Keep non-DNB dismissal
            if p.get("dismissal", "DNB") != "DNB":
                m["dismissal"] = p["dismissal"]
            # Update role if it gives more info
            if p.get("role") in ["All-rounder", "Bowler"] and m["role"] == "Batsman":
                m["role"] = p["role"]

    new_entries = []
    mom_applied = False
    for name, p in merged.items():
        pts = calculate_points(p)
        # Apply MOM bonus from admin field
        if mom_player and not mom_applied:
            player_clean = name.strip().lower().replace(".", "").replace(" ", "")
            mom_clean = mom_player.strip().lower().replace(".", "").replace(" ", "")
            if mom_clean in player_clean or player_clean in mom_clean:
                pts += 10
                p["mom"] = 1
                mom_applied = True
        entry = {
            "match": match_name,
            "player": name,
            "role": p["role"],
            "runs": p["runs"],
            "fours": p["fours"],
            "sixes": p["sixes"],
            "wickets": p["wickets"],
            "catches": p["catches"],
            "stumpings": p["stumpings"],
            "maidens": p["maidens"],
            "dismissal": p["dismissal"],
            "mom": p["mom"],
            "hattrick": p["hattrick"],
            "pts": pts,
        }
        new_entries.append(entry)
    return new_entries


@app.route("/api/upload-scorecard", methods=["POST"])
def upload_scorecard():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401

    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    match_name = request.form.get("match_name", "").strip()
    if not match_name:
        return jsonify({"error": "Match name required"}), 400

    mom_player = request.form.get("mom_player", "").strip().lower()

    image_file = request.files["image"]
    image_data = base64.standard_b64encode(image_file.read()).decode("utf-8")
    media_type = image_file.content_type or "image/png"

    # Build known players list for context
    all_players = []
    for team in TEAMS.values():
        for p in team["players"]:
            all_players.append(f"{p['name']} ({p['role']})")
    players_context = "\n".join(all_players)

    prompt = f"""You are reading an IPL cricket scorecard image. Extract ALL player statistics visible.

Known fantasy league players (for name matching):
{players_context}

CRITICAL: Return ONLY ONE entry per player. Never duplicate. For players who bat AND bowl, merge into one entry.

Return a JSON array with this exact structure:
[
  {{
    "player": "exact player name",
    "role": "Batsman" or "Bowler" or "All-rounder",
    "runs": number,
    "fours": number,
    "sixes": number,
    "wickets": number,
    "catches": number,
    "stumpings": number,
    "maidens": number,
    "dismissal": "Out" or "Not Out" or "DNB",
    "mom": 0,
    "hattrick": 0
  }}
]

Rules:
- ONE entry per player only — no duplicates
- dismissal = "DNB" if did not bat, "Not Out" if not out, "Out" if dismissed
- catches = catches taken in the field
- Return ONLY the JSON array, no other text

Scorecard image is attached."""

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        players_data = json.loads(raw)
        new_entries = process_players(players_data, match_name, mom_player)
        save_stats(new_entries)

        return jsonify({
            "success": True,
            "match": match_name,
            "players_processed": len(new_entries),
            "entries": new_entries
        })

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Could not parse scorecard data: {str(e)}", "raw": raw}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/add-mom", methods=["POST"])
def add_mom():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    player = data.get("player", "").strip()
    match = data.get("match", "").strip()

    if not player or not match:
        return jsonify({"error": "Player and match required"}), 400

    # Find and update in DB
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM match_stats WHERE match=%s", (match,))
                rows = [dict(r) for r in cur.fetchall()]
                search_name = player.strip().lower().replace(".", "").replace(" ", "")
                found = None
                for row in rows:
                    stat_name = row["player"].strip().lower().replace(".", "").replace(" ", "")
                    if stat_name == search_name or search_name in stat_name or stat_name in search_name:
                        found = row
                        break
                if not found:
                    return jsonify({"error": f"Player '{player}' not found in match '{match}'."}), 404
                if found["mom"] == 0:
                    cur.execute("UPDATE match_stats SET mom=1, pts=pts+10 WHERE id=%s", (found["id"],))
                    conn.commit()
                return jsonify({"success": True, "player": found["player"], "match": match})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cvc-change", methods=["POST"])
def api_cvc_change():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    team = data.get("team", "").strip()
    change_type = data.get("type", "").strip()
    from_player = data.get("from", "").strip()
    to_player = data.get("to", "").strip()
    date = data.get("date", "").strip()

    if not all([team, change_type, from_player, to_player, date]):
        return jsonify({"error": "All fields required"}), 400

    if team not in TEAMS:
        return jsonify({"error": "Unknown team"}), 400

    save_cvc_change({
        "team": team,
        "type": change_type,
        "from": from_player,
        "to": to_player,
        "date": date,
        "penalty": -150 if change_type == "C" else -75
    })

    return jsonify({"success": True})

@app.route("/api/cvc-changes")
def api_cvc_changes():
    return jsonify({"changes": get_all_cvc_changes()})

@app.route("/api/matches")
def api_matches():
    all_stats = get_all_stats()
    matches = sorted(list(set(s["match"] for s in all_stats)))
    return jsonify({"matches": matches})

@app.route("/api/fetch-scorecard", methods=["POST"])
def fetch_scorecard():
    """Fetch scorecard from CricketData.org API and process it."""
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    match_name = data.get("match_name", "").strip()
    match_id = data.get("match_id", "").strip()
    mom_player = data.get("mom_player", "").strip()

    if not match_name or not match_id:
        return jsonify({"error": "Match name and match ID required"}), 400

    api_key = os.environ.get("CRICKETDATA_API_KEY", "")
    if not api_key:
        return jsonify({"error": "CricketData API key not configured"}), 500

    try:
        # Fetch scorecard from CricketData
        url = f"https://api.cricapi.com/v1/match_scorecard?apikey={api_key}&id={match_id}"
        response = req.get(url, timeout=15)
        response.raise_for_status()
        result = response.json()

        if result.get("status") != "success":
            return jsonify({"error": f"API error: {result.get('message', 'Unknown error')}"}), 500

        scorecard = result.get("data", {})

        # Build known players context
        all_players = []
        for team in TEAMS.values():
            for p in team["players"]:
                all_players.append(f"{p['name']} ({p['role']})")
        players_context = "\n".join(all_players)

        # Pass raw scorecard JSON to Claude for extraction
        prompt = f"""You are processing an IPL cricket scorecard from CricketData API. Extract ALL player statistics.

Known fantasy league players (use for name matching):
{players_context}

Scorecard JSON:
{json.dumps(scorecard, indent=2)[:12000]}

CRITICAL: Return ONLY ONE entry per player. For players who bat AND bowl, merge into one entry.

Return a JSON array with this exact structure:
[
  {{
    "player": "exact player name",
    "role": "Batsman" or "Bowler" or "All-rounder",
    "runs": number,
    "fours": number,
    "sixes": number,
    "wickets": number,
    "catches": number,
    "stumpings": number,
    "maidens": number,
    "dismissal": "Out" or "Not Out" or "DNB",
    "mom": 0,
    "hattrick": 0
  }}
]

Rules:
- ONE entry per player only
- dismissal = "DNB" if did not bat, "Not Out" if not out, "Out" if dismissed
- catches = catches taken in the field
- Return ONLY the JSON array, nothing else"""

        ai_response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = ai_response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        players_data = json.loads(raw)
        new_entries = process_players(players_data, match_name, mom_player)
        save_stats(new_entries)

        return jsonify({
            "success": True,
            "match": match_name,
            "players_processed": len(new_entries),
            "entries": new_entries
        })

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Could not parse scorecard: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/adjust-points", methods=["POST"])
def adjust_points():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    player = data.get("player", "").strip()
    match = data.get("match", "").strip()
    adjustment = data.get("adjustment", 0)

    if not player or not match:
        return jsonify({"error": "Player and match required"}), 400

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM match_stats WHERE match=%s", (match,))
                rows = [dict(r) for r in cur.fetchall()]
                search_name = player.strip().lower().replace(".", "").replace(" ", "")
                found = None
                for row in rows:
                    stat_name = row["player"].strip().lower().replace(".", "").replace(" ", "")
                    if stat_name == search_name or search_name in stat_name or stat_name in search_name:
                        found = row
                        break
                if not found:
                    return jsonify({"error": f"Player '{player}' not found in match '{match}'."}), 404
                new_pts = found["pts"] + adjustment
                cur.execute("UPDATE match_stats SET pts=%s WHERE id=%s", (new_pts, found["id"]))
                conn.commit()
                return jsonify({"success": True, "player": found["player"], "match": match, "old_pts": found["pts"], "new_pts": new_pts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate-banter", methods=["POST"])
def generate_banter():
    data = request.get_json()
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "No prompt"}), 400
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({"banter": response.content[0].text.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
