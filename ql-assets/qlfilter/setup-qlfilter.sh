#!/bin/bash
# Determine the default network interface
net_interface=$(ip route | awk '/default/ {print $5}')
if [ -z "$net_interface" ]; then
    echo "Error: Could not determine default network interface."
    exit 1
fi
echo "Using network interface: $net_interface"

basedir="/opt/qlfilter"
# qlfilter.c will be placed directly in basedir by Ansible
qlfilter_c_path="$basedir/qlfilter.c" 
qlfilter_o_path="$basedir/qlfilter.o"

check_basedir(){
    if [ ! -d "$basedir" ]; then
        echo "Creating directory $basedir..."
        sudo mkdir -p "$basedir"
        # Permissions will be managed by Ansible, or script runs as root
    fi
}

install_depend() {
    depends=("clang" "gcc-multilib" "ethtool")
    missing_depends=()
    for dep in "${depends[@]}"; do
        if ! dpkg -s "$dep" >/dev/null 2>&1; then
            missing_depends+=("$dep")
        fi
    done

    if [[ ${#missing_depends[@]} -gt 0 ]]; then
        echo "Missing dependencies: ${missing_depends[*]}"
        echo "Preparing for installation..."
        sudo apt update
        for dep in "${missing_depends[@]}"; do
            sudo apt install -y "$dep"
        done
    else
        echo "All dependencies already installed."
    fi
}

build_qlfilter() {
    if [ ! -f "$qlfilter_c_path" ]; then
        echo "Error: $qlfilter_c_path not found. Ansible should place it here."
        exit 1
    fi
    echo "Building QLFilter from $qlfilter_c_path..."
    sudo clang -O2 -target bpf -c "$qlfilter_c_path" -o "$qlfilter_o_path"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to build qlfilter.o"
        exit 1
    fi
    echo "QLFilter built successfully: $qlfilter_o_path"
}

setup_qlfilter_service() {
    echo "Setting up qlfilter systemd service..."
    sudo tee /etc/systemd/system/qlfilter.service > /dev/null << EOF
[Unit]
Description=Quake Live Dedicated Server Filtering (XDP)
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/ip link set dev $net_interface xdp obj $qlfilter_o_path
ExecStop=/usr/sbin/ip link set dev $net_interface xdp off
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable qlfilter.service
    sudo systemctl restart qlfilter.service # Use restart to ensure it's running if already set up
    echo "qlfilter.service configured and started."
}

setup_qlfilter() {
    echo "Starting QLFilter setup..."
    check_basedir
    install_depend
    build_qlfilter
    setup_qlfilter_service
    echo "QLFilter setup complete!"
}

# Main execution
setup_qlfilter
