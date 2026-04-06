
from ui import create_app,db
from ui.models import QLInstance

app = create_app()
with app.app_context():
    instances = db.session.query(QLInstance).all()
    print(f"Found {len(instances)} instances.")
    for inst in instances:
        has_password = bool(inst.zmq_rcon_password)
        print(f"Instance ID: {inst.id}, Name: {inst.name}, RCON Port: {inst.zmq_rcon_port}, Has Password: {has_password}")
        if not has_password:
            print(f"WARNING: Instance {inst.id} missing RCON password!")
