"""Restaurant Booking domain scenario generators."""
import random
from datetime import datetime, timedelta
from typing import Dict, Any


def _generate_future_date_text(days_ahead: int = 2) -> str:
    """Generate future date as text like 'tomorrow', 'next Wednesday', or specific date."""
    if days_ahead == 1:
        return "tomorrow"
    elif days_ahead <= 7:
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        future_date = datetime.now() + timedelta(days=days_ahead)
        return f"next {weekdays[future_date.weekday()]}"
    else:
        future_date = datetime.now() + timedelta(days=days_ahead)
        return future_date.strftime("%Y-%m-%d")


def generate_dine_in(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a dine_in scenario (covers dinner, brunch, and group dining)."""
    # Determine meal type from use_case if available
    use_case_hint = persona.get('_temp_use_case', '')
    
    if 'brunch' in use_case_hint.lower():
        cuisines = ["American", "French", "Mediterranean", "Fusion"]
        time_window = ">=10:00"
        party_size = random.choice([2, 4])
        meal_type = "brunch"
    elif 'group' in use_case_hint.lower():
        cuisines = ["Italian", "American", "Steakhouse", "Mexican"]
        time_window = ">=18:00"
        party_size = random.choice([6, 8, 10])
        meal_type = "group dinner"
    else:
        cuisines = ["Italian", "Japanese", "Mediterranean", "Thai", "French", "Indian"]
        time_window = ">=18:00"
        party_size = random.choice([2, 4])
        meal_type = "dinner"
    
    cuisine = random.choice(cuisines)
    date_text = _generate_future_date_text(random.choice([1, 2, 5]))
    
    # Use persona's hometown for location
    hometown = persona.get('hometown', 'Downtown')
    location = hometown.split(',')[0].strip()  # Get city name
    
    # Generate restaurants
    restaurant_names = [
        f"{cuisine} Bistro",
        f"The {cuisine} Kitchen",
        f"{location} {cuisine}",
        f"Bella {cuisine}"
    ]
    
    restaurants = []
    for i in range(3):
        name = restaurant_names[i % len(restaurant_names)] if i < len(restaurant_names) else f"Restaurant {i+1}"
        restaurants.append({
            "restaurant_id": f"RST-{i+1:03d}",
            "name": name + f" #{i+1}" if i > 0 else name,
            "cuisine": cuisine,
            "address": f"{random.randint(100, 999)} {random.choice(['Main', 'Market', 'Oak', 'Elm'])} St, {location}",
            "rating": round(random.uniform(3.8, 4.8), 1),
            "price_range": random.choice(["$", "$$", "$$$"]),
            "hours": "Mon-Sun 17:00-22:00" if meal_type == "dinner" else "Mon-Sun 09:00-14:00"
        })
    
    # Optionally add a change_mind behavior for variety
    behaviors = []
    if random.random() < 0.3:  # 30% chance
        behaviors.append({
            "type_id": "user.change_mind",
            "instructions": f"After initial query and results, change the preference for date from {date_text} to next Wednesday."
        })
    
    return {
        "metadata": {
            "domain": "restaurant_booking",
            "use_case": "dine_in",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "date": date_text,
                    "time_window": time_window,
                    "party_size": party_size,
                    "location": location
                },
                "preferences": {
                    "cuisine": cuisine
                }
            },
            "success_criteria": {
                "target_selector": {
                    "cuisine": cuisine,
                    "location": location
                },
                "action": "make_reservation",
                "notes": f"Success if the assistant makes a reservation via make_reservation at one of the seeded {cuisine} restaurants in {location} for {party_size} people."
            },
            "objective": f"Find and book a restaurant for {meal_type}."
        },
        "user_agent": {
            "injected_behaviors": behaviors
        },
        "tool_agent": {
            "injected_behaviors": [],
            "context": {
                "seed": {
                    "restaurants": restaurants
                }
            }
        },
        "persona": persona['id']
    }

