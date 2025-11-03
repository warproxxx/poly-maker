import time
import pandas as pd
from data_updater.trading_utils import get_clob_client
from data_updater.google_utils import get_spreadsheet
from data_updater.find_markets import get_sel_df, get_all_markets, get_all_results, get_markets, add_volatility_to_df
from gspread_dataframe import set_with_dataframe
import traceback

# Initialize global variables
spreadsheet = get_spreadsheet()
client = get_clob_client()

wk_all = spreadsheet.worksheet("All Markets")
wk_vol = spreadsheet.worksheet("Volatility Markets")

sel_df = get_sel_df(spreadsheet, "Selected Markets")

def update_sheet(data, worksheet):
    all_values = worksheet.get_all_values()
    existing_num_rows = len(all_values)
    existing_num_cols = len(all_values[0]) if all_values else 0

    num_rows, num_cols = data.shape
    max_rows = max(num_rows, existing_num_rows)
    max_cols = max(num_cols, existing_num_cols)

    # Create a DataFrame with the maximum size and fill it with empty strings
    padded_data = pd.DataFrame('', index=range(max_rows), columns=range(max_cols))

    # Update the padded DataFrame with the original data and its columns
    padded_data.iloc[:num_rows, :num_cols] = data.values
    padded_data.columns = list(data.columns) + [''] * (max_cols - num_cols)

    # Update the sheet with the padded DataFrame, including column headers
    set_with_dataframe(worksheet, padded_data, include_index=False, include_column_header=True, resize=True)

def calculate_comprehensive_metrics(df):
    """
    Calculate comprehensive risk-adjusted metrics for ranking.

    Includes:
    - Sharpe Ratio
    - Sortino Ratio
    - Expected Profit
    - Regime-adjusted score
    """
    from poly_data.risk_metrics import calculate_metrics_for_market

    # Assume $100 capital deployment per market
    capital_to_deploy = 100

    metrics_list = []

    for _, row in df.iterrows():
        try:
            # Calculate expected daily reward (use optimal_reward_per_100 if available)
            reward_per_100 = row.get('optimal_reward_per_100', row.get('gm_reward_per_100', 0))
            expected_daily_reward = capital_to_deploy * reward_per_100 / 100

            # Get volatilities
            vol_1h = row.get('1_hour', 0)
            vol_24h = row.get('24_hour', 0)
            downside_vol = row.get('downside_vol_24h', vol_24h)

            # Estimate orderbook depth from spread
            spread = row.get('spread', 0.02)
            estimated_depth = 1000 / (spread * 100 + 1)  # Wider spread = less depth

            # Calculate comprehensive metrics
            metrics = calculate_metrics_for_market(
                expected_daily_reward=expected_daily_reward,
                capital_to_deploy=capital_to_deploy,
                best_bid=row.get('best_bid', 0.5),
                best_ask=row.get('best_ask', 0.5),
                volatility_1hour=vol_1h,
                volatility_24hour=vol_24h,
                downside_volatility_24hour=downside_vol,
                min_size=row.get('min_size', 100),
                orderbook_bid_depth=estimated_depth,
                orderbook_ask_depth=estimated_depth
            )

            metrics_list.append({
                'sharpe_ratio': metrics['sharpe_ratio'],
                'sortino_ratio': metrics['sortino_ratio'],
                'expected_daily_profit': metrics['expected_daily_profit'],
                'adjusted_daily_profit': metrics['adjusted_daily_profit'],
                'expected_roi_annual': metrics['expected_roi_annual']
            })
        except:
            metrics_list.append({
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'expected_daily_profit': 0,
                'adjusted_daily_profit': 0,
                'expected_roi_annual': 0
            })

    # Add metrics to dataframe
    metrics_df = pd.DataFrame(metrics_list)
    for col in metrics_df.columns:
        df[col] = metrics_df[col]

    return df

def sort_df(df):
    """
    Enhanced sorting with comprehensive risk-adjusted metrics.
    """
    # Calculate comprehensive metrics
    df = calculate_comprehensive_metrics(df)

    # Calculate the mean and standard deviation for each column
    mean_gm = df['gm_reward_per_100'].mean()
    std_gm = df['gm_reward_per_100'].std() if df['gm_reward_per_100'].std() > 0 else 1

    mean_volatility = df['volatility_sum'].mean()
    std_volatility = df['volatility_sum'].std() if df['volatility_sum'].std() > 0 else 1

    mean_sharpe = df['sharpe_ratio'].mean()
    std_sharpe = df['sharpe_ratio'].std() if df['sharpe_ratio'].std() > 0 else 1

    mean_profit = df['adjusted_daily_profit'].mean()
    std_profit = df['adjusted_daily_profit'].std() if df['adjusted_daily_profit'].std() > 0 else 1

    # Standardize the columns
    df['std_gm_reward_per_100'] = (df['gm_reward_per_100'] - mean_gm) / std_gm
    df['std_volatility_sum'] = (df['volatility_sum'] - mean_volatility) / std_volatility
    df['std_sharpe_ratio'] = (df['sharpe_ratio'] - mean_sharpe) / std_sharpe
    df['std_profit'] = (df['adjusted_daily_profit'] - mean_profit) / std_profit

    # Define a custom scoring function for best_bid and best_ask
    def proximity_score(value):
        if 0.1 <= value <= 0.25:
            return (0.25 - value) / 0.15
        elif 0.75 <= value <= 0.9:
            return (value - 0.75) / 0.15
        else:
            return 0

    df['bid_score'] = df['best_bid'].apply(proximity_score)
    df['ask_score'] = df['best_ask'].apply(proximity_score)

    # Regime score (boost good regimes)
    def regime_score(is_good):
        return 1.0 if is_good else -0.5

    df['regime_score'] = df['is_good_for_mm'].apply(regime_score)

    # ENHANCED COMPOSITE SCORE
    # Weights: Rewards (25%), Sharpe (30%), Profit (25%), Volatility (-15%), Proximity (5%), Regime (20%)
    df['composite_score'] = (
        df['std_gm_reward_per_100'] * 0.25 +      # Higher rewards are better
        df['std_sharpe_ratio'] * 0.30 +            # Higher Sharpe is better
        df['std_profit'] * 0.25 +                  # Higher profit is better
        -df['std_volatility_sum'] * 0.15 +         # Lower volatility is better
        (df['bid_score'] + df['ask_score']) * 0.05 + # Better price proximity
        df['regime_score'] * 0.20                  # Good regime is better
    )

    # Sort by the composite score in descending order
    sorted_df = df.sort_values(by='composite_score', ascending=False)

    # Drop the intermediate columns used for calculation
    sorted_df = sorted_df.drop(columns=[
        'std_gm_reward_per_100', 'std_volatility_sum', 'std_sharpe_ratio', 'std_profit',
        'bid_score', 'ask_score', 'regime_score', 'composite_score'
    ])

    return sorted_df

def fetch_and_process_data():
    global spreadsheet, client, wk_all, wk_vol, sel_df
    
    spreadsheet = get_spreadsheet()
    client = get_clob_client()

    wk_all = spreadsheet.worksheet("All Markets")
    wk_vol = spreadsheet.worksheet("Volatility Markets")
    wk_full = spreadsheet.worksheet("Full Markets")

    sel_df = get_sel_df(spreadsheet, "Selected Markets")


    all_df = get_all_markets(client)
    print("Got all Markets")
    all_results = get_all_results(all_df, client)
    print("Got all Results")
    m_data, all_markets = get_markets(all_results, sel_df, maker_reward=0.75)
    print("Got all orderbook")

    print(f'{pd.to_datetime("now")}: Fetched all markets data of length {len(all_markets)}.')
    new_df = add_volatility_to_df(all_markets)
    new_df['volatility_sum'] =  new_df['24_hour'] + new_df['7_day'] + new_df['14_day']
    
    new_df = new_df.sort_values('volatility_sum', ascending=True)
    new_df['volatilty/reward'] = ((new_df['gm_reward_per_100'] / new_df['volatility_sum']).round(2)).astype(str)

    # Define columns to include (with new metrics)
    base_columns = ['question', 'answer1', 'answer2', 'spread', 'rewards_daily_rate',
                    'gm_reward_per_100', 'optimal_reward_per_100', 'sm_reward_per_100',
                    'bid_reward_per_100', 'ask_reward_per_100']

    risk_columns = ['sharpe_ratio', 'sortino_ratio', 'expected_daily_profit',
                    'adjusted_daily_profit', 'expected_roi_annual']

    volatility_columns = ['volatility_sum', 'volatilty/reward', '1_hour', '3_hour',
                          '6_hour', '12_hour', '24_hour', '7_day', '30_day', 'downside_vol_24h']

    regime_columns = ['market_regime', 'regime_confidence', 'is_good_for_mm', 'hurst_exponent']

    market_columns = ['min_size', 'best_bid', 'best_ask', 'volatility_price',
                      'max_spread', 'tick_size', 'neg_risk', 'market_slug',
                      'token1', 'token2', 'condition_id']

    # Combine all columns (only include if they exist in dataframe)
    all_columns = base_columns + risk_columns + volatility_columns + regime_columns + market_columns
    existing_columns = [col for col in all_columns if col in new_df.columns]

    new_df = new_df[existing_columns]

    
    volatility_df = new_df.copy()
    volatility_df = volatility_df[new_df['volatility_sum'] < 20]
    # volatility_df = sort_df(volatility_df)
    volatility_df = volatility_df.sort_values('gm_reward_per_100', ascending=False)
   
    new_df = new_df.sort_values('gm_reward_per_100', ascending=False)
    

    print(f'{pd.to_datetime("now")}: Fetched select market of length {len(new_df)}.')

    if len(new_df) > 50:
        update_sheet(new_df, wk_all)
        update_sheet(volatility_df, wk_vol)
        update_sheet(m_data, wk_full)
    else:
        print(f'{pd.to_datetime("now")}: Not updating sheet because of length {len(new_df)}.')

if __name__ == "__main__":
    while True:
        try:
            fetch_and_process_data()
            time.sleep(60 * 60)  # Sleep for an hour
        except Exception as e:
            traceback.print_exc()
            print(str(e))
