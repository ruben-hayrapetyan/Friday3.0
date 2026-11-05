#!/bin/bash
# The server's hardening (HOSTED.md H63), run once by you with sudo: `sudo scripts/server/harden.sh`.
# - SSH by key only: already so (PasswordAuthentication no, PermitRootLogin no); checked here, not changed.
# - A firewall (ufw): nothing comes in except over Tailscale, and SSH from the home network as a way back in
#   should Tailscale be down. Other ports listening today (8050, printing, mail) stay reachable over Tailscale only.
# - fail2ban on SSH, reading the systemd journal (Debian 13 keeps no auth.log).
# - Automatic security updates (unattended-upgrades).
# - Lets you (not only root) run `tailscale serve`, so the Fridays can be put on the tailnet without sudo.
# Running it again changes nothing that's there.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run it with sudo"; exit 1; }
user="${SUDO_USER:?run it with sudo from your own account}"
lan="10.48.0.0/16"

sshd -T | grep -Eq '^passwordauthentication no' && echo "==> SSH: keys only (already)" \
    || { echo "SSH still takes passwords: not changing it here; tell Claude"; exit 1; }

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw fail2ban python3-systemd unattended-upgrades sqlite3 >/dev/null

ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow in on tailscale0 >/dev/null
ufw allow from "$lan" to any port 22 proto tcp >/dev/null
ufw --force enable >/dev/null
echo "==> Firewall on:"; ufw status | sed -n '4,$p'

cat > /etc/fail2ban/jail.d/sshd.local <<'JAIL'
[sshd]
enabled = true
backend = systemd
maxretry = 5
bantime = 1h
JAIL
systemctl enable -q --now fail2ban && systemctl restart fail2ban
echo "==> fail2ban: $(fail2ban-client status sshd | grep 'Currently banned' | xargs)"

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT
systemctl enable -q --now unattended-upgrades
echo "==> Automatic security updates on"

tailscale set --operator="$user"
echo "==> $user can run tailscale serve"
