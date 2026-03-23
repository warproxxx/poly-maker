import threading
import pandas as pd

# ============ Market Data ============

# List of all tokens being tracked
all_tokens = []

# Mapping between tokens in the same market (YES->NO, NO->YES)
REVERSE_TOKENS = {}  

# Order book data for all markets
all_data = {}  

# Market configuration data from Google Sheets
df = None  

# ============ Client & Parameters ============

# Polymarket client instance
client = None

# Trading parameters from Google Sheets
params = {}

# Lock for thread-safe trading operations
lock = threading.Lock()

# ============ Trade Function ============

# Pluggable trade callback — set to perform_tweet_trade for tweet markets
trade_function = None

# ============ Trading State ============

# Tracks trades that have been matched but not yet mined
# Format: {"token_side": {trade_id1, trade_id2, ...}}
performing = {}

# Timestamps for when trades were added to performing
# Used to clear stale trades
performing_timestamps = {}

# Timestamps for when positions were last updated
last_trade_update = {}

# Current open orders for each token
# Format: {token_id: {'buy': {price, size}, 'sell': {price, size}}}
orders = {}

# Current positions for each token
# Format: {token_id: {'size': float, 'avgPrice': float}}
positions = {}

