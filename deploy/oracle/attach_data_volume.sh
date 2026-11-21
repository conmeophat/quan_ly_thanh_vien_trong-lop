#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$EUID" -ne 0 ]]; then echo "Run with sudo."; exit 1; fi
if [[ $# -lt 1 ]]; then echo "Usage: sudo bash deploy/oracle/attach_data_volume.sh /dev/oracleoci/oraclevdb"; exit 1; fi
DEVICE="$1"
if [[ ! -b "$DEVICE" ]]; then echo "Not a block device: $DEVICE"; exit 1; fi
if findmnt -rn -S "$DEVICE" >/dev/null; then echo "Device is mounted. Refusing to format."; exit 1; fi
if [[ -n "$(lsblk -no MOUNTPOINT "$DEVICE" | tr -d '[:space:]')" ]]; then echo "Device appears mounted."; exit 1; fi
if blkid "$DEVICE" >/dev/null 2>&1; then echo "Existing filesystem detected; refusing to format."; exit 1; fi

echo "WARNING: this erases all data on $DEVICE."
read -r -p "Type FORMAT-$DEVICE to continue: " CONFIRM
if [[ "$CONFIRM" != "FORMAT-$DEVICE" ]]; then echo "Cancelled."; exit 1; fi
apt-get update
apt-get install -y e2fsprogs
mkfs.ext4 -F "$DEVICE"
UUID="$(blkid -s UUID -o value "$DEVICE")"
install -d -m 0750 -o root -g root /srv/class-merit-data
if ! grep -q "UUID=$UUID " /etc/fstab; then
  echo "UUID=$UUID /srv/class-merit-data ext4 defaults,nofail,_netdev 0 2" >> /etc/fstab
fi
mount /srv/class-merit-data
chmod 0750 /srv/class-merit-data
echo "Mounted at /srv/class-merit-data. Run install_ubuntu.sh next."
