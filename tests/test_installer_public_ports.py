import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_installer_infers_https_port_from_site_address(tmp_path):
    install_dir = run_installer_with_fakes(
        tmp_path,
        SITE_ADDRESS="qlsm.example.com:444",
    )

    env_text = (install_dir / ".env").read_text()
    assert "SITE_ADDRESS=qlsm.example.com:444\n" in env_text
    assert "PUBLIC_HTTP_PORT=80\n" in env_text
    assert "PUBLIC_HTTPS_PORT=444\n" in env_text


def test_installer_appends_public_https_port_to_bare_domain(tmp_path):
    install_dir = run_installer_with_fakes(
        tmp_path,
        SITE_ADDRESS="qlsm.example.com",
        PUBLIC_HTTPS_PORT="444",
    )

    env_text = (install_dir / ".env").read_text()
    assert "SITE_ADDRESS=qlsm.example.com:444\n" in env_text
    assert "PUBLIC_HTTPS_PORT=444\n" in env_text


def test_installer_respects_custom_public_http_port(tmp_path):
    install_dir = run_installer_with_fakes(
        tmp_path,
        PUBLIC_HTTP_PORT="8080",
    )

    env_text = (install_dir / ".env").read_text()
    assert "PUBLIC_HTTP_PORT=8080\n" in env_text


def test_installer_infers_https_port_from_ipv6_site_address(tmp_path):
    install_dir = run_installer_with_fakes(
        tmp_path,
        SITE_ADDRESS="[2001:db8::1]:444",
    )

    env_text = (install_dir / ".env").read_text()
    assert "SITE_ADDRESS=[2001:db8::1]:444\n" in env_text
    assert "PUBLIC_HTTPS_PORT=444\n" in env_text


def test_installer_rejects_invalid_public_ports(tmp_path):
    result = run_installer_with_fakes(
        tmp_path,
        check=False,
        PUBLIC_HTTPS_PORT="99999",
    )

    assert result.returncode != 0
    assert "PUBLIC_HTTPS_PORT must be a port number between 1 and 65535" in result.stderr


def run_installer_with_fakes(tmp_path, check=True, **env_overrides):
    install_dir = tmp_path / "qlsm-install"
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()

    write_executable(
        fakebin / "docker",
        """#!/usr/bin/env bash
if [[ "$1" == "--version" ]]; then
  echo "Docker version 99.0.0, build fake"
  exit 0
fi
if [[ "$1" == "compose" && "$2" == "version" ]]; then
  echo "Docker Compose version v99.0.0"
  exit 0
fi
if [[ "$1" == "compose" ]]; then
  exit 0
fi
echo "unexpected docker args: $*" >&2
exit 1
""",
    )
    write_executable(
        fakebin / "curl",
        f"""#!/usr/bin/env bash
out=""
url=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
if [[ -n "$out" ]]; then
  case "$url" in
    *docker-compose.yml) cp {ROOT / 'docker-compose.yml'} "$out" ;;
    *Caddyfile) cp {ROOT / 'Caddyfile'} "$out" ;;
    *host-init/Dockerfile) printf 'FROM scratch\n' > "$out" ;;
    *host-init/init.sh) printf '#!/usr/bin/env sh\nexit 0\n' > "$out" ;;
    *) printf '' > "$out" ;;
  esac
fi
exit 0
""",
    )

    env = os.environ.copy()
    env.update(env_overrides)
    env["INSTALL_DIR"] = str(install_dir)
    env["HOME"] = str(tmp_path / "home")
    env["PATH"] = f"{fakebin}:{env['PATH']}"

    result = subprocess.run(
        ["bash", str(ROOT / "qlsm-install.sh")],
        check=check,
        env=env,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check:
        return install_dir
    return result


def write_executable(path, content):
    path.write_text(content)
    path.chmod(0o755)
