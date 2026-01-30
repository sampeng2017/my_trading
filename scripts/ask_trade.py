#!/usr/bin/env python3
"""
Ask Trade Advisor - Interactive CLI for trade questions.

Usage:
    python scripts/ask_trade.py "Should I sell 100 shares of MSFT at 480?"
    python scripts/ask_trade.py --interactive
"""

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from src.agents.trade_advisor import TradeAdvisor


def load_config():
    """Load configuration from config.yaml"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'config.yaml'
    )
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_api_keys():
    """Get API keys from environment."""
    return {
        'gemini_api_key': os.environ.get('GEMINI_API_KEY')
    }


def print_response(response: dict):
    """Pretty print the advisor response."""
    rec = response.get('recommendation', 'UNKNOWN')
    confidence = response.get('confidence', 0)
    analysis = response.get('analysis', [])
    reasoning = response.get('reasoning', '')
    symbol = response.get('symbol')
    action = response.get('action')
    
    # Color codes
    COLORS = {
        'PROCEED': '\033[92m',      # Green
        'CAUTION': '\033[93m',      # Yellow
        'AVOID': '\033[91m',        # Red
        'ERROR': '\033[91m',        # Red
        'MORE_INFO_NEEDED': '\033[94m',  # Blue
        'RESET': '\033[0m',
        'BOLD': '\033[1m',
        'DIM': '\033[2m'
    }
    
    color = COLORS.get(rec, '')
    reset = COLORS['RESET']
    bold = COLORS['BOLD']
    dim = COLORS['DIM']
    
    # Header
    width = 70
    print()
    print('╔' + '═' * width + '╗')
    print(f'║{bold} Trade Advisor Response{reset}' + ' ' * (width - 23) + '║')
    print('╠' + '═' * width + '╣')
    
    # Recommendation and confidence
    rec_line = f'║ Recommendation: {color}{bold}{rec}{reset}'
    padding = width - len(f' Recommendation: {rec}') + 1
    print(rec_line + ' ' * padding + '║')
    
    conf_pct = f'{confidence * 100:.0f}%' if isinstance(confidence, float) else str(confidence)
    conf_line = f'║ Confidence: {bold}{conf_pct}{reset}'
    padding = width - len(f' Confidence: {conf_pct}') + 1
    print(conf_line + ' ' * padding + '║')
    
    if symbol or action:
        detail = f" Symbol: {symbol or 'N/A'}, Intent: {action or 'N/A'}"
        print(f'║{dim}{detail}{reset}' + ' ' * (width - len(detail)) + '║')
    
    print('╠' + '═' * width + '╣')
    
    # Analysis points
    print(f'║{bold} Analysis:{reset}' + ' ' * (width - 10) + '║')
    for point in analysis:
        # Wrap long lines
        point_str = f' • {point}'
        if len(point_str) > width - 2:
            point_str = point_str[:width - 5] + '...'
        print(f'║{point_str}' + ' ' * (width - len(point_str)) + '║')
    
    print('║' + ' ' * width + '║')
    
    # Reasoning
    print(f'║{bold} Reasoning:{reset}' + ' ' * (width - 11) + '║')
    
    # Word wrap reasoning
    words = reasoning.split()
    line = ' '
    for word in words:
        if len(line) + len(word) + 1 > width - 2:
            print(f'║{line}' + ' ' * (width - len(line)) + '║')
            line = ' ' + word
        else:
            line += ' ' + word if line != ' ' else word
    if line.strip():
        print(f'║{line}' + ' ' * (width - len(line)) + '║')
    
    print('╚' + '═' * width + '╝')
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Ask the Trade Advisor a question about your portfolio.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Should I sell 100 shares of MSFT at 480?"
  %(prog)s "Is it a good time to buy NVDA?"
  %(prog)s "What do you think of my portfolio concentration?"
  %(prog)s --interactive
        """
    )
    parser.add_argument(
        'question', 
        nargs='?', 
        help='Your question about a trade or portfolio'
    )
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Enter interactive mode (REPL)'
    )
    parser.add_argument(
        '--db-path',
        default=None,
        help='Path to database (default: from config)'
    )
    
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    api_keys = get_api_keys()
    
    if not api_keys.get('gemini_api_key'):
        print("Error: GEMINI_API_KEY environment variable not set.")
        print("Please set it: export GEMINI_API_KEY='your-key-here'")
        sys.exit(1)
    
    # Get database path
    db_path = args.db_path or config.get('database', {}).get('path', 'data/trading.db')
    if not os.path.isabs(db_path):
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            db_path
        )
    
    # Initialize advisor
    advisor = TradeAdvisor(
        db_path=db_path,
        gemini_key=api_keys['gemini_api_key'],
        config=config
    )
    
    if args.interactive:
        print("\n🤖 Trade Advisor - Interactive Mode")
        print("Type 'quit' or 'exit' to leave.\n")
        
        while True:
            try:
                question = input("📝 Ask: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
            
            if not question:
                continue
            if question.lower() in ('quit', 'exit', 'q'):
                print("Goodbye!")
                break
            
            print("\n⏳ Analyzing...")
            response = advisor.ask(question)
            print_response(response)
    
    elif args.question:
        print("\n⏳ Analyzing your question...")
        response = advisor.ask(args.question)
        print_response(response)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
