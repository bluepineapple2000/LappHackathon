from django.shortcuts import render
from django.utils import timezone
from datetime import datetime, timedelta
from .utils import (
    get_inventory_summary, 
    get_priority_queue, 
    get_customers, 
    get_racks_for_customer,
    get_shopping_cart_recommendations,
    calculate_hypothetical_consumption
)


def index(request):
    """Main dashboard view with tabs"""
    customers = get_customers()
    selected_customer = request.GET.get('customer', customers[0] if customers else None)
    
    racks = get_racks_for_customer(selected_customer) if selected_customer else []
    selected_rack = request.GET.get('rack', racks[0] if racks else None)
    
    # Get inventory data based on selected filters
    inventory = get_inventory_summary(customer=selected_customer, rack=selected_rack)
    
    # Sort by days until threshold for better visibility
    inventory.sort(key=lambda x: x['days_until_threshold'] if x['days_until_threshold'] else float('inf'))
    
    context = {
        'customers': customers,
        'selected_customer': selected_customer,
        'racks': racks,
        'selected_rack': selected_rack,
        'inventory': inventory,
    }
    
    return render(request, 'dashboard/index.html', context)


def warenkorb(request):
    """Shopping cart view - recommended items based on forecast with date simulation"""
    # Get reference date from request or use today
    reference_date_str = request.GET.get('reference_date', datetime.now().strftime('%Y-%m-%d'))
    try:
        reference_date = datetime.strptime(reference_date_str, '%Y-%m-%d')
    except ValueError:
        reference_date = datetime.now()
        reference_date_str = reference_date.strftime('%Y-%m-%d')
    
    # Get automatic shopping cart recommendations
    cart_items, total_price = get_shopping_cart_recommendations(max_price=500, reference_date=reference_date)
    
    # Enrich cart items with hypothetical consumption data
    for item in cart_items:
        # Find the corresponding inventory item to get depletion rate
        inventory = get_inventory_summary()
        for inv_item in inventory:
            if inv_item['drum_id'] == item['drum_id']:
                consumption_data = calculate_hypothetical_consumption(inv_item, reference_date)
                item['consumption_data'] = consumption_data
                break
    
    context = {
        'cart_items': cart_items,
        'total_price': total_price,
        'max_price': 500,
        'reference_date': reference_date_str,
        'reference_date_display': reference_date.strftime('%d.%m.%Y'),
        'today': datetime.now().strftime('%Y-%m-%d'),
    }
    
    return render(request, 'dashboard/warenkorb.html', context)


def sensors(request):
    """Sensor state view - voltage and signal strength"""
    customers = get_customers()
    selected_customer = request.GET.get('customer', customers[0] if customers else None)
    
    racks = get_racks_for_customer(selected_customer) if selected_customer else []
    selected_rack = request.GET.get('rack', racks[0] if racks else None)
    
    # Get inventory data to display sensor info
    sensor_data = get_inventory_summary(customer=selected_customer, rack=selected_rack)
    
    context = {
        'customers': customers,
        'selected_customer': selected_customer,
        'racks': racks,
        'selected_rack': selected_rack,
        'sensor_data': sensor_data,
    }
    
    return render(request, 'dashboard/sensors.html', context)


