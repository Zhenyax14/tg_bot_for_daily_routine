# Telegram Daily Bot — Despliegue en LXC de Proxmox

Documento operativo del CT 101 (`tgbot`). Complementa al `README.md` del repositorio,
que documenta la aplicación; aquí solo está lo que **no se deduce del repo**.

---

## Ficha del contenedor

| Parámetro | Valor |
|---|---|
| CTID | `101` |
| Hostname | `tgbot` |
| IP | `192.168.1.204/24` (estática) |
| Gateway | `192.168.1.1` |
| Nodo | `zhenyax14` |
| Plantilla | `debian-12-standard_12.7-1_amd64.tar.zst` |
| CPU | 1 core |
| RAM | 512 MB + 512 MB swap |
| Disco | 5 GB (`local-lvm`) |
| Privilegios | **No privilegiado** (`unprivileged: 1`) |
| Features | `nesting=1,keyctl=1` |
| Arranque con el nodo | `onboot: 1` |
| Runtime | Docker CE + docker-compose-plugin |
| Ruta de la app | `/opt/bot2` |

---

## 1. Crear el contenedor

Desde la **shell del nodo** (`root@zhenyax14`):

```bash
pveam update
pveam available --section system | grep debian-12
pveam download local debian-12-standard_12.7-1_amd64.tar.zst
```

> El número de versión cambia con el tiempo. Usar siempre el nombre exacto que
> devuelva `pveam available`; un nombre caducado da `404 Not Found (500)`.

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

## 2. Workaround obligatorio de AppArmor

**Sin este paso, Docker no arranca ningún contenedor dentro del LXC.**

Añadir al final de `/etc/pve/lxc/101.conf`, desde el nodo:

```bash
pct stop 101
cat >> /etc/pve/lxc/101.conf << 'EOF'
lxc.apparmor.profile: unconfined
lxc.mount.entry: /dev/null sys/module/apparmor/parameters/enabled none bind 0 0
EOF
pct start 101
```

Verificar que las líneas aparecen **una sola vez**:

```bash
pct config 101
```

### Por qué

`containerd.io` 1.7.28-2 (noviembre 2025) incorpora la corrección de
**CVE-2025-52881**, una vulnerabilidad crítica de escape de contenedor. El parche
reabre descriptores de fichero para operaciones sobre `procfs`, y eso dispara una
denegación de AppArmor cuando Docker corre dentro de un LXC anidado. Error resultante:

```
OCI runtime create failed: runc create failed: unable to start container process:
error during container init: open sysctl net.ipv4.ip_unprivileged_port_start file:
reopen fd 8: permission denied
```

La primera línea desactiva el perfil AppArmor del LXC. La segunda enmascara
`/sys/module/apparmor/parameters/enabled` para que Docker crea que AppArmor no
existe y no intente cargar su propio perfil.

### Lo que NO funciona (comprobado)

| Intento | Resultado |
|---|---|
| `--features nesting=1,keyctl=1` solo | Falla igual |
| Convertir el CT a privilegiado | Falla igual, y **rompe el CT** (ver abajo) |
| `docker run --privileged` | Falla igual |
| `--security-opt seccomp=unconfined` | Falla igual |
| `daemon.json` con `default-sysctl` | Falla igual |
| `lxc.sysctl...` en el conf | Proxmox no parsea esa clave |

El bloqueo lo impone AppArmor **del host**, no el aislamiento del contenedor. Por eso
ninguna opción del lado de Docker lo evita.

### Alternativa descartada

Bajar `containerd.io` a `1.7.28-1~debian.12~bookworm` y ponerlo en `apt-mark hold`.
Funciona, pero renuncia a las correcciones de seguridad de esa versión (incluidos
arreglos de tres vulnerabilidades de escape) y un `apt upgrade` distraído vuelve a
romper el despliegue.

### ⚠ Deuda técnica — revisar periódicamente

Desactivar AppArmor debilita el aislamiento del CT respecto al host. Es asumible en
LAN doméstica para un bot sin puertos expuestos, pero **no es la configuración final
deseable**. Cuando runc/Proxmox resuelvan la incompatibilidad aguas arriba, estas dos
líneas deben poder eliminarse. Seguimiento:

- `opencontainers/runc` issue #4972 y #4968
- Hilo del foro de Proxmox sobre `net.ipv4.ip_unprivileged_port_start`

Al eliminarlas, verificar con `docker run --rm hello-world` antes de dar por bueno.

### Aviso benigno

```
explicitly configured lxc.apparmor.profile overrides the following settings: features:nesting
```

Es informativo. Al poner el perfil a `unconfined`, el ajuste que `nesting=1` hacía
sobre AppArmor queda sin efecto. `keyctl=1` sigue activo, que es el que importa.

---

## 3. Acceso SSH

Debian 12 bloquea el login de root por SSH por defecto. Desde el nodo:

```bash
pct exec 101 -- sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
pct exec 101 -- systemctl restart ssh
```

Al recrear el CT cambia la huella del host. Desde el cliente Windows:

```bash
ssh-keygen -R 192.168.1.204
ssh root@192.168.1.204
```

> **Pendiente:** crear usuario admin con sudo y volver a
> `PermitRootLogin prohibit-password`. Probar el login nuevo en **otra ventana**
> antes de cerrar la sesión actual.

---

## 4. Instalar Docker

Dentro del CT:

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

Prueba de fuego — valida el workaround de AppArmor:

```bash
docker run --rm hello-world
```

Debe imprimir `Hello from Docker!`. Si da el error de `ip_unprivileged_port_start`,
revisar el paso 2 antes de continuar.

---

## 5. Desplegar la aplicación

```bash
cd /opt
git clone https://github.com/Zhenyax14/bot2.git
cd bot2

cp docker/.env.example .env
nano .env
chmod 600 .env
```

Contenido del `../../.env`:

```
TELEGRAM_BOT_TOKEN=<token de @BotFather>
CHAT_ID=-100xxxxxxxxxx
THREAD_ID=
STARTUP_MESSAGE=
```

> `CHAT_ID` de supergrupo empieza por `-100`.
> `THREAD_ID` vacío en grupos sin temas.
> `STARTUP_MESSAGE` vacío: ver la nota del apagado programado (paso 7).

### Arranque en seco

Valida el cableado completo sin token válido ni salida a la red:

```bash
DRY_RUN=1 docker compose -f docker/docker-compose.yaml run --rm -e DRY_RUN bot
```

Salida esperada:

```
WARNING  bot | DRY_RUN activo: no se envía nada a Telegram
INFO     ... | Programado morning-greeting a las 07:00
INFO     ... | Programado game-chance a las 07:15
INFO     ... | Programado good-night a las 22:00
INFO     ... | [DRY-RUN] <mensaje de arranque>
INFO     bot | Bot arrancado (Europe/Madrid)
```

`Ctrl+C` debe producir `Parado limpiamente` — confirma que el `SIGTERM` llega a
Python como PID 1 (depende del `CMD` en *exec form* del Dockerfile).

### Arranque real

```bash
docker compose -f docker/docker-compose.yaml up -d --build
docker compose -f docker/docker-compose.yaml logs -f
```

Buscar `Enviado: ...`. Si aparece `Fallo al enviar`, ver la tabla de diagnóstico
del `README.md` del repo.

### Alias

```bash
echo "alias dcb='docker compose -f /opt/bot2/docker/docker-compose.yaml'" >> ~/.bashrc
```

---

## 6. Persistencia tras reinicio

Tres capas independientes, las tres necesarias:

| Capa | Mecanismo | Dónde |
|---|---|---|
| CT arranca con el nodo | `onboot: 1` | Config del CT |
| Daemon Docker arranca con el CT | `systemctl enable docker` | Dentro del CT |
| Contenedor arranca con el daemon | `restart: unless-stopped` | `docker-compose.yaml` |

Prueba de la cadena completa, desde el nodo:

```bash
pct reboot 101
sleep 40 && pct exec 101 -- docker ps
```

---

## 7. Apagado y arranque programados

El cron vive **en el nodo**, no en el CT: un contenedor apagado no puede arrancarse
a sí mismo, y `pct` no existe dentro del CT.

```bash
# Desde el NODO
crontab -e
```

```cron
0  0 * * * /usr/sbin/pct shutdown 101 --timeout 60
45 6 * * * /usr/sbin/pct start 101
```

Detalles que importan:

- **Ruta absoluta.** El cron de root no hereda el `PATH` de la shell interactiva.
- **`shutdown`, no `stop`.** `shutdown` manda `SIGTERM` y espera; el bot lo maneja
  y registra `Parado limpiamente`. `stop` es un `SIGKILL`.
- **06:45, no 06:55.** Arranque del CT + daemon + posible build puede pasar de 5
  minutos. Si el bot arranca después de las 07:00, APScheduler descarta el job
  según el `misfire_grace_time` y el mensaje se pierde **sin error visible**.

Verificar la zona horaria del nodo, o el cron dispara desfasado:

```bash
date
timedatectl set-timezone Europe/Madrid
```

### Efecto secundario: `STARTUP_MESSAGE`

El mensaje de arranque se envía en **cada** arranque, por diseño. Con el cron
activo eso significa un mensaje diario al grupo a las 06:45. Dejar
`STARTUP_MESSAGE=` vacío en el `../../.env`.

### Solape con `onboot`

Si el nodo se reinicia fuera de la ventana prevista, el CT arranca ahí y sigue vivo
hasta el `shutdown` de medianoche. No rompe nada.

---

## 8. Errores encontrados y sus causas

| Síntoma | Causa | Solución |
|---|---|---|
| `404 Not Found (500)` al descargar plantilla | Versión del índice ya no está en el servidor | `pveam update` y usar el nombre de `pveam available` |
| `Permission denied` en SSH a root | Debian 12 bloquea root por defecto | `PermitRootLogin yes` |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | CT recreado, huella nueva | `ssh-keygen -R <IP>` **en el cliente** |
| `open sysctl net.ipv4.ip_unprivileged_port_start ... permission denied` | CVE-2025-52881 + AppArmor | Ver paso 2 |
| `pct: command not found` | Comando lanzado dentro del CT | Ejecutarlo en el nodo |
| `Could not chdir to home directory /root` | Flip `unprivileged` 1→0→1 desbarató los UIDs | Ver aviso abajo |

### ⚠ No cambiar `unprivileged` a mano

En un CT no privilegiado, el root interno es el uid `100000` del host; en uno
privilegiado es el uid `0`. Editar ese flag en el `.conf` de un CT ya creado deja
los ficheros con ownership inconsistente: `/root` deja de pertenecer al root del CT,
el prompt degenera a `-bash-5.2#` y servicios como Docker fallan al arrancar.

**No tiene arreglo práctico.** Destruir y recrear el CT.

### Distinguir dónde se está ejecutando cada comando

| Prompt | Ubicación | Comandos válidos |
|---|---|---|
| `root@zhenyax14` | Nodo Proxmox | `pct`, `qm`, `pveam`, `vzdump`, `/etc/pve/` |
| `root@tgbot` | Dentro del CT | `docker`, `apt`, `systemctl`, la app |

Todo lo que empiece por `pct` va **siempre** en el nodo.

---

## 9. Dimensionado — justificación

| Recurso | Asignado | Uso real | Nota |
|---|---|---|---|
| RAM | 512 MB | ~200-260 MB | Debian ~40 + dockerd ~120 + Python ~70 |
| Swap | 512 MB | — | Convierte un pico de OOM en lentitud |
| Disco | 5 GB | ~2-2.5 GB | Docker ~400 MB + imagen ~300 MB |
| CPU | 1 core | ~0% en reposo | El bot es I/O, no cómputo |

Llamar a APIs externas (Telegram, LLM) es I/O: unos 1-2 MB por conexión. **No
justifica más RAM ni más cores.** Ampliar en caliente si hiciera falta:

```bash
pct set 101 --memory 1024
pct set 101 --cores 2
pct resize 101 rootfs +2G   # + resize2fs dentro del CT
```

Medir antes de decidir:

```bash
pct exec 101 -- cat /sys/fs/cgroup/memory.peak
```

Crecimiento sostenido en vez de meseta = fuga, no falta de RAM.

---

## 10. Comandos de operación

```bash
# --- Desde el NODO ---
pct list
pct config 101
pct start 101 / pct shutdown 101 --timeout 60 / pct reboot 101
pct exec 101 -- docker ps
vzdump 101 --storage local --mode snapshot --compress zstd

# --- Dentro del CT ---
dcb ps
dcb logs -f
dcb logs --tail 50
dcb restart
dcb down && dcb up -d --build
dcb config                                    # variables expandidas
DRY_RUN=1 dcb run --rm -e DRY_RUN bot         # arranque en seco
```

Verificar credenciales sin arrancar la app:

```bash
set -a; source /opt/bot2/.env; set +a
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d chat_id="$CHAT_ID" -d text="ping"
```

`"ok":true` confirma token y chat.

---
