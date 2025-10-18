import argparse
import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple, Dict, List
from dotenv import load_dotenv

from core import LLMClient
from agents import SystemAgent, UserAgent, ToolAgent
from scenario import ExampleScenario, load_system_prompts
from runner import ConversationRunner, ConversationResult

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Run multi-agent conversation simulation')
    parser.add_argument('example_path', help='Path to scenario directory (e.g., data/scenarios/restaurant_booking/dine_in/rb_001)')
    parser.add_argument('--model', default='gpt-4o-mini', help='LLM model to use')
    parser.add_argument('--max-turns', type=int, default=20, help='Maximum conversation turns')
    parser.add_argument('--api-key', help='OpenAI API key (default: OPENAI_API_KEY env var)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose console output')
    parser.add_argument('--system-prompts-dir', help='Path to system prompts directory (default: prompts)')
    parser.add_argument('--system-agent-prompt', help='Path to system agent prompt file')
    parser.add_argument('--user-agent-prompt', help='Path to user agent prompt file') 
    parser.add_argument('--tool-agent-prompt', help='Path to tool agent prompt file')
    parser.add_argument('--prompt-version', default='v1', help='Version of prompts to use (default: v1)')
    return parser.parse_args()

def setup_logging(example_path: str, verbose: bool = False) -> Tuple[str, str, str]:
    """Set up logging and return output, log, and agent flow file paths"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    example_dir = Path(example_path)
    
    # Create new directory for this simulation run
    run_dir = example_dir / "runs" / f"simulate_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = run_dir / "simulate.log"
    output_file = run_dir / "simulate.out"
    agent_flow_file = run_dir / "agent_flow.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stderr) if verbose else logging.NullHandler()
        ]
    )
    
    return str(output_file), str(log_file), str(agent_flow_file)


def _resolve_prompts_dir(example_path: str) -> Path:
    """Resolve the prompts directory robustly when a custom dir is not provided."""
    # Prefer repo-root/prompts if present; fallback to legacy data/system_prompts
    cwd = Path(__file__).resolve().parent.parent  # src/ -> repo root
    candidate_new = cwd / 'prompts'
    if candidate_new.exists():
        return candidate_new
    candidate_old = cwd / 'data' / 'system_prompts'
    if candidate_old.exists():
        return candidate_old
    # Else, walk up from the example path to find siblings
    cur = Path(example_path).resolve()
    for parent in [cur] + list(cur.parents):
        sibling_new = parent.parent / 'prompts'
        if sibling_new.exists():
            return sibling_new
        sibling_old = parent.parent / 'data' / 'system_prompts'
        if sibling_old.exists():
            return sibling_old
    # Fallback to new default
    return Path('prompts')


def load_scenario_and_prompts(example_path: str, args: argparse.Namespace) -> Tuple[ExampleScenario, Dict[str, str]]:
    """Load scenario and system prompts"""
    try:
        # Load scenario from example_path
        scenario = ExampleScenario.load(example_path)
        
        # Load system prompts
        if args.system_agent_prompt or args.user_agent_prompt or args.tool_agent_prompt:
            # Load individual prompt files if specified
            system_prompts = {}
            custom_prompts = {
                'system_agent': args.system_agent_prompt,
                'user_agent': args.user_agent_prompt,
                'tool_agent': args.tool_agent_prompt
            }
            
            for agent_type, custom_path in custom_prompts.items():
                if custom_path:
                    # Use custom path
                    with open(custom_path, 'r') as f:
                        system_prompts[agent_type] = f.read().strip()
                else:
                    # Fall back to default location
                    prompts_dir = Path(args.system_prompts_dir) if args.system_prompts_dir else _resolve_prompts_dir(example_path)
                    prompt_file = prompts_dir / agent_type / f"{args.prompt_version}.txt"
                    with open(prompt_file, 'r') as f:
                        system_prompts[agent_type] = f.read().strip()
        else:
            # Use directory-based loading
            prompts_dir = Path(args.system_prompts_dir) if args.system_prompts_dir else _resolve_prompts_dir(example_path)
            system_prompts = load_system_prompts(str(prompts_dir), args.prompt_version)
        
        return scenario, system_prompts
        
    except FileNotFoundError as e:
        print(f"Error: Could not find required files: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading scenario: {e}", file=sys.stderr)
        sys.exit(1)

def create_agents(scenario: ExampleScenario, 
                 system_prompts: Dict[str, str], 
                 llm_client: LLMClient,
                 flow_logger=None) -> Tuple[SystemAgent, UserAgent, ToolAgent]:
    """Create the three agents with appropriate configurations"""
    try:
        # Create SystemAgent with raw tools JSON
        system_agent = SystemAgent(
            system_prompts['system_agent'],
            llm_client,
            scenario.tools
        )
        system_agent.flow_logger = flow_logger
        
        # Create UserAgent with new user_agent JSON
        user_agent = UserAgent(
            system_prompts['user_agent'],
            llm_client,
            scenario.user_agent
        )
        user_agent.flow_logger = flow_logger
        
        # Create ToolAgent with raw tools JSON
        tool_agent = ToolAgent(
            system_prompts['tool_agent'],
            llm_client,
            scenario.tools
        )
        tool_agent.flow_logger = flow_logger
        
        return system_agent, user_agent, tool_agent
        
    except Exception as e:
        print(f"Error creating agents: {e}", file=sys.stderr)
        sys.exit(1)

def format_output(result: ConversationResult, verbose: bool = False) -> Dict:
    """Format conversation result for output"""
    output_data = {
        'scenario': result.metadata.get('scenario', 'unknown'),
        'success': result.success,
        'termination_reason': result.termination_reason,
        'total_turns': result.metadata.get('total_turns', 0),
        'system_transcript': [
            {
                'role': msg.role.value,
                'content': msg.content,
                **({'metadata': msg.metadata} if getattr(msg, 'metadata', None) else {})
            }
            for msg in result.system_transcript
        ],
        'user_transcript': [
            {
                'role': msg.role.value,
                'content': msg.content,
                **({'metadata': msg.metadata} if getattr(msg, 'metadata', None) else {})
            }
            for msg in result.user_transcript
        ],
        'tool_transcript': [
            {
                'role': msg.role.value,
                'content': msg.content,
                **({'metadata': msg.metadata} if getattr(msg, 'metadata', None) else {})
            }
            for msg in result.tool_transcript
        ],
        'metadata': result.metadata
    }
    
    if verbose:
        output_data['summary'] = {
            'system_message_count': len(result.system_transcript),
            'user_message_count': len(result.user_transcript),
            'tool_message_count': len(result.tool_transcript),
            'had_tool_calls': result.metadata.get('had_tool_calls', False),
        }
    
    return output_data

def print_verbose_summary(result: ConversationResult):
    """Print human-readable summary if verbose mode"""
    print(f"\n=== Conversation Summary ===", file=sys.stderr)
    print(f"Scenario: {result.metadata.get('scenario', 'unknown')}", file=sys.stderr)
    print(f"Success: {result.success}", file=sys.stderr)
    print(f"Termination: {result.termination_reason}", file=sys.stderr)
    print(f"Total turns: {result.metadata.get('total_turns', 0)}", file=sys.stderr)
    print(f"System messages: {len(result.system_transcript)}", file=sys.stderr)
    print(f"User messages: {len(result.user_transcript)}", file=sys.stderr)
    print(f"Tool messages: {len(result.tool_transcript)}", file=sys.stderr)
    print(f"Had tool calls: {result.metadata.get('had_tool_calls', False)}", file=sys.stderr)
        
    print("=" * 30, file=sys.stderr)

def format_transcript_as_markdown(transcript: List, transcript_name: str, scenario_name: str) -> str:
    """Format a transcript as readable markdown"""
    markdown = f"# {transcript_name}\n\n"
    markdown += f"**Scenario:** {scenario_name}\n\n"
    markdown += f"**Messages:** {len(transcript)}\n\n"
    markdown += "---\n\n"
    
    for i, msg in enumerate(transcript, 1):
        role = msg['role']
        content = msg['content']
        
        # Format role as header
        if role == 'user':
            markdown += f"## 👤 User (Message {i})\n\n"
        elif role == 'assistant':
            markdown += f"## 🤖 Assistant (Message {i})\n\n"
        elif role == 'tool':
            markdown += f"## 🔧 Tool (Message {i})\n\n"
        else:
            markdown += f"## 🔧 {role.title()} (Message {i})\n\n"
        
        # Format content with proper escaping and structure
        if content.strip():
            # Handle multi-line content with proper indentation
            lines = content.split('\n')
            formatted_content = []
            
            for line in lines:
                # Escape XML-like tags so they show up in markdown preview
                escaped_line = line.replace('<think>', '&lt;think&gt;').replace('</think>', '&lt;/think&gt;')
                escaped_line = escaped_line.replace('<plan>', '&lt;plan&gt;').replace('</plan>', '&lt;/plan&gt;')
                escaped_line = escaped_line.replace('<reflect>', '&lt;reflect&gt;').replace('</reflect>', '&lt;/reflect&gt;')
                
                # Escape other markdown special characters in content
                escaped_line = escaped_line.replace('*', '\\*').replace('_', '\\_').replace('#', '\\#')
                formatted_content.append(escaped_line)
            
            markdown += '\n'.join(formatted_content)
            markdown += "\n\n"
        else:
            markdown += "*[Empty message]*\n\n"
        
        # Add separator between messages
        if i < len(transcript):
            markdown += "---\n\n"
    
    return markdown

def write_markdown_transcripts(result: ConversationResult, base_filename: str) -> Dict[str, str]:
    """Write all transcripts as markdown files and return the file paths"""
    base_path = Path(base_filename)
    output_dir = base_path.parent
    
    markdown_files = {}
    
    # Define transcript types and their data
    transcripts = [
        ("System Transcript", result.system_transcript, "system"),
        ("User Transcript", result.user_transcript, "user"), 
        ("Tool Transcript", result.tool_transcript, "tool")
    ]
    
    for transcript_name, transcript_data, file_suffix in transcripts:
        # Convert transcript data to the format expected by format_transcript_as_markdown
        formatted_data = [
            {
                'role': msg.role.value,
                'content': msg.content
            }
            for msg in transcript_data
        ]
        
        # Generate markdown content
        markdown_content = format_transcript_as_markdown(
            formatted_data, 
            transcript_name, 
            result.metadata.get('scenario', 'unknown')
        )
        
        # Create filename with simple name
        markdown_file = output_dir / f"{file_suffix}.md"
        
        # Write markdown file
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        markdown_files[file_suffix] = str(markdown_file)
    
    return markdown_files

def main():
    """Main CLI entry point"""
    try:
        # Load environment variables from .env file
        load_dotenv()
        
        # Parse arguments
        args = parse_arguments()
        
        # Set up logging and file paths
        output_file, log_file, agent_flow_file = setup_logging(args.example_path, args.verbose)
        logger = logging.getLogger(__name__)
        
        logger.info(f"Starting simulation with model: {args.model}")

        # Load scenario and prompts
        scenario, system_prompts = load_scenario_and_prompts(args.example_path, args)
        
        logger.info(f"Loaded scenario: {scenario.name}")
        
        # Initialize LLM client
        api_key = args.api_key or os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("OpenAI API key required")
            print("Error: OpenAI API key required. Set OPENAI_API_KEY environment variable or use --api-key", file=sys.stderr)
            sys.exit(1)
            
        llm_client = LLMClient(model=args.model, api_key=api_key)
        logger.info(f"Initialized LLM client with model: {args.model}")
        
        # Create agents with flow logger
        with open(agent_flow_file, 'w') as flow_logger:
            system_agent, user_agent, tool_agent = create_agents(scenario, system_prompts, llm_client, flow_logger)
            logger.info("Created all three agents")
            
            # Run conversation
            runner = ConversationRunner(scenario, system_agent, user_agent, tool_agent, args.max_turns)
            logger.info("Starting conversation simulation")
            result = runner.run_conversation()
        
        logger.info(f"Conversation completed. Success: {result.success}, Reason: {result.termination_reason}")
        
        # Format output
        output_data = format_output(result, args.verbose)
        
        # Write JSON output to file
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"JSON results saved to: {output_file}")
        
        # Write markdown transcripts
        markdown_files = write_markdown_transcripts(result, output_file)
        logger.info(f"Markdown transcripts saved:")
        for transcript_type, file_path in markdown_files.items():
            logger.info(f"  {transcript_type}: {file_path}")
        
        # Exit with appropriate code
        sys.exit(0 if result.success else 1)
        
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main() 