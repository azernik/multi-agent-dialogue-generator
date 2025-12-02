"""Calendar Assistant domain scenario generators."""
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List


def _generate_future_date(days_ahead: int = 7) -> str:
    """Generate a future date string."""
    future_date = datetime.now() + timedelta(days=days_ahead)
    return future_date.strftime("%Y-%m-%d")


def _generate_datetime_slot(date_str: str, hour: int = 9, duration_minutes: int = 60) -> Dict[str, str]:
    """Generate a datetime slot."""
    start_dt = datetime.fromisoformat(date_str + f"T{hour:02d}:00:00")
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return {
        "start": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "all_available": True
    }


def generate_schedule_meeting(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a schedule_meeting scenario."""
    meeting_titles = [
        "Team Sync", 
        "Project Review",
        "Weekly Planning",
        "Department Meeting",
        "Stakeholder Review"
    ]
    title = random.choice(meeting_titles)
    duration = random.choice([30, 60, 90])
    date = _generate_future_date(random.randint(3, 10))
    
    # Generate attendee emails based on persona's email domain
    persona_email = persona.get('email', 'user@example.com')
    domain = persona_email.split('@')[1] if '@' in persona_email else 'example.com'
    
    attendees = [
        f"colleague1@{domain}",
        f"colleague2@{domain}"
    ]
    
    return {
        "metadata": {
            "domain": "calendar_assistant",
            "use_case": "schedule_meeting",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "meeting_title": title,
                    "duration_minutes": duration,
                    "attendees": attendees
                },
                "preferences": {
                    "preferred_date": date,
                    "time_of_day": random.choice(["morning", "afternoon"])
                }
            },
            "success_criteria": {
                "target_selector": {
                    "meeting_title": title
                },
                "action": "create_meeting",
                "notes": f"Success if the assistant creates a meeting titled '{title}' via create_meeting with {duration} minute duration."
            },
            "objective": f"Schedule a {title.lower()} with team members"
        },
        "user_agent": {
            "injected_behaviors": []
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "available_slots": [
                        _generate_datetime_slot(date, 9, duration),
                        _generate_datetime_slot(date, 14, duration)
                    ]
                }
            }
        },
        "persona": persona['id']
    }


def generate_reschedule_meeting(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a reschedule_meeting scenario."""
    meeting_titles = ["Team Sync", "Client Call", "Review Session", "Training Workshop"]
    title = random.choice(meeting_titles)
    original_date = _generate_future_date(5)
    new_date = _generate_future_date(8)
    
    return {
        "metadata": {
            "domain": "calendar_assistant",
            "use_case": "reschedule_meeting",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "meeting_id": f"MTG-{random.randint(1000, 9999)}",
                    "original_date": original_date
                },
                "preferences": {
                    "new_date": new_date
                }
            },
            "success_criteria": {
                "target_selector": {
                    "meeting_title": title
                },
                "action": "reschedule_meeting",
                "notes": f"Success if the assistant reschedules the '{title}' meeting via reschedule_meeting."
            },
            "objective": f"Reschedule {title.lower()} to a different day"
        },
        "user_agent": {
            "injected_behaviors": [
                {
                    "instructions": "The user needs to reschedule due to a conflict and prefers the new date."
                }
            ]
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "existing_meetings": [
                        {
                            "meeting_id": f"MTG-{random.randint(1000, 9999)}",
                            "title": title,
                            "start": original_date + "T10:00:00Z",
                            "end": original_date + "T11:00:00Z",
                            "attendees": [persona.get('email', 'user@example.com')]
                        }
                    ],
                    "available_slots": [
                        _generate_datetime_slot(new_date, 10, 60),
                        _generate_datetime_slot(new_date, 14, 60)
                    ]
                }
            }
        },
        "persona": persona['id']
    }


def generate_recurring_one_on_one(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a recurring_one_on_one scenario."""
    # Generate colleague email based on persona's domain
    persona_email = persona.get('email', 'user@example.com')
    domain = persona_email.split('@')[1] if '@' in persona_email else 'example.com'
    colleague_email = f"colleague@{domain}"
    
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    preferred_day = random.choice(weekdays)
    
    return {
        "metadata": {
            "domain": "calendar_assistant",
            "use_case": "recurring_one_on_one",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "other_attendee_email": colleague_email,
                    "frequency": "weekly",
                    "duration_minutes": 30
                },
                "preferences": {
                    "preferred_day": preferred_day,
                    "time_of_day": random.choice(["morning", "afternoon"])
                }
            },
            "success_criteria": {
                "target_selector": {
                    "other_attendee_email": colleague_email,
                    "frequency": "weekly"
                },
                "action": "create_recurring_meeting",
                "notes": "Success if the assistant creates a weekly recurring one-on-one meeting series via create_recurring_meeting with 30-minute duration."
            },
            "objective": "Set up a weekly one-on-one meeting"
        },
        "user_agent": {
            "injected_behaviors": [
                {
                    "instructions": f"The user wants to set up a weekly sync meeting. They prefer {preferred_day}s but are flexible on the exact time."
                }
            ]
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "available_slots": [
                        _generate_datetime_slot(_generate_future_date(7), 9, 30)
                    ]
                }
            }
        },
        "persona": persona['id']
    }


def generate_outdoor_event(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate an outdoor_event scenario."""
    event_types = [
        ("Community Garden Workshop", "Community Garden"),
        ("Outdoor Team Building", "City Park"),
        ("Field Trip", persona.get('hometown', 'Local Park').split(',')[0] + " Zoo"),
        ("Nature Walk", "Nature Reserve"),
        ("Outdoor Concert", "Amphitheater")
    ]
    event_title, location = random.choice(event_types)
    date = _generate_future_date(random.randint(7, 14))
    
    return {
        "metadata": {
            "domain": "calendar_assistant",
            "use_case": "outdoor_event",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "event_title": event_title,
                    "location": location,
                    "duration_minutes": 180,
                    "attendees": [persona.get('email', 'user@example.com')]
                },
                "preferences": {
                    "preferred_date": date
                }
            },
            "success_criteria": {
                "target_selector": {
                    "event_title": event_title,
                    "location": location
                },
                "action": "create_meeting",
                "notes": f"Success if the assistant schedules the {event_title} at {location} via create_meeting for 180 minutes."
            },
            "objective": f"Schedule outdoor event: {event_title}"
        },
        "user_agent": {
            "injected_behaviors": [
                {
                    "instructions": "The user wants to schedule an outdoor event and wants to check the weather first."
                }
            ]
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "weather_forecast": {
                        "date": date,
                        "location": location,
                        "temperature": random.randint(60, 75),
                        "conditions": random.choice(["sunny", "partly cloudy", "clear"]),
                        "chance_of_rain": random.randint(5, 20),
                        "wind_speed": random.randint(5, 15),
                        "recommendation": "suitable"
                    },
                    "available_slots": [
                        _generate_datetime_slot(date, 10, 180)
                    ]
                }
            }
        },
        "persona": persona['id']
    }

