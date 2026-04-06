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
    
    # Subscribe to all RCON related channels
    patterns = ['rcon:cmd:*', 'rcon:response:*', 'rcon:status:*', 'rcon:stats:*']
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
