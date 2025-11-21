# Scenario Configuration Schema Guide

This document describes the schema for `task.slots` and `task.success_criteria` in scenario JSON files. It covers both the **syntax** (what the structure looks like) and **semantics** (what each field means and how to use it intelligently).

## Table of Contents

1. [Task Slots Schema](#task-slots-schema)
2. [Success Criteria Schema](#success-criteria-schema)
3. [Migration Guide](#migration-guide)
4. [Domain-Specific Patterns](#domain-specific-patterns)

---

## Task Slots Schema

### Structure

The `task.slots` object now has two top-level keys: `constraints` and `preferences`.

```json
{
  "task": {
    "slots": {
      "constraints": {
        "field1": "value1",
        "field2": 123
      },
      "preferences": {
        "field3": "value3"
      }
    }
  }
}
```

### Constraints vs Preferences: Semantics

**Constraints** (`task.slots.constraints`):
- **Must be satisfied** for the task to be considered successful
- The assistant should not violate these without explicit user agreement to change them
- Examples: required dates, party sizes, attendee emails, order IDs, account numbers
- If a constraint cannot be satisfied, the task is incomplete or impossible (unless the user explicitly agrees to modify it)

**Preferences** (`task.slots.preferences`):
- **Should be satisfied when possible**, but can be relaxed if no options exist
- The assistant can trade these off or suggest alternatives if needed
- Examples: cuisine type, price range, time-of-day preferences, optional features
- If a preference cannot be satisfied, the assistant can still succeed by finding acceptable alternatives and getting user confirmation

### Decision Framework: Constraint or Preference?

Ask yourself: **"If this requirement cannot be met, should the task fail, or can the assistant propose alternatives?"**

- **Constraint**: Task fails if not met → put in `constraints`
  - "Book a table for 4 people" → `party_size` is a constraint
  - "Reschedule meeting with Sarah" → `attendee_email` is a constraint
  - "Return order from Oct 22" → `target_order_date` is a constraint

- **Preference**: Task can succeed with alternatives → put in `preferences`
  - "Italian cuisine" → if no Italian restaurants, Mediterranean is acceptable → `preference`
  - "Wednesday afternoon" → if Wednesday is full, Thursday afternoon works → `preference`
  - "$$ price range" → if only $$$ available and user agrees, task succeeds → `preference`

### Examples

**Restaurant Booking** (`rb_002__persona_003.json`):
```json
"slots": {
  "constraints": {
    "date": "this Friday",
    "time_window": ">=19:00",
    "party_size": 4,
    "location": "San Francisco"
  },
  "preferences": {
    "cuisine": "Italian"
  }
}
```
- **Constraints**: Date, time, party size, and location are non-negotiable without user agreement
- **Preferences**: Cuisine can be relaxed if no Italian options exist

**Calendar Recurring Meeting** (`ca_ro_002__persona_002.json`):
```json
"slots": {
  "constraints": {
    "other_attendee_email": "sarah.chen@uoregon.edu",
    "frequency": "biweekly",
    "preferred_day": "Wednesday",
    "duration_minutes": 45
  },
  "preferences": {
    "time_of_day": "afternoon"
  }
}
```
- **Constraints**: Attendee, frequency, day, and duration are required
- **Preferences**: Time of day can be adjusted if afternoon slots aren't available

**Online Shopping Return** (legacy format, needs migration):
```json
"slots": {
  "target_order_date": "2025-10-22",
  "item_name": "Office Chair",
  "email": "patricia.nguyen@horizonenergy.com",
  "last4": "2947",
  "zip_code": "77001"
}
```
Should become:
```json
"slots": {
  "constraints": {
    "target_order_date": "2025-10-22",
    "email": "patricia.nguyen@horizonenergy.com",
    "last4": "2947",
    "zip_code": "77001"
  },
  "preferences": {
    "item_name": "Office Chair"
  }
}
```
- **Constraints**: Order date, email, payment info are required for identification
- **Preferences**: Item name helps narrow down, but order date + email is sufficient

---

## Success Criteria Schema

### Structure

The `task.success_criteria` object has three fields: `target_selector`, `action`, and `notes`.

```json
{
  "task": {
    "success_criteria": {
      "target_selector": {
        "field1": "value1",
        "field2": "value2"
      },
      "action": "tool_name",
      "notes": "Human-readable description of what success looks like, including any nuanced conditions."
    }
  }
}
```

### Field Descriptions

**`target_selector`** (object, required):
- **Purpose**: Identifies which entity/entities the assistant should operate on
- **Format**: Key-value pairs that match fields in the `tool_agent.context.seed` data or task slots
- **Usage**: The success judge uses this to verify the assistant worked with the correct data
- **Examples**:
  - `{"cuisine": "Italian", "location": "San Francisco"}` → matches restaurants in seed data
  - `{"placed_at": "2025-10-22"}` → matches orders from that date
  - `{"other_attendee_email": "sarah.chen@uoregon.edu"}` → matches meetings with that attendee

**`action`** (string, required):
- **Purpose**: Specifies which tool call must occur for success
- **Format**: Exact tool name from the domain's `tools.json` (e.g., `"make_reservation"`, `"create_return"`, `"create_recurring_meeting"`)
- **Usage**: The success judge checks that this tool was called (and ideally succeeded)
- **Note**: Use the exact tool name as defined in the toolset, not a description

**`notes`** (string, required):
- **Purpose**: Provides human-readable context for the success judge LLM
- **Format**: Plain text describing:
  - What "success" means in this scenario
  - Any nuanced conditions (e.g., "user must accept/confirm", "time must be >= 19:00", "must use pickup method")
  - Edge cases or trade-offs that are acceptable
- **Usage**: Helps the judge understand context that isn't captured in structured fields
- **Best practices**:
  - Be specific about constraints that must be satisfied
  - Mention if user acceptance/confirmation is required
  - Note acceptable trade-offs (e.g., "preference can be relaxed if user agrees")

### Writing Good Success Criteria

**1. Target Selector Should Match Seed Data Structure**

The `target_selector` keys should correspond to fields in `tool_agent.context.seed` or `task.slots.constraints`. This allows the judge to verify the assistant found the right entity.

**Good**:
```json
"target_selector": {
  "cuisine": "Italian",
  "location": "San Francisco"
}
```
Matches seed data: `{"restaurants": [{"cuisine": "Italian", "address": "...San Francisco..."}]}`

**Bad**:
```json
"target_selector": {
  "restaurant_name": "Bella Vista"
}
```
Too specific; the assistant might choose a different Italian restaurant, which should still be valid.

**2. Action Should Be the Primary Tool Call**

Choose the tool that represents the **core action** of the task, not intermediate steps.

**Good**:
- `"action": "make_reservation"` for booking tasks
- `"action": "create_return"` for return tasks
- `"action": "create_recurring_meeting"` for recurring meeting setup

**Bad**:
- `"action": "search_restaurants"` → this is a step, not the goal
- `"action": "check_availability"` → this is preparation, not completion

**3. Notes Should Be Comprehensive but Concise**

Include:
- What the tool call should accomplish
- Which constraints must be satisfied
- Whether user acceptance is required
- Acceptable trade-offs

**Example** (Restaurant):
```json
"notes": "Success if the assistant makes a reservation via make_reservation at one of the seeded Italian restaurants in San Francisco for 4 people on 'this Friday' at or after 19:00 local time, and the user accepts or confirms the booking."
```

**Example** (Calendar):
```json
"notes": "Success if the assistant creates a biweekly recurring one-on-one meeting series with Sara on Wednesdays using create_recurring_meeting (or an equivalent recurring-meeting tool), with 45-minute duration at a Wednesday afternoon time that works for both attendees, and the user accepts or confirms the plan."
```

### Examples by Domain

**Restaurant Booking** (`rb_002__persona_003.json`):
```json
"success_criteria": {
  "target_selector": {
    "cuisine": "Italian",
    "location": "San Francisco"
  },
  "action": "make_reservation",
  "notes": "Success if the assistant makes a reservation via make_reservation at one of the seeded Italian restaurants in San Francisco for 4 people on 'this Friday' at or after 19:00 local time, and the user accepts or confirms the booking."
}
```

**Calendar Recurring Meeting** (`ca_ro_002__persona_002.json`):
```json
"success_criteria": {
  "target_selector": {
    "other_attendee_email": "sarah.chen@uoregon.edu",
    "frequency": "biweekly",
    "preferred_day": "Wednesday"
  },
  "action": "create_recurring_meeting",
  "notes": "Success if the assistant creates a biweekly recurring one-on-one meeting series with Sara on Wednesdays using create_recurring_meeting (or an equivalent recurring-meeting tool), with 45-minute duration at a Wednesday afternoon time that works for both attendees, and the user accepts or confirms the plan."
}
```

**Online Shopping Return** (`os_ro_003__persona_031.json`):
```json
"success_criteria": {
  "target_selector": {
    "placed_at": "2025-10-22"
  },
  "action": "create_return",
  "notes": "Success if the assistant created a return (RMA) using pickup method for the order placed on 2025-10-22."
}
```

---

## Migration Guide

### Step 1: Analyze Existing Slots

For each field in the current flat `slots` object, ask:
- **Is this required for task success?** → Move to `constraints`
- **Can this be relaxed if needed?** → Move to `preferences`

### Step 2: Restructure Slots

**Before**:
```json
"slots": {
  "date": "this Friday",
  "party_size": 4,
  "cuisine": "Italian",
  "location": "San Francisco"
}
```

**After**:
```json
"slots": {
  "constraints": {
    "date": "this Friday",
    "party_size": 4,
    "location": "San Francisco"
  },
  "preferences": {
    "cuisine": "Italian"
  }
}
```

### Step 3: Add Success Criteria

If `success_criteria` doesn't exist, create it:

1. **Identify the target entity** from seed data or slots
2. **Determine the required tool call** from the domain's tools.json
3. **Write comprehensive notes** describing success conditions

**Example Migration** (Calendar Reschedule):

**Before**:
```json
"task": {
  "slots": {
    "meeting_title": "Research Sync",
    "original_date": "2025-11-11",
    "new_preferred_date": "2025-11-12"
  },
  "objective": "Reschedule the research sync meeting"
}
```

**After**:
```json
"task": {
  "slots": {
    "constraints": {
      "meeting_title": "Research Sync",
      "original_date": "2025-11-11",
      "new_preferred_date": "2025-11-12"
    }
  },
  "success_criteria": {
    "target_selector": {
      "meeting_title": "Research Sync",
      "original_date": "2025-11-11"
    },
    "action": "update_meeting",
    "notes": "Success if the assistant reschedules the Research Sync meeting from 2025-11-11 to 2025-11-12 using update_meeting, maintaining the same time (or equivalent local time), and the user accepts or confirms the change."
  },
  "objective": "Reschedule the research sync meeting"
}
```

---

## Domain-Specific Patterns

### Calendar Assistant

**Common Constraints**:
- `attendee_email` / `other_attendee_email` (required for identification)
- `frequency` (for recurring meetings)
- `duration_minutes` (required for scheduling)
- `original_date` / `new_preferred_date` (for rescheduling)

**Common Preferences**:
- `time_of_day` (morning/afternoon/evening)
- `preferred_day` (can often be adjusted if conflicts exist)

**Common Actions**:
- `create_meeting` (one-time)
- `create_recurring_meeting` (recurring series)
- `update_meeting` (reschedule/modify)
- `cancel_meeting` (cancel)

**Success Criteria Notes Patterns**:
- "Success if the assistant [action] with [attendee] on [date/time] and the user accepts or confirms."
- Include time zone considerations: "same time (or equivalent local time)"

### Restaurant Booking

**Common Constraints**:
- `date` (required)
- `party_size` (required)
- `location` (required)
- `time_window` (required, e.g., ">=19:00")

**Common Preferences**:
- `cuisine` (can be relaxed)
- `price_range` (can be adjusted)

**Common Actions**:
- `make_reservation` (primary action)
- `cancel_reservation` (for cancellation scenarios)

**Success Criteria Notes Patterns**:
- "Success if the assistant makes a reservation via make_reservation at [matching restaurants] for [party_size] on [date] at or after [time], and the user accepts or confirms the booking."

### Online Shopping

**Common Constraints**:
- `target_order_date` / `placed_at` (required for identification)
- `email` (required for account lookup)
- `last4` / `zip_code` (required for verification)

**Common Preferences**:
- `item_name` (helps narrow down, but date + email is sufficient)

**Common Actions**:
- `create_return` (for returns)
- `cancel_order` (for cancellations)
- `track_order` (for tracking)

**Success Criteria Notes Patterns**:
- "Success if the assistant created a return (RMA) using [method] for the order placed on [date]."
- Include method preferences if specified in injected behaviors

### Travel

**Common Constraints**:
- `departure_date` / `return_date` (required)
- `origin` / `destination` (required)
- `passenger_count` (required)

**Common Preferences**:
- `preferred_time` (can be adjusted)
- `seat_class` (can be upgraded/downgraded)
- `airline` (can be flexible)

**Common Actions**:
- `book_flight` (for flight booking)
- `book_hotel` (for hotel booking)
- `change_flight` (for modifications)

---

## Common Pitfalls and Best Practices

### Pitfall 1: Putting Everything in Constraints

**Bad**:
```json
"constraints": {
  "cuisine": "Italian",
  "price_range": "$$",
  "rating": ">=4.0"
}
```

**Good**:
```json
"constraints": {
  "date": "this Friday",
  "party_size": 4
},
"preferences": {
  "cuisine": "Italian",
  "price_range": "$$"
}
```

**Why**: If no Italian $$ restaurants exist, the task should still be completable with alternatives.

### Pitfall 2: Vague Target Selector

**Bad**:
```json
"target_selector": {
  "restaurant": "any"
}
```

**Good**:
```json
"target_selector": {
  "cuisine": "Italian",
  "location": "San Francisco"
}
```

**Why**: The selector should match fields that exist in seed data or slots, allowing verification.

### Pitfall 3: Missing User Acceptance in Notes

**Bad**:
```json
"notes": "Success if the assistant makes a reservation."
```

**Good**:
```json
"notes": "Success if the assistant makes a reservation via make_reservation and the user accepts or confirms the booking."
```

**Why**: The user agent must acknowledge completion for the task to be truly done.

### Pitfall 4: Wrong Action Tool

**Bad**:
```json
"action": "search_restaurants"
```

**Good**:
```json
"action": "make_reservation"
```

**Why**: The action should be the **completion** tool, not an intermediate step.

### Best Practice: Align with Injected Behaviors

If `user_agent.injected_behaviors` mentions preferences (e.g., "The user prefers pickup service"), ensure those preferences are reflected in `slots.preferences` and mentioned in `success_criteria.notes`.

---

## Validation Checklist

When updating a scenario file, verify:

- [ ] `task.slots` has both `constraints` and `preferences` keys (even if one is empty `{}`)
- [ ] All required/non-negotiable fields are in `constraints`
- [ ] All flexible/negotiable fields are in `preferences`
- [ ] `task.success_criteria` exists and has all three fields: `target_selector`, `action`, `notes`
- [ ] `target_selector` keys match fields in seed data or slots
- [ ] `action` is a valid tool name from the domain's `tools.json`
- [ ] `notes` mentions user acceptance/confirmation if required
- [ ] `notes` specifies which constraints must be satisfied
- [ ] JSON is valid (no syntax errors)

---

## Summary

- **Slots**: Split into `constraints` (must-have) and `preferences` (nice-to-have)
- **Success Criteria**: Always include `target_selector`, `action`, and `notes`
- **Target Selector**: Match seed data structure for verification
- **Action**: Use the completion tool, not intermediate steps
- **Notes**: Be specific about success conditions and user acceptance

This schema enables more precise success evaluation and clearer guidance for both the assistant and the evaluation judge.

