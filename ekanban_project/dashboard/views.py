from django.shortcuts import render
from datetime import datetime
from .utils import (
    get_inventory_summary, 
    get_priority_queue, 
    get_customers, 
    get_racks_for_customer,
    get_shopping_cart_recommendations,
    get_empty_soon_forecast,
    get_zero_usage_today,
    calculate_hypothetical_consumption,
    calculate_days_until_threshold,
    calculate_cart_totals,
    FREE_SHIPPING_THRESHOLD_EUR,
    MIN_ORDER_VALUE_EUR,
    DEMO_TODAY,
)


def _default_customer(customers):
    """Prefer Kunde B as default for demo, fallback to first customer."""
    if 'Kunde B' in customers:
        return 'Kunde B'
    return customers[0] if customers else None


def _to_native(value):
    """Convert numpy/pandas scalar-like values to JSON-safe native Python values."""
    if isinstance(value, dict):
        return {str(k): _to_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_to_native(v) for v in value)

    if hasattr(value, 'item'):
        try:
            return value.item()
        except Exception:
            pass

    return value


def _parse_reference_date(date_str):
    if not date_str:
        return DEMO_TODAY.date()
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return DEMO_TODAY.date()


def _refresh_cart_hypothetical(cart_items, reference_date):
    for item in cart_items:
        consumption_data = calculate_hypothetical_consumption(
            {
                'current_stock_m': item.get('current_stock_m', 0.0),
                'threshold_m': item.get('threshold_m', 0.0),
                'depletion_rate': item.get('depletion_rate', 0.0),
            },
            reference_date,
        )
        item['consumption_data'] = consumption_data
        item['hypothetical_remaining_m'] = consumption_data['remaining_length_m']
        item['days_until_empty_from_reference'] = calculate_days_until_threshold(
            consumption_data['remaining_length_m'],
            float(item.get('threshold_m', 0.0)),
            float(item.get('depletion_rate', 0.0)),
        )
    return cart_items



def index(request):
    """Main dashboard view with tabs"""
    customers = get_customers()
    selected_customer = request.GET.get('customer', _default_customer(customers))

    # Prognosemodus is intentionally not applied globally for now.
    forecast_mode = 'neutral'
    
    inventory_adjustments = request.session.get('inventory_adjustments', {})

    racks = get_racks_for_customer(selected_customer) if selected_customer else []
    selected_rack = request.GET.get('rack', racks[0] if racks else None)
    
    # Get inventory data based on selected filters
    inventory = get_inventory_summary(
        customer=selected_customer,
        rack=selected_rack,
        forecast_mode=forecast_mode,
        inventory_adjustments=inventory_adjustments,
    )
    
    # Sort by days until threshold for better visibility
    inventory.sort(key=lambda x: x['days_until_threshold'] if x['days_until_threshold'] else float('inf'))
    
    context = {
        'customers': customers,
        'selected_customer': selected_customer,
        'racks': racks,
        'selected_rack': selected_rack,
        'inventory': inventory,
        'forecast_mode': forecast_mode,
    }
    
    return render(request, 'dashboard/index.html', context)




def sensors(request):
    """Sensor state view - voltage and signal strength"""
    customers = get_customers()
    selected_customer = request.GET.get('customer', _default_customer(customers))

    # Prognosemodus is intentionally not applied globally for now.
    forecast_mode = 'neutral'
    
    inventory_adjustments = request.session.get('inventory_adjustments', {})

    racks = get_racks_for_customer(selected_customer) if selected_customer else []
    selected_rack = request.GET.get('rack', racks[0] if racks else None)
    
    # Get inventory data to display sensor info
    sensor_data = get_inventory_summary(
        customer=selected_customer,
        rack=selected_rack,
        forecast_mode=forecast_mode,
        inventory_adjustments=inventory_adjustments,
    )
    
    context = {
        'customers': customers,
        'selected_customer': selected_customer,
        'racks': racks,
        'selected_rack': selected_rack,
        'sensor_data': sensor_data,
        'forecast_mode': forecast_mode,
    }
    
    return render(request, 'dashboard/sensors.html', context)


def warenkorb(request):
    """Shopping cart demo with hypothetical future drum usage."""
    reference_date_value = request.POST.get('reference_date') or request.GET.get('reference_date')
    reference_date = _parse_reference_date(reference_date_value)

    forecast_mode = request.POST.get('forecast_mode') or request.GET.get('forecast_mode') or 'neutral'
    if forecast_mode not in {'defensiv', 'neutral', 'offensiv'}:
        forecast_mode = 'neutral'

    inventory_adjustments = request.session.get('inventory_adjustments', {})
    checkout_success = False

    last_reference_date = request.session.get('cart_reference_date')
    last_forecast_mode = request.session.get('cart_forecast_mode')

    cart_items = request.session.get('cart_items')
    should_reload_recommendations = (
        not cart_items
        or request.method == 'GET'
        or last_reference_date != reference_date.strftime('%Y-%m-%d')
        or last_forecast_mode != forecast_mode
    )

    if should_reload_recommendations:
        cart_items = get_shopping_cart_recommendations(
            reference_date=reference_date,
            forecast_mode=forecast_mode,
            inventory_adjustments=inventory_adjustments,
        )

    if request.method == 'POST':
        action = request.POST.get('action')
        item_id = request.POST.get('item_id')

        if action == 'reset_recommendations':
            cart_items = get_shopping_cart_recommendations(
                reference_date=reference_date,
                forecast_mode=forecast_mode,
                inventory_adjustments=inventory_adjustments,
            )

        elif action == 'remove_item' and item_id:
            cart_items = [x for x in cart_items if x.get('item_id') != item_id]

        elif action in {'increase_length', 'decrease_length', 'update_length'} and item_id:
            for item in cart_items:
                if item.get('item_id') != item_id:
                    continue

                unit = max(1.0, float(item.get('packaging_unit_m', 1.0)))
                current_length = float(item.get('order_length_m', unit))

                if action == 'increase_length':
                    item['order_length_m'] = current_length + unit
                elif action == 'decrease_length':
                    item['order_length_m'] = max(1.0, current_length - unit)
                else:
                    entered = request.POST.get('order_length_m', '')
                    try:
                        item['order_length_m'] = max(1.0, float(entered))
                    except ValueError:
                        item['order_length_m'] = current_length
                break

        elif action == 'checkout':
            updated_adjustments = dict(inventory_adjustments)
            for item in cart_items:
                drum_key = str(int(item['drum_id']))
                updated_adjustments[drum_key] = float(updated_adjustments.get(drum_key, 0.0)) + float(item['order_length_m'])

            request.session['inventory_adjustments'] = _to_native(updated_adjustments)
            inventory_adjustments = updated_adjustments
            cart_items = []
            checkout_success = True

        request.session['cart_items'] = _to_native(cart_items)

    cart_items = _refresh_cart_hypothetical(cart_items, reference_date)
    request.session['cart_items'] = _to_native(cart_items)
    request.session['cart_reference_date'] = reference_date.strftime('%Y-%m-%d')
    request.session['cart_forecast_mode'] = forecast_mode

    empty_soon_rows = get_empty_soon_forecast(
        reference_date=reference_date,
        forecast_mode=forecast_mode,
        inventory_adjustments=inventory_adjustments,
    )

    totals = calculate_cart_totals(cart_items)

    context = {
        'cart_items': cart_items,
        'totals': totals,
        'target_value': FREE_SHIPPING_THRESHOLD_EUR,
        'free_shipping_threshold': FREE_SHIPPING_THRESHOLD_EUR,
        'min_order_value': MIN_ORDER_VALUE_EUR,
        'reference_date': reference_date.strftime('%Y-%m-%d'),
        'reference_date_display': reference_date.strftime('%d.%m.%Y'),
        'forecast_mode': forecast_mode,
        'empty_soon_rows': empty_soon_rows,
        'demo_today': DEMO_TODAY.strftime('%d.%m.%Y'),
        'checkout_success': checkout_success,
    }
    return render(request, 'dashboard/warenkorb.html', context)


def warnsystem(request):
    """Warning system for production management: drums with zero usage today."""
    zero_usage_drums = get_zero_usage_today()
    context = {
        'zero_usage_drums': zero_usage_drums,
        'demo_today': DEMO_TODAY.strftime('%d.%m.%Y'),
    }
    return render(request, 'dashboard/warnsystem.html', context)


