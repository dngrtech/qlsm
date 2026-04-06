from ui import create_app
from ui import socketio
from dotenv import load_dotenv
import argparse  # Add this import
import os

load_dotenv()
app = create_app()

if __name__ == '__main__':
    # Add argument parsing to read the port from the shell script
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5001)
    args = parser.parse_args()

    print(f"Starting Flask-SocketIO server on port {args.port}...")
    
    # Use args.port here instead of a hardcoded number
    socketio.run(app, host='0.0.0.0', port=args.port, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
