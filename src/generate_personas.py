#!/usr/bin/env python3
"""
Generate personas from PersonaHub JSONL data.
Transforms raw PersonaHub entries into structured persona catalog format.

Usage:
    python src/generate_personas.py --input data/personas/personahub_filtered.jsonl \
                                    --output data/personas/new_personas.json \
                                    --start-id 56 \
                                    --count 10 \
                                    --model gpt-5.1
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Any
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from core import LLMClient


PERSONA_GENERATION_PROMPT = """You are creating a realistic persona for a dialogue simulation system.

Given this PersonaHub description:
{personahub_description}

Create a structured persona with these fields:
1. **name**: A realistic full name appropriate for the persona's background
2. **age**: A specific age (25-65) that fits their occupation/experience
3. **hometown**: Specific city and state/country
4. **occupation**: Their job title
5. **bio**: 2-3 sentence bio capturing their work, interests, and personality (make it personal and specific)
6. **writing_style**: How they communicate (e.g., "casual, lowercase, abbreviations", "formal professional", "friendly conversational")
7. **sample_messages**: Array of 3 casual messages showing their communication style (mix of requests, questions, confirmations)
8. **email**: Realistic email address based on their name/organization
9. **phone**: Phone number in appropriate format for their location

Return ONLY a JSON object with these exact fields. Make the persona feel real, specific, and conversational.

Example output format:
{
  "name": "Alex Rivera",
  "age": 32,
  "hometown": "Portland, OR",
  "occupation": "UX designer",
  "bio": "Alex Rivera designs mobile apps for a Portland startup, focusing on accessibility and intuitive interfaces. They run weekly design critique sessions, mentor junior designers, and speak at local tech meetups about inclusive design practices.",
  "writing_style": "casual friendly, some lowercase, uses em dashes",
  "sample_messages": [
    "hey — can we push tomorrow's standup to 10:30? client call ran over",
    "ordered wireframe stencils for the team, should arrive by friday",
    "love the new prototype! couple accessibility notes i'll drop in figma"
  ],
  "email": "alex.rivera@example.com",
  "phone": "+1-503-555-0142"
}"""


def load_personahub_entries(input_file: Path) -> List[Dict[str, Any]]:
    """Load PersonaHub JSONL file."""
    entries = []
    with open(input_file, 'r') as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def generate_persona_from_personahub(
    personahub_entry: Dict[str, Any],
    persona_id: str,
    llm_client: LLMClient
) -> Dict[str, Any]:
    """Use LLM to transform PersonaHub entry into structured persona."""
    
    # Extract the persona description from PersonaHub format
    persona_description = personahub_entry.get('persona', '')
    
    # Build prompt
    prompt = PERSONA_GENERATION_PROMPT.format(
        personahub_description=persona_description
    )
    
    # Call LLM
    messages = [
        {"role": "system", "content": "You are a persona generation assistant. Output only valid JSON."},
        {"role": "user", "content": prompt}
    ]
    
    response = llm_client.chat_completion(messages, temperature=0.8, max_tokens=800)
    response_text = response.choices[0].message.content.strip()
    
    # Parse JSON response
    # Remove markdown code blocks if present
    if response_text.startswith('```'):
        lines = response_text.split('\n')
        response_text = '\n'.join(lines[1:-1])
        if response_text.startswith('json'):
            response_text = response_text[4:].strip()
    
    persona_data = json.loads(response_text)
    
    # Add required fields
    persona_data['id'] = persona_id
    persona_data['use_cases'] = []  # To be filled in later
    
    return persona_data


def main():
    parser = argparse.ArgumentParser(
        description="Generate personas from PersonaHub data using LLM"
    )
    parser.add_argument(
        '--input',
        required=True,
        help='Path to PersonaHub JSONL file'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output JSON file for generated personas'
    )
    parser.add_argument(
        '--start-id',
        type=int,
        default=56,
        help='Starting persona ID number (default: 56)'
    )
    parser.add_argument(
        '--count',
        type=int,
        default=10,
        help='Number of personas to generate (default: 10)'
    )
    parser.add_argument(
        '--model',
        default='gpt-5.1',
        help='LLM model to use (default: gpt-5.1)'
    )
    parser.add_argument(
        '--api-key',
        help='OpenAI API key (default: OPENAI_API_KEY env var)'
    )
    parser.add_argument(
        '--append-to-catalog',
        action='store_true',
        help='Append to existing catalog.json instead of creating new file'
    )
    
    args = parser.parse_args()
    
    # Initialize LLM client
    api_key = args.api_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OpenAI API key required. Set OPENAI_API_KEY or use --api-key")
        return 1
    
    llm_client = LLMClient(model=args.model, api_key=api_key)
    
    # Load PersonaHub entries
    print(f"Loading PersonaHub entries from {args.input}...")
    personahub_entries = load_personahub_entries(Path(args.input))
    print(f"Found {len(personahub_entries)} PersonaHub entries")
    
    if args.count > len(personahub_entries):
        print(f"Warning: Requested {args.count} personas but only {len(personahub_entries)} available")
        args.count = len(personahub_entries)
    
    # Generate personas
    generated_personas = []
    for i in range(args.count):
        persona_id = f"persona_{args.start_id + i:03d}"
        print(f"\nGenerating {persona_id}...", end=' ', flush=True)
        
        try:
            persona = generate_persona_from_personahub(
                personahub_entries[i],
                persona_id,
                llm_client
            )
            generated_personas.append(persona)
            print(f"✓ {persona['name']}")
        except Exception as e:
            print(f"✗ Error: {e}")
            continue
    
    # Handle output
    if args.append_to_catalog:
        # Load existing catalog
        catalog_path = Path('data/personas/catalog.json')
        if catalog_path.exists():
            with open(catalog_path, 'r') as f:
                catalog = json.load(f)
            catalog['personas'].extend(generated_personas)
            output_path = catalog_path
            print(f"\n✓ Appended {len(generated_personas)} personas to {output_path}")
        else:
            print("Error: catalog.json not found, cannot append")
            return 1
    else:
        # Create new file
        catalog = {"personas": generated_personas}
        output_path = Path(args.output)
        print(f"\n✓ Created new file with {len(generated_personas)} personas")
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    print(f"Saved to: {output_path}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

