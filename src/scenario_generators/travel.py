"""Travel domain scenario generators."""
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List


def _generate_future_date(days_ahead: int = 30) -> str:
    """Generate a future date string."""
    future_date = datetime.now() + timedelta(days=days_ahead)
    return future_date.strftime("%Y-%m-%d")


def _generate_flight_data(origin: str, destination: str, departure_date: str, flight_class: str) -> Dict[str, Any]:
    """Generate realistic flight data."""
    airlines = [
        ("United Airlines", "UA"),
        ("American Airlines", "AA"),
        ("Delta", "DL"),
        ("Southwest Airlines", "WN")
    ]
    airline_name, airline_code = random.choice(airlines)
    flight_num = random.randint(100, 999)
    
    # Airport codes (simplified mapping)
    airport_map = {
        "Denver": "DEN",
        "Washington DC": "DCA",
        "New York": "JFK",
        "Los Angeles": "LAX",
        "Chicago": "ORD",
        "San Francisco": "SFO",
        "Boston": "BOS",
        "Seattle": "SEA",
        "Miami": "MIA",
        "Atlanta": "ATL"
    }
    
    origin_code = airport_map.get(origin, "XXX")
    dest_code = airport_map.get(destination, "YYY")
    
    departure_hour = random.randint(6, 20)
    duration_hours = random.randint(2, 6)
    arrival_hour = (departure_hour + duration_hours) % 24
    
    price = round(random.uniform(250, 600), 2)
    
    return {
        "flight_id": f"FLT-{airline_code}{flight_num}",
        "airline": airline_name,
        "airline_code": airline_code,
        "flight_number": f"{airline_code}{flight_num}",
        "departure": {
            "airport": origin_code,
            "airport_name": f"{origin} International Airport",
            "datetime": f"{departure_date}T{departure_hour:02d}:00:00Z",
            "terminal": random.choice(["A", "B", "C"]),
            "gate": f"{random.choice(['A', 'B', 'C'])}{random.randint(10, 45)}"
        },
        "arrival": {
            "airport": dest_code,
            "airport_name": f"{destination} International Airport",
            "datetime": f"{departure_date}T{arrival_hour:02d}:30:00Z",
            "terminal": random.choice(["1", "2", "3"]),
            "gate": f"C{random.randint(10, 30)}"
        },
        "duration": f"{duration_hours}h {random.choice([0, 15, 30, 45])}m",
        "stops": 0,
        "stop_details": [],
        "class": flight_class,
        "price": price,
        "currency": "USD",
        "refundable": random.choice([True, False]),
        "changeable": True,
        "baggage_included": {
            "carry_on": True,
            "checked": random.randint(1, 2)
        },
        "seats_available": random.randint(5, 20)
    }


def generate_book_flight(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a book_flight scenario."""
    # Popular city pairs
    city_pairs = [
        ("Denver", "Washington DC"),
        ("New York", "Los Angeles"),
        ("Chicago", "San Francisco"),
        ("Boston", "Miami"),
        ("Seattle", "Atlanta"),
        ("San Francisco", "New York")
    ]
    
    origin, destination = random.choice(city_pairs)
    departure_date = _generate_future_date(random.randint(30, 90))
    return_date = _generate_future_date(random.randint(32, 95))
    flight_class = random.choice(["economy", "business"])
    num_passengers = random.choice([1, 2])
    
    # Generate 3 outbound flights
    flights = [
        _generate_flight_data(origin, destination, departure_date, flight_class)
        for _ in range(3)
    ]
    
    # Generate return flights
    return_flights = [
        _generate_flight_data(destination, origin, return_date, flight_class)
        for _ in range(2)
    ]
    
    return {
        "metadata": {
            "domain": "travel",
            "use_case": "book_flight",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "origin": origin,
                    "destination": destination,
                    "departure_date": departure_date,
                    "return_date": return_date,
                    "num_passengers": num_passengers
                },
                "preferences": {
                    "class_preference": flight_class
                }
            },
            "success_criteria": {
                "target_selector": {
                    "departure_date": departure_date
                },
                "action": "book_flight",
                "notes": f"Success if the assistant booked a round-trip flight from {origin} to {destination} departing on {departure_date} for {num_passengers} passenger(s) via book_flight"
            },
            "objective": f"Book a round-trip flight from {origin} to {destination}."
        },
        "user_agent": {
            "injected_behaviors": []
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "flights": flights,
                    "return_flights": return_flights
                }
            },
            "injected_behaviors": []
        },
        "persona": persona['id']
    }


def generate_book_hotel(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a book_hotel scenario."""
    cities = [
        "Orlando",
        "Las Vegas",
        "New York",
        "San Francisco",
        "Boston",
        "Chicago",
        "Miami"
    ]
    
    location = random.choice(cities)
    check_in_date = _generate_future_date(random.randint(30, 90))
    nights = random.choice([2, 3, 4, 5])
    check_out = (datetime.fromisoformat(check_in_date) + timedelta(days=nights)).strftime("%Y-%m-%d")
    num_guests = random.choice([1, 2, 4])
    
    # Generate 3 hotels
    hotel_names = [
        f"{location} Resort",
        f"Downtown {location} Hotel",
        f"Budget Inn {location}"
    ]
    
    hotels = []
    for i, name in enumerate(hotel_names):
        rating = 5 - i  # 5, 4, 3 stars
        base_price = [150, 120, 80][i]
        price_per_night = base_price + random.randint(-20, 20)
        total_price = price_per_night * nights
        
        hotels.append({
            "hotel_id": f"HTL-{location[:3].upper()}{i+1:03d}",
            "name": name,
            "address": {
                "street": f"{random.randint(100, 9999)} {random.choice(['Main', 'Broadway', 'Park', 'Ocean'])} {'Street' if i < 2 else 'Drive'}",
                "city": location,
                "state": "FL" if location in ["Orlando", "Miami"] else "NV" if location == "Las Vegas" else "CA",
                "zip": str(random.randint(10000, 99999)),
                "country": "USA"
            },
            "rating": rating,
            "price_per_night": float(price_per_night),
            "total_price": float(total_price),
            "currency": "USD",
            "amenities": [
                "wifi",
                "pool" if i < 2 else None,
                "gym" if i == 0 else None,
                "breakfast" if i < 2 else None,
                "air_conditioning",
                "parking"
            ],
            "room_types_available": [
                {
                    "type": "standard",
                    "max_occupancy": 2,
                    "beds": "1 Queen"
                },
                {
                    "type": "deluxe" if i < 2 else "suite",
                    "max_occupancy": 4,
                    "beds": "2 Queens" if i < 2 else "1 King + Sofa"
                }
            ] if i < 2 else [
                {
                    "type": "standard",
                    "max_occupancy": 2,
                    "beds": "1 Full"
                }
            ],
            "cancellation_policy": {
                "free_cancellation": i < 2,
                "cancellation_deadline": f"{check_in_date}T23:59:59Z" if i < 2 else None,
                "cancellation_fee": 0 if i < 2 else 25.0
            },
            "images": []
        })
        
        # Remove None values from amenities
        hotels[-1]["amenities"] = [a for a in hotels[-1]["amenities"] if a is not None]
    
    return {
        "metadata": {
            "domain": "travel",
            "use_case": "book_hotel",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "location": location,
                    "check_in_date": check_in_date,
                    "check_out_date": check_out,
                    "num_guests": num_guests
                },
                "preferences": {
                    "room_type_preference": "standard"
                }
            },
            "success_criteria": {
                "target_selector": {
                    "check_in_date": check_in_date
                },
                "action": "book_hotel",
                "notes": f"Success if the assistant booked a hotel in {location} for check-in on {check_in_date} for {num_guests} guest(s) via book_hotel"
            },
            "objective": f"Book a hotel in {location} for {nights} nights."
        },
        "user_agent": {
            "injected_behaviors": []
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "hotels": hotels
                }
            },
            "injected_behaviors": []
        },
        "persona": persona['id']
    }

