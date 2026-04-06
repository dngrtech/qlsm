"""
Diagnostic script: Capture raw ZMQ frames for the 'status' command.
Shows exactly how the Quake Live server fragments the response.
"""
import asyncio
import zmq
import zmq.asyncio

SERVER_IP = "144.202.93.88"
SERVER_PORT = 28888
PASSWORD = "JGBHYfu&T$%#ES"

async def capture_status_frames():
    ctx = zmq.asyncio.Context()
    sock = ctx.socket(zmq.DEALER)

    sock.plain_username = b"rcon"
    sock.plain_password = PASSWORD.encode('utf-8')
    sock.zap_domain = b"rcon"
    sock.identity = b"debug_diag"
    sock.setsockopt(zmq.LINGER, 0)

    endpoint = f"tcp://{SERVER_IP}:{SERVER_PORT}"
    print(f"Connecting to {endpoint}...")
    sock.connect(endpoint)
    await asyncio.sleep(0.5)

    print("Sending 'register'...")
    await sock.send_string("register")
    await asyncio.sleep(0.3)

    # Drain any initial messages
    while await sock.poll(timeout=500):
        raw = await sock.recv()
        print(f"  [drain] {raw!r}")

    print("\nSending 'status'...")
    await sock.send_string("status")

    print("Capturing frames (3s window)...\n")
    print("=" * 80)

    frame_num = 0
    while await sock.poll(timeout=3000):
        raw = await sock.recv()
        frame_num += 1

        # Show raw bytes
        print(f"Frame {frame_num:3d} | {len(raw):4d} bytes | {raw!r}")

        # Show decoded with visible control chars
        try:
            decoded = raw.decode('utf-8', errors='replace')
            visible = decoded.replace('\n', '\\n').replace('\r', '\\r')
            for c in range(32):
                if c not in (10, 13):  # skip \n \r already handled
                    visible = visible.replace(chr(c), f'<{c:02d}>')
            print(f"          decoded: {visible}")
        except:
            pass
        print()

    print("=" * 80)
    print(f"Total frames captured: {frame_num}")

    sock.close()
    ctx.term()

if __name__ == "__main__":
    asyncio.run(capture_status_frames())
