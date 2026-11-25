"""Which cricket country each ground belongs to (for the venue country filter).

Cricsheet gives a city but no country. Countries follow cricket boards, so
Cardiff counts as England, Belfast as Ireland and the Caribbean as West Indies.
"""

from __future__ import annotations

_CITIES: dict[str, list[str]] = {
    "India": [
        "Ahmedabad", "Bangalore", "Bengaluru", "Chandigarh", "Chennai", "Cuttack", "Delhi", "Dharamsala", "Faridabad",
        "Guwahati", "Gwalior", "Hyderabad", "Indore", "Jaipur", "Jamshedpur", "Kanpur", "Kochi", "Kolkata", "Lucknow",
        "Mohali", "Mumbai", "Nagpur", "New Chandigarh", "Pune", "Raipur", "Rajkot", "Ranchi", "Thiruvananthapuram",
        "Vadodara", "Visakhapatnam", "Mullanpur",
    ],
    "New Zealand": [
        "Auckland", "Christchurch", "Dunedin", "Hamilton", "Lincoln", "Mount Maunganui", "Napier", "Nelson",
        "Queenstown", "Wellington", "Whangarei",
    ],
    "England": [
        "Birmingham", "Bristol", "Canterbury", "Cardiff", "Chester-le-Street", "Leeds", "London", "Manchester",
        "Nottingham", "Southampton", "Taunton",
    ],
    "Australia": [
        "Adelaide", "Brisbane", "Cairns", "Canberra", "Carrara", "Darwin", "Geelong", "Hobart", "Mackay", "Melbourne",
        "Perth", "Sydney", "Townsville", "Victoria",
    ],
    "South Africa": [
        "Benoni", "Bloemfontein", "Cape Town", "Centurion", "Durban", "East London", "Johannesburg", "Kimberley",
        "Paarl", "Pietermaritzburg", "Port Elizabeth", "Gqeberha", "Potchefstroom",
    ],
    "Pakistan": ["Faisalabad", "Karachi", "Lahore", "Multan", "Peshawar", "Rawalpindi", "Sind"],
    "Sri Lanka": ["Colombo", "Dambulla", "Hambantota", "Kandy", "Galle"],
    "Bangladesh": ["Bogra", "Chattogram", "Chittagong", "Dhaka", "Fatullah", "Khulna", "Mirpur", "Sylhet"],
    "West Indies": [
        "Antigua", "Bridgetown", "Coolidge", "Dominica", "Grenada", "Gros Islet", "Guyana", "Jamaica", "St George's",
        "St Kitts", "St Lucia", "St Vincent", "Tarouba", "Trinidad", "Basseterre", "Kingston", "Kingstown",
        "Port of Spain", "Providence", "North Sound", "Georgetown",
    ],
    "Zimbabwe": ["Bulawayo", "Harare"],
    "Ireland": ["Belfast", "Bready", "Dublin"],
    "Scotland": ["Aberdeen", "Ayr", "Dundee", "Edinburgh", "Glasgow"],
    "United Arab Emirates": ["Abu Dhabi", "Dubai", "Sharjah"],
    "Netherlands": ["Amstelveen", "Deventer", "Rotterdam", "The Hague", "Utrecht"],
    "Oman": ["Al Amarat", "Muscat"],
    "Nepal": ["Kathmandu", "Kirtipur"],
    "Namibia": ["Windhoek"],
    "Kenya": ["Nairobi", "Mombasa"],
    "Uganda": ["Entebbe", "Jinja", "Kampala"],
    "Rwanda": ["Kigali City"],
    "Tanzania": ["Dar-es-Salaam"],
    "Nigeria": ["Abuja", "Lagos"],
    "Ghana": ["Accra"],
    "Botswana": ["Gaborone"],
    "Malawi": ["Blantyre"],
    "Eswatini": ["Malkerns"],
    "United States": ["Dallas", "Houston", "Lauderhill", "New York", "Pearland"],
    "Canada": ["King City", "Toronto"],
    "Malaysia": ["Bangi", "Kuala Lumpur"],
    "Thailand": ["Bangkok"],
    "Singapore": ["Singapore"],
    "Hong Kong": ["Mong Kok"],
    "Japan": ["Nisshin", "Sano"],
    "South Korea": ["Incheon"],
    "China": ["Hangzhou"],
    "Indonesia": ["Bali"],
    "Bhutan": ["Gelephu"],
    "Qatar": ["Doha"],
    "Papua New Guinea": ["Port Moresby"],
    "Vanuatu": ["Port Vila"],
    "Samoa": ["Apia"],
    "Denmark": ["Brondby", "Copenhagen", "Ishoj", "Koge"],
    "Finland": ["Kerava", "Vantaa"],
    "Norway": ["Oslo"],
    "Sweden": ["Stockholm"],
    "Estonia": ["Tallinn"],
    "Germany": ["Krefeld"],
    "Austria": ["Graz", "Latschach"],
    "Belgium": ["Ghent", "Waterloo", "Zemst"],
    "Luxembourg": ["Walferdange"],
    "France": ["Dreux"],
    "Spain": ["Almeria", "Murcia"],
    "Portugal": ["Albergaria"],
    "Italy": ["Rome", "Spinaceto"],
    "Malta": ["Marsa"],
    "Cyprus": ["Episkopi"],
    "Czech Republic": ["Prague"],
    "Hungary": ["Szodliget"],
    "Romania": ["Ilfov County"],
    "Bulgaria": ["Sofia"],
    "Serbia": ["Belgrade"],
    "Croatia": ["Zagreb"],
    "Gibraltar": ["Gibraltar"],
    "Guernsey": ["Castel", "Port Soif", "Port  Soif", "St Peter Port"],
    "Jersey": ["St Saviour"],
    "Cayman Islands": ["George Town"],
    "Panama": ["Panama City"],
    "Costa Rica": ["Guacima"],
    "Mexico": ["Naucalpan"],
    "Brazil": ["Seropedica"],
    "Argentina": ["Buenos Aires"],
    "Colombia": ["Bogota"],
}
CITY_TO_COUNTRY = {city.lower(): country for country, cities in _CITIES.items() for city in cities}

# Name clues win over the city (same city name in two countries, or no city given)
NAME_CLUES: list[tuple[str, str]] = [
    ("sandys parish", "Bermuda"),
    ("national stadium, hamilton", "Bermuda"),
    ("cayman", "Cayman Islands"),
    ("niaz stadium", "Pakistan"),
    ("sheikhupura", "Pakistan"),
    ("chittagong", "Bangladesh"),
    ("mombasa", "Kenya"),
    ("galle", "Sri Lanka"),
]


def country_for(name: str, city: str, teams: list[str] | None = None) -> str:
    lowered = (name or "").lower()
    for clue, country in NAME_CLUES:
        if clue in lowered:
            return country
    country = CITY_TO_COUNTRY.get((city or "").strip().lower())
    if country:
        return country
    # Unknown city: the side that plays there most is usually the host
    for team in teams or []:
        if team and not any(word in team for word in ("Indians", "Kings", "Royals", "Capitals", "Riders", "Titans", "Giants", "Sunrisers", "Challengers", "Chargers", "Warriors")):
            return team
    return "Other"
