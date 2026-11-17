# Disposable Ubuntu 24.04 target for tests/test_runtime_upgrade_integration.py.
# systemd as PID 1, sshd for Ansible, the build prerequisites already present
# (so the installer's apt step is a no-op), and minqlx's global redis<3 the
# way setup_host.yml leaves a minqlx host. apt lists are kept so the apt
# guard can simulate. python3-apt is present as on every host setup_host.yml
# configured (Ansible's apt module would otherwise install it itself).
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv systemd-timesyncd dbus openssh-server sudo rsync patch make \
      python3 python3-apt python3-pip python3-venv python3-dev build-essential git ca-certificates && \
    pip3 install --break-system-packages 'redis<3' && \
    useradd -m -s /bin/bash ansible && \
    echo 'ansible ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ansible && \
    useradd -r -m -d /home/ql -s /bin/bash ql && chmod 0750 /home/ql && \
    mkdir -p /home/ansible/.ssh && systemctl enable ssh
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
