# eKanban - Lapp Group Cable Management System

A professional Django web application for monitoring cable inventory across racks and forecasting when cables will need to be reordered.

## Features

### 📊 Three Main Tabs

1. **Inventory Dashboard** 
   - Real-time cable inventory status per rack
   - Depletion forecasts based on current data
   - Filter by customer and rack
   - Visual status indicators (OK, WARNING, CRITICAL)
   - Days until reorder threshold

2. **Warenkorb (Shopping Basket)**
   - Priority queue of racks sorted by urgency
   - Shows which racks will be empty soonest
   - Quick cards with key metrics
   - Action alerts for critical items

3. **Sensor Status**
   - Monitor IoT sensor health
   - Battery voltage monitoring
   - WiFi signal strength (RSSI) tracking
   - Health indicators with thresholds

## Project Structure

```
ekanban_project/
├── ekanban/                           # Main project folder
│   ├── settings.py                    # Django configuration
│   ├── urls.py                        # URL routing
│   ├── wsgi.py                        # WSGI application
│   └── asgi.py                        # ASGI application
├── dashboard/                          # Dashboard app
│   ├── templates/dashboard/
│   │   ├── base.html                  # Base template with Bootstrap
│   │   ├── index.html                 # Inventory tab
│   │   ├── warenkorb.html            # Priority queue tab
│   │   └── sensors.html               # Sensor monitoring tab
│   ├── views.py                       # View handlers
│   ├── urls.py                        # App-specific URLs
│   ├── utils.py                       # Data loading and processing
│   └── apps.py                        # App configuration
├── manage.py                            # Django management script
├── venv/                               # Python virtual environment
└── requirements.txt                    # Python dependencies
```

## Installation & Setup

### Prerequisites
- Python 3.8+
- pip (Python package manager)

### Step 1: Set up Virtual Environment
```bash
cd /var/home/natalieboehm/Documents/Development/LappHackathon2026/ekanban_project
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install django pandas numpy
```

### Step 3: Run Migrations
```bash
python manage.py migrate
```

### Step 4: Start Development Server
```bash
python manage.py runserver 8000
```

The application will be available at: **http://localhost:8000**

## Data Source

The application loads data from CSV files:
- **drum_1167_linear_forecast.csv** - Contains forecast data with depletion rates
- **rack_kunde_a_regal_og.csv** - Customer and rack information

Place these files in the `data/` directory at the workspace root.

## Current Forecasting Method

The application currently uses **linear regression** forecasts from the CSV data:
- Depletion Rate (m/day) - constant decline rate
- Linear Forecast (m) - predicted cable length
- Days Until Threshold - calculated based on current usage

**Note:** This is ready to be upgraded with polynomial regression or other advanced forecasting methods as discussed in the analysis.

## Key Metrics

### Status Indicators
- **OK**: > 30 days until threshold
- **WARNING**: 7-30 days until threshold
- **CRITICAL**: < 7 days until threshold

### Sensor Health
- **Battery Voltage**: Should be > 3500 mV
- **Signal Strength (RSSI)**: 
  - Excellent: > -70 dBm
  - Good: -70 to -85 dBm
  - Weak: < -85 dBm

## Customization

### To modify thresholds:
Edit `dashboard/utils.py` - look for the `calculate_days_until_threshold()` function

### To add new views/tabs:
1. Add a new view in `dashboard/views.py`
2. Create a new template in `dashboard/templates/dashboard/`
3. Add corresponding URL in `dashboard/urls.py`

### To change styling:
Edit the CSS in `dashboard/templates/dashboard/base.html` - customize the `:root` CSS variables for colors and styling.

## Future Enhancements

1. **Database Integration** - Replace CSV loading with persistent database
2. **Advanced Forecasting** - Implement polynomial regression, ARIMA, or machine learning models
3. **Real-time Updates** - Add WebSocket support for live data updates
4. **User Accounts** - Add authentication and per-user preferences
5. **Export Functionality** - Generate PDF reports and Excel exports
6. **Alerts System** - Email/SMS notifications for critical items
7. **Historical Analysis** - Track trends over time
8. **Mobile App** - Responsive design or native mobile application

## Troubleshooting

### Port 8000 already in use:
```bash
python manage.py runserver 8001  # Use a different port
```

### Data not loading:
- Verify CSV files are in the `data/` directory
- Check file names match exactly in `dashboard/utils.py`
- Ensure CSV headers match the expected column names

### Template not found errors:
- Verify app is listed in INSTALLED_APPS in `settings.py`
- Ensure templates are in `dashboard/templates/dashboard/` directory

## License

© 2026 Lapp Group. All rights reserved.

---

**Developed for:** Lapp Hackathon 2026
**Current Date:** April 3, 2026
