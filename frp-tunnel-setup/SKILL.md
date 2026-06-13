---
name: frp-tunnel-setup
description: Use this skill whenever the user mentions frp, frps, frpc, 内网穿透, 公网访问本地服务, VPS 转发, local service tunneling, exposing a local agent/harness, or Jira/TeamCity port mapping through a VPS. It helps create, inspect, bind, verify, troubleshoot, and safely operate frp server and client setups, including no-domain HTTP access via tcp remotePort mappings.
---

# frp Tunnel Setup

Use this skill to help the user build or reuse an frp-based tunnel between a VPS and local machines. The default pattern is no-domain `tcp` forwarding:

```text
http://VPS_PUBLIC_IP:REMOTE_PORT
  -> frps on VPS
  -> frpc on local machine
  -> local service on 127.0.0.1:LOCAL_PORT
```

## First steps

1. Identify whether the user needs server setup, client binding, a new port mapping, verification, troubleshooting, or a security review.
2. Read the relevant reference before giving commands:
   - Server state, port plan, templates: `references/frp-setup-record.md`
   - Client binding workflow: `references/frp-client-binding.md`
   - Local credentials if present and explicitly needed on this machine: `references/frp-secrets.local.md`
3. Treat credentials carefully. Never print real tokens unless the user explicitly asks for them. Prefer placeholders in docs, plans, and committed files.

## Decision defaults

- If there is no domain, use `type = "tcp"` and expose `http://VPS_PUBLIC_IP:REMOTE_PORT`.
- Use the existing VPS `81.68.211.31` and port range `18080-18089` when the user asks for this known setup.
- Use `remotePort = 18080` for agent/harness unless it is already occupied.
- Use `remotePort = 18081` for Jira and `18082` for TeamCity, matching the existing record.
- Keep local services bound to `127.0.0.1` unless the user has a reason to expose them on the LAN.
- Require `auth.method = "token"` and `transport.tls.enable = true` on frpc.
- Require `transport.tls.force = true` and `allowPorts` on frps.

## Server workflow

When asked to set up or inspect `frps` on a VPS:

1. Confirm OS and architecture with `uname -s` and `uname -m`.
2. Use GitHub Releases for the latest stable frp binary unless the user pins a version.
3. Install `frps` under `/opt/frp/frps`, config under `/etc/frp/frps.toml`, logs under `/var/log/frp/frps.log`.
4. Create or verify a systemd service at `/etc/systemd/system/frps.service`.
5. Open only required firewall and cloud security group ports:
   - `7000/tcp` for frpc control connection
   - selected business ports, normally `18080-18089/tcp`
6. Verify with:
   - `systemctl status frps --no-pager`
   - `ss -lntp | grep frps`
   - `journalctl -u frps -n 100 --no-pager`

## Client workflow

When asked to bind a local service to the existing VPS:

1. Determine local OS, architecture, and `LOCAL_PORT`.
2. Confirm the local service responds first: `curl -i http://127.0.0.1:LOCAL_PORT/`.
3. Create `frpc.toml` with:
   - `serverAddr`
   - `serverPort = 7000`
   - token auth
   - TLS enabled
   - one or more `[[proxies]]`
4. Start `frpc` in foreground for first verification.
5. Verify the public endpoint: `curl -i http://VPS_PUBLIC_IP:REMOTE_PORT/`.
6. Only after verification, offer systemd or launchd persistence.

## Adding a mapping

Use this template and replace all placeholders:

```toml
[[proxies]]
name = "SERVICE_NAME"
type = "tcp"
localIP = "127.0.0.1"
localPort = LOCAL_PORT
remotePort = REMOTE_PORT
```

Choose `REMOTE_PORT` from the allowed range and avoid collisions. After editing `frpc.toml`, restart `frpc` and verify from both the VPS and an outside network.

## Safety checklist

For agent/harness or any high-privilege service, include these reminders:

- Do not expose an unauthenticated control surface to the public internet.
- Use app-level auth, IP allowlists, command allowlists, audit logs, and a kill switch.
- Rotate frp tokens if they were pasted into chat, logs, screenshots, or committed files.
- Prefer a domain plus HTTPS, or a private overlay network, for long-term sensitive use.

## Response style

Be operational and concrete. Give commands that can be copied, but separate VPS commands from local-machine commands. End with verification steps and rollback or stop commands.
