#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# The security boundary is this firewall, not the permission system.
# Model: open egress to the internet; block RFC 1918 private ranges (home
# network / localhost) with narrow carve-outs for Docker infrastructure;
# lock ingress to established connections + the Docker bridge gateway (VS Code).

# 1. Snapshot Docker DNS NAT rules before flushing
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

# 2. Flush all tables
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X

# 3. Restore Docker internal DNS NAT (redirects container DNS to 127.0.0.11)
if [ -n "$DOCKER_DNS_RULES" ]; then
    echo "Restoring Docker DNS rules..."
    iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
    iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
    echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
else
    echo "No Docker DNS rules to restore"
    # In some Docker/WSL2 configurations the embedded resolver binds on an
    # ephemeral port rather than :53 and relies on NAT REDIRECT to reach it.
    # Detect the listening port and synthesize the redirect rules.
    DNS_UDP_PORT=$(ss -ulnp 2>/dev/null | grep -oE '127\.0\.0\.11:[0-9]+' | cut -d: -f2 | head -1 || true)
    DNS_TCP_PORT=$(ss -tlnp 2>/dev/null | grep -oE '127\.0\.0\.11:[0-9]+' | cut -d: -f2 | head -1 || true)
    if [ -n "$DNS_UDP_PORT" ] && [ "$DNS_UDP_PORT" != "53" ]; then
        echo "Synthesizing Docker DNS NAT redirect: UDP 53 → $DNS_UDP_PORT"
        iptables -t nat -A OUTPUT -d 127.0.0.11/32 -p udp --dport 53 -j REDIRECT --to-ports "$DNS_UDP_PORT"
    fi
    if [ -n "$DNS_TCP_PORT" ] && [ "$DNS_TCP_PORT" != "53" ]; then
        echo "Synthesizing Docker DNS NAT redirect: TCP 53 → $DNS_TCP_PORT"
        iptables -t nat -A OUTPUT -d 127.0.0.11/32 -p tcp --dport 53 -j REDIRECT --to-ports "$DNS_TCP_PORT"
    fi
fi

# 4. Always allow loopback (Docker's 127.0.0.11 resolver uses this)
iptables -A INPUT  -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# 5. Detect Docker bridge gateway (default route next-hop)
HOST_IP=$(ip route | grep default | awk '{print $3}')
[ -z "$HOST_IP" ] && { echo "ERROR: cannot detect Docker bridge gateway"; exit 1; }
echo "Docker bridge gateway: $HOST_IP"

# ── INPUT ──────────────────────────────────────────────────────────────────────
# Responses to connections the container initiated
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
# VS Code server: accept connections from the Docker bridge gateway only
iptables -A INPUT -s "$HOST_IP" -j ACCEPT

# ── OUTPUT ────────────────────────────────────────────────────────────────────
# Docker infrastructure lives in 172.16.0.0/12; carve it out before the block.
iptables -A OUTPUT -d "$HOST_IP"          -j ACCEPT  # Docker bridge gateway
# WSL host IP — set WSL_HOST_IP to your WSL host's address to carve it out of the
# RFC 1918 block below (find it with `ip route show | awk '/^default/{print $3}'`
# inside WSL, or leave unset if you don't need to reach the WSL host).
WSL_HOST_IP="${WSL_HOST_IP:-}"
if [ -n "$WSL_HOST_IP" ]; then
    iptables -A OUTPUT -d "$WSL_HOST_IP" -j ACCEPT  # WSL host
fi

# Allow DNS to whichever nameserver the container is configured to use.
# In Docker Desktop environments this sits in 192.168.65.0/24, which would
# otherwise be caught by the 192.168.0.0/16 REJECT below.
DNS_SERVER=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf)
if [ -n "$DNS_SERVER" ]; then
    echo "Allowing DNS to nameserver: $DNS_SERVER"
    iptables -A OUTPUT -d "$DNS_SERVER" -p udp --dport 53 -j ACCEPT
    iptables -A OUTPUT -d "$DNS_SERVER" -p tcp --dport 53 -j ACCEPT
fi

# Block RFC 1918 private ranges and loopback on non-lo interfaces.
# This prevents the container from initiating connections to localhost (other
# than via lo, which is already accepted above) or any home/LAN device.
iptables -A OUTPUT -d 127.0.0.0/8    -j REJECT --reject-with icmp-admin-prohibited
iptables -A OUTPUT -d 10.0.0.0/8     -j REJECT --reject-with icmp-admin-prohibited
iptables -A OUTPUT -d 172.16.0.0/12  -j REJECT --reject-with icmp-admin-prohibited
iptables -A OUTPUT -d 192.168.0.0/16 -j REJECT --reject-with icmp-admin-prohibited
iptables -A OUTPUT -d 169.254.0.0/16 -j REJECT --reject-with icmp-admin-prohibited

# ── Default policies ──────────────────────────────────────────────────────────
iptables -P INPUT   DROP
iptables -P FORWARD DROP
iptables -P OUTPUT  ACCEPT  # everything not blocked above is permitted

echo "Firewall configuration complete"
echo "Verifying firewall rules..."

# DNS must work before egress checks (curl needs it)
echo "  Checking DNS..."
if ! dig +short +time=5 example.com | grep -qE '^[0-9]'; then
    echo "ERROR: DNS resolution failed — Docker DNS NAT may not have restored correctly"
    exit 1
fi
echo "  DNS: PASS"

# A private (RFC 1918) LAN address must be blocked. 192.168.1.1 is an arbitrary
# representative of a home/LAN range — the assertion is that RFC 1918 egress is
# rejected, not anything about a specific device.
LAN_PROBE_IP="${LAN_PROBE_IP:-192.168.1.1}"
echo "  Checking a private LAN address ($LAN_PROBE_IP) is blocked..."
if curl --connect-timeout 3 "http://$LAN_PROBE_IP" >/dev/null 2>&1; then
    echo "ERROR: reached $LAN_PROBE_IP — RFC 1918 egress not blocked"
    exit 1
fi
echo "  Private LAN: PASS (blocked)"

# Internet egress must be open
echo "  Checking internet egress (example.com)..."
if ! curl --connect-timeout 5 https://example.com >/dev/null 2>&1; then
    echo "ERROR: cannot reach example.com — internet egress broken"
    exit 1
fi
echo "  Internet egress: PASS"

echo "Firewall up: open egress, locked ingress, RFC 1918 blocked (Docker bridge and WSL host exempted)."
