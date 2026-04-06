#!/bin/bash

set -e

# Define the Ansible user
ANSIBLE_USER=ansible

# Check if user exists, if not, create the user
if ! id "$ANSIBLE_USER" &>/dev/null; then
    echo "Creating user $ANSIBLE_USER..."
    sudo useradd -m -s /bin/bash $ANSIBLE_USER
    echo "User $ANSIBLE_USER created."
else
    echo "User $ANSIBLE_USER already exists."
fi

# Set up SSH directory 
sudo -u $ANSIBLE_USER mkdir -p /home/$ANSIBLE_USER/.ssh


echo "Appending public key to authorized_keys..."
sudo cp /root/.ssh/authorized_keys /home/$ANSIBLE_USER/.ssh/authorized_keys

# Set proper permissions for SSH directory and its contents
echo "Setting permissions for SSH directory and files..."
sudo chmod 700 /home/$ANSIBLE_USER/.ssh
sudo chmod 600 /home/$ANSIBLE_USER/.ssh/authorized_keys
sudo chown -R $ANSIBLE_USER:$ANSIBLE_USER /home/$ANSIBLE_USER/.ssh

# Configure passwordless sudo
echo "Configuring passwordless sudo..."
echo "$ANSIBLE_USER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$ANSIBLE_USER
sudo chmod 0440 /etc/sudoers.d/$ANSIBLE_USER

# Fix DNS resolution
echo "Fixing DNS resolution..."
echo "nameserver 1.1.1.1" > /etc/resolv.conf

echo "Setup complete."