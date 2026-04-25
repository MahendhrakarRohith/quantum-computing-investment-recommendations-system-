import pandas as pd
from fastapi import FastAPI, Request, Query, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
import json
import sqlite3
import requests
import re
import random
import string
import yfinance as yf
from fastapi import Form, Response, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
import bcrypt

# 📢 1. CONFIGURE GEMINI AI SDK
from google import genai
from dotenv import load_dotenv
load_dotenv()

gemini_client = None
if os.getenv("GEMINI_API_KEY"):
    gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

_GEMINI_MODEL_CANDIDATES = [
    os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),       
    "gemini-2.0-flash",              
    "gemini-1.5-flash",              
]

def _call_gemini(prompt: str):
    if not gemini_client: return None, "gemini_client_unconfigured (API Key missing)"
    last_error = "Unknown Error"
    for model_name in _GEMINI_MODEL_CANDIDATES:
        if not model_name: continue
        try:
            response = gemini_client.models.generate_content(model=model_name, contents=prompt)
            return response.text.strip(), model_name
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Gemini API Error on {model_name}: {last_error}")
            continue
    return None, f"Google API Error: {last_error}"

# 📢 2. IMPORT INTERNAL MODULES
from app.ml.engine import PredictionEngine
from app.ml.sentiment import get_news_sentiment
from app.services.websocket import AngelOneWebSocket 
from app.core.config import settings

# 📢 3. QUANTUM LIBRARIES (QISKIT)
from qiskit_optimization.applications import Knapsack
from qiskit_optimization.algorithms import MinimumEigenOptimizer

try:
    from qiskit_algorithms import QAOA
    from qiskit_algorithms.optimizers import COBYLA
    from qiskit.primitives import Sampler
    _qaoa_available = True
except ImportError:
    _qaoa_available = False
    QAOA = COBYLA = Sampler = None

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 🛡️ DYNAMIC FOLDER ROUTING (Works on any OS)
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # This gets the /app folder
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, "..")) # This goes up one level to root

templates_dir = os.path.join(ROOT_DIR, "templates")
templates = Jinja2Templates(directory=templates_dir)

DB_PATH = os.path.join(ROOT_DIR, "market_leaderboard.db")


# --- 🔒 AUTHENTICATION & PROFILE SETUP ---
def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def generate_user_id():
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"USR-{chars}"

def init_user_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Base Users & History Tables
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_history (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, symbol TEXT, action TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
                  
    # Smart Column Upgrader (Adds profile fields without deleting data)
    new_columns = [("user_id", "TEXT UNIQUE"), ("name", "TEXT"), ("age", "INTEGER"), ("preferred_risk", "TEXT DEFAULT 'moderate'")]
    for col_name, col_type in new_columns:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass 
            
    conn.commit()
    conn.close()

init_user_db() 

def log_user_action(username: str, symbol: str, action: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO user_history (username, symbol, action) VALUES (?, ?, ?)", (username, symbol, action))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Failed to log history: {e}")

# --- 🧠 HELPER FUNCTIONS ---
def get_latest_news(symbol: str):
    if not settings.NEWS_API_KEY: return []
    search_query = symbol.split('-')[0] 
    company_names = {"TCS": "Tata Consultancy", "RELIANCE": "Reliance", "HDFCBANK": "HDFC", "INFY": "Infosys", "SBI": "State Bank"}
    query_name = company_names.get(search_query, search_query)
    url = f"https://newsapi.org/v2/everything?q=%22{query_name}%22&domains=moneycontrol.com,economictimes.indiatimes.com,livemint.com,cnbctv18.com&sortBy=publishedAt&pageSize=5&language=en&apiKey={settings.NEWS_API_KEY}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("status") == "ok":
            valid_articles = []
            for item in data.get("articles", []):
                title = item.get("title", "").lower()
                if search_query.lower() in title or query_name.lower() in title:
                    valid_articles.append({"title": item.get("title"), "url": item.get("url"), "source": item.get("source", {}).get("name", "News"), "date": item.get("publishedAt", "")[:10]})
                if len(valid_articles) == 3: break
            return valid_articles
    except: pass
    return []

def calculate_optimized_weights(top_stocks):
    allocations, total_score, scores = {}, 0, {}
    for stock in top_stocks:
        symbol = stock["symbol"]
        upside = float(stock["upside"]) if stock["upside"] > 0 else 0.1
        conf_match = re.search(r'([0-9.]+)% confidence', stock.get("reason", ""))
        score = upside * (((float(conf_match.group(1)) if conf_match else 50.0) / 100.0) ** 2)
        scores[symbol] = score
        total_score += score
    if total_score == 0: return {stock["symbol"]: 20.0 for stock in top_stocks} 
    for symbol, score in scores.items(): allocations[symbol] = max(5.0, min(40.0, (score / total_score) * 100))
    adjusted_total = sum(allocations.values())
    for symbol in allocations: allocations[symbol] = round((allocations[symbol] / adjusted_total) * 100, 1)
    return allocations

def _solve_knapsack_classical(values, weights, labels, budget):
    capacity = int(max(1, round(budget)))
    int_weights = [max(1, int(round(w))) for w in weights]
    dp = [(0.0, []) for _ in range(capacity + 1)]
    for idx in range(len(values)):
        w, v = int_weights[idx], values[idx]
        for cap in range(capacity, w - 1, -1):
            prev_val, prev_indices = dp[cap - w]
            if prev_val + v > dp[cap][0]: dp[cap] = (prev_val + v, prev_indices + [idx])
    best_indices = max(dp, key=lambda x: x[0])[1]
    portfolio, total_spent, total_expected_profit = {}, 0.0, 0.0
    for i in best_indices:
        symbol = labels[i]
        if symbol not in portfolio: portfolio[symbol] = {"shares": 0, "price": weights[i], "total_value": 0.0, "expected_profit": 0.0}
        portfolio[symbol]["shares"] += 1
        portfolio[symbol]["total_value"] = round(portfolio[symbol]["total_value"] + weights[i], 2)
        portfolio[symbol]["expected_profit"] = round(portfolio[symbol]["expected_profit"] + values[i], 2)
        total_spent += weights[i]
        total_expected_profit += values[i]
    return portfolio, total_spent, total_expected_profit

def optimize_portfolio_qaoa(budget: float, ai_predictions: list):
    if budget <= 0 or not ai_predictions: raise ValueError("Invalid budget/predictions.")
    values, weights, labels = [], [], []
    for stock in ai_predictions:
        price = float(stock['price'])
        expected_profit = price * (float(stock['expected_return_pct']) / 100.0)
        for _ in range(min(5, int(budget // price))):
            values.append(expected_profit)
            weights.append(price)
            labels.append(stock['symbol'])
    if not weights: raise ValueError("Budget too low.")
    
    if _qaoa_available:
        qp = Knapsack(values=values, weights=weights, max_weight=budget).to_quadratic_program()
        selected_vector = MinimumEigenOptimizer(QAOA(sampler=Sampler(), optimizer=COBYLA(maxiter=30), reps=1)).solve(qp).x
    else:
        portfolio, total_spent, total_expected_profit = _solve_knapsack_classical(values, weights, labels, budget)
        return {"status": "success", "requested_funds": round(budget, 2), "total_spent": round(total_spent, 2), "remaining_cash": round(budget - total_spent, 2), "projected_return_inr": round(total_expected_profit, 2), "portfolio": portfolio, "solver": "classical-fallback"}

    portfolio, total_spent, total_expected_profit = {}, 0.0, 0.0
    for i, is_selected in enumerate(selected_vector):
        if is_selected == 1:
            symbol = labels[i]
            if symbol not in portfolio: portfolio[symbol] = {"shares": 0, "price": weights[i], "total_value": 0.0, "expected_profit": 0.0}
            portfolio[symbol]["shares"] += 1
            portfolio[symbol]["total_value"] = round(portfolio[symbol]["total_value"] + weights[i], 2)
            portfolio[symbol]["expected_profit"] = round(portfolio[symbol]["expected_profit"] + values[i], 2)
            total_spent += weights[i]
            total_expected_profit += values[i]
    return {"status": "success", "requested_funds": round(budget, 2), "total_spent": round(total_spent, 2), "remaining_cash": round(budget - total_spent, 2), "projected_return_inr": round(total_expected_profit, 2), "portfolio": portfolio, "solver": "quantum-qaoa"}

def fetch_market_data_safe(yf_symbol: str):
    try:
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="5d")
        if hist.empty: return None
        current = float(hist['Close'].iloc[-1])
        fi = ticker.fast_info
        try:
            info = ticker.info
            pe, eps, div_yield, sma_50, sma_200, target = info.get('trailingPE', 'N/A'), info.get('trailingEps', 'N/A'), info.get('dividendYield', 0.0), info.get('fiftyDayAverage', 0.0), info.get('twoHundredDayAverage', 0.0), info.get('targetMeanPrice', 'N/A')
        except:
            pe, eps, div_yield, sma_50, sma_200, target = 'N/A', 'N/A', 0.0, 0.0, 0.0, 'N/A'
        return {
            "current": current, "prev_close": float(hist['Close'].iloc[-2]) if len(hist) > 1 else current,
            "open": float(hist['Open'].iloc[-1]), "day_low": float(hist['Low'].iloc[-1]), "day_high": float(hist['High'].iloc[-1]),
            "volume": int(hist['Volume'].iloc[-1]), "mcap": fi.get('marketCap', 0), "high_52": fi.get('yearHigh', 0.0), "low_52": fi.get('yearLow', 0.0),
            "pe": pe, "eps": eps, "div_yield": div_yield, "sma_50": sma_50, "sma_200": sma_200, "target_price": target
        }
    except: return None

def resolve_ticker_with_ai(raw_input: str) -> str:
    if not gemini_client: return raw_input.replace(' ', '').upper()
    prompt = f"""Find the official National Stock Exchange of India (NSE) ticker symbol for: "{raw_input}". RULES: Return ONLY the ticker (e.g., RELIANCE, TCS, INFY). No .NS or -EQ. NO quotes or punctuation. If invalid, return UNKNOWN."""
    ai_text, model_used = _call_gemini(prompt)
    if ai_text:
        resolved = ai_text.strip().upper().replace('`', '').replace('"', '')
        if " " in resolved: resolved = resolved.split()[-1]
        return resolved
    return raw_input.replace(' ', '').upper()

# --- 📡 WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None
    async def connect(self, websocket: WebSocket):
        if self.loop is None: self.loop = asyncio.get_running_loop()
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try: await connection.send_text(json.dumps(message))
            except: pass

manager = ConnectionManager()
angel_ws = AngelOneWebSocket(manager)

@app.on_event("startup")
async def startup_event():
    print("🚀 Starting Hybrid Quantum-AI Core Engine...")
    asyncio.create_task(angel_ws.connect_and_stream())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text() 
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- 🌐 API ROUTES ---
@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})

@app.post("/api/signup")
async def signup(name: str = Form(...), email: str = Form(...), age: int = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH) 
    c = conn.cursor()
    try:
        hashed_pw = get_password_hash(password)
        new_id = generate_user_id()
        c.execute("INSERT INTO users (username, password_hash, user_id, name, age) VALUES (?, ?, ?, ?, ?)", (email, hashed_pw, new_id, name, age))
        conn.commit()
        return {"status": "success", "message": f"Account created! Your Secure ID is {new_id}. Please log in."}
    except sqlite3.IntegrityError:
        return {"error": "Email is already registered."}
    finally:
        conn.close()

@app.post("/api/login")
async def login(response: Response, login_identifier: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH) 
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if "@" in login_identifier:
        c.execute("SELECT * FROM users WHERE username = ?", (login_identifier,))
    else:
        c.execute("SELECT * FROM users WHERE user_id = ?", (login_identifier.upper(),))
    user = c.fetchone()
    conn.close()

    if not user or not verify_password(password, user['password_hash']): return {"error": "Invalid Email/ID or password"}
    response.set_cookie(key="session_token", value=user['username'], httponly=True, max_age=86400) 
    return {"status": "success"}

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return RedirectResponse(url="/login")

@app.get("/")
async def home(request: Request, symbol: str = Query("RELIANCE")):
    session = request.cookies.get("session_token")
    if not session: return RedirectResponse(url="/login")

    try:
        clean_symbol = symbol.upper().replace('-EQ', '').strip()
        resolved_symbol = await asyncio.to_thread(resolve_ticker_with_ai, clean_symbol)

        if resolved_symbol != "UNKNOWN": log_user_action(session, resolved_symbol, "Searched Ticker")
        if resolved_symbol == "UNKNOWN" or not resolved_symbol:
            return templates.TemplateResponse("index.html", {"request": request, "ticker": symbol.upper(), "current_price": "0.00", "recommendation": "INVALID", "recommendation_class": "hold", "ai_analysis": f"System Alert: '{symbol}' is not recognized.", "sentiment": "N/A", "news": []})

        yf_symbol = resolved_symbol + ".NS"
        market_data = await asyncio.to_thread(fetch_market_data_safe, yf_symbol)

        if not market_data or market_data["current"] == 0.0:
            market_data = {"current": 0.0, "prev_close": 0.0, "open": 0.0, "day_low": 0.0, "day_high": 0.0, "volume": 0, "mcap": 0, "high_52": 0.0, "low_52": 0.0, "pe": "N/A", "eps": "N/A", "div_yield": 0.0, "sma_50": 0.0, "sma_200": 0.0, "target_price": "N/A"}

        current, day_low, day_high, high_52, low_52, mcap, pe = market_data["current"], market_data["day_low"], market_data["day_high"], market_data["high_52"], market_data["low_52"], market_data["mcap"], market_data["pe"]
        news_articles = await asyncio.to_thread(get_latest_news, resolved_symbol)
        news_titles = [article['title'] for article in news_articles] if news_articles else ["No recent news."]
        
        try:
            mcap_fmt = f"₹{mcap / 1000000000000:.2f} Trillion" if mcap > 1000000000000 else f"₹{mcap / 1000000000:.2f} Billion"
            prompt = f"""
            Analyze {resolved_symbol}. DATA: Price: ₹{current}, Range: ₹{day_low}-₹{day_high}, 52W: ₹{low_52}-₹{high_52}, P/E: {pe}, News: {news_titles}.
            Output exactly this HTML format:
            <div class="space-y-4 not-italic">
                <div><h5 class="text-quantPurple font-bold mb-1 border-b border-gray-700 pb-1">Key Stock Metrics</h5><ul class="text-xs text-gray-300 space-y-1 list-disc pl-4"><li><b>P/E Ratio:</b> {pe}</li><li><b>Market Cap:</b> {mcap_fmt}</li></ul></div>
                <div><h5 class="text-quantPurple font-bold mb-1 border-b border-gray-700 pb-1">AI Narrative</h5><ul class="text-xs text-gray-300 space-y-1 list-disc pl-4"><li>[Write 2 sentences synthesizing the data and news]</li></ul></div>
                <div class="mt-3 pt-2 border-t border-gray-700"><span class="font-bold text-gray-400 text-xs">FINAL RECOMMENDATION:</span> [STRONG BUY, BUY, HOLD, SELL, or STRONG SELL]</div>
            </div>
            """
            ai_text, model_used = await asyncio.to_thread(_call_gemini, prompt)
            
            if ai_text:
                ai_analysis = ai_text.replace('```html', '').replace('```', '').strip()
                if ai_analysis.startswith('"'): ai_analysis = ai_analysis[1:-1]
                elif ai_analysis.startswith("'"): ai_analysis = ai_analysis[1:-1]
            else: ai_analysis = "AI analysis unavailable."
            
            rec, rec_class = "HOLD", "hold"
            if "STRONG BUY" in ai_analysis.upper(): rec, rec_class = "STRONG BUY", "buy"
            elif "BUY" in ai_analysis.upper(): rec, rec_class = "BUY", "buy"
            elif "STRONG SELL" in ai_analysis.upper(): rec, rec_class = "STRONG SELL", "sell"
            elif "SELL" in ai_analysis.upper(): rec, rec_class = "SELL", "sell"
            
        except Exception as e:
            ai_analysis, rec, rec_class = f"AI Error: {str(e)}", "HOLD", "hold"

        return templates.TemplateResponse("index.html", {"request": request, "ticker": resolved_symbol, "current_price": f"{current:,.2f}", "recommendation": rec, "recommendation_class": rec_class, "ai_analysis": ai_analysis, "sentiment": "AI Generated", "news": news_articles})
    except Exception as e: return HTMLResponse(content=str(e), status_code=500)

@app.get("/stock/{ticker}")
async def stock_detail(request: Request, ticker: str):
    session = request.cookies.get("session_token")
    if not session: return RedirectResponse(url="/login")

    try:
        clean_ticker = ticker.upper().replace('-EQ', '').strip()
        yf_symbol = clean_ticker + ".NS"
        log_user_action(session, clean_ticker, "Viewed AI Graph")
        market_data = await asyncio.to_thread(fetch_market_data_safe, yf_symbol)
        news_articles = await asyncio.to_thread(get_latest_news, clean_ticker)
        
        if not market_data: market_data = {"current": 0.0, "prev_close": 0.0, "open": 0.0, "day_low": 0.0, "day_high": 0.0, "volume": 0, "mcap": 0, "high_52": 0.0, "low_52": 0.0, "pe": "N/A", "eps": "N/A", "div_yield": 0.0, "sma_50": 0.0, "sma_200": 0.0, "target_price": "N/A"}
        return templates.TemplateResponse("stock_detail.html", {"request": request, "ticker": clean_ticker, "data": market_data, "news": news_articles})
    except Exception as e: return HTMLResponse(content=str(e), status_code=500)

@app.get("/api/discover")
async def discover_best_stock():
    try:
        conn = sqlite3.connect(DB_PATH) 
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM recommendations WHERE current_price > 50 ORDER BY upside DESC LIMIT 50')
        top_stocks = cursor.fetchall()
        conn.close()

        high_conf_stocks, other_stocks = [], []
        for stock in top_stocks:
            stock_dict = dict(stock)
            conf_match = re.search(r'([0-9.]+)% confidence', stock_dict.get("reason", ""))
            if conf_match and float(conf_match.group(1)) >= 80.0: high_conf_stocks.append(stock_dict)
            else: other_stocks.append(stock_dict)
        
        final_top_5 = (high_conf_stocks + other_stocks)[:5]
        if final_top_5:
            optimized_allocations = calculate_optimized_weights(final_top_5)
            for stock in final_top_5: stock["quantum_allocation"] = optimized_allocations.get(stock["symbol"], 20.0)
            return {"stocks": final_top_5, "top_news": get_latest_news(final_top_5[0]["symbol"])}
        else: return {"error": "Database is empty. Please run the background scanner first."}
    except Exception as e: return {"error": f"Database error: {str(e)}"}

@app.get("/api/build-portfolio")
async def build_portfolio(funds: float = Query(10000.0)):
    try:
        if funds < 100: return {"error": "Minimum investment is ₹100."}
        discover_data = await discover_best_stock()
        if "error" in discover_data: return discover_data
        qaoa_recs = [{'symbol': s['symbol'], 'price': float(s['current_price']), 'expected_return_pct': float(s['upside'])} for s in discover_data["stocks"]]
        allocation_result = await asyncio.to_thread(optimize_portfolio_qaoa, funds, qaoa_recs)
        return {"status": "success", "requested_funds": funds, "data": allocation_result}
    except Exception as e: return {"error": f"Portfolio failed: {str(e)}"}
    
# --- 🧑‍🚀 PROFILE & USER ROUTES ---
@app.get("/profile")
async def user_profile(request: Request):
    session = request.cookies.get("session_token")
    if not session: return RedirectResponse(url="/login")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Ro
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (session,))
    user_data = c.fetchone()
    
    user_dict = dict(user_data) if user_data else {}
    
    # THE FIX: If the database returns None (NULL) for old accounts, set a safe default
    if user_dict.get("user_id") is None: user_dict["user_id"] = "N/A"
    if user_dict.get("name") is None: user_dict["name"] = "Investor"
    if user_dict.get("age") is None: user_dict["age"] = 30
    if user_dict.get("preferred_risk") is None: user_dict["preferred_risk"] = "moderate"
    
    user_dict["email"] = session

    c.execute("SELECT symbol, action, datetime(timestamp, 'localtime') as ts FROM user_history WHERE username = ? ORDER BY timestamp DESC LIMIT 20", (session,))
    history = c.fetchall()
    conn.close()

    return templates.TemplateResponse("profile.html", {"request": request, "user": user_dict, "history": history})

@app.post("/update-profile")
async def update_profile(request: Request, name: str = Form(...), age: int = Form(...), risk_preference: str = Form(...)):
    session = request.cookies.get("session_token")
    if not session: return RedirectResponse(url="/login")

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET name = ?, age = ?, preferred_risk = ? WHERE username = ?", (name, age, risk_preference, session))
        conn.commit()
        conn.close()
    except Exception as e: print(f"Profile Update Error: {e}")

    return RedirectResponse(url="/profile", status_code=303)


@app.get("/api/commodities")
async def get_commodities():
    try:
        gold = await asyncio.to_thread(fetch_market_data_safe, "GOLDBEES.NS")
        silver = await asyncio.to_thread(fetch_market_data_safe, "SILVERBEES.NS")
        
        hyd_gold_10g_base = 135650.00
        hyd_silver_1kg_base = 93000.00
        
        gold_change_pct = ((gold["current"] - gold["prev_close"]) / gold["prev_close"]) if gold and gold["prev_close"] else 0
        silver_change_pct = ((silver["current"] - silver["prev_close"]) / silver["prev_close"]) if silver and silver["prev_close"] else 0
        
        live_hyd_gold = hyd_gold_10g_base * (1 + gold_change_pct)
        live_hyd_silver = hyd_silver_1kg_base * (1 + silver_change_pct)

        fd_rates = [
            {"bank": "SBI (1-2 Yr)", "rate": "6.80%"},
            {"bank": "HDFC (15 Mo)", "rate": "7.25%"},
            {"bank": "Post Office", "rate": "7.40%"}
        ]
        
        return {
            "status": "success",
            "gold": {"price": live_hyd_gold, "change": round(gold_change_pct * 100, 2)},
            "silver": {"price": live_hyd_silver, "change": round(silver_change_pct * 100, 2)},
            "fd": fd_rates
        }
    except Exception as e: return {"error": str(e)}