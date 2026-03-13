---
name: deploy-doris
description: Deploy Apache Doris locally from compiled output. Use this skill when the user says "部署 doris", "deploy doris", "重新部署", "redeploy doris", or wants to copy build artifacts and start a local Doris cluster. Also triggers for "启动 FE/BE" or "start FE/BE" when in the Doris repo context.
---

# Deploy Doris Locally

Deploy a compiled Doris build and start a local single-node cluster.

## Configuration

Before using this skill, determine the following paths. If not explicitly provided by the user, use these defaults or auto-detect:

| Variable | How to determine | Default |
|----------|-----------------|---------|
| `REPO_ROOT` | The Doris repo root (where `build.sh` lives) | Current working directory if it contains `build.sh` |
| `DEPLOY_DIR` | Where to deploy Doris | `$REPO_ROOT/../doris-deploy` |
| `JAVA_HOME` | JDK 17+ installation | Auto-detect via `/usr/libexec/java_home` (macOS) or existing `$JAVA_HOME` env var |
| `MYSQL_BIN` | Path to `mysql` client binary | Auto-detect via `which mysql` |

On macOS with Homebrew, typical values:
- `JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`
- `MYSQL_BIN=/opt/homebrew/opt/mysql-client/bin/mysql`

## Paths

- **Source (build output):** `$REPO_ROOT/output/`
  - `output/fe/` → FE artifacts
  - `output/be/` → BE artifacts
- **Target (deploy dir):** `$DEPLOY_DIR/`
  - `fe/` — Frontend installation
  - `be/` — Backend installation

## Deployment Modes

The user may request:
- **Full deploy** (default): Deploy both FE and BE
- **FE only**: `--fe` — only deploy and start Frontend
- **BE only**: `--be` — only deploy and start Backend

## Clean Mode

- **Default**: Preserve existing data (`doris-meta/`, `storage/`, `log/`)
- **`--clean`**: Remove `doris-meta/`, `storage/`, and `log/` for a fresh start

## Prerequisites

Before every command that uses `mysql` or starts FE/BE, you MUST:

1. **Unset all proxy vars** — FE/BE start scripts reject `HTTP_PROXY`/`ALL_PROXY`:
   ```bash
   unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
   ```
2. **Ensure mysql client is on PATH** (if not already):
   ```bash
   export PATH="$(dirname $MYSQL_BIN):$PATH"
   ```
3. **Set JAVA_HOME**:
   ```bash
   export JAVA_HOME="$JAVA_HOME"
   ```

Combine these into a single prefix for every shell command:
```bash
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy && export PATH="$(dirname $MYSQL_BIN):$PATH" && export JAVA_HOME="$JAVA_HOME"
```

**Note:** Homebrew's mysql-client doesn't support `\G` in `-e` mode. Use plain SQL output (no `\G`).

## Step-by-Step Procedure

### 1. Stop existing processes

Always stop running processes before copying new binaries to avoid corruption.

```bash
cd $DEPLOY_DIR 2>/dev/null && be/bin/stop_be.sh 2>/dev/null || true; fe/bin/stop_fe.sh 2>/dev/null || true
# Verify nothing is still running
pgrep -f "doris_be|PaloFe|DorisFE" && echo "WARNING: processes still running" || echo "All stopped"
```

### 2. Copy build artifacts

```bash
# For FE:
mkdir -p $DEPLOY_DIR/fe
# Preserve data dirs if not --clean
cp -r $REPO_ROOT/output/fe/bin $DEPLOY_DIR/fe/
cp -r $REPO_ROOT/output/fe/conf $DEPLOY_DIR/fe/
cp -r $REPO_ROOT/output/fe/lib $DEPLOY_DIR/fe/
cp -r $REPO_ROOT/output/fe/webroot $DEPLOY_DIR/fe/ 2>/dev/null || true
cp -r $REPO_ROOT/output/fe/plugins $DEPLOY_DIR/fe/ 2>/dev/null || true
mkdir -p $DEPLOY_DIR/fe/log $DEPLOY_DIR/fe/doris-meta

# For BE:
mkdir -p $DEPLOY_DIR/be
cp -r $REPO_ROOT/output/be/bin $DEPLOY_DIR/be/
cp -r $REPO_ROOT/output/be/conf $DEPLOY_DIR/be/
cp -r $REPO_ROOT/output/be/lib $DEPLOY_DIR/be/
cp -r $REPO_ROOT/output/be/www $DEPLOY_DIR/be/ 2>/dev/null || true
mkdir -p $DEPLOY_DIR/be/log $DEPLOY_DIR/be/storage
```

If `--clean` was requested, before copying:
```bash
rm -rf $DEPLOY_DIR/fe/doris-meta $DEPLOY_DIR/fe/log
rm -rf $DEPLOY_DIR/be/storage $DEPLOY_DIR/be/log
```

### 3. Start FE

All commands must include the prerequisite env setup (unset proxies, PATH, JAVA_HOME) chained with `&&`.

```bash
<prereqs> && cd $DEPLOY_DIR/fe && bin/start_fe.sh --daemon
```

Wait for FE to be ready (poll MySQL port 9030, up to 60 seconds):
```bash
<prereqs> && for i in $(seq 1 30); do
  mysql -h127.0.0.1 -P9030 -uroot -e "SHOW FRONTENDS" 2>/dev/null && break
  sleep 2
done
```

### 4. Start BE

```bash
<prereqs> && cd $DEPLOY_DIR/be && bin/start_be.sh --daemon
```

Wait a few seconds for BE process to start:
```bash
sleep 3 && pgrep -f doris_be > /dev/null && echo "BE process started" || echo "ERROR: BE failed to start"
```

### 5. Add BE backend

Always attempt to add the backend — on non-clean deploys it will error with "already exists" which is safe to ignore.

```bash
<prereqs> && mysql -h127.0.0.1 -P9030 -uroot -e "ALTER SYSTEM ADD BACKEND '127.0.0.1:9050';" 2>&1 || true
```

### 6. Verify BE is alive

Poll until the Alive column shows `true` (column 10 in tab-separated SHOW BACKENDS output):

```bash
<prereqs> && for i in $(seq 1 15); do
  alive=$(mysql -h127.0.0.1 -P9030 -uroot -N -e "SHOW BACKENDS" 2>/dev/null | awk -F'\t' '{print $10}')
  if [ "$alive" = "true" ]; then
    echo "BE is alive!"
    mysql -h127.0.0.1 -P9030 -uroot -e "SHOW BACKENDS"
    break
  fi
  echo "Waiting for BE alive... ($i/15)"
  sleep 2
done
```

### 7. Final status summary

Print a summary showing:
- FE status (running/not, PID)
- BE status (alive/not, PID)
- Connection info: `mysql -h127.0.0.1 -P9030 -uroot`
- FE Web UI: `http://127.0.0.1:8030`
- BE Web UI: `http://127.0.0.1:8040`

## Default Ports Reference

| Service | Port | Purpose |
|---------|------|---------|
| FE HTTP | 8030 | Web UI |
| FE Query | 9030 | MySQL protocol |
| FE RPC | 9020 | Internal RPC |
| FE Edit Log | 9010 | Raft consensus |
| BE Heartbeat | 9050 | Used in ADD BACKEND |
| BE Thrift | 9060 | FE-BE communication |
| BE HTTP | 8040 | Web UI |
| BE BRPC | 8060 | Internal BRPC |

## Troubleshooting

- **FE won't start**: Check `fe/log/fe.out` and `fe/log/fe.log` for errors. Common issue: port already in use.
- **BE won't start**: Check `be/log/be.out` and `be/log/be.INFO` for errors. On macOS, `vm.max_map_count` warning can be ignored.
- **BE not becoming alive**: Check `be/log/be.WARNING` — often a port conflict or FE can't reach BE on heartbeat port.
- **"Backend already exists"**: Safe to ignore on non-clean deploys.
