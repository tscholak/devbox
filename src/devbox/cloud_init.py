"""Cloud-init template handling."""

from __future__ import annotations

import base64
from pathlib import Path


DEFAULT_CLOUD_INIT = r"""#cloud-config
package_update: true
packages:
  - curl
  - git
  - xz-utils
  - ca-certificates
  - jq

write_files:
  - path: /usr/local/sbin/first-boot.sh
    permissions: '0755'
    owner: root:root
    content: |
      #!/usr/bin/env bash
      set -euo pipefail
      LOG=/var/log/first-boot.log
      exec >>"$LOG" 2>&1

      # 1) Detect Lambda persistent FS mount (NFS path or the Ubuntu-24 image path you observed)
      PERSIST=""
      if mount | grep -q "/lambda/nfs/"; then
        PERSIST="$(mount | awk '/\/lambda\/nfs\//{print $3; exit}')"
      elif [ -d /home/ubuntu/home ]; then
        PERSIST="/home/ubuntu/home"
      fi
      if [ -z "${PERSIST}" ]; then
        echo "No persistent FS found; skipping persistent home setup."
        exit 0
      fi

      # 2) Initial prep (idempotent)
      if [ ! -f "$PERSIST/.bootstrap_done" ]; then
        mkdir -p "$PERSIST/.ssh" "$PERSIST/nix" "$PERSIST/work"
        if [ -d /home/ubuntu/.ssh ] && [ ! -f "$PERSIST/.ssh/authorized_keys" ]; then
          cp -a /home/ubuntu/.ssh/* "$PERSIST/.ssh/" || true
        fi
        chown -R ubuntu:ubuntu "$PERSIST"
        chmod 700 "$PERSIST/.ssh" || true
        touch "$PERSIST/.bootstrap_done"
      fi

      # 3) Bind-mount persistent FS as /home/ubuntu (systemd mount unit)
      unit=/etc/systemd/system/home-ubuntu.mount
      cat > "$unit" <<EOF
      [Unit]
      Description=Bind mount persistent home on /home/ubuntu
      RequiresMountsFor=$PERSIST
      After=network-online.target
      [Mount]
      What=$PERSIST
      Where=/home/ubuntu
      Type=none
      Options=bind
      [Install]
      WantedBy=multi-user.target
      EOF
      systemctl daemon-reload
      systemctl enable --now home-ubuntu.mount

      # 4) Persist /nix on the same FS
      mkdir -p /home/ubuntu/nix
      chown -R ubuntu:ubuntu /home/ubuntu/nix
      if ! mountpoint -q /nix; then
        mkdir -p /nix
        mount --bind /home/ubuntu/nix /nix
        echo "/home/ubuntu/nix /nix none bind 0 0" >> /etc/fstab
      fi

      # 5) Install Nix (multi-user) + devenv (idempotent)
      if ! command -v nix >/dev/null 2>&1; then
        sh <(curl -L https://nixos.org/nix/install) --daemon
      fi
      if [ -f /etc/profile.d/nix.sh ]; then
        grep -q 'profile.d/nix.sh' /home/ubuntu/.bashrc || echo 'source /etc/profile.d/nix.sh' >> /home/ubuntu/.bashrc
      fi
      sudo -u ubuntu bash -lc "nix --version || true"
      sudo -u ubuntu bash -lc "nix profile install nixpkgs#devenv || true"

runcmd:
  - [ bash, -lc, "/usr/local/sbin/first-boot.sh" ]
"""


def load_cloud_init_template(template_path: str | None, use_default: bool) -> str:
    """Load cloud-init template.

    Args:
        template_path: Path to custom template file
        use_default: Whether to use default template if no custom path

    Returns:
        Cloud-init YAML content

    Raises:
        FileNotFoundError: If template_path specified but not found
        ValueError: If neither template_path nor use_default is provided
    """
    if template_path:
        path = Path(template_path)
        if not path.exists():
            raise FileNotFoundError(f"Cloud-init template not found: {template_path}")
        return path.read_text(encoding="utf-8")

    if use_default:
        return DEFAULT_CLOUD_INIT

    raise ValueError("No cloud-init template specified and use_default is False")


def encode_cloud_init(content: str) -> str:
    """Encode cloud-init content to base64.

    Args:
        content: Cloud-init YAML content

    Returns:
        Base64-encoded string
    """
    return base64.b64encode(content.encode("utf-8")).decode("ascii")
