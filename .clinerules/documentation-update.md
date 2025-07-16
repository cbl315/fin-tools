---
description: Automatically updates documentation files after task completion
author: Cline
version: 1.0
tags: ["documentation", "markdown", "auto-update"]
globs: ["**/*.md"]
---

# Documentation Auto-Update Rule

## Purpose
This rule ensures documentation is automatically updated whenever a related task is completed.

## Behavior
1. After each task completion (when attempt_completion is used):
   - Identifies all modified files during the task
   - Checks if there are corresponding documentation files
   - Updates documentation with relevant changes

## Documentation Update Logic
For each modified file:
1. If a corresponding .md documentation file exists (e.g., file.py → file_docs.md):
   - Adds a new "## Recent Changes" section if it doesn't exist
   - Appends a timestamped entry describing the changes
   - Maintains a changelog of the last 5 changes

2. For general project documentation (README.md, docs/*.md):
   - Updates any affected sections based on the changes
   - Adds references to new functionality

## Example Update
```markdown
## Recent Changes

### [2025-07-16 10:30:00]
- Updated web3_manager.py with new contract interaction methods
- Added error handling for transaction failures

### [2025-07-15 14:45:00]
- Initial implementation of web3 utilities
```

## Configuration
Add to pyproject.toml to customize:
```toml
[tool.clinerules.documentation]
max_changelog_entries = 5  # Number of changes to keep
date_format = "%Y-%m-%d %H:%M:%S"
ignored_files = ["temp/*", "tests/*"]
```

## Implementation Notes
- Runs after successful task completion
- Only updates documentation if changes were made to related files
- Preserves existing documentation structure
- Uses git diff to identify changes when possible
