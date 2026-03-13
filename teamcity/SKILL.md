---
name: teamcity
description: Use when the user asks about CI/CD pipeline status, build failures, build logs, or mentions a TeamCity build. Also use when checking if a branch or PR passed CI, diagnosing build failures, or retrieving build problems and test results.
---

# TeamCity Pipeline Integration

## Overview

Query TeamCity builds via REST API. Check build status by branch/PR, diagnose failures with build problems + failed tests + log tail.

## Configuration

Credentials in `~/.teamcity.conf`:

```bash
TEAMCITY_URL="http://43.132.222.7:8111"
TEAMCITY_TOKEN='your_token_here'
# TEAMCITY_INTERFACE="tun0"    # Optional: VPN interface
```

For multiple TeamCity instances, set `TEAMCITY_CONF` env var to point to a different config:

```bash
TEAMCITY_CONF=~/.teamcity-staging.conf bash ~/.claude/skills/teamcity/teamcity.sh status MyProject_Build feature/login
```

## Helper Script

Use `~/.claude/skills/teamcity/teamcity.sh` for all operations:

```bash
bash ~/.claude/skills/teamcity/teamcity.sh <command> [args...]
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `projects` | List all projects |
| `configs [project_id]` | List build configurations |
| `builds <config_id> [branch]` | Recent builds for a config, optionally by branch |
| `build <build_id>` | Full build details (JSON) |
| `status <config_id> [branch]` | Latest finished build status |
| `problems <build_id>` | Build problems (failure reasons) |
| `tests <build_id> [FAILURE]` | Test results, filter by status |
| `log <build_id>` | Full build log |
| `log-tail <build_id> [lines]` | Last N lines of log (default 200) |
| `diagnose <build_id>` | Full diagnosis: details + problems + failed tests + log tail |
| `branch-builds <branch> [count]` | Builds across ALL configs for a branch |
| `queue [config_id]` | Queued builds |
| `running [config_id]` | Running builds |
| `web <build_id>` | Print web URL for build |

## Typical Workflows

### Check branch CI status

```bash
# Find the build config ID first
bash ~/.claude/skills/teamcity/teamcity.sh configs

# Check latest status for a branch
bash ~/.claude/skills/teamcity/teamcity.sh status MyProject_Build feature/my-branch

# Or find all builds for a branch across configs
bash ~/.claude/skills/teamcity/teamcity.sh branch-builds feature/my-branch
```

### Diagnose a failed build

```bash
# One-command full diagnosis
bash ~/.claude/skills/teamcity/teamcity.sh diagnose <build_id>

# Or step by step:
bash ~/.claude/skills/teamcity/teamcity.sh problems <build_id>
bash ~/.claude/skills/teamcity/teamcity.sh tests <build_id> FAILURE
bash ~/.claude/skills/teamcity/teamcity.sh log-tail <build_id> 300
```

### Check PR pipeline (branch-based)

TeamCity tracks PRs via branch names. For GitHub PRs, the branch name is typically `refs/pull/<number>/merge` or the source branch name:

```bash
# Try source branch name first
bash ~/.claude/skills/teamcity/teamcity.sh branch-builds feature/add-auth

# Or try PR ref
bash ~/.claude/skills/teamcity/teamcity.sh branch-builds "refs/pull/123/merge"
```

## REST API Reference (manual curl)

```bash
source ~/.teamcity.conf
curl -s -H "Authorization: Bearer $TEAMCITY_TOKEN" -H "Accept: application/json" \
  "${TEAMCITY_URL}/app/rest/builds?locator=buildType:(id:CONFIG_ID),branch:(name:BRANCH),count:5,defaultFilter:false&fields=build(id,number,status,branchName,statusText,webUrl)"
```

Key endpoints:

| Operation | Endpoint |
|-----------|----------|
| List builds | `/app/rest/builds?locator=...` |
| Build details | `/app/rest/builds/id:<id>` |
| Build problems | `/app/rest/problemOccurrences?locator=build:(id:<id>)` |
| Test results | `/app/rest/testOccurrences?locator=build:(id:<id>)` |
| Build log | `/downloadBuildLog.html?buildId=<id>` |
| Build configs | `/app/rest/buildTypes` |
| Projects | `/app/rest/projects` |

### Build Locator Dimensions

| Dimension | Example | Purpose |
|-----------|---------|---------|
| `buildType` | `buildType:(id:MyProject_Build)` | Filter by config |
| `branch` | `branch:(name:main)` | Filter by branch |
| `status` | `status:FAILURE` | SUCCESS, FAILURE, UNKNOWN |
| `state` | `state:finished` | queued, running, finished, any |
| `count` | `count:10` | Limit results |
| `defaultFilter` | `defaultFilter:false` | Include non-default branches |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Only seeing default branch builds | Add `defaultFilter:false` to locator |
| Branch not found | Try exact branch name from VCS, including `refs/...` prefix |
| 401 Unauthorized | Check token in `~/.teamcity.conf`, ensure single quotes around token |
| Empty log output | Use `/downloadBuildLog.html` not `/app/rest/` for logs |
| Can't find build config ID | Run `configs` command first to list all IDs |

## Doris Regression Pipeline — Log Analysis

The Doris CI pipeline runs regression tests on a deployed cluster. When builds fail (especially due to BE crashes), the `diagnose` command alone is often insufficient because:
- The build log tail is dominated by coverage upload steps, not crash info
- Crash details (be.out, core dumps) are embedded deep inside the full build log or in a separately uploaded log archive

### Step-by-step Crash Diagnosis

#### Step 1: Initial Triage

Start with `diagnose` to get an overview, then check if all test failures share the same root cause:

```bash
SKILL_DIR="$(dirname "$(readlink -f "$0")" 2>/dev/null || echo "$HOME/.gemini/antigravity/skills/teamcity")"
TC="bash $SKILL_DIR/teamcity.sh"

$TC diagnose <build_id>
```

If all failed tests show the same error like `No backend available as scan node` or `Connection refused`, this indicates a BE crash or startup failure — not individual test bugs.

#### Step 2: Search Build Log for Crash Indicators

Use `log` + `grep` to search the full build log for specific patterns. The full log is very large, so always pipe through `grep`:

```bash
# Check for ASAN errors (AddressSanitizer)
$TC log <build_id> | grep -i -B 2 -A 30 \
  "ASAN|AddressSanitizer|heap-buffer-overflow|use-after-free|SUMMARY:.*Sanitizer"

# Check for classic crash signals
$TC log <build_id> | grep -i -B 2 -A 10 \
  "SIGSEGV|SIGABRT|signal|Segmentation|core dump|CHECK failed|DORIS_CHECK"

# Check if BE was alive and when it died
$TC log <build_id> | grep -i -B 2 -A 10 \
  "be is not alive|not alive|No backend available|Connection refused.*8042"

# Check core dump detection results
$TC log <build_id> | grep -i -B 2 -A 20 \
  "we got corename|no core dump|core is not empty|after check core|exit_flag"

# Check if BE process was found dead
$TC log <build_id> | grep -i -B 2 -A 5 \
  "No such process|be.*pid|stop_be"
```

#### Step 3: Find and Download Log Archive

Failed builds upload a log tarball to Alibaba Cloud OSS. Search for the download URL:

```bash
# Find the log archive URL
$TC log <build_id> | grep -i "if you need fail regression log" -A 1

# Also check for coredump archive URL
$TC log <build_id> | grep -i "core file http"
```

This typically prints URLs like:
```
http://opensource-pipeline.oss-cn-hongkong.aliyuncs.com/regression/OpenSourcePiplineRegression_<timestamp>_<pr>_<commit>_<pipeline>.tar.gz
```

Download and extract the archive:
```bash
curl -sL "<log_archive_url>" -o /tmp/pipeline_log.tar.gz
tar xzf /tmp/pipeline_log.tar.gz -C /tmp/
```

#### Step 4: Examine Key Files in the Archive

The extracted archive has this structure:
```
<pr_id>_<commit>_<pipeline_name>/
├── be/
│   ├── conf/
│   │   └── be.conf              # BE configuration — check priority_networks, ports
│   └── log/
│       ├── be.out               # ★ Most critical: crash stack traces appear here
│       ├── be.INFO.log.*        # Detailed BE info log
│       ├── be.WARNING.log.*     # BE warning/error log
│       ├── be.gc.log.*          # JVM GC logs
│       └── jni.log              # JNI/Java side logs
├── fe/
│   ├── conf/                    # FE configuration
│   └── log/
│       ├── fe.log               # FE main log
│       ├── fe.warn.log          # FE warnings
│       └── fe.out               # FE console output
├── dmesg.txt                    # Kernel messages — check for OOM killer
├── doris-regression-test.*.log  # Regression test runner log
├── docker_logs/                 # Third-party container logs (hive, mysql, etc.)
└── show_variables/              # Cluster variable dumps
```

**Key files to check, in priority order:**

1. **`be/log/be.out`** — Contains crash stack traces (ASAN errors, SEGV signals, CHECK failures). Two startup sequences may appear if the pipeline restarts BE. Look for:
   - `AddressSanitizer` errors with stack traces
   - `SIGSEGV` / `SIGABRT` signal handlers
   - `CHECK failed` or `DORIS_CHECK` assertion failures
   - LSAN "Suppressions used" lines (these appear at normal process exit — if they appear without preceding crash info, the process exited cleanly or was killed externally)

2. **`be/log/be.WARNING.log.*`** — Contains WARNING and ERROR level logs. Often has initialization errors.

3. **`be/log/be.INFO.log.*`** — Full info log. Note: if BE was restarted, this file may only contain logs from the **second** startup (the first startup's logs get overwritten). Check the PID in log entries to distinguish startups.

4. **`be/conf/be.conf`** — Check for misconfiguration:
   - `priority_networks` — must match the network the FE/pipeline uses to reach BE
   - Port settings (`be_port`, `heartbeat_service_port`, `webserver_port`, `brpc_port`)

5. **`dmesg.txt`** — Check for OOM killer events:
   ```bash
   grep -i "oom\|killed\|out of memory\|doris" /tmp/<archive>/dmesg.txt
   ```

6. **`doris-regression-test.*.log`** — The regression test runner log. First few lines show connection config. Check initial errors to see if BE was already dead when tests started:
   ```bash
   head -50 /tmp/<archive>/doris-regression-test.*.log
   grep -m 5 "ERROR\|not alive\|Connection refused" /tmp/<archive>/doris-regression-test.*.log
   ```

7. **`fe/log/fe.log`** — If BE reported alive but queries fail, check FE logs for backend status changes.

### Common Crash Patterns

| Pattern | Where to Find | Meaning |
|---------|--------------|---------|
| `AddressSanitizer: heap-buffer-overflow` | be.out | Memory corruption bug in BE C++ code |
| `AddressSanitizer: use-after-free` | be.out | Dangling pointer access |
| `SIGSEGV` / `Segmentation fault` | be.out | Null pointer or invalid memory access |
| `CHECK failed` / `DORIS_CHECK` | be.out | Assertion failure in BE code |
| `No backend available as scan node` | build log / regression log | BE is dead or unreachable from FE |
| `Connection refused` to port 8042 | build log | BE HTTP server is down |
| `kill: (PID) - No such process` | build log | BE process already died before stop |
| `no core dump file` + clean LSAN exit | build log + be.out | BE was killed externally (OOM) or network misconfiguration |
| `oom_kill_process` / `Out of memory` | dmesg.txt | Kernel OOM killer terminated BE |
| LSAN Suppressions without crash trace | be.out | Clean exit — likely killed by signal or network issue, not a code bug |
| `priority_networks=127.0.0.1/24` + `Connection refused` on external IP | be.conf + build log | BE bound to localhost but pipeline connects via external IP |

### Distinguishing Code Bugs vs Infrastructure Issues

**Code bug indicators:**
- ASAN error with stack trace in be.out → points to exact source file and line
- CHECK/DORIS_CHECK failure → assertion violated in logic
- Crash happens reproducibly during a specific test

**Infrastructure issue indicators:**
- All tests fail with the same "BE not alive" error
- No crash trace in be.out (clean LSAN exit)
- `be.conf` misconfiguration (priority_networks, ports)
- `dmesg.txt` shows OOM kill
- BE was dead before tests even started
- Failed tests span unrelated categories (JDBC, MTMV, CDC, auth, etc.)
