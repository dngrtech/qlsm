import os
from pathlib import Path


def inventory_filename_for_host(host):
    suffix = "_self_host.yml" if host.provider == "self" else "_standalone_host.yml"
    return f"{host.name}{suffix}"


def generate_standalone_inventory(host, inventory_dir="ansible/inventory", ansible_host=None):
    inventory_path = Path(inventory_dir).resolve() / inventory_filename_for_host(host)
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    effective_host = ansible_host if ansible_host is not None else host.ip_address
    inventory_path.write_text(f"""all:
  hosts:
    {host.name}:
      ansible_host: {effective_host}
      ansible_user: {host.ssh_user}
      ansible_ssh_private_key_file: {os.path.abspath(host.ssh_key_path)}
      ansible_port: {host.ssh_port}
      ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
""")
    return str(inventory_path)
