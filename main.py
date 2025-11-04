import gc                      # Garbage collection
import time                    # Time functions
import asyncio                 # Asynchronous I/O
import traceback               # Exception handling
import threading               # Thread management

from poly_data.polymarket_client import PolymarketClient
from poly_data.data_utils import update_markets, update_positions, update_orders
from poly_data.websocket_handlers import connect_market_websocket, connect_user_websocket
import poly_data.global_state as global_state
from poly_data.data_processing import remove_from_performing
from dotenv import load_dotenv
import config  # Centralized configuration

load_dotenv()
config.print_config()  # Print configuration on startup

def update_once():
    """
    Initialize the application state by fetching market data, positions, and orders.
    """
    update_markets()    # Get market information from Google Sheets
    update_positions()  # Get current positions from Polymarket
    update_orders()     # Get current orders from Polymarket

def remove_from_pending():
    """
    Clean up stale trades that have been pending for too long (>15 seconds).
    This prevents the system from getting stuck on trades that may have failed.
    """
    try:
        current_time = time.time()
            
        # Iterate through all performing trades
        for col in list(global_state.performing.keys()):
            for trade_id in list(global_state.performing[col]):
                
                try:
                    # If trade has been pending for more than STALE_TRADE_TIMEOUT seconds, remove it
                    if current_time - global_state.performing_timestamps[col].get(trade_id, current_time) > config.STALE_TRADE_TIMEOUT:
                        print(f"Removing stale entry {trade_id} from {col} after {config.STALE_TRADE_TIMEOUT} seconds")
                        remove_from_performing(col, trade_id)
                        print("After removing: ", global_state.performing, global_state.performing_timestamps)
                except:
                    print("Error in remove_from_pending")
                    print(traceback.format_exc())                
    except:
        print("Error in remove_from_pending")
        print(traceback.format_exc())

def update_periodically():
    """
    Background thread function that periodically updates market data, positions and orders.
    - Positions and orders are updated every UPDATE_INTERVAL seconds
    - Market data is updated every (UPDATE_INTERVAL × MARKET_UPDATE_CYCLES) seconds
    - Stale pending trades are removed each cycle
    """
    i = 1
    while True:
        time.sleep(config.UPDATE_INTERVAL)  # Update interval from config

        try:
            # Clean up stale trades
            remove_from_pending()

            # Update positions and orders every cycle
            update_positions(avgOnly=True)  # Only update average price, not position size
            update_orders()

            # Update market data every MARKET_UPDATE_CYCLES cycles
            if i % config.MARKET_UPDATE_CYCLES == 0:
                update_markets()
                i = 1
                    
            gc.collect()  # Force garbage collection to free memory
            i += 1
        except:
            print("Error in update_periodically")
            print(traceback.format_exc())
            
async def main():
    """
    Main application entry point. Initializes client, data, and manages websocket connections.
    """
    # Initialize client
    global_state.client = PolymarketClient()
    
    # Initialize state and fetch initial data
    global_state.all_tokens = []
    update_once()
    print("After initial updates: ", global_state.orders, global_state.positions)

    print("\n")
    print(f'There are {len(global_state.df)} market, {len(global_state.positions)} positions and {len(global_state.orders)} orders. Starting positions: {global_state.positions}')

    # Start background update thread
    update_thread = threading.Thread(target=update_periodically, daemon=True)
    update_thread.start()
    
    # Main loop - maintain websocket connections
    while True:
        try:
            # Connect to market and user websockets simultaneously
            await asyncio.gather(
                connect_market_websocket(global_state.all_tokens), 
                connect_user_websocket()
            )
            print("Reconnecting to the websocket")
        except:
            print("Error in main loop")
            print(traceback.format_exc())

        await asyncio.sleep(config.WEBSOCKET_RECONNECT_DELAY)
        gc.collect()  # Clean up memory

if __name__ == "__main__":
    asyncio.run(main())