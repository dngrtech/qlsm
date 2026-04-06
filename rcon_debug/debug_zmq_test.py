import asyncio
import zmq
import zmq.asyncio
import argparse
import sys

async def test_rcon(ip, port, password):
    print(f"Testing ZMQ RCON to {ip}:{port} with password '{password}'...")
    
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.DEALER)
    
    # Setup PLAIN auth
    socket.plain_username = b"rcon"
    socket.plain_password = password.encode('utf-8')
    socket.zap_domain = b"rcon"
    
    # Identity
    identity = b"debug_test"
    socket.identity = identity
    
    socket.setsockopt(zmq.LINGER, 0)
    
    endpoint = f"tcp://{ip}:{port}"
    print(f"Connecting to {endpoint}...")
    
    try:
        socket.connect(endpoint)
        
        # Give it a moment to connect
        await asyncio.sleep(0.5)
        
        print("Sending 'register'...")
        await socket.send_string("register")
        
        # Wait a bit
        await asyncio.sleep(0.5)
        
        print("Sending 'status'...")
        await socket.send_string("status")
        
        print("Waiting for response (5s timeout)...")
        
        if await socket.poll(timeout=5000):
            raw = await socket.recv()
            print(f"RECEIVED RESPONSE ({len(raw)} bytes):")
            try:
                print(raw.decode('utf-8', errors='replace'))
            except:
                print(raw)
        else:
            print("TIMED OUT: No response received.")
            print("Possible causes:")
            print("1. Wrong password (ZMQ auth failed silently)")
            print("2. Wrong IP/Port")
            print("3. Firewall blocking")
            print("4. QLDS server not running or ZMQ RCON not enabled")
            
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 debug_zmq_test.py <IP> <PORT> <PASSWORD>")
        sys.exit(1)
        
    asyncio.run(test_rcon(sys.argv[1], sys.argv[2], sys.argv[3]))
