"""Banking domain scenario generators."""
import random
from typing import Dict, Any


def generate_check_account_balance(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a check_account_balance scenario."""
    account_types = ["checking", "savings"]
    target_account = random.choice(account_types)
    
    # Generate realistic account balances
    checking_balance = round(random.uniform(500, 5000), 2)
    savings_balance = round(random.uniform(5000, 25000), 2)
    
    return {
        "metadata": {
            "domain": "banking",
            "use_case": "check_account_balance",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "target_account": target_account
                },
                "preferences": {}
            },
            "success_criteria": {
                "target_selector": {
                    "account_type": target_account
                },
                "action": "get_account_balance",
                "notes": f"Success if the assistant retrieves the balance for the {target_account} account using get_account_balance and tells the user the balance."
            },
            "objective": "Check bank account balance"
        },
        "user_agent": {
            "injected_behaviors": []
        },
        "tool_agent": {
            "injected_behaviors": [],
            "context": {
                "seed": {
                    "accounts": [
                        {
                            "account_id": "ACC-001",
                            "account_type": "checking",
                            "nickname": "Everyday Checking",
                            "masked_number": f"****{random.randint(1000, 9999)}",
                            "currency": "USD"
                        },
                        {
                            "account_id": "ACC-002",
                            "account_type": "savings",
                            "nickname": "Emergency Fund",
                            "masked_number": f"****{random.randint(1000, 9999)}",
                            "currency": "USD"
                        }
                    ],
                    "balances": [
                        {
                            "account_id": "ACC-001",
                            "current_balance": checking_balance,
                            "available_balance": round(checking_balance - random.uniform(0, 100), 2),
                            "currency": "USD",
                            "last_updated": "2025-11-26T14:32:10Z"
                        },
                        {
                            "account_id": "ACC-002",
                            "current_balance": savings_balance,
                            "available_balance": savings_balance,
                            "currency": "USD",
                            "last_updated": "2025-11-26T14:32:10Z"
                        }
                    ]
                }
            }
        },
        "persona": persona['id']
    }


def generate_report_card_lost_or_stolen(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a report_card_lost_or_stolen scenario."""
    card_types = ["debit", "credit"]
    card_type = random.choice(card_types)
    last4 = random.randint(1000, 9999)
    
    return {
        "metadata": {
            "domain": "banking",
            "use_case": "report_card_lost_or_stolen",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "card_type": card_type,
                    "last4": str(last4)
                },
                "preferences": {}
            },
            "success_criteria": {
                "target_selector": {
                    "card_type": card_type,
                    "last4": str(last4)
                },
                "action": "report_card_lost_stolen",
                "notes": f"Success if the assistant reports the {card_type} card ending in {last4} as lost/stolen via report_card_lost_stolen."
            },
            "objective": f"Report {card_type} card as lost or stolen"
        },
        "user_agent": {
            "injected_behaviors": [
                {
                    "instructions": f"The user needs to report their {card_type} card as lost. They know the last 4 digits."
                }
            ]
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "cards": [
                        {
                            "card_id": f"CARD-{random.randint(100, 999)}",
                            "card_type": card_type,
                            "masked_number": f"****{last4}",
                            "status": "active",
                            "expiry": "2027-12-31"
                        }
                    ]
                }
            }
        },
        "persona": persona['id']
    }


def generate_dispute_charge(persona: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Generate a dispute_charge scenario."""
    merchant_names = ["Amazon", "Walmart", "Target", "Best Buy", "Apple Store"]
    merchant = random.choice(merchant_names)
    amount = round(random.uniform(50, 500), 2)
    last4 = random.randint(1000, 9999)
    
    return {
        "metadata": {
            "domain": "banking",
            "use_case": "dispute_charge",
            "scenario_id": scenario_id
        },
        "domain_ref": {
            "toolset_path": "../tools.json"
        },
        "task": {
            "slots": {
                "constraints": {
                    "transaction_id": f"TXN-{random.randint(100000, 999999)}",
                    "amount": amount,
                    "merchant": merchant
                },
                "preferences": {}
            },
            "success_criteria": {
                "target_selector": {
                    "merchant": merchant,
                    "amount": amount
                },
                "action": "dispute_transaction",
                "notes": f"Success if the assistant disputes the ${amount} charge from {merchant} via dispute_transaction."
            },
            "objective": f"Dispute unauthorized charge from {merchant}"
        },
        "user_agent": {
            "injected_behaviors": [
                {
                    "instructions": "The user sees a charge they don't recognize and wants to dispute it."
                }
            ]
        },
        "tool_agent": {
            "context": {
                "seed": {
                    "transactions": [
                        {
                            "transaction_id": f"TXN-{random.randint(100000, 999999)}",
                            "date": "2025-11-24",
                            "merchant": merchant,
                            "amount": amount,
                            "currency": "USD",
                            "card_last4": str(last4),
                            "status": "posted",
                            "disputeable": True
                        }
                    ]
                }
            }
        },
        "persona": persona['id']
    }

