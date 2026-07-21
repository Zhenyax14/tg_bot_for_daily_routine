# Telegram Daily Bot — Deployment on Proxmox LXC

Operational document for CT 101 (`tgbot`). Complements the repo's `README.md`,
which documents the application; this only covers what **can't be inferred from
the repo**.

---

## Container profile

| Parameter | Value |
|---|---|
| CTID | `101` |
| Hostname | `tgbot` |
| IP | `192.168.1.204/24` (static) |
| Gateway | `192.168.1.1` |
| Node | `zhenyax14` |
| Template | `debian-12-standard_12.7-1_amd64.tar.zst` |
| CPU | 1 core |
| RAM | 512 MB + 512 MB swap |
| Disk | 5 GB (`local-lvm`) |
| Privileges | **Unprivileged** (`unprivileged: 1`) |
| Features | `nesting=1,keyctl=1` |
| Boot with node | `onboot: 1` |
| Runtime | Docker CE + docker-compose-plugin |
| App path | `/opt/bot2` |

---

## 1. Create the container

From the **node shell** (`root@zhenyax14`):

```bash
pveam update
pveam available --section system | grep debian-12
pveam download local debian-12-standard_12.7-1_amd64.tar.zst
```

> The version number changes over time. Always use the exact name returned by
> `pveam available`; a stale name returns `404 Not Found (500)`.

```bash
pct create 101 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname tgbot \
  --cores 1 \
  --memory 512 \
  --swap 512 \
  --rootfs local-lvm:5 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.1.204/24,gw=192.168.1.1 \
  --unprivileged 1 \
  --features nesting=1,keyctl=1 \
  --onboot 1 \
  --password
```

---

## 2. Mandatory AppArmor workaround

**Without this step, Docker cannot start any container inside the LXC.**

Append to the end of `/etc/pve/lxc/101.conf`, from the node:

```bash
pct stop 101
cat >> /etc/pve/lxc/101.conf << 'EOF'
lxc.apparmor.profile: unconfined
lxc.mount.entry: /dev/null sys/module/apparmor/parameters/enabled none bind 0 0
EOF
pct start 101
```

Verify the lines appear **exactly once**:

```bash
pct config 101
```

### Why

`containerd.io` 1.7.28-2 (November 2025) includes the fix for
**CVE-2025-52881**, a critical container escape vulnerability. The patch reopens
file descriptors for `procfs` operations, which triggers an AppArmor denial when
Docker runs inside a nested LXC. Resulting error:

```
OCI runtime create failed: runc create failed: unable to start container process:
error during container init: open sysctl net.ipv4.ip_unprivileged_port_start file:
reopen fd 8: permission denied
```

The first line disables the LXC's AppArmor profile. The second masks
`/sys/module/apparmor/parameters/enabled` so Docker believes AppArmor doesn't
exist and doesn't try to load its own profile.

### What did NOT work (tested)

| Attempt | Result |
|---|---|
| `--features nesting=1,keyctl=1` alone | Same failure |
| Converting the CT to privileged | Same failure, and **breaks the CT** (see below) |
| `docker run --privileged` | Same failure |
| `--security-opt seccomp=unconfined` | Same failure |
| `daemon.json` with `default-sysctl` | Same failure |
| `lxc.sysctl...` in the conf | Proxmox doesn't parse that key |

The block is enforced by AppArmor **on the host**, not by container isolation.
That's why no Docker-side option avoids it.

### Discarded alternative

Downgrading `containerd.io` to `1.7.28-1~debian.12~bookworm` and holding it with
`apt-mark hold`. It works, but forfeits that version's security fixes (including
fixes for three escape vulnerabilities), and an absent-minded `apt upgrade` breaks
the deployment again.

### ⚠ Technical debt — review periodically

Disabling AppArmor weakens the CT's isolation from the host. Acceptable on a home
LAN for a bot with no exposed ports, but **not the desired final configuration**.
Once runc/Proxmox fix the incompatibility upstream, these two lines should be
removable. Tracking:

- `opencontainers/runc` issues #4972 and #4968
- Proxmox forum thread on `net.ipv4.ip_unprivileged_port_start`

When removing them, verify with `docker run --rm hello-world` before considering
it done.

### Benign warning

```
explicitly configured lxc.apparmor.profile overrides the following settings: features:nesting
```

Informational only. Setting the profile to `unconfined` makes the AppArmor-related
adjustment that `nesting=1` used to make redundant. `keyctl=1` remains active, which
is the one that matters.

---

## 3. SSH access

Debian 12 blocks root SSH login by default. From the node:

```bash
pct exec 101 -- sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
pct exec 101 -- systemctl restart ssh
```

Recreating the CT changes the host fingerprint. From the Windows client:

```bash
ssh-keygen -R 192.168.1.204
ssh root@192.168.1.204
```

> **Pending:** create a sudo admin user and revert to
> `PermitRootLogin prohibit-password`. Test the new login in **another window**
> before closing the current session.

---

## 4. Install Docker

Inside the CT:

```bash
apt update && apt upgrade -y
apt install -y ca-certificates curl gnupg git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian bookworm stable" \
> /etc/apt/sources.list.d/docker.list

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable docker
```

Smoke test — validates the AppArmor workaround:

```bash
docker run --rm hello-world
```

Should print `Hello from Docker!`. If it gives the
`ip_unprivileged_port_start` error, revisit step 2 before continuing.

---

## 5. Deploy the application

```bash
cd /opt
git clone https://github.com/Zhenyax14/bot2.git
cd bot2

cp docker/.env.example .env
nano .env
chmod 600 .env
```

`.env` contents:

```
TELEGRAM_BOT_TOKEN=<token from @BotFather>
CHAT_ID=-100xxxxxxxxxx
THREAD_ID=
STARTUP_MESSAGE=
```

> `CHAT_ID` for a supergroup starts with `-100`.
> `THREAD_ID` empty for groups without topics.
> `STARTUP_MESSAGE` empty: see the scheduled shutdown note (step 7).

### Dry run

Validates the full wiring without a valid token or network access:

```bash
DRY_RUN=1 docker compose -f docker/docker-compose.yaml run --rm -e DRY_RUN bot
```

Expected output:

```
WARNING  bot | DRY_RUN active: nothing sent to Telegram
INFO     ... | Scheduled morning-greeting at 07:00
INFO     ... | Scheduled game-chance at 07:15
INFO     ... | Scheduled good-night at 22:00
INFO     ... | [DRY-RUN] <startup message>
INFO     bot | Bot started (Europe/Madrid)
```

`Ctrl+C` should produce `Stopped cleanly` — confirms `SIGTERM` reaches Python as
PID 1 (depends on the Dockerfile's *exec form* `CMD`).

### Real startup

```bash
docker compose -f docker/docker-compose.yaml up -d --build
docker compose -f docker/docker-compose.yaml logs -f
```

Look for `Sent: ...`. If `Failed to send` appears, check the diagnostic table in
the repo's `README.md`.

### Alias

```bash
echo "alias dcb='docker compose -f /opt/bot2/docker/docker-compose.yaml'" >> ~/.bashrc
```

---

## 6. Persistence across reboots

Three independent layers, all required:

| Layer | Mechanism | Where |
|---|---|---|
| CT boots with the node | `onboot: 1` | CT config |
| Docker daemon boots with the CT | `systemctl enable docker` | Inside the CT |
| Container boots with the daemon | `restart: unless-stopped` | `docker-compose.yaml` |

Test the full chain, from the node:

```bash
pct reboot 101
sleep 40 && pct exec 101 -- docker ps
```

---

## 7. Scheduled shutdown and startup

Cron lives **on the node**, not inside the CT: a shut-down container can't start
itself, and `pct` doesn't exist inside the CT.

```bash
# From the NODE
crontab -e
```

```cron
0  0 * * * /usr/sbin/pct shutdown 101 --timeout 60
45 6 * * * /usr/sbin/pct start 101
```

Details that matter:

- **Absolute path.** Root's cron doesn't inherit the interactive shell's `PATH`.
- **`shutdown`, not `stop`.** `shutdown` sends `SIGTERM` and waits; the bot
  handles it and logs `Stopped cleanly`. `stop` is a `SIGKILL`.
- **06:45, not 06:55.** CT boot + daemon + possible rebuild can exceed 5 minutes.
  If the bot starts after 07:00, APScheduler drops the job per its
  `misfire_grace_time`, and the message is lost **with no visible error**.

Check the node's timezone, or the cron fires off-schedule:

```bash
date
timedatectl set-timezone Europe/Madrid
```

### Side effect: `STARTUP_MESSAGE`

The startup message is sent on **every** startup, by design. With the cron
active, that means a daily message to the group at 06:45. Leave
`STARTUP_MESSAGE=` empty in the `.env`.

### Overlap with `onboot`

If the node reboots outside the planned window, the CT starts there and stays up
until the midnight `shutdown`. Nothing breaks.

---

## 8. Errors encountered and their causes

| Symptom | Cause | Fix |
|---|---|---|
| `404 Not Found (500)` downloading the template | Index version no longer on the server | `pveam update` and use the name from `pveam available` |
| `Permission denied` on SSH to root | Debian 12 blocks root by default | `PermitRootLogin yes` |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | CT recreated, new fingerprint | `ssh-keygen -R <IP>` **on the client** |
| `open sysctl net.ipv4.ip_unprivileged_port_start ... permission denied` | CVE-2025-52881 + AppArmor | See step 2 |
| `pct: command not found` | Command run inside the CT | Run it on the node instead |
| `Could not chdir to home directory /root` | Flipping `unprivileged` 1→0→1 broke the UIDs | See warning below |

### ⚠ Don't flip `unprivileged` by hand

In an unprivileged CT, the internal root is the host's uid `100000`; in a
privileged one it's uid `0`. Editing that flag in an already-created CT's `.conf`
leaves the filesystem with inconsistent ownership: `/root` stops belonging to the
CT's root, the prompt degrades to `-bash-5.2#`, and services like Docker fail to
start.

**There's no practical fix.** Destroy and recreate the CT.

### Telling apart where each command runs

| Prompt | Location | Valid commands |
|---|---|---|
| `root@zhenyax14` | Proxmox node | `pct`, `qm`, `pveam`, `vzdump`, `/etc/pve/` |
| `root@tgbot` | Inside the CT | `docker`, `apt`, `systemctl`, the app |

Anything starting with `pct` **always** goes on the node.

---

## 9. Sizing — rationale

| Resource | Assigned | Real usage | Note |
|---|---|---|---|
| RAM | 512 MB | ~200-260 MB | Debian ~40 + dockerd ~120 + Python ~70 |
| Swap | 512 MB | — | Turns an OOM spike into slowness instead |
| Disk | 5 GB | ~2-2.5 GB | Docker ~400 MB + image ~300 MB |
| CPU | 1 core | ~0% idle | The bot is I/O-bound, not compute |

Calling external APIs (Telegram, LLM) is I/O: roughly 1-2 MB per connection.
**Doesn't justify more RAM or cores.** Scale up live if ever needed:

```bash
pct set 101 --memory 1024
pct set 101 --cores 2
pct resize 101 rootfs +2G   # + resize2fs inside the CT
```

Measure before deciding:

```bash
pct exec 101 -- cat /sys/fs/cgroup/memory.peak
```

Sustained growth instead of a plateau = a leak, not a lack of RAM.

---

## 10. Operations commands

```bash
# --- From the NODE ---
pct list
pct config 101
pct start 101 / pct shutdown 101 --timeout 60 / pct reboot 101
pct exec 101 -- docker ps
vzdump 101 --storage local --mode snapshot --compress zstd

# --- Inside the CT ---
dcb ps
dcb logs -f
dcb logs --tail 50
dcb restart
dcb down && dcb up -d --build
dcb config                                    # expanded variables
DRY_RUN=1 dcb run --rm -e DRY_RUN bot         # dry run
```

Verify credentials without starting the app:

```bash
set -a; source /opt/bot2/.env; set +a
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d chat_id="$CHAT_ID" -d text="ping"
```

`"ok":true` confirms token and chat are correct.

---