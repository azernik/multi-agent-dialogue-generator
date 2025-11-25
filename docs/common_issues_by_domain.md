# Common Issues by Domain/Use Case

This document tracks recurring failure patterns organized by domain and use case, based on analysis of orchestration runs.

**See also:** [Failure Modes Guide](failure_modes_guide.md) for detailed explanations of configuration balance and failure patterns.

## Common Patterns Across Domains

### User Agent References Missing Entities

**Pattern:** User agent mentions specific entities (cards, transactions, orders) that don't exist in seed data, causing assistant to either miss required tool calls or fabricate data.

**Appears in:**
- Banking: Card references, transaction amounts/dates
- Online shopping: Order IDs, transaction details
- Travel: Flight numbers, booking references

**See specific examples below by use case.**

## Banking

### check_account_balance

**Quick reference:**
- `ba_001__persona_005`: Assistant didn't call get_account_balance, fabricated balance instead (faithfulness + success failure)
- `ba_003__persona_032`: Assistant flipped sign of negative balance (-1324.58 to +$1,324.58) (faithfulness failure)
- `ba_008__persona_037`: User agent acted like assistant (role confusion)

---

### dispute_charge

**Quick reference:**
- `ba_001__persona_010`: Seed data missing second transaction user claims exists (user says two $249.99 charges, seed has only one) → assistant provides phone support script instead of calling submit_dispute

---

### report_card_lost_or_stolen

**Quick reference:**
- `ba_rc_002__persona_041`: Seed data missing transaction user reports (user says $84.19 at 9:37 pm, seed has $42.18 and $7.50 with no time)
- `ba_rc_003__persona_042`: Card reference mismatch (user says cashback card ending 4418, seed has Business Card ending 2468)

**Issue: Card reference mismatch between user agent and seed data**

**Description:** The user agent references a credit card (e.g., "cashback card ending in 4418") that doesn't exist in the seed data. The seed data contains a different card (e.g., "Business Card ending in 2468"). The assistant correctly identifies the mismatch and guides the user to contact support instead of executing the required tool action, resulting in a success failure.

**Examples:**
- `ba_rc_003__persona_042`: User references "cashback credit card ending in 4418" but seed data only has "Business Card ending in 2468"
- Similar pattern likely exists in other scenarios where card nicknames or last-4 digits don't match

**Root cause:** Configuration mismatch - the user agent's card reference doesn't align with what's available in `tool_agent.context.seed.accounts`.

**Fix:** Ensure that:
1. The card referenced by the user agent (nickname, last-4 digits, or account_type) matches a card that exists in seed data, OR
2. The user agent is configured to reference the card that actually exists in seed data

**Related failure modes:**
- Success failures (missing required tool call)
- The assistant correctly avoids acting on wrong card but fails to execute required action

---

## Calendar Assistant

### outdoor_event

**Quick reference:**
- `ca_oe_001__persona_005`: Assistant planned trip details and provided schedules but never called create_meeting (success failure)
- `ca_oe_002__persona_006`: Syntax failure (structure_invalid_block_format) - cascaded from planning without execution
- `ca_oe_003__persona_002`: User provided email and confirmed date/time, but assistant said "You're all set" without calling create_meeting (success failure)
- `ca_oe_004__persona_004`: Assistant checked weather and compared dates but only provided planning help, never called create_meeting (success failure)
- `ca_oe_005__persona_001`: Impossible scenario (bad weather) - syntax failure suggests similar planning-without-execution pattern

**Issue: Missing required tool parameters (attendees) causes assistant to avoid create_meeting call**

**Description:** The assistant treats "schedule an outdoor event" as a planning/consultation task rather than executing a calendar event creation. Success criteria require `create_meeting` to be called, but the tool requires an `attendees` array (emails) that is not provided in slots or consistently provided by the user agent. The assistant avoids the tool call due to missing required parameters and instead provides helpful planning information, resulting in success failures.

**Examples:**
- `ca_oe_001__persona_005`: Assistant provided detailed trip schedules and permission slips but never created calendar event
- `ca_oe_003__persona_002`: User explicitly provided email (`maya.chen@uoregon.edu`) and confirmed details, but assistant still didn't call create_meeting
- `ca_oe_004__persona_004`: Assistant checked weather, compared dates, provided backup plans, but never executed create_meeting

**Root cause:** Configuration mismatch - `create_meeting` tool requires `attendees` array (required parameter), but:
1. Slots don't include attendee emails
2. User agent doesn't consistently provide attendee emails in conversation
3. Assistant interprets missing required parameters as a signal to avoid the tool call and provide planning help instead

**Fix:** 
1. Add `attendees` to slots (e.g., `attendees: ["user@example.com"]` for personal events), OR
2. Make `attendees` optional in tool definition (default to user's email if not provided), OR
3. Update user agent instructions to explicitly provide attendee email when confirming event details, OR
4. Clarify success criteria to explicitly require `create_meeting` execution (not just planning)

**Related failure modes:**
- Missing Required Data for Tool Calls (failure_modes_guide.md #3)
- Success Criteria Too Demanding or Out of Scope (failure_modes_guide.md #2) - criteria become unachievable if required parameters aren't available

---

### recurring_one_on_one

**Quick reference:**
- `ca_ro_002__persona_002`: Assistant claimed meeting was created but never called create_recurring_meeting (syntax failure, hallucination)
- `ca_ro_003__persona_005`: Assistant described meeting details but never called create_recurring_meeting (success failure)
- `ca_ro_004__persona_006`: Assistant told user to create the meeting themselves, never called create_recurring_meeting (success failure)
- `ca_ro_005__persona_007`: Impossible scenario - assistant called create_recurring_meeting despite conflicts (success failure)

**Issue: Assistant fails to execute create_recurring_meeting tool call, occasionally hallucinates having done so**

**Description:** The assistant fails to execute the final `create_recurring_meeting` tool call despite having all required information. In some cases, the assistant's reasoning block claims to have called the tool or received tool results, but no tool call appears in the conversation. In other cases, the assistant explicitly avoids the tool call by telling the user to create the meeting themselves. This results in success failures and occasional faithfulness failures (hallucination).

**Examples:**
- `ca_ro_002__persona_002`: Reasoning block says "I created the recurring meeting" but no tool call occurred; assistant provided meeting details as if it had been created
- `ca_ro_003__persona_005`: Reasoning block says "Tool returned suggested recurring slots" but no tool call occurred; assistant described meeting details without creating it
- `ca_ro_004__persona_006`: Assistant explicitly told user "You can now create a recurring calendar event with those details" instead of calling the tool
- `ca_ro_005__persona_007`: Assistant called create_recurring_meeting successfully but ignored conflicts (impossible scenario handling issue)

**Root cause:** The assistant is not executing the required tool call despite having sufficient information. The reasoning block sometimes describes tool calls that don't occur, indicating a disconnect between reasoning and action execution.

**Fix:** Improve the system prompt to:
1. Explicitly require tool execution for task completion (not just planning/description)
2. Prevent reasoning block from describing tool calls unless actually executing them in the same turn
3. Ensure reasoning about tool calls aligns with the action block output

**Related failure modes:**
- Success failures (missing required tool call)
- Faithfulness failures (hallucinating tool calls/results in reasoning block)

---

### reschedule_meeting

**Quick reference:**
- `ca_rm_001__persona_004`: Configuration mismatch - user references different attendees/time/location than seed data → assistant hallucinated completion without calling update_meeting
- `ca_rm_002__persona_002`: Configuration mismatch - user says meeting with "Sara" (sara.lopez) but seed has "Sarah" (sarah.chen) → assistant found wrong meeting, then hallucinated completion
- `ca_rm_003__persona_005`: Configuration mismatch - user references different attendees than seed data → assistant never called find_meeting, just hallucinated completion

**Issue: Configuration mismatch causes assistant to hallucinate rescheduling completion**

**Description:** The user agent references meeting details (attendees, time, location) that don't match what exists in seed data. The assistant either finds the wrong meeting or can't find a matching meeting. When the user corrects the assistant, the assistant still can't locate the correct meeting. Instead of continuing to search or asking for clarification, the assistant hallucinates that it has successfully rescheduled the meeting, claiming to have called `update_meeting` when no such tool call occurred. This results in success failures and faithfulness failures (hallucination).

**Examples:**
- `ca_rm_001__persona_004`: User references meeting with ana.luque@ucm.es and javier.ortega@ucm.es at 16:00-18:00 CET in "Aula Magna", but seed data has maria.gonzalez@ucm.es and carlos.mendez@ucm.es at 14:00-15:00 UTC in "Conference Room A". Assistant found EVT-010, user said it's wrong, assistant searched again but couldn't find match, then claimed completion without calling update_meeting
- `ca_rm_002__persona_002`: User says meeting is with "Sara" (sara.lopez@uoregon.edu), 60 minutes, at 2pm Pacific, but seed data has "Sarah" (sarah.chen@uoregon.edu), 30 minutes, at 14:00 UTC. Assistant found wrong meeting, user corrected, assistant searched again but still found wrong meeting, then reasoning block claimed "I used update_meeting" but no tool call exists
- `ca_rm_003__persona_005`: User references meeting with alex.hernandez@mpls.k12.mn.us and priya.shah@mpls.k12.mn.us, but seed data has lisa.park@mpls.k12.mn.us and jordan.miles@mpls.k12.mn.us. Assistant never called find_meeting at all, just claimed to have moved the meeting

**Root cause:** Configuration mismatch - the user agent's meeting references (attendees, time, location) don't align with what's available in `tool_agent.context.seed.existing_meeting`. When the assistant can't find a matching meeting, it hallucinates completion rather than continuing to search or properly handling the mismatch.

**Fix:** Ensure that:
1. The meeting details referenced by the user agent (attendees, time, location) match what exists in seed data, OR
2. The user agent is configured to reference the meeting that actually exists in seed data, OR
3. If multiple meetings are possible, seed data should include the meeting that matches user agent references

**Related failure modes:**
- Success failures (missing required tool call - update_meeting)
- Faithfulness failures (hallucinating tool calls/results in reasoning block)
- Configuration mismatches (user agent references ≠ seed data)

---

## Online Shopping

### cancel_order

**Quick reference:**
- `os_co_005__persona_052`: Configuration mismatch - success criteria requires cancel_order but seed data shows item already shipped and not cancelable (success failure)
- `os_co_006__persona_053`: Syntax failure - empty say action, possibly caused by plan mismatch or missing prompt guidance

**Issue: Configuration mismatch - success criteria requires cancel_order on non-cancelable item**

**Description:** Success criteria requires `cancel_order` action, but seed data shows the target item is already shipped with `cancelable: false`. The assistant correctly identifies the item cannot be canceled and offers a return instead, but this violates the success criteria.

**Examples:**
- `os_co_005__persona_052`: Phone case is shipped (`status: "shipped"`, `cancelable: false`) but success criteria requires `cancel_order`

**Root cause:** Configuration mismatch - success criteria requires an action that is impossible given seed data state.

**Fix:** Align seed data with success criteria:
1. Change item status from "shipped" to "pending" and `cancelable: false` to `cancelable: true`, OR
2. Remove shipment entry for the item, OR
3. Update success criteria to require `create_return` instead of `cancel_order` if item is already shipped

**Issue: Syntax failure - empty say action**

**Description:** Assistant produces empty `<action type="say">` with no content, violating syntax rules (`structure_missing_block`, `turn_structure_invalid_say`). This can occur when the assistant's plan includes steps that conflict with available data (e.g., plan says "estimate refund" but refund info already exists in order details).

**Examples:**
- `os_co_006__persona_053`: After getting order details, assistant produced empty say action instead of proceeding with cancellation

**Root cause:** 
1. Plan mismatch - assistant's plan includes unnecessary steps that conflict with available data
2. Missing prompt guidance - system prompt doesn't explicitly forbid empty say actions (though syntax checker enforces it)

**Fix:**
1. Update system prompt to explicitly state that say actions must contain actual text (not empty or only whitespace)
2. Review scenarios where assistant plans include steps that may conflict with available data

**Related failure modes:**
- Syntax failures (empty say actions)
- Configuration mismatches (plan vs. data availability)


---
