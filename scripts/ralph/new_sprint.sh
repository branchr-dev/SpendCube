#!/bin/bash
# Create a new sprint folder with proper structure
#
# Usage: ./scripts/ralph/new_sprint.sh PROJECT_NAME ["optional summary"]
#
# Example:
#   ./scripts/ralph/new_sprint.sh USER_DASHBOARD "Add analytics dashboard"

set -e

PROJECT_NAME="${1:?Usage:  PROJECT_NAME [summary]}"
SUMMARY="${2:-[Project summary to be added]}"

TIMESTAMP=$(date +%Y-%m-%dT%H%M)
SPRINT_DIR="logs/sprints/${TIMESTAMP}_${PROJECT_NAME}"

if [ -d "$SPRINT_DIR" ]; then
    echo "Error: Sprint folder already exists: $SPRINT_DIR"
    exit 1
fi

mkdir -p "${SPRINT_DIR}/ralph"

cat > "${SPRINT_DIR}/STATUS.md" << EOF
# Sprint Status

**Status:** in_progress
**Started:** $(date '+%Y-%m-%d %H:%M')
**Completed:** -

## Quick Links
- PRD: \`PRD.json\`
- Session: \`SESSION.md\`
- Progress: \`PROGRESS.txt\`

## Summary
${SUMMARY}
EOF

cat > "${SPRINT_DIR}/PRD.json" << EOF
{
  "project": {
    "id": "${PROJECT_NAME}-$(date +%Y-%m)",
    "name": "${PROJECT_NAME//_/ }",
    "created": "$(date +%Y-%m-%d)",
    "status": "in_progress",
    "owner": "tom",
    "sprint_folder": "${SPRINT_DIR}"
  },
  "summary": "${SUMMARY}",
  "decisions": {},
  "context": {
    "existing_tables": {},
    "key_files": [],
    "patterns_to_follow": []
  },
  "userStories": [],
  "verification": {
    "queries": {},
    "expected_counts": {},
    "checks": []
  },
  "risks": [],
  "outOfScope": []
}
EOF

cat > "${SPRINT_DIR}/SESSION.md" << EOF
# ${PROJECT_NAME//_/ } - Session Log

## Project Overview
- **Sprint:** \`${SPRINT_DIR}\`
- **PRD:** \`PRD.json\`
- **Status:** In Progress
- **Started:** $(date '+%Y-%m-%d %H:%M')

## Summary
${SUMMARY}

## Decisions Made
- (To be documented)

## Key Context
- (To be documented)

## Story Status
| ID | Title | Status |
|----|-------|--------|
| - | - | - |

## Notes
- (Session notes)
EOF

echo "✓ Created sprint folder: ${SPRINT_DIR}"
echo ""
echo "Files created:"
echo "  - ${SPRINT_DIR}/STATUS.md"
echo "  - ${SPRINT_DIR}/PRD.json"
echo "  - ${SPRINT_DIR}/SESSION.md"
echo "  - ${SPRINT_DIR}/ralph/"
echo ""
echo "Next steps:"
echo "  1. Use /prd to populate PRD.json interactively, or edit it directly"
echo "  2. Run: ./scripts/ralph/ralph.sh ${SPRINT_DIR}/PRD.json 20"
echo "  3. Monitor: tail -f ${SPRINT_DIR}/ralph/LIVE.log"
