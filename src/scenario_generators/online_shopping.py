"""Online Shopping domain scenario generators."""
import random
from datetime import datetime, timedelta
from typing import Dict, Any


def _generate_past_date(days_ago: int = 30) -> str:
    """Generate a past date string."""
    past_date = datetime.now() - timedelta(days=days_ago)
    return past_date.strftime("%Y-%m-%d")


def _mask_email(email: str) -> str:
    """Mask an email address."""
    if '@' not in email:
        return "u***@example.com"
    local, domain = email.split('@')
    return f"{local[0]}***@{domain}"


def generate_track_order(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a track_order scenario."""
    items = [
        "Bluetooth Headphones",
        "Wireless Mouse",
        "USB-C Cable",
        "Laptop Stand",
        "Phone Case",
        "Water Bottle"
    ]
    item_name = random.choice(items)
    price = round(random.uniform(20, 150), 2)
    order_date = _generate_past_date(random.randint(5, 15))
    last4 = str(random.randint(1000, 9999))
    
    persona_email = persona.get('email', 'user@example.com')
    
    return {
        "metadata": {
            "domain": "online_shopping",
            "use_case": "track_order",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "target_order_date": order_date,
                    "email": persona_email,
                    "last4": last4
                },
                "preferences": {
                    "item_name": item_name
                }
            },
            "success_criteria": {
                "target_selector": {
                    "placed_at": order_date
                },
                "action": "get_shipment_status",
                "notes": f"Success if the assistant provided tracking status/information for the order placed on {order_date} via get_shipment_status."
            },
            "objective": "Track an order that was placed."
        },
        "user_agent": {
            "injected_behaviors": [
                {
                    "instructions": "The user knows the approximate order date and item name, but doesn't know the exact order_id."
                }
            ]
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "orders": [
                        {
                            "order_id": f"ODR-{random.randint(100000, 199999)}",
                            "placed_at": f"{order_date}T{random.randint(9, 17)}:{random.randint(10, 59)}:00Z",
                            "status": random.choice(["shipped", "in_transit", "delivered"]),
                            "total": price,
                            "currency": "USD",
                            "email_masked": _mask_email(persona_email),
                            "last4": last4,
                            "items": [
                                {
                                    "item_id": f"SKU-{random.randint(100, 999)}",
                                    "name": item_name,
                                    "qty": 1,
                                    "unit_price": price,
                                    "currency": "USD",
                                    "status": random.choice(["shipped", "delivered"]),
                                    "cancelable": False,
                                    "returnable": True
                                }
                            ],
                            "shipments": [
                                {
                                    "shipment_id": f"SHP-{random.randint(8000, 9999)}",
                                    "carrier": random.choice(["USPS", "UPS", "FedEx"]),
                                    "tracking_number": f"9400111899{random.randint(2200000000, 2299999999)}",
                                    "status": random.choice(["in_transit", "delivered"]),
                                    "eta": _generate_past_date(random.randint(1, 3)),
                                    "items": [
                                        {
                                            "item_id": f"SKU-{random.randint(100, 999)}",
                                            "qty": 1
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            }
        },
        "persona": persona['id']
    }


def generate_return_order(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a return_order scenario."""
    items = [
        "Yoga Mat",
        "Kitchen Blender",
        "Desk Lamp",
        "Running Shoes",
        "Backpack",
        "Coffee Maker"
    ]
    item_name = random.choice(items)
    price = round(random.uniform(30, 150), 2)
    order_date = _generate_past_date(random.randint(10, 25))
    last4 = str(random.randint(1000, 9999))
    persona_email = persona.get('email', 'user@example.com')
    
    # Extract zip from hometown if possible
    hometown = persona.get('hometown', 'Unknown')
    zip_code = str(random.randint(10000, 99999))
    
    return {
        "metadata": {
            "domain": "online_shopping",
            "use_case": "return_order",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "target_order_date": order_date,
                    "email": persona_email,
                    "last4": last4,
                    "zip_code": zip_code
                },
                "preferences": {
                    "item_name": item_name
                }
            },
            "success_criteria": {
                "target_selector": {
                    "placed_at": order_date
                },
                "action": "create_return",
                "notes": f"Success if the assistant created a return (RMA) for the order placed on {order_date} via create_return."
            },
            "objective": "Return an order that was delivered."
        },
        "user_agent": {
            "injected_behaviors": [
                {
                    "instructions": "The user knows the approximate order date and item name, but doesn't know the exact order_id."
                }
            ]
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "orders": [
                        {
                            "order_id": f"ODR-{random.randint(100000, 199999)}",
                            "placed_at": f"{order_date}T{random.randint(9, 17)}:{random.randint(10, 59)}:00Z",
                            "status": "delivered",
                            "total": price,
                            "currency": "USD",
                            "email_masked": _mask_email(persona_email),
                            "last4": last4,
                            "items": [
                                {
                                    "item_id": f"SKU-{random.randint(100, 999)}",
                                    "name": f"{item_name} - Premium",
                                    "qty": 1,
                                    "unit_price": price,
                                    "currency": "USD",
                                    "status": "delivered",
                                    "cancelable": False,
                                    "returnable": True
                                }
                            ],
                            "shipments": [
                                {
                                    "shipment_id": f"SHP-{random.randint(8000, 9999)}",
                                    "carrier": random.choice(["USPS", "UPS", "FedEx"]),
                                    "tracking_number": f"9400111899{random.randint(2200000000, 2299999999)}",
                                    "status": "delivered",
                                    "eta": _generate_past_date(5),
                                    "items": [
                                        {
                                            "item_id": f"SKU-{random.randint(100, 999)}",
                                            "qty": 1
                                        }
                                    ]
                                }
                            ],
                            "payment": {
                                "method_masked": f"****{last4}",
                                "captured": price,
                                "refundable": price,
                                "currency": "USD"
                            },
                            "policy": {
                                "cancel_window": "Before shipment",
                                "return_window": "30 days from delivery",
                                "restocking_fees": False,
                                "methods_supported": ["dropoff", "pickup"]
                            },
                            "cancelable_any": False,
                            "returnable_any": True
                        }
                    ],
                    "dropoff_locations": [
                        {
                            "location_id": "LOC-001",
                            "name": "USPS Store - Downtown",
                            "address": f"123 Main St, {hometown.split(',')[0]}, {zip_code}",
                            "hours": "Mon-Fri 9am-5pm, Sat 10am-2pm",
                            "distance_km": round(random.uniform(0.5, 2.0), 1)
                        }
                    ]
                },
                "rules": []
            }
        },
        "persona": persona['id']
    }


def generate_cancel_order(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a cancel_order scenario."""
    items = ["Tablet", "Smart Watch", "Headphones", "Keyboard", "Monitor"]
    item_name = random.choice(items)
    price = round(random.uniform(100, 500), 2)
    order_date = _generate_past_date(random.randint(1, 3))
    last4 = str(random.randint(1000, 9999))
    persona_email = persona.get('email', 'user@example.com')
    
    return {
        "metadata": {
            "domain": "online_shopping",
            "use_case": "cancel_order",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "target_order_date": order_date,
                    "email": persona_email,
                    "last4": last4
                },
                "preferences": {
                    "item_name": item_name
                }
            },
            "success_criteria": {
                "target_selector": {
                    "placed_at": order_date
                },
                "action": "cancel_order",
                "notes": f"Success if the assistant cancels the order placed on {order_date} via cancel_order."
            },
            "objective": "Cancel a recent order"
        },
        "user_agent": {
            "injected_behaviors": [
                {
                    "instructions": "The user changed their mind and wants to cancel the order before it ships."
                }
            ]
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "orders": [
                        {
                            "order_id": f"ODR-{random.randint(100000, 199999)}",
                            "placed_at": f"{order_date}T{random.randint(9, 17)}:{random.randint(10, 59)}:00Z",
                            "status": "processing",
                            "total": price,
                            "currency": "USD",
                            "email_masked": _mask_email(persona_email),
                            "last4": last4,
                            "items": [
                                {
                                    "item_id": f"SKU-{random.randint(100, 999)}",
                                    "name": item_name,
                                    "qty": 1,
                                    "unit_price": price,
                                    "currency": "USD",
                                    "status": "pending",
                                    "cancelable": True,
                                    "returnable": False
                                }
                            ],
                            "shipments": [],
                            "cancelable_any": True,
                            "returnable_any": False
                        }
                    ]
                }
            }
        },
        "persona": persona['id']
    }

