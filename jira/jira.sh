#!/bin/bash
# Jira API helper script
# Usage: bash jira.sh <command> [args...]
#   view <ISSUE_KEY>           - View issue details
#   search <JQL>               - Search issues with JQL
#   comment <ISSUE_KEY> <BODY> - Add comment to issue
#   create <PROJECT> <TYPE> <SUMMARY> [DESC] [ASSIGNEE] - Create issue
#   transitions <ISSUE_KEY>    - List available transitions
#   transition <ISSUE_KEY> <ID> [COMMENT] - Transition issue

set -euo pipefail

source ~/.jira.conf
unset HTTP_PROXY http_proxy HTTPS_PROXY https_proxy 2>/dev/null || true

AUTH_HEADER="Authorization: Bearer $JIRA_TOKEN"

jira_curl() {
    curl -s -H "$AUTH_HEADER" "$@"
}

cmd_view() {
    local key="$1"
    jira_curl "$JIRA_URL/rest/api/2/issue/$key?fields=summary,status,assignee,reporter,description,comment,issuetype,priority,created,updated" \
    | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'errorMessages' in d:
    print('Error:', '; '.join(d['errorMessages']))
    sys.exit(1)
f=d['fields']
key=d['key']
print(f'Key:      {key}')
print(f'Type:     {f[\"issuetype\"][\"name\"]}')
print(f'Summary:  {f[\"summary\"]}')
print(f'Status:   {f[\"status\"][\"name\"]}')
print(f'Priority: {(f.get(\"priority\") or {}).get(\"name\",\"N/A\")}')
print(f'Assignee: {(f.get(\"assignee\") or {}).get(\"displayName\",\"Unassigned\")}')
print(f'Reporter: {(f.get(\"reporter\") or {}).get(\"displayName\",\"N/A\")}')
print(f'Created:  {f[\"created\"]}')
print(f'Updated:  {f[\"updated\"]}')
desc = f.get('description') or '(none)'
print(f'--- Description ---')
print(desc[:5000])
comments = (f.get('comment') or {}).get('comments',[])
if comments:
    print(f'--- Comments ({len(comments)}) ---')
    for c in comments[-5:]:
        print(f'  [{c[\"created\"][:10]}] {c[\"author\"][\"displayName\"]}: {c[\"body\"][:200]}')
"
}

cmd_search() {
    local jql="$1"
    jira_curl --get \
        --data-urlencode "jql=$jql" \
        --data-urlencode "fields=key,summary,status,assignee,priority,updated" \
        --data-urlencode "maxResults=20" \
        "$JIRA_URL/rest/api/2/search" \
    | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'errorMessages' in d:
    print('Error:', '; '.join(d['errorMessages']))
    sys.exit(1)
print(f'Total: {d[\"total\"]} (showing {len(d[\"issues\"])})')
for i in d['issues']:
    f=i['fields']
    status=f['status']['name']
    assignee=(f.get('assignee') or {}).get('displayName','Unassigned')
    print(f'  {i[\"key\"]:12s} [{status:15s}] {f[\"summary\"][:60]}')
"
}

cmd_comment() {
    local key="$1"
    local body="$2"
    jira_curl -X POST \
        -H "Content-Type: application/json" \
        -d "$(python3 -c "import json; print(json.dumps({'body': '$body'}))")" \
        "$JIRA_URL/rest/api/2/issue/$key/comment" \
    | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'errorMessages' in d:
    print('Error:', '; '.join(d['errorMessages']))
    sys.exit(1)
print(f'Comment added by {d[\"author\"][\"displayName\"]} at {d[\"created\"]}')
"
}

cmd_transitions() {
    local key="$1"
    jira_curl "$JIRA_URL/rest/api/2/issue/$key/transitions" \
    | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'errorMessages' in d:
    print('Error:', '; '.join(d['errorMessages']))
    sys.exit(1)
for t in d['transitions']:
    print(f'  ID: {t[\"id\"]:4s} -> {t[\"name\"]} (to: {t[\"to\"][\"name\"]})')
"
}

cmd_create() {
    local project="$1"
    local issuetype="$2"
    local summary="$3"
    local description="${4:-}"
    local assignee="${5:-$JIRA_USER}"
    local data
    data=$(python3 -c "
import json,sys
project, issuetype, summary, description, assignee = sys.argv[1:6]
fields = {
    'project': {'key': project},
    'issuetype': {'name': issuetype},
    'summary': summary,
}
if description:
    fields['description'] = description
if assignee:
    fields['assignee'] = {'name': assignee}
print(json.dumps({'fields': fields}))
" "$project" "$issuetype" "$summary" "$description" "$assignee")
    jira_curl -X POST \
        -H "Content-Type: application/json" \
        -d "$data" \
        "$JIRA_URL/rest/api/2/issue" \
    | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'errorMessages' in d:
    print('Error:', '; '.join(d['errorMessages']))
    sys.exit(1)
if 'errors' in d and d['errors']:
    print('Error:', '; '.join(f'{k}: {v}' for k,v in d['errors'].items()))
    sys.exit(1)
print(f'Created: {d[\"key\"]}')
print(f'URL:     $JIRA_URL/browse/{d[\"key\"]}')
"
}

cmd_transition() {
    local key="$1"
    local tid="$2"
    local comment="${3:-}"
    local data
    if [ -n "$comment" ]; then
        data="{\"transition\":{\"id\":\"$tid\"},\"update\":{\"comment\":[{\"add\":{\"body\":\"$comment\"}}]}}"
    else
        data="{\"transition\":{\"id\":\"$tid\"}}"
    fi
    local response
    response=$(jira_curl -X POST \
        -H "Content-Type: application/json" \
        -d "$data" \
        -w "\nHTTP_CODE:%{http_code}" \
        "$JIRA_URL/rest/api/2/issue/$key/transitions")
    local http_code=$(echo "$response" | grep "HTTP_CODE:" | cut -d: -f2)
    if [ "$http_code" = "204" ] || [ "$http_code" = "200" ]; then
        echo "Transition successful for $key (transition ID: $tid)"
    else
        echo "Transition failed (HTTP $http_code):"
        echo "$response" | grep -v "HTTP_CODE:"
    fi
}

case "${1:-help}" in
    view)        cmd_view "$2" ;;
    search)      cmd_search "$2" ;;
    comment)     cmd_comment "$2" "$3" ;;
    create)      cmd_create "$2" "$3" "$4" "${5:-}" "${6:-}" ;;
    transitions) cmd_transitions "$2" ;;
    transition)  cmd_transition "$2" "$3" "${4:-}" ;;
    *)
        echo "Usage: bash jira.sh <command> [args...]"
        echo "  view <KEY>                    - View issue details"
        echo "  search '<JQL>'                - Search with JQL"
        echo "  comment <KEY> '<body>'        - Add comment"
        echo "  create <PROJ> <TYPE> <SUMMARY> [DESC] [ASSIGNEE] - Create issue"
        echo "  transitions <KEY>             - List transitions"
        echo "  transition <KEY> <ID> [comment] - Do transition"
        ;;
esac
