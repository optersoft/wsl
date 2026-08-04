"""cloud-init user-data applied on a distribution's first boot.

Creates the `box` user, sets the hostname and a couple of conveniences. Kept
byte-for-byte compatible with the `box-wsl` crate so a machine created by
either tool looks the same.
"""

from __future__ import annotations

USER_DATA_TEMPLATE = """#cloud-config

users:

  - name: box
    groups: sudo,users,netdev,audio
    sudo: ALL=(ALL) NOPASSWD:ALL
    plain_text_passwd: password
    lock_passwd: false
    shell: /bin/bash

write_files:

  - path: /etc/wsl.conf
    append: true
    content: |
      [user]
      default=box
      [network]
      hostname={name}
      generateHosts=false

  - path: /etc/hostname
    defer: true
    content: |
      {name}

  - path: /etc/hosts
    content: |
      127.0.0.1       localhost
      127.0.1.1       {name}.  {name}

  - path: /home/box/.hushlogin
    owner: box:box
    defer: true

  - path: /home/box/.bash_aliases
    owner: box:box
    defer: true
    content: |
      alias install-docker="curl -L sh.xtec.dev/docker.sh | sh"

runcmd:
  - hostnamectl --transient set-hostname {name}
"""


def user_data(name: str) -> str:
    """Render the cloud-config for a distribution named `name`."""
    return USER_DATA_TEMPLATE.format(name=name)
