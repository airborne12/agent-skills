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
  *)              echo "Unknown command: $cmd"; usage ;;
esac
