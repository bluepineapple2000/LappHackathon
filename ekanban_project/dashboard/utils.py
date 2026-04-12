"""
Utility functions for loading and processing CSV data with polynomial regression forecasting
"""
import pandas as pd
import numpy as np
from pathlib import Path
from django.conf import settings
from datetime import datetime, timedelta

CSV_DIR = Path(__file__).resolve().parent.parent.parent / 'data'


def load_pricing_data():
    """Load pricing and lead times data"""
    csv_file = CSV_DIR / 'pricing_and_leadtimes.csv'
    
    if not csv_file.exists():
        return pd.DataFrame()
    
    df = pd.read_csv(csv_file)
    return df


def calculate_polynomial_forecast(historical_data, degree=2):
    """
    Calculate polynomial regression forecast for better accuracy
    
    Args:
        historical_data: Series of cable length measurements over time
        degree: Degree of polynomial (default 2 for quadratic)
    
    Returns:
        Depletion rate and forecast values
    """
    try:
        if len(historical_data) < 3:
            return None
        
        x = np.arange(len(historical_data))
        y = historical_data.values
        
        # Fit polynomial
        coeffs = np.polyfit(x, y, degree)
        poly = np.poly1d(coeffs)
        
        # Calculate depletion rate (negative slope)
        # For polynomial, take derivative and evaluate at the end
        poly_deriv = np.polyder(poly)
        depletion_rate = abs(float(poly_deriv(len(historical_data) - 1)))
        
        return {
            'coefficients': coeffs,
            'depletion_rate': max(0.01, depletion_rate)  # Minimum 0.01 to avoid division by zero
        }
    except:
        return None


def load_forecast_data():
    """Load all forecast CSV files from the data directory"""
    csv_file = CSV_DIR / 'drum_1167_linear_forecast.csv'
    
    if not csv_file.exists():
        return []
    
    df = pd.read_csv(csv_file)
    return df.to_dict('records')


def load_rack_data():
    """Load rack customer data from CSV"""
    csv_file = CSV_DIR / 'rack_kunde_a_regal_og.csv'
    
    if not csv_file.exists():
        return []
    
    df = pd.read_csv(csv_file)
    return df.to_dict('records')


def get_inventory_summary(customer=None, rack=None, use_polynomial=True):
    """Get aggregated inventory summary with polynomial regression forecast data"""
    # Combine data from both sources
    data = load_forecast_data() + load_rack_data()
    
    if not data:
        return []
    
    df = pd.DataFrame(data)
    
    # Filter by customer and rack if specified
    if customer:
        df = df[df['tenant'] == customer]
    if rack:
        df = df[df['rack'] == rack]
    
    # Group by drum_id to get the best forecast
    summary = []
    for drum_id, drum_group in df.groupby('drum_id'):
        drum_group = drum_group.sort_values('date')
        
        # Get latest entry
        latest = drum_group.iloc[-1]
        
        # Try polynomial regression if we have enough data
        poly_forecast = None
        if use_polynomial and len(drum_group) >= 3:
            poly_forecast = calculate_polynomial_forecast(
                drum_group['daily_avg_cable_length_m'],
                degree=2
            )
        
        # Use polynomial depletion rate if available, otherwise use linear
        if poly_forecast:
            depletion_rate = poly_forecast['depletion_rate']
        else:
            depletion_rate = latest['depletion_rate_m_per_day']
        
        summary.append({
            'drum_id': int(latest['drum_id']),
            'customer': latest['tenant'],
            'rack': latest['rack'],
            'product': latest['product'],
            'part_number': latest['part_number'],
            'current_length_m': latest['daily_avg_cable_length_m'],
            'order_threshold_m': latest['order_threshold_m'],
            'forecast_length_m': latest['linear_forecast_m'],
            'depletion_rate': depletion_rate,
            'days_until_threshold': calculate_days_until_threshold(
                latest['daily_avg_cable_length_m'],
                latest['order_threshold_m'],
                depletion_rate
            ),
            'avg_battery_voltage': latest['avg_battery_voltage'],
            'avg_signal_strength': latest['avg_signal_strength'],
            'r_squared': latest['r_squared'],
        })
    
    return summary


def calculate_days_until_threshold(current_length, threshold, depletion_rate):
    """Calculate days until cable depletes to threshold"""
    if depletion_rate <= 0:
        return None
    
    days = (current_length - threshold) / depletion_rate
    return max(0, round(days, 1))


def get_priority_queue():
    """Get racks ordered by urgency (soonest to be empty)"""
    summary = get_inventory_summary()
    
    # Filter out items already below threshold or with no valid forecast
    priority = [item for item in summary if item['days_until_threshold'] and item['days_until_threshold'] > 0]
    
    # Sort by days until threshold (ascending = soonest first)
    priority.sort(key=lambda x: x['days_until_threshold'])
    
    return priority


def get_shopping_cart_recommendations(max_price=500, reference_date=None):
    """
    Generate automatic shopping cart recommendations based on forecast and delivery times.
    
    Algorithm:
    1. For each drum that will be empty within delivery_time_days + 2 days
    2. Calculate how many units are needed based on forecast
    3. Add to cart until total price reaches max_price
    
    Args:
        max_price: Maximum budget in euros
        reference_date: Date to calculate from (for demo purposes). If None, uses today
    
    Returns:
        Tuple of (list of recommended items, total price)
    """
    from datetime import datetime, timedelta
    
    if reference_date is None:
        reference_date = datetime.now()
    elif isinstance(reference_date, str):
        reference_date = datetime.strptime(reference_date, '%Y-%m-%d')
    
    pricing_df = load_pricing_data()
    if pricing_df.empty:
        return [], 0
    
    # Create a lookup dictionary for pricing data
    pricing_dict = {}
    for _, row in pricing_df.iterrows():
        pricing_dict[str(row['part_number'])] = {
            'product_name': row['product_name'],
            'price_per_meter': row['price_per_meter_eur'],
            'delivery_time_days': row['delivery_time_days'],
            'packaging_unit_m': row['packaging_unit_m']
        }
    
    # Get all inventory items
    inventory = get_inventory_summary()
    cart = []
    total_price = 0
    
    for item in inventory:
        part_number = str(item['part_number'])
        
        if part_number not in pricing_dict:
            continue
        
        pricing = pricing_dict[part_number]
        delivery_time = pricing['delivery_time_days']
        packaging_unit = pricing['packaging_unit_m']
        price_per_meter = pricing['price_per_meter']
        
        # Check if drum will be empty within delivery time + 2 days per drum
        days_until_empty = item['days_until_threshold']
        if days_until_empty is None:
            continue
        
        # Add 2 days buffer per drum unit existing
        critical_days = delivery_time + 2
        
        if days_until_empty <= critical_days:
            # Calculate how much cable will be consumed by the reference date + delivery time
            time_until_delivery = delivery_time
            cable_consumed_until_delivery = item['depletion_rate'] * time_until_delivery
            
            # Calculate cable needed (from current to threshold + buffer for consumption)
            cable_at_delivery = item['current_length_m'] - cable_consumed_until_delivery
            cable_needed = max(0, item['order_threshold_m'] - cable_at_delivery + (item['depletion_rate'] * 2))
            
            # Round up to nearest packaging unit
            units_needed = int(np.ceil(cable_needed / packaging_unit))
            if units_needed == 0:
                units_needed = 1  # Always recommend at least one unit
            
            total_length = units_needed * packaging_unit
            item_price = total_length * price_per_meter
            
            # Check if adding this item would exceed budget
            if total_price + item_price <= max_price:
                cart.append({
                    'drum_id': item['drum_id'],
                    'part_number': part_number,
                    'product_name': pricing['product_name'],
                    'product': item['product'],
                    'units_needed': units_needed,
                    'total_length_m': total_length,
                    'price_per_meter': price_per_meter,
                    'item_price': round(item_price, 2),
                    'delivery_days': delivery_time,
                    'days_until_empty': days_until_empty,
                    'current_stock_m': item['current_length_m'],
                    'threshold_m': item['order_threshold_m'],
                    'depletion_rate': item['depletion_rate'],
                    'cable_at_delivery_m': round(cable_at_delivery, 2),
                })
                total_price += item_price
            elif not cart:
                # If this is the first item and it exceeds budget, add it anyway
                cart.append({
                    'drum_id': item['drum_id'],
                    'part_number': part_number,
                    'product_name': pricing['product_name'],
                    'product': item['product'],
                    'units_needed': units_needed,
                    'total_length_m': total_length,
                    'price_per_meter': price_per_meter,
                    'item_price': round(item_price, 2),
                    'delivery_days': delivery_time,
                    'days_until_empty': days_until_empty,
                    'current_stock_m': item['current_length_m'],
                    'threshold_m': item['order_threshold_m'],
                    'depletion_rate': item['depletion_rate'],
                    'cable_at_delivery_m': round(cable_at_delivery, 2),
                })
                total_price += item_price
    
    return cart, round(total_price, 2)


def calculate_hypothetical_consumption(inventory_item, reference_date):
    """
    Calculate hypothetical cable consumption from today to a future date.
    
    Args:
        inventory_item: Inventory item with depletion_rate
        reference_date: Future date to calculate consumption to
    
    Returns:
        Dictionary with consumption data
    """
    from datetime import datetime
    
    if isinstance(reference_date, str):
        reference_date = datetime.strptime(reference_date, '%Y-%m-%d')
    
    today = datetime.now()
    days_difference = (reference_date - today).days
    
    consumption = inventory_item['depletion_rate'] * days_difference
    remaining_length = max(0, inventory_item['current_length_m'] - consumption)
    
    return {
        'days_from_today': days_difference,
        'consumption_m': round(consumption, 2),
        'remaining_length_m': round(remaining_length, 2),
        'will_be_below_threshold': remaining_length < inventory_item['order_threshold_m'],
    }


def get_customers():
    """Get list of unique customers from forecast data"""
    data = load_forecast_data() + load_rack_data()
    if not data:
        return []
    
    df = pd.DataFrame(data)
    return sorted(df['tenant'].unique().tolist())


def get_racks_for_customer(customer):
    """Get list of racks for a specific customer"""
    data = load_forecast_data() + load_rack_data()
    if not data:
        return []
    
    df = pd.DataFrame(data)
    df = df[df['tenant'] == customer]
    return sorted(df['rack'].unique().tolist())

