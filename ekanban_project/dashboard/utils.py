"""
Utility functions for loading and processing CSV data with polynomial regression forecasting
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

CSV_DIR = Path(__file__).resolve().parent.parent.parent / 'data'

# Demo cost rules from data/costs.txt
FREE_SHIPPING_THRESHOLD_EUR = 500
SHIPPING_COST_EUR = 25
MIN_ORDER_VALUE_EUR = 150
MIN_ORDER_SURCHARGE_EUR = 20
CUT_COST_EUR = 20
STANDARD_LENGTHS_M = {100, 500, 1000}
SAFETY_BUFFER_DAYS = 1
DEMO_TODAY = datetime(2026, 4, 22)


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


def apply_forecast_mode(depletion_rate, mode='neutral'):
    """
    Apply forecast mode adjustment to depletion rate
    
    Args:
        depletion_rate: Base depletion rate
        mode: 'defensiv' (worst case +20%), 'neutral' (expected), 'offensiv' (best case -20%)
    
    Returns:
        Adjusted depletion rate
    """
    if mode == 'defensiv':
        return depletion_rate * 1.2  # 20% higher consumption (worst case)
    elif mode == 'offensiv':
        return depletion_rate * 0.8  # 20% lower consumption (best case)
    else:  # neutral
        return depletion_rate


def get_inventory_summary(
    customer=None,
    rack=None,
    use_polynomial=True,
    forecast_mode='neutral',
    inventory_adjustments=None,
):
    """Get aggregated inventory summary with polynomial regression forecast data
    
    Args:
        customer: Filter by customer name
        rack: Filter by rack name
        use_polynomial: Use polynomial regression for forecast
        forecast_mode: 'defensiv', 'neutral', or 'offensiv' for forecast adjustment
    """
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

        added_length_m = 0.0
        if inventory_adjustments:
            added_length_m = float(inventory_adjustments.get(str(int(latest['drum_id'])), 0.0))
        
        # Use polynomial depletion rate if available, otherwise use linear
        if poly_forecast:
            depletion_rate = poly_forecast['depletion_rate']
        else:
            depletion_rate = latest['depletion_rate_m_per_day']
        
        # Apply forecast mode adjustment
        adjusted_depletion_rate = apply_forecast_mode(depletion_rate, forecast_mode)
        
        current_length_m = float(latest['daily_avg_cable_length_m']) + added_length_m
        forecast_length_m = float(latest['linear_forecast_m']) + added_length_m

        summary.append({
            'drum_id': int(latest['drum_id']),
            'customer': latest['tenant'],
            'rack': latest['rack'],
            'product': latest['product'],
            'part_number': latest['part_number'],
            'current_length_m': current_length_m,
            'order_threshold_m': latest['order_threshold_m'],
            'forecast_length_m': forecast_length_m,
            'depletion_rate': adjusted_depletion_rate,
            'days_until_threshold': calculate_days_until_threshold(
                current_length_m,
                latest['order_threshold_m'],
                adjusted_depletion_rate
            ),
            'avg_battery_voltage': latest['avg_battery_voltage'],
            'avg_signal_strength': latest['avg_signal_strength'],
            'r_squared': latest['r_squared'],
            'replenished_length_m': added_length_m,
        })
    
    return summary


def calculate_days_until_threshold(current_length, threshold, depletion_rate):
    """Calculate days until cable depletes to threshold"""
    if depletion_rate <= 0:
        return None
    
    days = (current_length - threshold) / depletion_rate
    return max(0, round(days, 1))


def get_priority_queue(forecast_mode='neutral', inventory_adjustments=None):
    """Get racks ordered by urgency (soonest to be empty)"""
    summary = get_inventory_summary(
        forecast_mode=forecast_mode,
        inventory_adjustments=inventory_adjustments,
    )
    
    # Filter out items already below threshold or with no valid forecast
    priority = [item for item in summary if item['days_until_threshold'] and item['days_until_threshold'] > 0]
    
    # Sort by days until threshold (ascending = soonest first)
    priority.sort(key=lambda x: x['days_until_threshold'])
    
    return priority


def _build_pricing_lookup(pricing_df):
    pricing_dict = {}
    for _, row in pricing_df.iterrows():
        pricing_dict[str(row['part_number'])] = {
            'product_name': row['product_name'],
            'price_per_meter': float(row['price_per_meter_eur']),
            'delivery_time_days': int(row['delivery_time_days']),
            'packaging_unit_m': float(row['packaging_unit_m']),
        }
    return pricing_dict


def _build_cart_item(item, pricing, order_length_m, reason):
    return {
        'item_id': f"{item['drum_id']}::{item['part_number']}",
        'drum_id': int(item['drum_id']),
        'part_number': str(item['part_number']),
        'product_name': pricing['product_name'],
        'product': item['product'],
        'price_per_meter': float(pricing['price_per_meter']),
        'delivery_days': int(pricing['delivery_time_days']),
        'packaging_unit_m': float(pricing['packaging_unit_m']),
        'order_length_m': float(order_length_m),
        'reason': reason,
        'days_until_empty': (
            None if item['days_until_threshold'] is None else float(item['days_until_threshold'])
        ),
        'current_stock_m': float(item['current_length_m']),
        'threshold_m': float(item['order_threshold_m']),
        'depletion_rate': float(item['depletion_rate']),
    }


def _normalize_reference_date(reference_date):
    if reference_date is None:
        return DEMO_TODAY.date()
    if isinstance(reference_date, datetime):
        return reference_date.date()
    if hasattr(reference_date, 'year') and hasattr(reference_date, 'month') and hasattr(reference_date, 'day'):
        return reference_date
    if isinstance(reference_date, str):
        try:
            return datetime.strptime(reference_date, '%Y-%m-%d').date()
        except ValueError:
            return DEMO_TODAY.date()
    return DEMO_TODAY.date()


def calculate_hypothetical_consumption(item, reference_date):
    """Project consumption from demo-today until a selected reference date."""
    normalized_date = _normalize_reference_date(reference_date)
    day_delta = max(0, (normalized_date - DEMO_TODAY.date()).days)

    current_length_m = float(item.get('current_length_m', item.get('current_stock_m', 0.0)))
    threshold_m = float(item.get('order_threshold_m', item.get('threshold_m', 0.0)))
    depletion_rate = max(0.0, float(item.get('depletion_rate', 0.0)))

    consumption_m = round(day_delta * depletion_rate, 1)
    remaining_length_m = max(0.0, round(current_length_m - consumption_m, 1))

    days_until_threshold_from_reference = calculate_days_until_threshold(
        remaining_length_m,
        threshold_m,
        depletion_rate,
    )

    return {
        'days_from_today': day_delta,
        'consumption_m': consumption_m,
        'remaining_length_m': remaining_length_m,
        'will_be_below_threshold': remaining_length_m <= threshold_m,
        'days_until_threshold_from_reference': days_until_threshold_from_reference,
    }


def _forecast_buffer_days(forecast_mode):
    if forecast_mode == 'defensiv':
        return 10
    if forecast_mode == 'offensiv':
        return 2
    return 5


def _determine_empty_soon_reason(item, projection, pricing, forecast_mode):
    days_until_threshold = projection['days_until_threshold_from_reference']
    risk_window = int(pricing['delivery_time_days']) + SAFETY_BUFFER_DAYS + _forecast_buffer_days(forecast_mode)

    if projection['will_be_below_threshold']:
        return 'Unter Schwellwert zum Referenzdatum', risk_window
    if days_until_threshold is not None and days_until_threshold <= risk_window:
        return f"Lieferzeit + Puffer ({risk_window} Tage) >= Restlaufzeit", risk_window
    return None, risk_window


def get_empty_soon_forecast(
    reference_date,
    forecast_mode='neutral',
    inventory_adjustments=None,
    customer=None,
    rack=None,
):
    """Return debug rows for drums that are likely to be empty soon."""
    pricing_df = load_pricing_data()
    if pricing_df.empty:
        return []

    pricing_lookup = _build_pricing_lookup(pricing_df)
    inventory = get_inventory_summary(
        customer=customer,
        rack=rack,
        forecast_mode=forecast_mode,
        inventory_adjustments=inventory_adjustments,
    )

    rows = []
    for item in inventory:
        pricing = pricing_lookup.get(str(item['part_number']))
        if not pricing:
            continue

        projection = calculate_hypothetical_consumption(item, reference_date)
        reason, risk_window = _determine_empty_soon_reason(item, projection, pricing, forecast_mode)
        if not reason:
            continue

        rows.append({
            'drum_id': int(item['drum_id']),
            'part_number': str(item['part_number']),
            'product': item['product'],
            'current_stock_m': float(item['current_length_m']),
            'hypothetical_remaining_m': float(projection['remaining_length_m']),
            'days_until_empty_from_reference': projection['days_until_threshold_from_reference'],
            'delivery_days': int(pricing['delivery_time_days']),
            'risk_window_days': int(risk_window),
            'depletion_rate': float(item['depletion_rate']),
            'reason': reason,
            'suggested_order_m': float(pricing['packaging_unit_m']),
        })

    rows.sort(
        key=lambda x: (
            x['days_until_empty_from_reference'] is None,
            x['days_until_empty_from_reference'] if x['days_until_empty_from_reference'] is not None else float('inf'),
        )
    )
    return rows


def _attach_hypothetical_fields(cart_item, reference_date):
    consumption_data = calculate_hypothetical_consumption(
        {
            'current_length_m': cart_item['current_stock_m'],
            'order_threshold_m': cart_item['threshold_m'],
            'depletion_rate': cart_item['depletion_rate'],
        },
        reference_date,
    )
    cart_item['consumption_data'] = consumption_data
    cart_item['hypothetical_remaining_m'] = consumption_data['remaining_length_m']
    cart_item['days_until_empty_from_reference'] = consumption_data['days_until_threshold_from_reference']
    return cart_item


def get_shopping_cart_recommendations(
    reference_date,
    forecast_mode='neutral',
    inventory_adjustments=None,
    customer=None,
    rack=None,
):
    """Build recommendation list with hypothetical usage until reference date."""
    pricing_df = load_pricing_data()
    if pricing_df.empty:
        return []

    pricing_lookup = _build_pricing_lookup(pricing_df)
    inventory = get_inventory_summary(
        customer=customer,
        rack=rack,
        forecast_mode=forecast_mode,
        inventory_adjustments=inventory_adjustments,
    )

    if not inventory:
        return []

    selected_items = []
    reserve_candidates = []
    for item in inventory:
        pricing = pricing_lookup.get(str(item['part_number']))
        if not pricing:
            continue

        projection = calculate_hypothetical_consumption(item, reference_date)
        reason, _ = _determine_empty_soon_reason(item, projection, pricing, forecast_mode)
        order_length_m = float(pricing['packaging_unit_m'])
        base_item = _build_cart_item(
            item,
            pricing,
            order_length_m,
            reason or 'Auffuellen bis Versandfreigrenze',
        )
        base_item = _attach_hypothetical_fields(base_item, reference_date)
        if reason:
            selected_items.append(base_item)
        else:
            reserve_candidates.append(base_item)

    # Demo behavior: only top up when at least one risk drum was selected.
    if selected_items:
        subtotal = sum(x['order_length_m'] * x['price_per_meter'] for x in selected_items)
        reserve_candidates.sort(
            key=lambda x: (
                x['days_until_empty_from_reference'] is None,
                x['days_until_empty_from_reference'] if x['days_until_empty_from_reference'] is not None else float('inf'),
            )
        )

        for candidate in reserve_candidates:
            if subtotal >= FREE_SHIPPING_THRESHOLD_EUR:
                break
            selected_items.append(candidate)
            subtotal += candidate['order_length_m'] * candidate['price_per_meter']

    selected_items.sort(
        key=lambda x: (
            x['days_until_empty_from_reference'] is None,
            x['days_until_empty_from_reference'] if x['days_until_empty_from_reference'] is not None else float('inf'),
        )
    )
    return selected_items


def calculate_cart_totals(cart_items):
    """Calculate totals and all demo cost surcharges for the cart."""
    subtotal = round(sum(item['order_length_m'] * item['price_per_meter'] for item in cart_items), 2)

    cut_positions = 0
    for item in cart_items:
        order_length = float(item['order_length_m'])
        if int(round(order_length)) not in STANDARD_LENGTHS_M:
            cut_positions += 1

    cut_costs = round(cut_positions * CUT_COST_EUR, 2)
    shipping_cost = 0.0 if subtotal >= FREE_SHIPPING_THRESHOLD_EUR or subtotal == 0 else float(SHIPPING_COST_EUR)
    min_order_surcharge = 0.0
    if 0 < subtotal < MIN_ORDER_VALUE_EUR:
        min_order_surcharge = float(MIN_ORDER_SURCHARGE_EUR)

    total = round(subtotal + cut_costs + shipping_cost + min_order_surcharge, 2)

    return {
        'subtotal': subtotal,
        'cut_positions': cut_positions,
        'cut_costs': cut_costs,
        'shipping_cost': shipping_cost,
        'min_order_surcharge': min_order_surcharge,
        'remaining_to_free_shipping': round(max(0.0, FREE_SHIPPING_THRESHOLD_EUR - subtotal), 2),
        'total': total,
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

