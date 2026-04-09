#!/bin/bash
# Ralph Wiggum Loop - Autonomous AI Agent for PRD Execution
#
# Usage: ./scripts/ralph/ralph.sh [prd_file] [max_iterations]
#
# Example:
#   ./scripts/ralph/ralph.sh logs/sprints/2026-04-06T1400_MY_PROJECT/PRD.json 15
#
# PRD JSON must have:
#   - userStories[] with: id, title, description, acceptanceCriteria[], passes
#
# Each story runs in a FRESH Claude context window.
# State persists through: git commits, progress log, PRD passes flags.
#
# REAL-TIME MONITORING:
#   tail -f logs/sprints/<folder>/ralph/LIVE.log

set -e

PRD_FILE="${1:-logs/sprints/example/PRD.json}"
MAX_ITERATIONS=${2:-20}
ITERATION=0

PRD_DIR=$(dirname "$PRD_FILE")
PRD_NAME=$(basename "$PRD_FILE" .json)

if [[ "$PRD_NAME" == "PRD" ]]; then
    RALPH_DIR="${PRD_DIR}/ralph"
    PROGRESS_FILE="${PRD_DIR}/PROGRESS.txt"
    mkdir -p "$RALPH_DIR"
    LOG_FILE="${RALPH_DIR}/run_$(date +%Y%m%d_%H%M%S).log"
    LIVE_FILE="${RALPH_DIR}/LIVE.log"
else
    PROGRESS_FILE="${PRD_DIR}/${PRD_NAME}_PROGRESS.txt"
    LOG_FILE="${PRD_DIR}/ralph_run_$(date +%Y%m%d_%H%M%S).log"
    LIVE_FILE="${PRD_DIR}/LIVE_RALPH.log"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

init_live_file() {
    cat > "$LIVE_FILE" << EOF
╔══════════════════════════════════════════════════════════════════════════════╗
║  RALPH WIGGUM LOOP - LIVE STATUS                                             ║
║  Monitor with: tail -f ${LIVE_FILE}                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Started: $(date)
PRD: ${PRD_FILE}

EOF
}

live() {
    local timestamp=$(date '+%H:%M:%S')
    echo "[$timestamp] $@" >> "$LIVE_FILE"
}

log() {
    local level=$1
    shift
    local msg="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local short_ts=$(date '+%H:%M:%S')

    case $level in
        INFO)  echo -e "${BLUE}[$timestamp]${NC} $msg" ;;
        OK)    echo -e "${GREEN}[$timestamp] ✓${NC} $msg" ;;
        WARN)  echo -e "${YELLOW}[$timestamp] ⚠${NC} $msg" ;;
        ERROR) echo -e "${RED}[$timestamp] ✗${NC} $msg" ;;
        STEP)  echo -e "${MAGENTA}[$timestamp] →${NC} $msg" ;;
        *)     echo -e "[$timestamp] $msg" ;;
    esac

    echo "[$timestamp] [$level] $msg" >> "$LOG_FILE"
    echo "[$short_ts] [$level] $msg" >> "$LIVE_FILE"
}

echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Ralph Wiggum Loop - Starting                                ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo -e "${CYAN}  PRD:      ${PRD_FILE}${NC}"
echo -e "${CYAN}  Progress: ${PROGRESS_FILE}${NC}"
echo -e "${CYAN}  Log:      ${LOG_FILE}${NC}"
echo -e "${CYAN}  Live:     ${LIVE_FILE}${NC}"
echo -e "${CYAN}  Max:      ${MAX_ITERATIONS} iterations${NC}"
echo ""
echo -e "${YELLOW}  📺 MONITOR LIVE: tail -f ${LIVE_FILE}${NC}"
echo ""

init_live_file
log INFO "Ralph loop starting"

if ! command -v jq &> /dev/null; then
    log ERROR "jq is required but not installed. Install with: brew install jq"
    exit 1
fi

if [ ! -f "$PRD_FILE" ]; then
    log ERROR "PRD file not found: ${PRD_FILE}"
    exit 1
fi

if [ ! -f "$PROGRESS_FILE" ]; then
    cat > "$PROGRESS_FILE" << EOF
# Ralph Loop Progress Log
# PRD: ${PRD_FILE}
# Created: $(date)
#
# This file tracks all story completions, blockers, and learnings.

EOF
    log INFO "Created progress file: $PROGRESS_FILE"
fi

get_next_story() {
    jq -r '.userStories[] | select(.passes == false) | .id' "$PRD_FILE" | head -1
}

get_story_details() {
    local story_id=$1
    jq -r ".userStories[] | select(.id == \"$story_id\")" "$PRD_FILE"
}

get_story_counts() {
    local total=$(jq -r '.userStories | length' "$PRD_FILE")
    local complete=$(jq -r '[.userStories[] | select(.passes == true)] | length' "$PRD_FILE")
    local remaining=$((total - complete))
    echo "$complete/$total ($remaining remaining)"
}

update_live_status() {
    local story_id=$1
    local status=$2
    echo "" >> "$LIVE_FILE"
    echo "════════════════════════════════════════════════════════════════════════" >> "$LIVE_FILE"
    echo "  CURRENT: $story_id - $status" >> "$LIVE_FILE"
    echo "  TIME: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LIVE_FILE"
    echo "════════════════════════════════════════════════════════════════════════" >> "$LIVE_FILE"
}

mark_story_passed() {
    local story_id=$1
    local temp_file=$(mktemp)
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    jq "(.userStories[] | select(.id == \"$story_id\")) |= . + {passes: true, completed_at: \"$timestamp\"}" "$PRD_FILE" > "$temp_file"
    mv "$temp_file" "$PRD_FILE"
    log OK "Marked $story_id as passed"
}

log_progress() {
    local story_id=$1
    local status=$2
    local message=$3
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    cat >> "$PROGRESS_FILE" << EOF

---

### [$story_id] - $timestamp
**Status:** $status
$message

EOF
    log INFO "Logged progress for $story_id: $status"
}

build_prompt() {
    local story_id=$1
    local story_details=$2
    local story_title=$(echo "$story_details" | jq -r '.title')
    local story_desc=$(echo "$story_details" | jq -r '.description')
    local project_name=$(jq -r '.project.name' "$PRD_FILE")
    local project_id=$(jq -r '.project.id' "$PRD_FILE")

    cat << EOF
You are working on story ${story_id}: ${story_title}

## Project Context
**Project:** ${project_name}
**Project ID:** ${project_id}
**PRD:** ${PRD_FILE}
**Progress Log:** ${PROGRESS_FILE}

This is part of a Ralph Wiggum Loop execution. Each story runs in a FRESH context window.
Memory persists through: git commits, progress log, PRD passes flags.

## Story Description
${story_desc}

## Acceptance Criteria
$(echo "$story_details" | jq -r '.acceptanceCriteria[]' | sed 's/^/- /')

## CRITICAL Instructions

1. **Focus:** Complete ONLY this story. Do not work on other stories.

2. **Context First:** Read the PRD and session log for full context:
   - PRD: ${PRD_FILE}
   - Session: ${PRD_DIR}/SESSION.md

3. **Completion Signal:** When done, output EXACTLY on its own line:
   \`\`\`
   STORY_COMPLETE: ${story_id}
   \`\`\`

4. **Blocker Signal:** If you cannot complete, output EXACTLY:
   \`\`\`
   STORY_BLOCKED: ${story_id}: <reason>
   \`\`\`

5. **Commit:** After making changes, commit with message:
   \`feat: complete ${story_id} - ${story_title}\`

6. **Log Discoveries:** Append any learnings to the progress log.

## Repository
Working directory: $(pwd)

BEGIN STORY EXECUTION
EOF
}

show_status() {
    echo -e "\n${BLUE}=== Current Status: $(get_story_counts) ===${NC}"
    jq -r '.userStories[] | "  \(if .passes then "✓" else "○" end) \(.id): \(.title)"' "$PRD_FILE"
    echo "" >> "$LIVE_FILE"
    echo "=== STATUS: $(get_story_counts) ===" >> "$LIVE_FILE"
    jq -r '.userStories[] | "  \(if .passes then "✓" else "○" end) \(.id): \(.title)"' "$PRD_FILE" >> "$LIVE_FILE"
}

show_status

cat >> "$LOG_FILE" << EOF

================================================================================
RALPH LOOP SESSION STARTED
================================================================================
Time: $(date)
PRD: $PRD_FILE
Max Iterations: $MAX_ITERATIONS
================================================================================

EOF

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))

    echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  Iteration $ITERATION of $MAX_ITERATIONS${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    log INFO "Starting iteration $ITERATION"

    NEXT_STORY=$(get_next_story)

    if [ -z "$NEXT_STORY" ]; then
        log OK "All stories complete! Ralph is done."
        show_status
        echo "" >> "$LOG_FILE"
        echo "=================================================================================" >> "$LOG_FILE"
        echo "ALL STORIES COMPLETE - $(date)" >> "$LOG_FILE"
        echo "=================================================================================" >> "$LOG_FILE"
        echo "" >> "$LIVE_FILE"
        echo "🎉 ALL STORIES COMPLETE! $(date)" >> "$LIVE_FILE"
        exit 0
    fi

    STORY_DETAILS=$(get_story_details "$NEXT_STORY")
    STORY_TITLE=$(echo "$STORY_DETAILS" | jq -r '.title')

    log INFO "Processing story: $NEXT_STORY"
    echo -e "${BLUE}Story:${NC} ${NEXT_STORY}"
    echo -e "${BLUE}Title:${NC} ${STORY_TITLE}"

    update_live_status "$NEXT_STORY" "STARTING"

    PROMPT=$(build_prompt "$NEXT_STORY" "$STORY_DETAILS")

    echo -e "\n${YELLOW}Spawning Claude for story...${NC}"
    echo -e "${YELLOW}(This creates a fresh context window)${NC}\n"

    log STEP "Spawning Claude with prompt for $NEXT_STORY"

    echo "$PROMPT" > /tmp/ralph_prompt_${NEXT_STORY}.txt

    echo "--- PROMPT FOR $NEXT_STORY ---" >> "$LOG_FILE"
    echo "$PROMPT" >> "$LOG_FILE"
    echo "--- END PROMPT ---" >> "$LOG_FILE"

    update_live_status "$NEXT_STORY" "CLAUDE WORKING..."
    live "Claude is processing ${NEXT_STORY}..."

    if command -v stdbuf &> /dev/null; then
        echo "$PROMPT" | stdbuf -oL claude --print --dangerously-skip-permissions 2>&1 | tee /tmp/ralph_output.txt | while IFS= read -r line; do
            echo "$line"
            echo "[CLAUDE] $line" >> "$LIVE_FILE"
        done
    else
        echo "$PROMPT" | claude --print --dangerously-skip-permissions 2>&1 | tee /tmp/ralph_output.txt
    fi

    echo "" >> "$LOG_FILE"
    echo "--- OUTPUT FROM CLAUDE FOR $NEXT_STORY ---" >> "$LOG_FILE"
    cat /tmp/ralph_output.txt >> "$LOG_FILE"
    echo "--- END OUTPUT ---" >> "$LOG_FILE"

    update_live_status "$NEXT_STORY" "CHECKING RESULT..."

    if grep -q "STORY_COMPLETE: ${NEXT_STORY}" /tmp/ralph_output.txt; then
        log OK "Story ${NEXT_STORY} completed!"
        update_live_status "$NEXT_STORY" "✓ COMPLETE"
        mark_story_passed "$NEXT_STORY"
        log_progress "$NEXT_STORY" "PASSED" "Story completed successfully by Ralph loop iteration $ITERATION"

        if git diff --quiet && git diff --cached --quiet; then
            log WARN "No git changes detected - story may have been documentation only"
        else
            log STEP "Committing changes..."
            git add -A
            git commit -m "feat: complete ${NEXT_STORY} - ${STORY_TITLE}" || log WARN "No changes to commit"
            live "Committed: ${NEXT_STORY}"
        fi

    elif grep -q "STORY_BLOCKED: ${NEXT_STORY}" /tmp/ralph_output.txt; then
        BLOCK_REASON=$(grep "STORY_BLOCKED: ${NEXT_STORY}" /tmp/ralph_output.txt | sed "s/STORY_BLOCKED: ${NEXT_STORY}: //")
        log ERROR "Story ${NEXT_STORY} blocked: ${BLOCK_REASON}"
        update_live_status "$NEXT_STORY" "✗ BLOCKED: $BLOCK_REASON"
        log_progress "$NEXT_STORY" "BLOCKED" "Blocked: $BLOCK_REASON"

        echo -e "${YELLOW}Pausing for manual intervention.${NC}"
        echo -e "${YELLOW}Options: [r]etry, [s]kip, [m]ark complete, [q]uit${NC}"
        read -r response
        case $response in
            r) ITERATION=$((ITERATION - 1)); log INFO "Retrying $NEXT_STORY"; live "User requested retry for $NEXT_STORY" ;;
            s) log WARN "Skipping $NEXT_STORY"; log_progress "$NEXT_STORY" "SKIPPED" "Manually skipped by user"; live "User skipped $NEXT_STORY" ;;
            m) mark_story_passed "$NEXT_STORY"; log_progress "$NEXT_STORY" "MANUAL_PASS" "Manually marked complete by user"; live "User manually passed $NEXT_STORY" ;;
            q) log INFO "User quit ralph loop"; live "User quit ralph loop"; exit 1 ;;
        esac
    else
        log WARN "Story ${NEXT_STORY} output unclear - no completion signal found"
        update_live_status "$NEXT_STORY" "⚠ UNCLEAR OUTPUT"
        log_progress "$NEXT_STORY" "UNCLEAR" "Output did not contain STORY_COMPLETE or STORY_BLOCKED signal"

        echo -e "${YELLOW}Mark as complete? [y/n/r]etry${NC}"
        read -r response
        case $response in
            y) mark_story_passed "$NEXT_STORY"; log_progress "$NEXT_STORY" "MANUAL_PASS" "Manually marked as passed by user (unclear output)"; live "User manually passed $NEXT_STORY (unclear output)" ;;
            r) ITERATION=$((ITERATION - 1)); log INFO "Retrying $NEXT_STORY"; live "User requested retry for $NEXT_STORY" ;;
            *) log INFO "Continuing to next story (leaving $NEXT_STORY incomplete)"; live "Skipping $NEXT_STORY (user chose to continue)" ;;
        esac
    fi

    echo -e "\n${BLUE}Sleeping 2 seconds before next iteration...${NC}"
    live "Sleeping 2s before next iteration..."
    sleep 2
done

log WARN "Max iterations ($MAX_ITERATIONS) reached"
show_status

echo "" >> "$LOG_FILE"
echo "=================================================================================" >> "$LOG_FILE"
echo "MAX ITERATIONS REACHED - $(date)" >> "$LOG_FILE"
echo "=================================================================================" >> "$LOG_FILE"

echo "" >> "$LIVE_FILE"
echo "⚠ MAX ITERATIONS REACHED - $(date)" >> "$LIVE_FILE"
