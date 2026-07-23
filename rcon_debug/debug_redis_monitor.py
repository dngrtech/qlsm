import os
import redis
import time
from datetime import datetime

def monitor():
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/1')
    redis_password = os.environ.get('REDIS_PASSWORD')
    
    print(f"Connecting to Redis at {redis_url}...")
    r = redis.from_url(redis_url, decode_responses=True, password=redis_password)
    pubsub = r.pubsub()
    
    # Subscribe to all RCON related channels. Channels are prefixed by
    # REDIS_PREFIX (default 'rcon'), matching ui/rcon_transport.py — dev
    # environments use e.g. 'rcon-dev-1', so a hardcoded 'rcon:' misses them.
    prefix = os.environ.get('REDIS_PREFIX', 'rcon')
    patterns = [f'{prefix}:cmd:*', f'{prefix}:response:*', f'{prefix}:status:*', f'{prefix}:stats:*']
    pubsub.psubscribe(*patterns)
    
    print(f"Subscribed to patterns: {', '.join(patterns)}")
    print("Waiting for messages... (Ctrl+C to stop)")
    
    for message in pubsub.listen():
        if message['type'] == 'pmessage':
            channel = message['channel']
            data = message['data']
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            print(f"[{timestamp}] {channel}: {data}")

if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        print("\nStopping monitor...")
    except Exception as e:
        print(f"Error: {e}")
