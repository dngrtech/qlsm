#!/usr/bin/env python3
"""
Test RCON connection to a QLDS instance directly (bypasses Redis).

Usage:
    python scripts/test_rcon_connection.py <IP> <PORT> <PASSWORD>
    
Example:
    python scripts/test_rcon_connection.py 144.202.93.88 28888 "JGBHYfu&T$%#ES"
"""

import asyncio
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rcon_service.instance_connection import InstanceConnection

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

log = logging.getLogger(__name__)


def on_message(host_id: int, instance_id: int, message: str):
    """Callback for received messages."""
    print(f"\n>>> RCON MESSAGE <<<")
    print(f"{message}")
    print(f">>> END MESSAGE <<<\n")


def on_status(host_id: int, instance_id: int, status: str):
    """Callback for status changes."""
    print(f"[STATUS] {status}")


async def main():
    if len(sys.argv) < 4:
        print("Usage: python test_rcon_connection.py <IP> <PORT> <PASSWORD>")
        print("Example: python test_rcon_connection.py 144.202.93.88 28888 'password'")
        sys.exit(1)
    
    ip = sys.argv[1]
    port = int(sys.argv[2])
    password = sys.argv[3]
    
    print(f"Testing RCON connection to {ip}:{port}")
    print("=" * 50)
    
    conn = InstanceConnection(
        host_id=0,
        instance_id=0,
        on_message=on_message,
        on_status_change=on_status
    )
    
    # Connect
    success = await conn.connect(ip, port, password)
    if not success:
        print("Failed to connect!")
        return
    
    print("\nConnected! Enter commands (type 'quit' to exit):")
    print("Try: status, serverinfo, players, say Hello World\n")
    
    try:
        while True:
            # Get command from user
            try:
                cmd = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("RCON> ")
                )
            except EOFError:
                break
            
            cmd = cmd.strip()
            if not cmd:
                continue
            
            if cmd.lower() == 'quit':
                break
            
            # Send command
            await conn.send(cmd)
            
            # Wait a bit for response
            await asyncio.sleep(0.5)
    
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        await conn.disconnect()
        print("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
