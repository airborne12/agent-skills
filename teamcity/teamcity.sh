#!/usr/bin/env bash
set -euo pipefail

# TeamCity CLI helper for Claude Code
# Config: ~/.teamcity.conf

CONF="${TEAMCITY_CONF:-$HOME/.teamcity.conf}"
if [[ ! -f "$CONF" ]]; then
  echo "ERROR: Config file not found: $CONF"
  echo "Create it with:"
  echo '  TEAMCITY_URL="http://43.132.222.7:8111"'
  echo '  TEAMCITY_TOKEN="your_token_here"'
  exit 1
fi
source "$CONF"

: "${TEAMCITY_URL:?TEAMCITY_URL not set in $CONF}"
: "${TEAMCITY_TOKEN:?TEAMCITY_TOKEN not set in $CONF}"

# Strip trailing slash
TEAMCITY_URL="${TEAMCITY_URL%/}"

# Optional: network interface (e.g. tun0 for VPN)
CURL_OPTS=(-s -H "Authorization: Bearer $TEAMCITY_TOKEN" -H "Accept: application/json")
if [[ -n "${TEAMCITY_INTERFACE:-}" ]]; then
  CURL_OPTS+=(--interface "$TEAMCITY_INTERFACE")
fi

tc_api() {
  local endpoint="$1"
  curl "${CURL_OPTS[@]}" "${TEAMCITY_URL}${endpoint}"
}

tc_api_text() {
  local endpoint="$1"
  curl -s -H "Authorization: Bearer $TEAMCITY_TOKEN" -H "Accept: text/plain" \
    ${TEAMCITY_INTERFACE:+--interface "$TEAMCITY_INTERFACE"} \
    "${TEAMCITY_URL}${endpoint}"
}

usage() {
  cat <<'EOF'
Usage: teamcity.sh <command> [args...]

Commands:
  projects                          List all projects
  configs [project_id]              List build configurations (optionally filter by project)
  builds <build_type_id> [branch]   List recent builds for a config (optionally filter by branch)
  build <build_id>                  Get build details by ID
  status <build_type_id> [branch]   Get latest build status for a config+branch
  problems <build_id>               Get build problems (failure reasons)
  tests <build_id> [status]         Get test results (optionally filter: FAILURE, SUCCESS)
  log <build_id>                    Download full build log
  log-tail <build_id> [lines]       Get last N lines of build log (default: 200)
  queue [build_type_id]             List queued builds
  running [build_type_id]           List running builds
  branch-builds <branch> [count]    Get builds across ALL configs for a branch
  diagnose <build_id>               Full failure diagnosis: status + problems + failed tests + log tail
  web <build_id>                    Print web URL for a build

  Doris Log Artifacts:
  log-urls <build_id>               Extract doris log archive URLs from build log
  log-download <build_id> [dir]     Download & extract doris log archives (default dir: /tmp/doris-logs)
  log-cat <build_id> [pattern]      Download, extract, and print matching log files (default: *.log)
  diagnose-logs <build_id>          Full diagnosis + auto-fetch doris log archives

EOF
  exit 1
}

cmd_projects() {
  tc_api "/app/rest/projects?fields=project(id,name,description)" | jq -r '
    .project[]? | "\(.id)\t\(.name)\t\(.description // "")"
  ' | column -t -s $'\t'
}

cmd_configs() {
  local url="/app/rest/buildTypes?fields=buildType(id,name,projectName,projectId)"
  if [[ -n "${1:-}" ]]; then
    url="/app/rest/buildTypes?locator=affectedProject:(id:$1)&fields=buildType(id,name,projectName,projectId)"
  fi
  tc_api "$url" | jq -r '.buildType[]? | "\(.id)\t\(.projectName)\t\(.name)"' | column -t -s $'\t'
}

cmd_builds() {
  local build_type_id="$1"
  local branch="${2:-}"
  local locator="buildType:(id:${build_type_id}),count:10,defaultFilter:false"
  if [[ -n "$branch" ]]; then
    locator="${locator},branch:(name:${branch})"
  fi
  tc_api "/app/rest/builds?locator=${locator}&fields=build(id,number,status,state,branchName,statusText,finishDate,webUrl)" \
    | jq -r '.build[]? | "\(.id)\t\(.number)\t\(.status // .state)\t\(.branchName // "default")\t\(.statusText // "")\t\(.finishDate // "")"' \
    | column -t -s $'\t'
}

cmd_build() {
  local build_id="$1"
  tc_api "/app/rest/builds/id:${build_id}?fields=id,number,status,state,statusText,branchName,buildType(id,name,projectName),webUrl,startDate,finishDate,agent(name),triggered(type,user(username)),problemOccurrences(count),testOccurrences(count,passed,failed,muted,ignored)" \
    | jq '.'
}

cmd_status() {
  local build_type_id="$1"
  local branch="${2:-}"
  local locator="buildType:(id:${build_type_id}),count:1,defaultFilter:false,state:finished"
  if [[ -n "$branch" ]]; then
    locator="${locator},branch:(name:${branch})"
  fi
  tc_api "/app/rest/builds?locator=${locator}&fields=build(id,number,status,state,statusText,branchName,webUrl,finishDate)" \
    | jq -r '.build[0]? // empty | "Build #\(.number) [\(.status)] \(.branchName // "default")\nStatus: \(.statusText // "N/A")\nFinished: \(.finishDate // "N/A")\nURL: \(.webUrl)"'
}

cmd_problems() {
  local build_id="$1"
  tc_api "/app/rest/problemOccurrences?locator=build:(id:${build_id})&fields=problemOccurrence(id,type,identity,details)" \
    | jq -r '.problemOccurrence[]? | "--- Problem: \(.type) ---\nIdentity: \(.identity // "N/A")\nDetails:\n\(.details // "No details")\n"'
}

cmd_tests() {
  local build_id="$1"
  local status_filter="${2:-}"
  local locator="build:(id:${build_id})"
  if [[ -n "$status_filter" ]]; then
    locator="${locator},status:${status_filter}"
  fi
  tc_api "/app/rest/testOccurrences?locator=${locator},count:100&fields=testOccurrence(id,name,status,duration,details)" \
    | jq -r '.testOccurrence[]? | "\(.status)\t\(.duration // 0)ms\t\(.name)\t\(.details // "" | split("\n")[0])"' \
    | column -t -s $'\t'
}

cmd_log() {
  local build_id="$1"
  tc_api_text "/downloadBuildLog.html?buildId=${build_id}"
}

cmd_log_tail() {
  local build_id="$1"
  local lines="${2:-200}"
  tc_api_text "/downloadBuildLog.html?buildId=${build_id}" | tail -n "$lines"
}

cmd_queue() {
  local locator=""
  if [[ -n "${1:-}" ]]; then
    locator="locator=buildType:(id:$1)&"
  fi
  tc_api "/app/rest/buildQueue?${locator}fields=build(id,number,buildTypeId,branchName,state,waitReason)" \
    | jq -r '.build[]? | "\(.id)\t\(.buildTypeId)\t\(.branchName // "default")\t\(.state)\t\(.waitReason // "")"' \
    | column -t -s $'\t'
}

cmd_running() {
  local locator="state:running"
  if [[ -n "${1:-}" ]]; then
    locator="${locator},buildType:(id:$1)"
  fi
  tc_api "/app/rest/builds?locator=${locator}&fields=build(id,number,buildTypeId,branchName,status,state,percentageComplete,statusText,webUrl)" \
    | jq -r '.build[]? | "\(.id)\t#\(.number)\t\(.buildTypeId)\t\(.branchName // "default")\t\(.percentageComplete // 0)%\t\(.statusText // "")"' \
    | column -t -s $'\t'
}

cmd_branch_builds() {
  local branch="$1"
  local count="${2:-5}"
  tc_api "/app/rest/builds?locator=branch:(name:${branch}),count:${count},defaultFilter:false&fields=build(id,number,status,state,buildType(id,name),branchName,statusText,finishDate,webUrl)" \
    | jq -r '.build[]? | "\(.id)\t\(.buildType.id)\t#\(.number)\t\(.status // .state)\t\(.statusText // "")\t\(.webUrl)"' \
    | column -t -s $'\t'
}

cmd_diagnose() {
  local build_id="$1"

  echo "===== BUILD DETAILS ====="
  cmd_build "$build_id"

  echo ""
  echo "===== BUILD PROBLEMS ====="
  local problems
  problems=$(cmd_problems "$build_id")
  if [[ -z "$problems" ]]; then
    echo "No build problems found."
  else
    echo "$problems"
  fi

  echo ""
  echo "===== FAILED TESTS ====="
  local failed_tests
  failed_tests=$(cmd_tests "$build_id" "FAILURE" 2>/dev/null)
  if [[ -z "$failed_tests" ]]; then
    echo "No failed tests."
  else
    echo "$failed_tests"
  fi

  echo ""
  echo "===== BUILD LOG (last 100 lines) ====="
  cmd_log_tail "$build_id" 100
}

cmd_web() {
  local build_id="$1"
  echo "${TEAMCITY_URL}/viewLog.html?buildId=${build_id}"
}

# --- Doris Log Artifact Commands ---

# OSS URL prefix for doris log archives
OSS_LOG_URL_PREFIX="http://opensource-pipeline.oss-cn-hongkong.aliyuncs.com/regression"

# Extract doris log archive URLs from build log
# Log upload always happens near the end, so we use tail to avoid downloading the full log (200MB+)
cmd_log_urls() {
  local build_id="$1"
  local tail_lines="${2:-10000}"
  tc_api_text "/downloadBuildLog.html?buildId=${build_id}" \
    | tail -n "$tail_lines" \
    | grep -oE "http://opensource-pipeline[^[:space:]'\"]*\.(tar\.gz|zip)" \
    | sort -u
}

# Download and extract doris log archives to a local directory
cmd_log_download() {
  local build_id="$1"
  local dest_dir="${2:-/tmp/doris-logs/${build_id}}"
  mkdir -p "$dest_dir"

  local urls
  urls=$(cmd_log_urls "$build_id")
  if [[ -z "$urls" ]]; then
    echo "No doris log archive URLs found in build $build_id"
    return 1
  fi

  echo "Found log archives:"
  echo "$urls"
  echo ""

  while IFS= read -r url; do
    local filename
    filename=$(basename "$url")
    echo "--- Downloading: $filename ---"
    if curl -s ${TEAMCITY_INTERFACE:+--interface "$TEAMCITY_INTERFACE"} \
         -o "${dest_dir}/${filename}" "$url"; then
      echo "  Saved to: ${dest_dir}/${filename}"
      # Auto-extract based on file type
      if [[ "$filename" == *.tar.gz || "$filename" == *.tgz ]]; then
        echo "  Extracting tar.gz..."
        tar -xzf "${dest_dir}/${filename}" -C "$dest_dir" 2>/dev/null && \
          echo "  Extracted to: ${dest_dir}/" || \
          echo "  WARNING: extraction failed"
      elif [[ "$filename" == *.zip ]]; then
        echo "  Extracting zip..."
        unzip -qo "${dest_dir}/${filename}" -d "$dest_dir" 2>/dev/null && \
          echo "  Extracted to: ${dest_dir}/" || \
          echo "  WARNING: extraction failed"
      fi
    else
      echo "  ERROR: download failed"
    fi
  done <<< "$urls"

  echo ""
  echo "All files in ${dest_dir}/:"
  find "$dest_dir" -type f -name "*.log" -o -name "*.out" -o -name "*.conf" | sort
}

# Download, extract, and print matching log file contents
cmd_log_cat() {
  local build_id="$1"
  local pattern="${2:-*.log}"
  local dest_dir="/tmp/doris-logs/${build_id}"

  # Download if not already extracted
  if [[ ! -d "$dest_dir" ]] || [[ -z "$(find "$dest_dir" -name "$pattern" -type f 2>/dev/null)" ]]; then
    cmd_log_download "$build_id" "$dest_dir" >/dev/null 2>&1
  fi

  local log_files
  log_files=$(find "$dest_dir" -type f -name "$pattern" | sort)
  if [[ -z "$log_files" ]]; then
    echo "No files matching '$pattern' found in build $build_id logs"
    return 1
  fi

  while IFS= read -r f; do
    local rel_path="${f#${dest_dir}/}"
    echo "===== ${rel_path} (last 200 lines) ====="
    tail -n 200 "$f"
    echo ""
  done <<< "$log_files"
}

# Full diagnosis with doris log archive auto-fetch
cmd_diagnose_logs() {
  local build_id="$1"

  # Run standard diagnosis first
  cmd_diagnose "$build_id"

  echo ""
  echo "===== DORIS LOG ARCHIVES ====="
  local urls
  urls=$(cmd_log_urls "$build_id")
  if [[ -z "$urls" ]]; then
    echo "No doris log archives found for this build."
    return 0
  fi

  echo "Found log archive URLs:"
  echo "$urls"
  echo ""

  local dest_dir="/tmp/doris-logs/${build_id}"
  cmd_log_download "$build_id" "$dest_dir" >/dev/null 2>&1

  # Print key log files: fe.log, be.out, be.INFO (last 100 lines each)
  for log_name in "fe/log/fe.log" "fe/log/fe.warn.log" "be/log/be.out" "be/log/be.INFO" "be/log/be.WARNING"; do
    local log_file
    log_file=$(find "$dest_dir" -path "*${log_name}" -type f 2>/dev/null | head -1)
    if [[ -n "$log_file" ]]; then
      echo ""
      echo "===== ${log_name} (last 100 lines) ====="
      tail -n 100 "$log_file"
    fi
  done

  # Print regression test logs if present
  local reg_logs
  reg_logs=$(find "$dest_dir" -path "*/regression-test/log/*" -name "*.log" -type f 2>/dev/null)
  if [[ -n "$reg_logs" ]]; then
    while IFS= read -r f; do
      local rel_path="${f#${dest_dir}/}"
      echo ""
      echo "===== ${rel_path} (last 100 lines) ====="
      tail -n 100 "$f"
    done <<< "$reg_logs"
  fi
}

# Main dispatch
[[ $# -lt 1 ]] && usage

cmd="$1"
shift

case "$cmd" in
  projects)       cmd_projects ;;
  configs)        cmd_configs "${1:-}" ;;
  builds)         [[ $# -lt 1 ]] && { echo "Usage: builds <build_type_id> [branch]"; exit 1; }; cmd_builds "$@" ;;
  build)          [[ $# -lt 1 ]] && { echo "Usage: build <build_id>"; exit 1; }; cmd_build "$1" ;;
  status)         [[ $# -lt 1 ]] && { echo "Usage: status <build_type_id> [branch]"; exit 1; }; cmd_status "$@" ;;
  problems)       [[ $# -lt 1 ]] && { echo "Usage: problems <build_id>"; exit 1; }; cmd_problems "$1" ;;
  tests)          [[ $# -lt 1 ]] && { echo "Usage: tests <build_id> [FAILURE|SUCCESS]"; exit 1; }; cmd_tests "$@" ;;
  log)            [[ $# -lt 1 ]] && { echo "Usage: log <build_id>"; exit 1; }; cmd_log "$1" ;;
  log-tail)       [[ $# -lt 1 ]] && { echo "Usage: log-tail <build_id> [lines]"; exit 1; }; cmd_log_tail "$@" ;;
  queue)          cmd_queue "${1:-}" ;;
  running)        cmd_running "${1:-}" ;;
  branch-builds)  [[ $# -lt 1 ]] && { echo "Usage: branch-builds <branch> [count]"; exit 1; }; cmd_branch_builds "$@" ;;
  diagnose)       [[ $# -lt 1 ]] && { echo "Usage: diagnose <build_id>"; exit 1; }; cmd_diagnose "$1" ;;
  web)            [[ $# -lt 1 ]] && { echo "Usage: web <build_id>"; exit 1; }; cmd_web "$1" ;;
  log-urls)       [[ $# -lt 1 ]] && { echo "Usage: log-urls <build_id>"; exit 1; }; cmd_log_urls "$1" ;;
  log-download)   [[ $# -lt 1 ]] && { echo "Usage: log-download <build_id> [dir]"; exit 1; }; cmd_log_download "$@" ;;
  log-cat)        [[ $# -lt 1 ]] && { echo "Usage: log-cat <build_id> [pattern]"; exit 1; }; cmd_log_cat "$@" ;;
  diagnose-logs)  [[ $# -lt 1 ]] && { echo "Usage: diagnose-logs <build_id>"; exit 1; }; cmd_diagnose_logs "$1" ;;
  *)              echo "Unknown command: $cmd"; usage ;;
esac
