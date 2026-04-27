import os
import json
import base64
import requests as req
from bs4 import BeautifulSoup
import anthropic
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, render_template, send_from_directory, make_response
from flask_cors import CORS
app = Flask(__name__)
CORS(app)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"), cursor_factory=RealDictCursor)
def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS match_stats (id SERIAL PRIMARY KEY, match VARCHAR(100) NOT NULL, player VARCHAR(100) NOT NULL, role VARCHAR(50), runs INTEGER DEFAULT 0, fours INTEGER DEFAULT 0, sixes INTEGER DEFAULT 0, wickets INTEGER DEFAULT 0, catches INTEGER DEFAULT 0, stumpings INTEGER DEFAULT 0, maidens INTEGER DEFAULT 0, dismissal VARCHAR(20) DEFAULT 'DNB', mom INTEGER DEFAULT 0, hattrick INTEGER DEFAULT 0, pts REAL DEFAULT 0, UNIQUE(match, player))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS cvc_changes (id SERIAL PRIMARY KEY, team VARCHAR(100) NOT NULL, type VARCHAR(5) NOT NULL, from_player VARCHAR(100), to_player VARCHAR(100), date VARCHAR(20), penalty INTEGER DEFAULT 0)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS banter_reactions (id SERIAL PRIMARY KEY, match VARCHAR(100) NOT NULL, emoji VARCHAR(10) NOT NULL, count INTEGER DEFAULT 0, UNIQUE(match, emoji))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS banter_comments (id SERIAL PRIMARY KEY, match VARCHAR(100) NOT NULL, author VARCHAR(50) NOT NULL, comment TEXT NOT NULL, created_at TIMESTAMP DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS banter_cache (match VARCHAR(100) PRIMARY KEY, banter TEXT NOT NULL, created_at TIMESTAMP DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS replacements (id SERIAL PRIMARY KEY, team VARCHAR(100) NOT NULL, out_player VARCHAR(100) NOT NULL, in_player VARCHAR(100) NOT NULL, date VARCHAR(20) NOT NULL, reason VARCHAR(200) DEFAULT 'Ruled out')""")
        conn.commit()
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
                    cur.execute("""INSERT INTO match_stats (match, player, role, runs, fours, sixes, wickets, catches, stumpings, maidens, dismissal, mom, hattrick, pts) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (match, player) DO UPDATE SET runs=EXCLUDED.runs, fours=EXCLUDED.fours, sixes=EXCLUDED.sixes, wickets=EXCLUDED.wickets, catches=EXCLUDED.catches, stumpings=EXCLUDED.stumpings, maidens=EXCLUDED.maidens, dismissal=EXCLUDED.dismissal, mom=EXCLUDED.mom, hattrick=EXCLUDED.hattrick, pts=EXCLUDED.pts, role=EXCLUDED.role""", (e["match"], e["player"], e["role"], e["runs"], e["fours"], e["sixes"], e["wickets"], e["catches"], e["stumpings"], e["maidens"], e["dismissal"], e["mom"], e["hattrick"], e["pts"]))
            conn.commit()
    except Exception as ex:
        print(f"DB save error: {ex}")
def save_cvc_change(change):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO cvc_changes (team, type, from_player, to_player, date, penalty) VALUES (%s,%s,%s,%s,%s,%s)", (change["team"], change["type"], change["from"], change["to"], change["date"], change["penalty"]))
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
        {"name":"Dewald Brevis","role":"Batsman","ipl":"CSK","cvc":None},
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
        {"name":"Ayush Mhatre","role":"Batsman","ipl":"CSK","cvc":None,"ruled_out":True},
        {"name":"Eshan Malinga","role":"Bowler","ipl":"SRH","cvc":None},
        {"name":"Jason Holder","role":"All-rounder","ipl":"GT","cvc":None},
        {"name":"Khaleel Ahmed","role":"Bowler","ipl":"CSK","cvc":None,"ruled_out":True},
        {"name":"Cooper Connolly","role":"All-rounder","ipl":"PBKS","cvc":None},
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
        {"name":"Harshal Patel","role":"Bowler","ipl":"SRH","cvc":None},
        {"name":"Marcus Stoinis","role":"All-rounder","ipl":"PK","cvc":None},
        {"name":"Naman Dhir","role":"Batsman","ipl":"MI","cvc":None},
        {"name":"Shardul Thakur","role":"All-rounder","ipl":"MI","cvc":None},
        {"name":"Anrich Nortje","role":"Bowler","ipl":"LSG","cvc":None},
    ]},
    "Vikram Jumani": {"players": [
        {"name":"Yashasvi Jaiswal","role":"Batsman","ipl":"RR","cvc":"C"},
        {"name":"Nicholas Pooran","role":"Batsman","ipl":"LSG","cvc":None},
        {"name":"Shreyas Iyer","role":"Batsman","ipl":"PK","cvc":None},
        {"name":"Priyansh Arya","role":"Batsman","ipl":"PK","cvc":"VC"},
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
        {"name":"Hardik Pandya","role":"All-rounder","ipl":"MI","cvc":None},
        {"name":"Axar Patel","role":"All-rounder","ipl":"DC","cvc":"VC"},
        {"name":"Tilak Varma","role":"Batsman","ipl":"MI","cvc":None},
        {"name":"Kuldeep Yadav","role":"Bowler","ipl":"DC","cvc":None},
        {"name":"Cameron Green","role":"All-rounder","ipl":"KKR","cvc":None},
        {"name":"Rajat Patidar","role":"Batsman","ipl":"RCB","cvc":"C"},
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
        {"name":"Aiden Markram","role":"All-rounder","ipl":"LSG","cvc":None},
        {"name":"Vaibhav Sooryavanshi","role":"Batsman","ipl":"RR","cvc":"VC"},
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
        {"name":"Varun Chakravarthy","role":"Bowler","ipl":"KKR","cvc":None},
        {"name":"Jos Buttler","role":"Batsman","ipl":"GT","cvc":"VC"},
        {"name":"Philip Salt","role":"Batsman","ipl":"RCB","cvc":None},
        {"name":"Trent Boult","role":"Bowler","ipl":"MI","cvc":None},
        {"name":"Rashid Khan","role":"Bowler","ipl":"GT","cvc":None},
        {"name":"Will Jacks","role":"All-rounder","ipl":"MI","cvc":None},
        {"name":"Mohammed Shami","role":"Bowler","ipl":"LSG","cvc":None},
        {"name":"Rahul Tripathi","role":"Batsman","ipl":"KKR","cvc":None},
        {"name":"Noor Ahmad","role":"Bowler","ipl":"CSK","cvc":None},
        {"name":"Venkatesh Iyer","role":"All-rounder","ipl":"RCB","cvc":None},
        {"name":"Abhishek Porel","role":"Batsman","ipl":"DC","cvc":None},
        {"name":"Vyshak Vijaykumar","role":"Bowler","ipl":"PK","cvc":None},
    ]},
}
MATCH_ORDER = {
    "RCB vs SRH": 1,"MI vs KKR": 2,"RR vs CSK": 3,"PBKS vs GT": 4,"LSG vs DC": 5,
    "KKR vs SRH": 6,"CSK vs PBKS": 7,"MI vs DC": 8,"RR vs GT": 9,"SRH vs LSG": 10,
    "RCB vs CSK": 11,"KKR vs PBKS": 12,"RR vs MI": 13,"DC vs GT": 14,"KKR vs LSG": 15,
    "RR vs RCB": 16,"PBKS vs SRH": 17,"CSK vs DC": 18,"LSG vs GT": 19,"MI vs RCB": 20,
    "SRH vs RR": 21,"CSK vs KKR": 22,"RCB vs LSG": 23,"MI vs PBKS": 24,"GT vs KKR": 25,
    "RCB vs DC": 26,"SRH vs CSK": 27,"KKR vs RR": 28,"PBKS vs LSG": 29,"GT vs MI": 30,
    "SRH vs DC": 31,"LSG vs RR": 32,"MI vs CSK": 33,"RCB vs GT": 34,"DC vs PBKS": 35,
    "RR vs SRH": 36,"GT vs CSK": 37,"LSG vs KKR": 38,"DC vs RCB": 39,"PBKS vs RR": 40,
    "MI vs SRH": 41,"GT vs RCB": 42,"RR vs DC": 43,"CSK vs MI": 44,"SRH vs KKR": 45,
    "GT vs PBKS": 46,"MI vs LSG": 47,"DC vs CSK": 48,"SRH vs PBKS": 49,"LSG vs RCB": 50,
    "DC vs KKR": 51,"RR vs GT": 52,"CSK vs LSG": 53,"RCB vs MI": 54,"PBKS vs DC": 55,
    "GT vs SRH": 56,"RCB vs KKR": 57,"PBKS vs MI": 58,"LSG vs CSK": 59,"KKR vs GT": 60,
    "PBKS vs RCB": 61,"DC vs RR": 62,"CSK vs SRH": 63,"RR vs LSG": 64,"KKR vs MI": 65,
    "CSK vs GT": 66,"SRH vs RCB": 67,"LSG vs PBKS": 68,"MI vs RR": 69,"KKR vs DC": 70,
}
MATCH_DATES = {
    "RCB vs SRH": "2026-03-28","MI vs KKR": "2026-03-29","RR vs CSK": "2026-03-30",
    "PBKS vs GT": "2026-03-31","LSG vs DC": "2026-04-01","KKR vs SRH": "2026-04-02",
    "CSK vs PBKS": "2026-04-03","MI vs DC": "2026-04-04","RR vs GT": "2026-04-04",
    "SRH vs LSG": "2026-04-05","RCB vs CSK": "2026-04-05","KKR vs PBKS": "2026-04-06",
    "RR vs MI": "2026-04-07","DC vs GT": "2026-04-08","KKR vs LSG": "2026-04-09",
    "RR vs RCB": "2026-04-10","PBKS vs SRH": "2026-04-11","CSK vs DC": "2026-04-11",
    "LSG vs GT": "2026-04-12","MI vs RCB": "2026-04-12","SRH vs RR": "2026-04-13",
    "CSK vs KKR": "2026-04-14","RCB vs LSG": "2026-04-15","MI vs PBKS": "2026-04-16",
    "GT vs KKR": "2026-04-17","RCB vs DC": "2026-04-18","SRH vs CSK": "2026-04-18",
    "KKR vs RR": "2026-04-19","PBKS vs LSG": "2026-04-19","GT vs MI": "2026-04-20",
    "SRH vs DC": "2026-04-21","LSG vs RR": "2026-04-22","MI vs CSK": "2026-04-23",
    "RCB vs GT": "2026-04-24","DC vs PBKS": "2026-04-25","RR vs SRH": "2026-04-25",
    "GT vs CSK": "2026-04-26","LSG vs KKR": "2026-04-26","DC vs RCB": "2026-04-27",
    "PBKS vs RR": "2026-04-28","MI vs SRH": "2026-04-29","GT vs RCB": "2026-04-30",
    "RR vs DC": "2026-05-01","CSK vs MI": "2026-05-02","SRH vs KKR": "2026-05-03",
    "GT vs PBKS": "2026-05-03","MI vs LSG": "2026-05-04","DC vs CSK": "2026-05-05",
    "SRH vs PBKS": "2026-05-06","LSG vs RCB": "2026-05-07","DC vs KKR": "2026-05-08",
    "RR vs GT": "2026-05-09","CSK vs LSG": "2026-05-10","RCB vs MI": "2026-05-10",
    "PBKS vs DC": "2026-05-11","GT vs SRH": "2026-05-12","RCB vs KKR": "2026-05-13",
    "PBKS vs MI": "2026-05-14","LSG vs CSK": "2026-05-15","KKR vs GT": "2026-05-16",
    "PBKS vs RCB": "2026-05-17","DC vs RR": "2026-05-17","CSK vs SRH": "2026-05-18",
    "RR vs LSG": "2026-05-19","KKR vs MI": "2026-05-20","CSK vs GT": "2026-05-21",
    "SRH vs RCB": "2026-05-22","LSG vs PBKS": "2026-05-23","MI vs RR": "2026-05-24",
    "KKR vs DC": "2026-05-24",
}
def get_match_date(match_name):
    if match_name in MATCH_DATES:
        return MATCH_DATES[match_name]
    parts = match_name.split(" vs ")
    if len(parts) == 2:
        return MATCH_DATES.get(f"{parts[1]} vs {parts[0]}", "2026-01-01")
    return "2026-01-01"
def get_match_order(match_name):
    if match_name in MATCH_ORDER:
        return MATCH_ORDER[match_name]
    parts = match_name.split(" vs ")
    if len(parts) == 2:
        return MATCH_ORDER.get(f"{parts[1]} vs {parts[0]}", 999)
    return 999
def calculate_points(player_data):
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
    pts += runs * 1
    pts += fours * 1
    pts += sixes * 2
    pts += wickets * 25
    pts += catches * 3
    pts += stumpings * 5
    pts += maidens * 10
    if runs == 0 and dismissal == "Out":
        if role == "Batsman": pts -= 6
        elif role == "All-rounder": pts -= 4
        elif role == "Bowler": pts -= 2
    if dismissal == "Not Out":
        if role == "Batsman": pts += 6
        elif role == "All-rounder": pts += 4
        elif role == "Bowler": pts += 2
    if runs >= 100: pts += 30
    elif runs >= 75: pts += 20
    elif runs >= 50: pts += 10
    elif runs >= 30: pts += 5
    if hattrick: pts += 30
    if wickets >= 5: pts += 30
    elif wickets == 4: pts += 20
    elif wickets == 3: pts += 10
    elif wickets == 2: pts += 5
    if mom: pts += 10
    return pts
NAME_ALIASES = {
    "Dewald Brewis": "Dewald Brevis",
    "Varun Chakaravarthy": "Varun Chakravarthy",
    "Philip Salt": "Philip Salt",
    "Phil Salt": "Philip Salt",
    "Ravindrasinh Anirudhsinh Jadeja": "Ravindra Jadeja",
    "Jadeja": "Ravindra Jadeja",
    "romario shepherd": "Romario Shepherd",
    "D payne": "David Payne",
    "I Kishan": "Ishan Kishan",
    "Ishan Pranav Kumar Pandey Kishan": "Ishan Kishan",
    "Mohammed Siraj": "Mohammed Siraj",
    "KL Rahul": "KL Rahul",
    "Digvesh Singh Rathi": "Digvesh Rathi",
    "Vijaykumar Vyshak": "Vyshak Vijaykumar",
}
def normalize_name(name):
    if name in NAME_ALIASES:
        return NAME_ALIASES[name]
    for team in TEAMS.values():
        for p in team["players"]:
            if p["name"].lower() == name.lower():
                return p["name"]
    name_parts = set(name.lower().split())
    for team in TEAMS.values():
        for p in team["players"]:
            known_parts = set(p["name"].lower().split())
            if name_parts.issubset(known_parts) or known_parts.issubset(name_parts):
                return p["name"]
    return name
def get_all_replacements():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM replacements ORDER BY id")
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"DB read error: {e}")
        return []
def get_player_role(player_name):
    canonical = normalize_name(player_name)
    for owner, team in TEAMS.items():
        for p in team["players"]:
            if p["name"] == canonical:
                return p["role"]
    return "Batsman"
def get_leaderboard():
    all_stats = get_all_stats()
    cvc_changes = get_all_cvc_changes()
    deduped = {}
    for stat in all_stats:
        key = f"{stat['player']}|{stat['match']}"
        if key not in deduped or stat["pts"] > deduped[key]["pts"]:
            deduped[key] = stat
    all_stats = list(deduped.values())
    matches_played = sorted(list(set(s["match"] for s in all_stats)), key=get_match_order)
    owner_match_pts = {owner: {} for owner in TEAMS}
    cvc_history = {}
    for change in cvc_changes:
        team = change["team"]
        if team not in cvc_history:
            cvc_history[team] = []
        cvc_history[team].append(change)
    def get_cvc_at_match_time(owner, match_name):
        match_date = get_match_date(match_name)
        cvc_state = {}
        for p in TEAMS[owner]["players"]:
            if p["cvc"] in ("C", "VC"):
                cvc_state[p["name"]] = p["cvc"]
        if owner in cvc_history:
            changes = sorted(cvc_history[owner], key=lambda c: c["date"], reverse=True)
            for change in changes:
                if change["date"] >= match_date:
                    change_type = change["type"]
                    to_player = change["to_player"]
                    from_player = change["from_player"]
                    if to_player in cvc_state and cvc_state[to_player] == change_type:
                        del cvc_state[to_player]
                    cvc_state[from_player] = change_type
        return cvc_state
    def get_multiplier(owner, player_name, match_name):
        cvc_state = get_cvc_at_match_time(owner, match_name)
        role = cvc_state.get(player_name)
        if role:
            return 2 if role == "C" else 1.5
        player_normalized = player_name.lower().replace(" ", "").replace(".", "")
        for roster_name, r in cvc_state.items():
            roster_normalized = roster_name.lower().replace(" ", "").replace(".", "")
            if player_normalized == roster_normalized:
                return 2 if r == "C" else 1.5
        return 1
    replacement_effective = {}
    for r in get_all_replacements():
        team = r["team"]
        if team not in replacement_effective:
            replacement_effective[team] = {}
        replacement_effective[team][r["in_player"]] = r["date"]
    for stat in all_stats:
        player_name = normalize_name(stat["player"])
        match = stat["match"]
        raw_pts = stat["pts"]
        for owner, team in TEAMS.items():
            for p in team["players"]:
                if p["name"] == player_name:
                    if owner in replacement_effective and player_name in replacement_effective[owner]:
                        effective_date = replacement_effective[owner][player_name]
                        match_date = get_match_date(match)
                        if match_date < effective_date:
                            continue
                    mult = get_multiplier(owner, player_name, match)
                    if match not in owner_match_pts[owner]:
                        owner_match_pts[owner][match] = 0
                    owner_match_pts[owner][match] += raw_pts * mult
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
        result.append({"name": owner, "total": round(total, 1), "penalty": round(penalty, 1), "match_pts": {m: round(match_pts.get(m, 0), 1) for m in matches_played}})
    result.sort(key=lambda x: x["total"], reverse=True)
    for i, r in enumerate(result):
        r["rank"] = i + 1
    return result, matches_played, cvc_changes
@app.route("/")
def index():
    response = make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
@app.route("/admin")
def admin():
    return render_template("admin.html")
@app.route("/api/add-replacement", methods=["POST"])
def add_replacement():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    team = data.get("team", "").strip()
    out_player = data.get("out_player", "").strip()
    in_player = data.get("in_player", "").strip()
    date = data.get("date", "").strip()
    reason = data.get("reason", "Ruled out").strip()
    if not all([team, out_player, in_player, date]):
        return jsonify({"error": "All fields required"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO replacements (team, out_player, in_player, date, reason) VALUES (%s,%s,%s,%s,%s)", (team, out_player, in_player, date, reason))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/replacements")
def api_replacements():
    return jsonify({"replacements": get_all_replacements()})
@app.route("/api/leaderboard")
def api_leaderboard():
    lb, matches, cvc_changes = get_leaderboard()
    replacements = get_all_replacements()
    return jsonify({"leaderboard": lb, "matches": matches, "cvc_changes": cvc_changes, "replacements": replacements})
@app.route("/api/teams")
def api_teams():
    all_stats = get_all_stats()
    cvc_changes = get_all_cvc_changes()
    cvc_history = {}
    for change in cvc_changes:
        team = change["team"]
        if team not in cvc_history:
            cvc_history[team] = []
        cvc_history[team].append(change)
    def get_cvc_at_time(owner, match_name):
        match_date = get_match_date(match_name)
        cvc_state = {}
        for p in TEAMS[owner]["players"]:
            if p["cvc"] in ("C", "VC"):
                cvc_state[p["name"]] = p["cvc"]
        if owner in cvc_history:
            changes = sorted(cvc_history[owner], key=lambda c: c["date"], reverse=True)
            for change in changes:
                if change["date"] >= match_date:
                    to_player = change["to_player"]
                    from_player = change["from_player"]
                    change_type = change["type"]
                    if to_player in cvc_state and cvc_state[to_player] == change_type:
                        del cvc_state[to_player]
                    cvc_state[from_player] = change_type
        return cvc_state
    all_replacements = get_all_replacements()
    replacement_effective = {}
    for r in all_replacements:
        t = r["team"]
        if t not in replacement_effective:
            replacement_effective[t] = {}
        replacement_effective[t][r["in_player"]] = r["date"]
    teams_out = {}
    for owner, team in TEAMS.items():
        player_data = {}
        for stat in all_stats:
            name = normalize_name(stat["player"])
            match = stat["match"]
            raw_pts = stat["pts"]
            roster_names = [p["name"] for p in team["players"]]
            if name not in roster_names:
                continue
            if owner in replacement_effective and name in replacement_effective[owner]:
                effective_date = replacement_effective[owner][name]
                if get_match_date(match) < effective_date:
                    continue
            cvc_state = get_cvc_at_time(owner, match)
            role = cvc_state.get(name)
            mult = 2 if role == "C" else 1.5 if role == "VC" else 1
            if name not in player_data:
                player_data[name] = {"total_pts": 0, "total_runs": 0, "total_wkts": 0, "matches": []}
            player_data[name]["total_pts"] += raw_pts * mult
            player_data[name]["total_runs"] += stat.get("runs", 0)
            player_data[name]["total_wkts"] += stat.get("wickets", 0)
            player_data[name]["matches"].append({"match": match, "pts": round(raw_pts * mult, 1), "raw_pts": raw_pts, "mult": mult, "runs": stat.get("runs", 0), "wkts": stat.get("wickets", 0), "mom": stat.get("mom", 0)})
        players_out = []
        for p in team["players"]:
            name = p["name"]
            pd = player_data.get(name, {"total_pts": 0, "total_runs": 0, "total_wkts": 0, "matches": []})
            players_out.append({"name": name, "role": p["role"], "ipl": p["ipl"], "cvc": p["cvc"], "ruled_out": p.get("ruled_out", False), "raw_pts": round(sum(m["raw_pts"] for m in pd["matches"]), 1), "display_pts": round(pd["total_pts"], 1), "total_runs": pd["total_runs"], "total_wkts": pd["total_wkts"], "matches": sorted(pd["matches"], key=lambda m: get_match_order(m["match"]))})
        teams_out[owner] = sorted(players_out, key=lambda x: x["display_pts"], reverse=True)
    return jsonify({"teams": teams_out})
@app.route("/api/players")
def api_players():
    all_stats = get_all_stats()
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
        player_totals[name]["matches"].append({"match": stat["match"], "match_num": get_match_order(stat["match"]), "pts": stat["pts"], "runs": stat.get("runs", 0), "wkts": stat.get("wickets", 0), "mom": stat.get("mom", 0)})
    players = sorted(player_totals.values(), key=lambda x: x["total_pts"], reverse=True)
    for p in players:
        p["total_pts"] = round(p["total_pts"], 1)
        p["matches"] = sorted(p["matches"], key=lambda m: m["match_num"])
    return jsonify({"players": players})
def process_players(players_data, match_name, mom_player):
    merged = {}
    for p in players_data:
        name = p["player"].strip()
        if name not in merged:
            merged[name] = {"player": name, "role": p.get("role") or get_player_role(name), "runs": p.get("runs", 0), "fours": p.get("fours", 0), "sixes": p.get("sixes", 0), "wickets": p.get("wickets", 0), "catches": p.get("catches", 0), "stumpings": p.get("stumpings", 0), "maidens": p.get("maidens", 0), "dismissal": p.get("dismissal", "DNB"), "mom": p.get("mom", 0), "hattrick": p.get("hattrick", 0)}
        else:
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
            if p.get("dismissal", "DNB") != "DNB":
                m["dismissal"] = p["dismissal"]
            if p.get("role") in ["All-rounder", "Bowler"] and m["role"] == "Batsman":
                m["role"] = p["role"]
    new_entries = []
    mom_applied = False
    for name, p in merged.items():
        pts = calculate_points(p)
        if mom_player and not mom_applied:
            player_clean = name.strip().lower().replace(".", "").replace(" ", "")
            mom_clean = mom_player.strip().lower().replace(".", "").replace(" ", "")
            if mom_clean in player_clean or player_clean in mom_clean:
                pts += 10
                p["mom"] = 1
                mom_applied = True
        new_entries.append({"match": match_name, "player": name, "role": p["role"], "runs": p["runs"], "fours": p["fours"], "sixes": p["sixes"], "wickets": p["wickets"], "catches": p["catches"], "stumpings": p["stumpings"], "maidens": p["maidens"], "dismissal": p["dismissal"], "mom": p["mom"], "hattrick": p["hattrick"], "pts": pts})
    return new_entries
@app.route("/api/fetch-scorecard", methods=["POST"])
def fetch_scorecard():
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
        url = f"https://api.cricapi.com/v1/match_scorecard?apikey={api_key}&id={match_id}"
        response = req.get(url, timeout=15)
        response.raise_for_status()
        result = response.json()
        if result.get("status") != "success":
            return jsonify({"error": f"API error: {result.get('reason', result.get('message', 'Unknown error'))}"}), 500
        scorecard_data = result.get("data", {})
        innings_list = scorecard_data.get("scorecard", [])
        if not innings_list:
            return jsonify({"error": "No scorecard data available for this match"}), 500
        players = {}
        def get_or_create(name):
            if name not in players:
                players[name] = {"player": name, "role": get_player_role(name), "runs": 0, "fours": 0, "sixes": 0, "wickets": 0, "catches": 0, "stumpings": 0, "maidens": 0, "dismissal": "DNB", "mom": 0, "hattrick": 0}
            return players[name]
        for innings in innings_list:
            for bat in innings.get("batting", []):
                name = bat["batsman"]["name"]
                p = get_or_create(name)
                dismissal_text = bat.get("dismissal-text", "")
                dismissal = "Not Out" if dismissal_text == "not out" else ("Out" if dismissal_text else "DNB")
                if bat.get("r", 0) > p["runs"]:
                    p["runs"] = bat.get("r", 0)
                    p["fours"] = bat.get("4s", 0)
                    p["sixes"] = bat.get("6s", 0)
                if dismissal != "DNB":
                    p["dismissal"] = dismissal
        for innings in innings_list:
            for bowl in innings.get("bowling", []):
                name = bowl["bowler"]["name"]
                p = get_or_create(name)
                p["wickets"] += bowl.get("w", 0)
                p["maidens"] += bowl.get("m", 0)
        for innings in innings_list:
            for catch in innings.get("catching", []):
                catcher_info = catch.get("catcher", {})
                name = catcher_info.get("name", "")
                if not name:
                    continue
                alt_names = catcher_info.get("altnames", [])
                matched_name = name
                if name not in players:
                    for alt in alt_names:
                        if alt in players:
                            matched_name = alt
                            break
                p = get_or_create(matched_name)
                p["catches"] += catch.get("catch", 0)
                p["stumpings"] += catch.get("stumped", 0)
        new_entries = process_players(list(players.values()), match_name, mom_player)
        save_stats(new_entries)
        return jsonify({"success": True, "match": match_name, "players_processed": len(new_entries), "entries": new_entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/delete-all-matches", methods=["POST"])
def delete_all_matches():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM match_stats")
                deleted = cur.rowcount
            conn.commit()
        return jsonify({"success": True, "rows_deleted": deleted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/delete-match", methods=["POST"])
def delete_match():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    match_name = data.get("match_name", "").strip()
    if not match_name:
        return jsonify({"error": "Match name required"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM match_stats WHERE match=%s", (match_name,))
                deleted = cur.rowcount
            conn.commit()
        return jsonify({"success": True, "match": match_name, "rows_deleted": deleted})
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
    save_cvc_change({"team": team, "type": change_type, "from": from_player, "to": to_player, "date": date, "penalty": -150 if change_type == "C" else -75})
    return jsonify({"success": True})
@app.route("/api/delete-cvc", methods=["POST"])
def delete_cvc():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    cvc_id = data.get("id")
    if not cvc_id:
        return jsonify({"error": "ID required"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cvc_changes WHERE id=%s", (cvc_id,))
                deleted = cur.rowcount
            conn.commit()
        return jsonify({"success": True, "deleted": deleted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/rename-match", methods=["POST"])
def rename_match():
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key != os.environ.get("ADMIN_KEY", "ipl2026admin"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()
    if not old_name or not new_name:
        return jsonify({"error": "Both old and new match names required"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE match_stats SET match=%s WHERE match=%s", (new_name, old_name))
                updated = cur.rowcount
            conn.commit()
        return jsonify({"success": True, "old_name": old_name, "new_name": new_name, "rows_updated": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/cvc-changes")
def api_cvc_changes():
    return jsonify({"changes": get_all_cvc_changes()})
@app.route("/api/matches")
def api_matches():
    all_stats = get_all_stats()
    matches = sorted(list(set(s["match"] for s in all_stats)))
    return jsonify({"matches": matches})
@app.route("/api/banter-reactions", methods=["GET"])
def get_banter_reactions():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT match, emoji, count FROM banter_reactions")
                rows = [dict(r) for r in cur.fetchall()]
        result = {}
        for row in rows:
            if row["match"] not in result:
                result[row["match"]] = {}
            result[row["match"]][row["emoji"]] = row["count"]
        return jsonify(result)
    except Exception as e:
        return jsonify({}), 500
@app.route("/api/banter-reactions", methods=["POST"])
def update_banter_reaction():
    data = request.get_json()
    match = data.get("match", "").strip()
    emoji = data.get("emoji", "").strip()
    delta = data.get("delta", 1)
    if not match or not emoji:
        return jsonify({"error": "match and emoji required"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO banter_reactions (match, emoji, count) VALUES (%s, %s, %s) ON CONFLICT (match, emoji) DO UPDATE SET count = GREATEST(0, banter_reactions.count + %s) RETURNING count", (match, emoji, max(0, delta), delta))
                new_count = cur.fetchone()["count"]
            conn.commit()
        return jsonify({"success": True, "count": new_count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/banter-comments/<path:match>", methods=["GET"])
def get_banter_comments(match):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, author, comment, created_at FROM banter_comments WHERE match=%s ORDER BY created_at ASC", (match,))
                rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])
        return jsonify(rows)
    except Exception as e:
        return jsonify([]), 500
@app.route("/api/banter-comments", methods=["POST"])
def add_banter_comment():
    data = request.get_json()
    match = data.get("match", "").strip()
    author = data.get("author", "").strip()
    comment = data.get("comment", "").strip()
    if not match or not author or not comment:
        return jsonify({"error": "match, author and comment required"}), 400
    if len(comment) > 200:
        return jsonify({"error": "Comment too long"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO banter_comments (match, author, comment) VALUES (%s, %s, %s) RETURNING id", (match, author, comment))
                new_id = cur.fetchone()["id"]
            conn.commit()
        return jsonify({"success": True, "id": new_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/generate-banter", methods=["POST"])
def generate_banter():
    data = request.get_json()
    prompt = data.get("prompt", "")
    match = data.get("match", "").strip()
    if not prompt:
        return jsonify({"error": "No prompt"}), 400
    if match:
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT banter FROM banter_cache WHERE match=%s", (match,))
                    row = cur.fetchone()
                    if row:
                        return jsonify({"banter": row["banter"], "cached": True})
        except Exception:
            pass
    try:
        response = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=300, messages=[{"role": "user", "content": prompt}])
        banter = response.content[0].text.strip()
        if match:
            try:
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("INSERT INTO banter_cache (match, banter) VALUES (%s, %s) ON CONFLICT (match) DO NOTHING", (match, banter))
                        cur.execute("DELETE FROM banter_cache WHERE match NOT IN (SELECT match FROM banter_cache ORDER BY created_at DESC LIMIT 5)")
                    conn.commit()
            except Exception:
                pass
        return jsonify({"banter": banter})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
