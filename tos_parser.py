import csv
import re
import os
from datetime import datetime

# Regex to parse TOS option symbols
# Format examples:
# - SPY 100 18 JUL 26 450 CALL
# - SPY 100 02 JUL 26 450 C
# - SPY 100 18 JUL 26 450.5 PUT
# - SPY260702C00450000 (OCC Format)
OPTION_REGEX = re.compile(
    r'^([A-Z]{1,6})\s+(\d+)?\s*(\d{1,2}\s+[A-Z]{3}\s+\d{2,4})\s+([\d.]+)\s+(CALL|PUT|C|P)$',
    re.IGNORECASE
)
OCC_REGEX = re.compile(
    r'^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$',
    re.IGNORECASE
)

def parse_option_symbol(symbol):
    """
    Parse a symbol to determine if it is an option and extract details.
    Returns a dict with details.
    """
    symbol = symbol.strip()
    
    # Check OCC format (e.g. SPY260702C00450000)
    occ_match = OCC_REGEX.match(symbol)
    if occ_match:
        underlying = occ_match.group(1).upper()
        year = "20" + occ_match.group(2)
        month = occ_match.group(3)
        day = occ_match.group(4)
        opt_type = "CALL" if occ_match.group(5).upper() == "C" else "PUT"
        strike = float(occ_match.group(6)) / 1000.0
        expiry = f"{day} {month} {year}" # normalize or parse
        # Convert month number to short name for display
        try:
            m_name = datetime.strptime(month, "%m").strftime("%b").upper()
            expiry = f"{day} {m_name} {year[2:]}"
        except:
            pass
        return {
            "is_option": True,
            "underlying": underlying,
            "expiry": expiry,
            "strike": strike,
            "option_type": opt_type,
            "multiplier": 100
        }
        
    # Check TOS format (e.g. SPY 100 18 JUL 26 450 CALL)
    tos_match = OPTION_REGEX.match(symbol)
    if tos_match:
        underlying = tos_match.group(1).upper()
        expiry = tos_match.group(3).upper()
        strike = float(tos_match.group(4))
        opt_type = tos_match.group(5).upper()
        if opt_type in ("C", "CALL"):
            opt_type = "CALL"
        elif opt_type in ("P", "PUT"):
            opt_type = "PUT"
        return {
            "is_option": True,
            "underlying": underlying,
            "expiry": expiry,
            "strike": strike,
            "option_type": opt_type,
            "multiplier": 100
        }
        
    # If not matching option patterns, treat as stock/ETF itself
    return {
        "is_option": False,
        "underlying": symbol.upper(),
        "expiry": None,
        "strike": None,
        "option_type": None,
        "multiplier": 1
    }

def parse_date(date_str):
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %H:%M"
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            pass
    raise ValueError(f"Could not parse date: {date_str}")

def parse_tos_csv(filepath):
    """
    Parse TOS CSV file to retrieve executions.
    """
    executions = []
    
    if not os.path.exists(filepath):
        return []
        
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
        
    in_executions = False
    headers = None
    
    # Store detected column mappings
    time_col = None
    symbol_col = None
    price_col = None
    qty_col = None
    side_col = None
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            if in_executions:
                in_executions = False
            continue
            
        reader = csv.reader([line_str])
        try:
            parts = next(reader)
        except:
            continue
            
        parts = [p.strip() for p in parts]
        
        # Look for headers dynamically
        time_key = next((p for p in parts if p in ("Time", "Execution Time", "Exec Time")), None)
        symbol_key = next((p for p in parts if p == "Symbol"), None)
        price_key = next((p for p in parts if p in ("Price", "Net Price")), None)
        qty_key = next((p for p in parts if p == "Qty"), None)
        side_key = next((p for p in parts if p == "Side"), None)
        
        if not in_executions and time_key and symbol_key and price_key and qty_key and side_key:
            in_executions = True
            headers = parts
            time_col = time_key
            symbol_col = symbol_key
            price_col = price_key
            qty_col = qty_key
            side_col = side_key
            continue
            
        if in_executions:
            # Check if this row is a total row or a section separator
            if any(p in ("TOTAL", "OVERALL TOTALS") for p in parts):
                continue
                
            if len(parts) < len(headers):
                continue
                
            # Create a dict from headers and row
            exec_dict = {}
            for h, val in zip(headers, parts):
                if h:
                    exec_dict[h] = val.strip()
                    
            norm_exec = {}
            
            # Map time
            if time_col in exec_dict:
                try:
                    norm_exec["time"] = parse_date(exec_dict[time_col])
                except Exception as e:
                    continue
            else:
                continue
                
            # Map side
            if side_col in exec_dict:
                norm_exec["side"] = exec_dict[side_col].upper() # BUY or SELL
                if norm_exec["side"].startswith("BOT"):
                    norm_exec["side"] = "BUY"
                elif norm_exec["side"].startswith("SOLD") or norm_exec["side"].startswith("SLD"):
                    norm_exec["side"] = "SELL"
            else:
                continue
                
            # Map qty
            if qty_col in exec_dict:
                try:
                    qty_val = exec_dict[qty_col].replace("+", "").replace("-", "").strip()
                    norm_exec["qty"] = abs(int(float(qty_val)))
                except:
                    continue
            else:
                continue
                
            # Map price
            if price_col in exec_dict:
                try:
                    price_val = exec_dict[price_col].replace("$", "").replace(",", "").strip()
                    norm_exec["price"] = float(price_val)
                except:
                    continue
            else:
                continue
                
            # Map symbol (reconstruct if split columns are present)
            symbol_val = exec_dict.get("Symbol", "")
            exp_val = exec_dict.get("Exp", "")
            strike_val = exec_dict.get("Strike", "")
            type_val = exec_dict.get("Type", "")
            
            if exp_val and strike_val and type_val:
                norm_exec["symbol"] = f"{symbol_val} 100 {exp_val} {strike_val} {type_val}"
            else:
                norm_exec["symbol"] = symbol_val
                
            norm_exec["pos_effect"] = exec_dict.get("Pos Effect", "").upper()
            executions.append(norm_exec)
            
    return executions

def pair_trades(executions):
    """
    Pairs BUY and SELL executions into round-trip trades.
    Uses FIFO pairing.
    """
    by_symbol = {}
    for ex in executions:
        symbol = ex["symbol"]
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(ex)
        
    trades = []
    
    for symbol, sym_execs in by_symbol.items():
        sym_execs.sort(key=lambda x: x["time"])
        
        inventory = [] 
        direction = None 
        
        sym_details = parse_option_symbol(symbol)
        multiplier = sym_details["multiplier"]
        
        current_trade = None
        
        for ex in sym_execs:
            side = ex["side"] 
            qty = ex["qty"]
            price = ex["price"]
            exec_time = ex["time"]
            
            if not inventory:
                direction = "LONG" if side == "BUY" else "SHORT"
                inventory.append({
                    "time": exec_time,
                    "price": price,
                    "qty": qty
                })
                
                current_trade = {
                    "symbol": symbol,
                    "underlying": sym_details["underlying"],
                    "is_option": sym_details["is_option"],
                    "option_type": sym_details["option_type"],
                    "strike": sym_details["strike"],
                    "expiry": sym_details["expiry"],
                    "direction": direction,
                    "entry_time": exec_time,
                    "entries": [{
                        "time": exec_time,
                        "price": price,
                        "qty": qty
                    }],
                    "exits": [],
                    "closed": False,
                    "qty": qty,
                    "entry_price": price
                }
                continue
                
            is_same_dir = (direction == "LONG" and side == "BUY") or (direction == "SHORT" and side == "SELL")
            
            exits_qty = 0  # initialize here so it's always defined after the if/else
            if is_same_dir:
                inventory.append({
                    "time": exec_time,
                    "price": price,
                    "qty": qty
                })
                current_trade["entries"].append({
                    "time": exec_time,
                    "price": price,
                    "qty": qty
                })
                current_trade["qty"] += qty
                total_cost = sum(x["price"] * x["qty"] for x in current_trade["entries"])
                current_trade["entry_price"] = round(total_cost / current_trade["qty"], 4)
            else:
                exits_qty = qty
                current_trade["exits"].append({
                    "time": exec_time,
                    "price": price,
                    "qty": qty
                })
                
                while exits_qty > 0 and inventory:
                    first = inventory[0]
                    match_qty = min(first["qty"], exits_qty)
                    
                    first["qty"] -= match_qty
                    exits_qty -= match_qty
                    
                    if first["qty"] == 0:
                        inventory.pop(0)
                        
                if not inventory:
                    current_trade["closed"] = True
                    current_trade["exit_time"] = exec_time
                    total_exit_val = sum(x["price"] * x["qty"] for x in current_trade["exits"])
                    total_exit_qty = sum(x["qty"] for x in current_trade["exits"])
                    current_trade["exit_price"] = round(total_exit_val / total_exit_qty, 4)
                    
                    if direction == "LONG":
                        current_trade["pnl"] = round((current_trade["exit_price"] - current_trade["entry_price"]) * current_trade["qty"] * multiplier, 2)
                    else:
                        current_trade["pnl"] = round((current_trade["entry_price"] - current_trade["exit_price"]) * current_trade["qty"] * multiplier, 2)
                        
                    current_trade["pnl_pct"] = round((current_trade["pnl"] / (current_trade["entry_price"] * current_trade["qty"] * multiplier)) * 100, 2) if current_trade["entry_price"] else 0
                    current_trade["win"] = current_trade["pnl"] > 0
                    
                    trades.append(current_trade)
                    current_trade = None
            
            if exits_qty > 0:
                direction = "LONG" if side == "BUY" else "SHORT"
                inventory.append({
                    "time": exec_time,
                    "price": price,
                    "qty": exits_qty
                })
                current_trade = {
                    "symbol": symbol,
                    "underlying": sym_details["underlying"],
                    "is_option": sym_details["is_option"],
                    "option_type": sym_details["option_type"],
                    "strike": sym_details["strike"],
                    "expiry": sym_details["expiry"],
                    "direction": direction,
                    "entry_time": exec_time,
                    "entries": [{
                        "time": exec_time,
                        "price": price,
                        "qty": exits_qty
                    }],
                    "exits": [],
                    "closed": False,
                    "qty": exits_qty,
                    "entry_price": price
                }
                
        if current_trade:
            current_trade["exit_time"] = None
            current_trade["exit_price"] = None
            current_trade["pnl"] = None
            current_trade["pnl_pct"] = None
            current_trade["win"] = None
            trades.append(current_trade)
            
    trades.sort(key=lambda x: x["entry_time"], reverse=True)
    return trades

def load_and_parse_trades(filepath):
    execs = parse_tos_csv(filepath)
    return pair_trades(execs)
