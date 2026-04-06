"""
Message parser for Quake Live RCON responses.

Handles parsing and formatting of QLDS RCON message formats,
including color code handling.
"""

import re
from typing import Optional


# Quake color codes: ^0 through ^9, ^a-^z
COLOR_CODE_PATTERN = re.compile(r'\^[0-9a-zA-Z]')


def strip_color_codes(text: str) -> str:
    """Remove Quake color codes from text.
    
    Quake uses ^0-^9 and ^a-^z for coloring text.
    
    Args:
        text: Text potentially containing color codes
        
    Returns:
        Text with color codes removed
    """
    return COLOR_CODE_PATTERN.sub('', text)


def parse_rcon_message(raw: bytes) -> str:
    """Parse a Quake Live RCON response message.
    
    QLDS RCON responses can come in several formats:
    - print "Message text"  -> extracts "Message text"
    - broadcast: print "Text" -> "^8Server^7: Text"
    - Raw text passthrough
    
    Args:
        raw: Raw bytes received from ZMQ socket
        
    Returns:
        Parsed message text (UTF-8 decoded)
    """
    try:
        text = raw.decode('utf-8', errors='replace')
    except Exception:
        return str(raw)
    
    # Strip Quake control characters (matches reference Windows app's formatMessage)
    text = text.replace(chr(25), '')   # NAK
    text = text.replace(chr(19), '')   # XOFF/DC3
    text = text.replace('\\n', '')     # Literal \n (two chars: backslash + n)
    
    # Check for print/broadcast prefixes using lstripped version,
    # but DON'T lstrip raw frames — they may be individual spaces or
    # field data that provides column alignment in status output.
    stripped = text.lstrip()
    
    # Handle "print" prefix format: print "content\n"
    if stripped.startswith('print "') and stripped.rstrip().endswith('"'):
        # Extract content between quotes, preserving internal newlines
        end = stripped.rstrip()
        return end[7:-1]
    
    # Handle broadcast format
    if stripped.startswith('broadcast:'):
        content = stripped[10:].strip()
        if content.startswith('print "') and content.endswith('"'):
            return f"^8Server^7: {content[7:-1]}\n"
        return f"^8Server^7: {content}\n"
    
    # Raw frames: return untouched (preserves spacing for status output)
    return text


def format_for_display(message: str, strip_colors: bool = False) -> str:
    """Format an RCON message for display.
    
    Args:
        message: The message text
        strip_colors: If True, remove color codes
        
    Returns:
        Formatted message
    """
    if strip_colors:
        return strip_color_codes(message)
    return message


def parse_status_response(raw: str) -> Optional[dict]:
    """Parse a 'status' command response into structured data.
    
    Args:
        raw: Raw status response text
        
    Returns:
        Dict with server info and player list, or None if parse fails
    """
    lines = raw.strip().split('\n')
    if len(lines) < 2:
        return None
    
    result = {
        'map': None,
        'players': [],
        'raw': raw
    }
    
    # First line often contains map info
    for line in lines:
        line = line.strip()
        if line.startswith('map:'):
            result['map'] = line.split(':', 1)[1].strip()
        elif line.startswith('num ') or line.startswith('--- '):
            # Header lines, skip
            continue
        elif re.match(r'^\s*\d+\s+', line):
            # Player line (starts with player number)
            # Format varies, but typically: num score ping name lastmsg address qport rate
            parts = line.split()
            if len(parts) >= 4:
                result['players'].append({
                    'num': parts[0],
                    'score': parts[1],
                    'ping': parts[2],
                    'name': strip_color_codes(' '.join(parts[3:]))
                })
    
    return result
