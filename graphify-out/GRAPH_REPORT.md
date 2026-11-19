# Graph Report - Agent-Brigade  (2026-11-19)

## Corpus Check
- 347 files · ~142,548 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 14 file(s) not represented in the graph (top: (none) 5, .css 5, .example 1)

## Summary
- 3998 nodes · 13399 edges · 180 communities (148 shown, 32 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 945 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2ee4fb37`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ClaudeCliRunner
- planner_limits.py
- Readiness Checks
- PlanValidationError
- get_session
- planner.py
- Planning Jobs
- Publisher API
- hook.py
- Tracker Models
- Transcript & Messages
- Publisher Guard
- Planning API
- tester_run.py
- JiraClient
- Tracker Items Board
- Jira Sync
- Run IDs & Folders
- Plan Formatting Tests
- Check Model
- Planning API Tests
- services/publisher.py
- Jira Client Tests
- Publisher CLI Tests
- Planner Prompt
- main
- builder_run.py
- Readiness Tests
- test_publisher_api.py
- Approval Errors & Jira Write
- Plan Check & Parse
- App Factory
- run_directory
- Settings Tests
- Health & Projects API
- Settings
- Planning Pipeline Tests
- Git Repo Helpers
- Planner & Runner Docs
- team_project
- Uploaded Files
- Plan File Validation
- attempt_rows.py
- Story Samples
- db/models.py
- FakeJira
- CI Workflow
- Launch
- Technical Document Concepts
- Plan Block Parsing
- _Loop
- pathlib
- Thread UI
- Planning UI
- Re-plan Tests
- Layer Import Tests
- Publisher UI
- Publisher Screen Mockup
- Page Shell & Tabs
- Planning Stories Screen
- Trackers & Publish Guard Docs
- Plan Tree UI
- orchestrator.js
- Planning Tree
- App Shell JS
- Planning Plan Screen
- Safety Screen
- Backend & Database Docs
- Plan View UI
- Story Card UI
- project
- Check Panel UI
- Plan Side UI
- Runner Security Docs
- Approve & Re-plan Docs
- Epic List UI
- Plan Task UI
- Story State UI
- Brigade Logo
- Attachments UI
- Package Import Tests
- agent_stream.py
- task_run.py
- Markdown UI
- Popup UI
- VS Live Share Config
- Phases & Testing Docs
- Brigade Favicon
- project_commands.py
- testfiles.py
- progress.py
- test_task_continue_api.py
- agent-brigade
- Item
- settled
- test_interrupted.py
- sources.py
- AgentError
- agent_reports.py
- _ask
- Inputs
- test_merge_git.py
- GitError
- .run
- test_stream_events.py
- wanted
- StoryRunner
- guard.py
- test_agent_prompts.py
- decide
- test_agent_record.py
- builder_session.py
- test_run_control_api.py
- AgentLimit
- judge_attempt
- go
- test_reset.py
- agent_items
- step_items.py
- orchestrator_items
- test_upgrade.py
- plan_order.py
- role_settings
- run_lock
- RunControlService
- ContinueService
- decide.py
- measure_attempt
- command_line
- agent_definitions
- run_git
- TaskControlService
- wait_for
- test_orchestrator_api.py
- api/run_control.py
- profiles.py
- test_stage_report_api.py
- api/orchestrator.py
- events.py
- test_plan_order.py
- json_lines
- plan_view.py
- builder_prompt
- _sub_task_id
- orch-model.js
- claude_md_check.py
- test_retryable.py
- test_heartbeat.py
- agent_requests.py
- test_plan_fields.py
- builder.md
- reviewer.md
- tester.md
- orch-feed.js
- orch-run.js
- orch-stories.js
- .client
- orch-report.js
- orch-strip.js
- orch-taskbar.js

## God Nodes (most connected - your core abstractions)
1. `Settings` - 131 edges
2. `run_directory()` - 125 edges
3. `get_session()` - 120 edges
4. `team_project()` - 95 edges
5. `JiraClient` - 93 edges
6. `TeamRunner` - 88 edges
7. `project()` - 75 edges
8. `build_attempt()` - 72 edges
9. `run_task()` - 71 edges
10. `load_plan()` - 67 edges

## Surprising Connections (you probably didn't know these)
- `run()` --uses--> `FeedError`  [INFERRED]
  backend/api/orchestrator.py → pipeline/feed/sources.py
- `run()` --uses--> `GitError`  [INFERRED]
  backend/api/planning.py → pipeline/workspace/git.py
- `summary_out()` --uses--> `StoryRun`  [INFERRED]
  backend/api/planning.py → core/db/models.py
- `load_settings()` --uses--> `Settings`  [INFERRED]
  backend/main.py → core/settings.py
- `create_app()` --uses--> `Settings`  [INFERRED]
  backend/main.py → core/settings.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Architecture decision records 0001-0004** — docs_adr_0001_one_central_database, docs_adr_0002_core_pipeline_backend_layers, docs_adr_0003_plain_html_frontend, docs_adr_0004_agents_in_claude_agents [EXTRACTED 1.00]
- **Builder, tester and reviewer sub-task loop** — docs_technical_document_builder_agent, docs_technical_document_tester_agent, docs_technical_document_reviewer_agent, docs_technical_document_orchestrator [EXTRACTED 1.00]
- **Five-tab web page** — docs_technical_document_publisher_tab, docs_technical_document_planning_tab, docs_technical_document_orchestrator_tab, docs_technical_document_overview_tab, docs_technical_document_delivery_tab [EXTRACTED 1.00]
- **index.html tab panels** — frontend_index_publisher_section, frontend_index_planning_section, frontend_index_orchestrator_section, frontend_index_sidebar_nav [EXTRACTED 1.00]
- **Epic to Story to Sub-task hierarchy** — docs_screens_02_planning_stories_epic_101, docs_screens_02_planning_stories_story_101, docs_screens_02_planning_stories_story_102, docs_screens_02_planning_stories_story_103, docs_screens_02_planning_stories_subtasks [EXTRACTED 1.00]
- **Epic to Stories hierarchy in Jira plan** — docs_screens_01_publisher_epic_101, docs_screens_01_publisher_story_101, docs_screens_01_publisher_story_102, docs_screens_01_publisher_story_103 [EXTRACTED 1.00]
- **Planning flow: browse JIRA tree, pick story, review and approve plan** — docs_screens_03_planning_plan_jira_projects_tree, docs_screens_03_planning_plan_story_list, docs_screens_03_planning_plan_plan_panel, docs_screens_03_planning_plan_approve_replan [INFERRED 0.85]

## Communities (180 total, 32 thin omitted)

### Community 0 - "ClaudeCliRunner"
Cohesion: 0.17
Nodes (26): agent_header(), claude_command(), ClaudeCliRunner, answer(), FakeRun, request(), test_a_limit_stop_without_a_known_limit_still_reports_the_reason(), test_a_read_only_agent_gets_its_tools_folders_and_deny_rules() (+18 more)

### Community 1 - "planner_limits.py"
Cohesion: 0.16
Nodes (14): load_planner_limits(), planner_limits(), PlannerLimits, _positive(), ProfileError, table(), test_a_bad_value_names_the_key(), test_a_missing_or_broken_file_is_a_profile_error() (+6 more)

### Community 2 - "Readiness Checks"
Cohesion: 0.09
Nodes (30): acceptance_criteria(), _label(), _blocked_by(), check_story_key(), format_story(), _item(), _links(), read_story() (+22 more)

### Community 3 - "PlanValidationError"
Cohesion: 0.26
Nodes (10): _acceptance_criteria(), check_task(), _complexity(), _flag(), _paths(), PlanValidationError, relative_path(), _story_fields() (+2 more)

### Community 4 - "get_session"
Cohesion: 0.09
Nodes (27): lifespan(), get_engine(), get_session(), make_engine(), session_factory(), init_db(), Project, TrackerItem (+19 more)

### Community 5 - "planner.py"
Cohesion: 0.09
Nodes (14): PlanFileError, check_budget(), docs_folder(), NotReady, plan_record(), plan_story(), PlanResult, ask_planner() (+6 more)

### Community 6 - "Planning Jobs"
Cohesion: 0.05
Nodes (30): _finish(), JobContext, _plan(), PlanningJob, run_job(), PlanningService, taken(), Conflict (+22 more)

### Community 7 - "Publisher API"
Cohesion: 0.08
Nodes (36): confirm(), download(), file_out(), list_chats(), open_chat(), _plan(), read_uploads(), run() (+28 more)

### Community 8 - "hook.py"
Cohesion: 0.05
Nodes (58): move_to(), NoPath, _to(), StatusNames, make_sync(), StorySync, Journal, mirror() (+50 more)

### Community 9 - "Tracker Models"
Cohesion: 0.13
Nodes (13): kind_of(), _name(), WorkItem, _answers(), _dependencies(), _doc_target(), _inside(), _jira_dependencies() (+5 more)

### Community 10 - "Transcript & Messages"
Cohesion: 0.10
Nodes (30): message_with_files(), split_files(), wrap(), fix_prompt(), Bubble, find_transcript(), main(), parse_transcript() (+22 more)

### Community 11 - "Publisher Guard"
Cohesion: 0.12
Nodes (24): _create(), Created, created_note(), main(), publish(), PublishResult, verify(), _with_epic() (+16 more)

### Community 12 - "Planning API"
Cohesion: 0.18
Nodes (27): approve(), checks(), get_run(), plan(), replan(), run(), run_out(), service() (+19 more)

### Community 13 - "tester_run.py"
Cohesion: 0.06
Nodes (22): _posix_command_line(), Baseline, read_baseline(), check_lines(), failure_text(), run_checks(), _fail(), merge_feedback() (+14 more)

### Community 14 - "JiraClient"
Cohesion: 0.05
Nodes (20): TrackerError, _error(), JiraClient, quote_jql(), _wait_seconds(), check(), main(), story() (+12 more)

### Community 15 - "Tracker Items Board"
Cohesion: 0.18
Nodes (20): board(), BoardItem, _fields(), _key_order(), last_synced(), replace_board(), _row_fields(), SyncCounts (+12 more)

### Community 16 - "Jira Sync"
Cohesion: 0.18
Nodes (15): sync(), _board_item(), board_items(), sync_board(), SyncError, board(), settings(), test_a_jira_error_changes_nothing() (+7 more)

### Community 17 - "Run IDs & Folders"
Cohesion: 0.11
Nodes (12): new_run_id(), project_folder(), RunIdError, test_a_run_folder_is_inside_the_projects_brigade_folder(), test_a_run_id_is_the_story_key_the_date_and_4_hex_characters(), test_a_run_id_needs_a_real_story_key(), test_a_used_id_is_made_again(), test_anything_that_is_not_a_run_id_is_refused() (+4 more)

### Community 18 - "Plan Formatting Tests"
Cohesion: 0.14
Nodes (24): format_plan(), planned(), test_a_budget_shows_what_planning_used_and_what_is_left(), test_a_budget_smaller_than_the_task_limits_gets_a_warning(), test_a_replan_and_a_replaced_plan_are_shown(), test_commands_are_shown_or_the_view_says_none_listed(), test_notes_no_links_and_approval_are_shown(), test_the_plan_reads_like_the_planning_screen() (+16 more)

### Community 19 - "Check Model"
Cohesion: 0.14
Nodes (11): Story, Check, plural(), StoryCheck, check_checkout(), check_project_files(), format_checks(), main() (+3 more)

### Community 20 - "Planning API Tests"
Cohesion: 0.13
Nodes (16): Inline, Later, make_world(), plan(), test_a_failed_readiness_check_fails_the_run_with_the_check_text(), test_a_refused_plan_fails_the_run_with_the_reason(), test_a_story_not_on_the_board_or_a_bad_key_is_refused(), test_approve_with_jira_down_keeps_the_plan_waiting() (+8 more)

### Community 21 - "services/publisher.py"
Cohesion: 0.11
Nodes (21): prepare_files(), save_files(), PublisherService, confirmed_keys(), confirmed_records(), created_from(), last_confirmed(), open_proposal() (+13 more)

### Community 22 - "Jira Client Tests"
Cohesion: 0.21
Nodes (22): JiraError, body(), issue_json(), make(), wrapped(), test_a_blocks_link_puts_the_blocker_in_the_inward_issue(), test_a_comment_goes_to_its_own_issue_as_rich_text(), test_check_lists_the_space_and_its_epics() (+14 more)

### Community 23 - "Publisher CLI Tests"
Cohesion: 0.24
Nodes (22): run(), epic_reply(), reply(), issue(), ok(), runner(), factory(), handler() (+14 more)

### Community 24 - "Planner Prompt"
Cohesion: 0.13
Nodes (20): _clean(), _cut(), fix_prompt(), _money(), planner_prompt(), _previous_plan(), _subtask(), previous() (+12 more)

### Community 25 - "main"
Cohesion: 0.06
Nodes (69): format_build(), _money(), is_prepared(), LoopRun, start_loop(), main(), parser(), prepare_story() (+61 more)

### Community 26 - "builder_run.py"
Cohesion: 0.04
Nodes (57): validate_run_id(), plan_path(), reopen_rows(), resume_note(), resume_ready(), build_attempt(), _feedback(), _task() (+49 more)

### Community 27 - "Readiness Tests"
Cohesion: 0.26
Nodes (17): Epic, item(), ready_project(), statuses(), story(), test_a_dirty_checkout_fails_the_run_of_checks(), test_a_ready_story(), test_all_done_fails() (+9 more)

### Community 28 - "test_publisher_api.py"
Cohesion: 0.07
Nodes (30): check_upload(), _docx(), extract_text(), FileRejected, _pdf(), _plain(), docx_bytes(), proposal() (+22 more)

### Community 29 - "Approval Errors & Jira Write"
Cohesion: 0.15
Nodes (25): ApprovalError, approve_plan(), _check(), _comment(), JiraWriteError, mark_superseded(), _pair(), _waiting() (+17 more)

### Community 30 - "Plan Check & Parse"
Cohesion: 0.24
Nodes (15): check_plan(), jira(), plan(), story(), subtask(), test_a_broken_plan_block_is_refused(), test_a_good_plan_passes(), test_a_story_that_already_exists_under_the_epic_is_refused() (+7 more)

### Community 31 - "App Factory"
Cohesion: 0.13
Nodes (8): create_app(), load_settings(), client(), make_settings(), test_a_bad_setting_stops_startup_and_names_it(), test_local_only_project_is_named_after_its_folder(), test_no_project_in_env_means_an_empty_list(), test_starting_twice_does_not_duplicate_and_picks_up_changes()

### Community 32 - "run_directory"
Cohesion: 0.06
Nodes (61): newest_attempt(), run_directory(), unsettle(), completed(), _path(), resume_stage(), save(), agent_file_of() (+53 more)

### Community 33 - "Settings Tests"
Cohesion: 0.15
Nodes (18): clean_env(), load(), test_a_path_with_a_hidden_escape_character_is_rejected(), test_defaults_when_nothing_is_set(), test_docs_dir(), test_docs_dir_must_be_inside_the_project(), test_empty_values_in_env_file_mean_not_set(), test_ensure_dirs_creates_folders() (+10 more)

### Community 34 - "Health & Projects API"
Cohesion: 0.14
Nodes (5): health(), db_session(), list_projects(), HealthOut, ProjectOut

### Community 35 - "Settings"
Cohesion: 0.08
Nodes (13): get_settings(), Settings, approve(), fetch_story(), finish(), parser(), plan(), project_root() (+5 more)

### Community 36 - "Planning Pipeline Tests"
Cohesion: 0.16
Nodes (24): main(), jira_board(), planner(), project(), test_a_budget_that_is_not_a_positive_amount_is_refused(), test_a_failed_readiness_check_stops_before_the_planner(), test_a_run_id_is_used_once(), test_a_subtask_without_criteria_stops_before_anything_runs() (+16 more)

### Community 37 - "Git Repo Helpers"
Cohesion: 0.14
Nodes (16): validate_base_ref(), test_clean_checkout_on_main(), test_unknown_base_branch(), make_repo(), test_a_branch_or_worktree_the_orchestrator_did_not_make_is_still_a_change(), test_a_failing_git_command_says_which(), test_bad_base_branches_are_refused(), test_changed_paths_lists_new_files_one_by_one_and_renames_both_names() (+8 more)

### Community 38 - "Planner & Runner Docs"
Cohesion: 0.12
Nodes (18): Agent Brigade CLAUDE.md, Agent runner (claude_runner), Planner agent, Planner JSON plan answer, Re-plan flow, Publisher agent, pipeline.publisher.cli read-only tool, Choosing the Epic procedure (+10 more)

### Community 39 - "team_project"
Cohesion: 0.09
Nodes (53): answer_of_reviewer(), answer_of_tester(), built_and_checked(), _script(), team_project(), TeamRunner, test_a_task_logs_each_stage_and_hands_each_agent_its_event_file(), outcome() (+45 more)

### Community 40 - "Uploaded Files"
Cohesion: 0.21
Nodes (11): chat_folder(), find(), list_files(), safe_name(), save(), stored_names(), StoredFile, test_a_name_that_is_not_a_stored_name_is_not_saved() (+3 more)

### Community 41 - "Plan File Validation"
Cohesion: 0.17
Nodes (22): _candidate_documents(), parse_planner_answer(), save_plan(), validate_tasks(), document(), task(), test_a_bad_run_id_never_becomes_a_path(), test_a_bad_stored_plan_is_refused() (+14 more)

### Community 42 - "attempt_rows.py"
Cohesion: 0.09
Nodes (19): agent_runs_of(), attempt_of(), BuildRecordError, checks_of(), finish_agent_run(), finish_attempt(), reopen_attempt(), start_agent_run() (+11 more)

### Community 43 - "Story Samples"
Cohesion: 0.25
Nodes (14): answer(), entry(), merge(), test_a_good_answer_becomes_the_plan_and_records_only_new_jira_links(), test_a_jira_dependency_the_planner_left_out_is_put_back(), test_bad_dependencies_are_refused(), test_cycles_sizes_paths_and_empty_outcomes_are_refused(), test_doc_targets_must_be_in_the_docs_folder() (+6 more)

### Community 44 - "db/models.py"
Cohesion: 0.12
Nodes (19): AgentRun, Attempt, Base, BudgetReservation, Check, Merge, SubTask, record_checks() (+11 more)

### Community 46 - "FakeJira"
Cohesion: 0.11
Nodes (6): adf_to_text(), _inline(), text_to_adf(), test_adf_lists_code_and_mentions(), test_adf_round_trip_keeps_paragraphs_and_lines(), FakeJira

### Community 47 - "CI Workflow"
Cohesion: 0.11
Nodes (17): runs-on, steps, jobs, checks, name, on, pull_request, push (+9 more)

### Community 48 - "Launch"
Cohesion: 0.05
Nodes (48): is_loop_process(), Launch, launch_loop(), _lock_pid(), loop_alive(), loop_command(), read_launch(), spawn_detached() (+40 more)

### Community 49 - "Technical Document Concepts"
Cohesion: 0.12
Nodes (14): Agent Brigade Technical Document, Agent Brigade, Story budget and reservations, Builder agent, Worktree isolation per sub-task, Four locks, Merging into the story branch, Orchestrator (+6 more)

### Community 50 - "Plan Block Parsing"
Cohesion: 0.14
Nodes (7): _add(), find_plan_block(), without_plan_block(), _Builder, _is_tool_result(), _texts(), test_the_last_plan_block_is_taken_and_removed_from_the_text()

### Community 51 - "_Loop"
Cohesion: 0.06
Nodes (15): BackgroundSync, Hearing, _key(), _Loop, _newest(), StoryResult, TaskOutcome, result() (+7 more)

### Community 52 - "pathlib"
Cohesion: 0.06
Nodes (13): write_json_atomic(), utc_now(), TaskInterrupted, step_lines(), step_result(), StepResult, _run_lines(), report_path() (+5 more)

### Community 53 - "Thread UI"
Cohesion: 0.29
Nodes (12): add(), clearThread(), createdLinks(), fileChip(), linkItem(), notice(), publisherBubble(), replay() (+4 more)

### Community 54 - "Planning UI"
Cohesion: 0.38
Nodes (13): card(), check(), epicShown(), hit(), init(), load(), notice(), plan() (+5 more)

### Community 55 - "Re-plan Tests"
Cohesion: 0.26
Nodes (17): replan_story(), story(), work_item(), first_plan(), test_a_plan_of_another_story_or_a_missing_run_is_named(), test_a_refused_replan_leaves_the_old_plan_waiting(), test_a_replaced_plan_cannot_be_replanned_again(), test_a_replan_is_a_new_run_made_from_the_old_one_and_your_idea() (+9 more)

### Community 56 - "Layer Import Tests"
Cohesion: 0.27
Nodes (8): layer_of(), module_name(), runtime_imports(), visit(), source_files(), test_no_module_imports_a_layer_above_it(), test_the_check_sees_runtime_imports_and_skips_type_checking_ones(), violations()

### Community 57 - "Publisher UI"
Cohesion: 0.44
Nodes (12): autoGrow(), confirm(), init(), loadChats(), newChat(), openChat(), reportProblems(), send() (+4 more)

### Community 58 - "Publisher Screen Mockup"
Cohesion: 0.20
Nodes (12): Chat ID badge (PUB-001234), Jira items creation notice, EPIC-101: CSV Summariser, JIRA Plan card (Epic, Stories, Sub-tasks tree), Message composer (attach, send), Previous Chats collapsible panel, Publisher screen (chat UI), Sidebar navigation (Publisher, Planning, Orchestrator) (+4 more)

### Community 59 - "Page Shell & Tabs"
Cohesion: 0.22
Nodes (11): Delivery tab, Documenter agent, Orchestrator tab, Planning tab, Web page (five tabs), frontend/index.html page shell, SVG icon sprite, Orchestrator panel placeholder (+3 more)

### Community 60 - "Planning Stories Screen"
Cohesion: 0.22
Nodes (10): EPIC-101: CSV Summariser, JIRA Projects and Epics panel, Plan button (per story), Planning screen (Agent Brigade UI), Sidebar navigation (Publisher, Planning, Orchestrator), STORY-101: CSV Upload & Validation, STORY-102: Data Analysis & Summary Generation, STORY-103: Visualizations & Output (+2 more)

### Community 61 - "Trackers & Publish Guard Docs"
Cohesion: 0.20
Nodes (10): GitHub optional tracker, Jira Cloud tracker, Jira status, label and comment flow, Publish guard, Jira Publisher agent, Publisher tab, Tracker adapters (Jira, GitHub), Previous chats drawer (+2 more)

### Community 62 - "Plan Tree UI"
Cohesion: 0.42
Nodes (7): badge(), details(), el(), gist(), icon(), keyLabel(), render()

### Community 63 - "orchestrator.js"
Cohesion: 0.18
Nodes (20): foldLeft(), init(), paintRun(), paintStories(), paintTask(), pickTask(), readAll(), readCounts() (+12 more)

### Community 64 - "Planning Tree"
Cohesion: 0.36
Nodes (4): build_tree(), EpicNode, StoryNode, TreeView

### Community 65 - "App Shell JS"
Cohesion: 0.31
Nodes (5): getJson(), loadProjects(), recall(), start(), TABS

### Community 66 - "Planning Plan Screen"
Cohesion: 0.32
Nodes (8): Approve Plan / Re-plan actions, JIRA Projects and Epics tree (KAN Ledger CLI, KAN-9 Reports), Plan for Story panel (epic, run ID, branch, model, summary), Planning Screen (plan view for story KAN-10), Sidebar navigation (Publisher, Planning, Orchestrator), Story list with Plan buttons (KAN-10, KAN-11, KAN-12) and subtasks, Sync from JIRA button, Task card T1 (needs, run as, files, accept, outcome, verify, read, notes)

### Community 67 - "Safety Screen"
Cohesion: 0.17
Nodes (6): prohibitions(), criteria_list(), _cut(), test_forbidding_text_is_found(), test_ordinary_text_passes(), test_criteria_lose_their_list_markers_and_keep_their_words()

### Community 68 - "Backend & Database Docs"
Cohesion: 0.29
Nodes (6): Backend JSON API, FastAPI backend, SQLite database (brigade.db), Live events (events.jsonl, SSE), Overview tab, Settings and environment variables

### Community 69 - "Plan View UI"
Cohesion: 0.46
Nodes (7): budgetLines(), commandRows(), header(), links(), metrics(), notes(), render()

### Community 70 - "Story Card UI"
Cohesion: 0.52
Nodes (6): badge(), button(), panel(), render(), runLine(), viewButton()

### Community 71 - "project"
Cohesion: 0.10
Nodes (40): release(), run_story(), test_the_story_loop_logs_the_merge_and_each_retry_in_its_attempt_folder(), attempts(), StopOnceHolding, test_a_continued_task_waits_for_its_turn_like_any_other(), test_a_loop_that_is_running_puts_a_continued_task_back_to_work(), test_a_new_loop_continues_a_stopped_task_in_the_same_attempt() (+32 more)

### Community 72 - "Check Panel UI"
Cohesion: 0.53
Nodes (4): chips(), headline(), problem(), render()

### Community 73 - "Plan Side UI"
Cohesion: 0.60
Nodes (5): approvalBar(), notice(), notices(), render(), runStrip()

### Community 74 - "Runner Security Docs"
Cohesion: 0.40
Nodes (5): Agent runner, Claude Code CLI runtime, Environment allowlist for agents, No sandbox limitation, Threats and controls

### Community 75 - "Approve & Re-plan Docs"
Cohesion: 0.40
Nodes (5): Approve and re-plan, Plan (plan.json), Planner agent, Readiness checks, Target project and CLAUDE.md

### Community 76 - "Epic List UI"
Cohesion: 0.60
Nodes (3): epicButton(), rail(), render()

### Community 77 - "Plan Task UI"
Cohesion: 0.70
Nodes (4): badges(), needs(), render(), row()

### Community 78 - "Story State UI"
Cohesion: 0.60
Nodes (3): describe(), newTally(), tally()

### Community 79 - "Brigade Logo"
Cohesion: 0.83
Nodes (4): Agent Brigade logo, Blue and orange ring connecting agents, Central orchestrator robot (large, glowing eyes, orange-rimmed visor), Four surrounding agent robots

### Community 80 - "Attachments UI"
Cohesion: 0.83
Nodes (3): clear(), pick(), render()

### Community 82 - "agent_stream.py"
Cohesion: 0.11
Nodes (15): AgentStory, _dict(), _dump(), _list(), _money(), _edits_detail(), _file_title(), last_line() (+7 more)

### Community 83 - "task_run.py"
Cohesion: 0.09
Nodes (18): CheckReport, BuildResult, write_build_report(), check_rows(), format_checks(), _names(), write_check_report(), check_attempt() (+10 more)

### Community 95 - "project_commands.py"
Cohesion: 0.11
Nodes (24): check_command_lists(), check_commands(), check_provenance(), _command(), describe(), empty_commands(), _linked_doc(), _normal() (+16 more)

### Community 98 - "testfiles.py"
Cohesion: 0.06
Nodes (37): extra_files(), is_secret_file(), normalize(), protected(), under(), files_that_lost_tests(), holds_a_test(), is_test_path() (+29 more)

### Community 99 - "progress.py"
Cohesion: 0.13
Nodes (10): AgentOut, AttemptOut, MergeOut, ProgressOut, TaskOut, _agent(), ProgressService, AttemptRows (+2 more)

### Community 102 - "test_task_continue_api.py"
Cohesion: 0.16
Nodes (7): interrupted(), Launcher, Processes, test_an_interrupted_task_is_continued_from_its_last_checkpoint(), test_reading_the_run_marks_what_a_dead_loop_left_as_stopped(), word_of(), world()

### Community 104 - "Item"
Cohesion: 0.11
Nodes (21): mask_secrets(), feed(), Item, _safe(), shorten(), stable_index(), test_a_bearer_token_keeps_the_word_bearer(), test_a_secret_assignment_keeps_its_name_and_hides_the_value() (+13 more)

### Community 105 - "settled"
Cohesion: 0.14
Nodes (28): ask(), clear_request(), _path(), pending(), reason_of(), request_path(), settle(), settled() (+20 more)

### Community 106 - "test_interrupted.py"
Cohesion: 0.11
Nodes (20): AttemptFact, attempts_of_run(), clear_stale_lock(), _log(), notice(), unfinished_keys(), died_in_the_middle(), newest() (+12 more)

### Community 107 - "sources.py"
Cohesion: 0.11
Nodes (17): _clean(), stage_report(), attempt_items(), available(), _checked(), FeedError, _path(), story_log_items() (+9 more)

### Community 108 - "AgentError"
Cohesion: 0.13
Nodes (11): AgentError, AgentReply, AgentRequest, _added(), ask_for_report(), _spent(), _sum(), usage_of() (+3 more)

### Community 109 - "agent_reports.py"
Cohesion: 0.15
Nodes (19): _entries(), extract_json(), _number(), parse_reviewer(), parse_tester(), ReportError, ReviewerReport, TesterReport (+11 more)

### Community 110 - "_ask"
Cohesion: 0.12
Nodes (14): Asked, _ask(), _measure(), commit_staged(), stage_paths(), staged_diff(), fingerprints(), written_between() (+6 more)

### Community 111 - "Inputs"
Cohesion: 0.11
Nodes (14): attempt_paths(), commit_attempt(), diff_for_review(), add_review(), build_findings(), tester_lines(), verify_results(), verify_source() (+6 more)

### Community 112 - "test_merge_git.py"
Cohesion: 0.17
Nodes (18): _merge_locked(), head_commit(), abort_merge(), begin_merge(), fast_forward(), finish_merge(), is_ancestor(), MergeConflict (+10 more)

### Community 113 - "GitError"
Cohesion: 0.18
Nodes (17): GitError, add_attempt_worktree(), add_story_worktree(), branch_exists(), create_branch(), _free(), list_worktrees(), remove_worktree() (+9 more)

### Community 114 - ".run"
Cohesion: 0.09
Nodes (10): AgentStopped, claude_settings(), read_events(), parse_reply(), _reply(), stop_reason(), _table(), _text() (+2 more)

### Community 115 - "test_stream_events.py"
Cohesion: 0.19
Nodes (17): test_the_note_is_cleared_when_the_agent_is_killed_for_taking_too_long(), test_a_stop_asked_before_the_start_means_the_agent_is_never_started(), test_a_stop_during_the_run_kills_the_agent_and_says_it_was_stopped(), test_a_stop_file_that_never_appears_changes_nothing(), events_path(), FakePopen, FakeProcess, lines() (+9 more)

### Community 116 - "wanted"
Cohesion: 0.11
Nodes (21): _path(), spent(), wanted(), go(), stopped(), test_a_cancelled_task_is_final(), test_a_continue_whose_worktree_is_gone_is_refused_and_keeps_the_stop(), test_a_merged_task_is_done() (+13 more)

### Community 117 - "StoryRunner"
Cohesion: 0.16
Nodes (18): catch_up(), world(), test_a_story_loop_beats_for_as_long_as_it_runs(), test_a_board_that_missed_the_whole_run_is_caught_up_from_the_report(), test_a_run_without_a_report_is_refused(), test_the_command_exits_1_with_the_reason(), test_without_jira_set_up_it_says_so(), board() (+10 more)

### Community 118 - "guard.py"
Cohesion: 0.14
Nodes (10): check_against_jira(), _norm(), parse_plan(), _Reader, _story(), _subtasks(), Plan, PlanCheck (+2 more)

### Community 119 - "test_agent_prompts.py"
Cohesion: 0.14
Nodes (14): _how(), reviewer_prompt(), _tail(), _verify_lines(), _bullets(), check_lines(), tester_prompt(), review() (+6 more)

### Community 120 - "decide"
Cohesion: 0.22
Nodes (17): decide(), VerifyResult, green(), test_a_check_that_already_failed_at_baseline_is_left_to_the_reviewer(), test_a_check_that_did_not_exist_at_baseline_is_a_defect_too(), test_a_check_that_timed_out_is_a_defect_even_if_it_failed_at_baseline(), test_a_criterion_with_no_test_and_no_reason_names_the_criterion(), test_a_failing_check_cannot_be_outvoted_by_a_pass() (+9 more)

### Community 121 - "test_agent_record.py"
Cohesion: 0.15
Nodes (15): reap_orphan(), agent_record_path(), AgentRecord, read_record(), recorded(), test_a_process_that_took_the_id_over_is_left_alone(), test_an_agent_that_is_gone_is_not_killed_and_no_note_means_nothing_to_do(), test_the_orphan_agent_is_stopped_only_when_its_session_is_in_the_command_line() (+7 more)

### Community 122 - "builder_session.py"
Cohesion: 0.13
Nodes (12): path_rule(), secret_rules(), allowed_commands(), builder_request(), deny_rules(), test_path_rules_use_two_slashes_and_the_windows_drive_as_a_folder(), test_secret_rules_cover_every_env_file_in_every_folder(), test_on_windows_the_drive_becomes_a_folder_in_every_rule() (+4 more)

### Community 123 - "test_run_control_api.py"
Cohesion: 0.15
Nodes (15): Launcher, Processes, start(), story_lines(), test_a_finished_run_is_not_started_again(), test_a_paused_run_is_continued_not_started(), test_a_run_that_is_not_in_the_project_is_not_found(), test_a_run_that_stopped_or_was_interrupted_is_continued_not_started() (+7 more)

### Community 124 - "AgentLimit"
Cohesion: 0.17
Nodes (12): AgentLimit, asked(), hit(), test_a_limit_in_a_stream_keeps_what_it_spent(), test_a_limit_is_still_an_agent_error_for_every_caller_that_catches_one(), test_any_other_failure_is_not_a_limit(), test_running_out_of_time_in_a_stream_is_a_limit_too(), test_running_out_of_time_is_a_limit_with_nothing_to_record() (+4 more)

### Community 125 - "judge_attempt"
Cohesion: 0.14
Nodes (12): agent_events_path(), attempt_dir(), AttemptLog, _committed(), judge_attempt(), _skip_reason(), steps(), test_a_failed_attempt_says_why_in_its_log() (+4 more)

### Community 126 - "go"
Cohesion: 0.13
Nodes (19): go(), interrupted(), stopped(), test_a_cancelled_task_is_final(), test_a_continue_whose_worktree_is_gone_is_refused_and_keeps_the_stop(), test_a_merged_task_is_done(), test_a_run_whose_budget_is_used_up_is_refused(), test_a_task_still_being_stopped_must_be_waited_for() (+11 more)

### Community 127 - "test_reset.py"
Cohesion: 0.21
Nodes (13): reset_run(), ResetResult, delete_branches(), finished(), locked(), test_a_folder_that_frees_itself_while_we_retry_is_removed(), test_a_folder_that_will_not_go_is_reported_not_a_crash_and_the_rest_is_removed(), test_a_run_whose_branches_are_still_there_is_refused_and_told_what_to_delete() (+5 more)

### Community 128 - "agent_items"
Cohesion: 0.27
Nodes (17): agent_items(), test_a_call_without_a_result_yet_is_pending(), test_a_failed_result_is_an_error_and_a_refused_one_is_blocked(), test_a_failed_run_is_an_error(), test_a_missing_file_has_no_items(), test_a_rate_limit_warning_and_a_block_are_shown(), test_a_time_inside_the_event_wins_over_the_times_file(), test_a_tool_call_is_paired_with_its_result_and_shows_the_path_inside_the_worktree() (+9 more)

### Community 129 - "step_items.py"
Cohesion: 0.19
Nodes (13): _builder_outcome(), _count(), _judge_outcome(), _lines(), _make(), _merge_outcome(), _single(), _skipped() (+5 more)

### Community 130 - "orchestrator_items"
Cohesion: 0.33
Nodes (17): orchestrator_items(), step(), test_a_builder_that_failed_shows_its_error(), test_a_finish_whose_start_is_missing_is_shown_with_its_outcome(), test_a_judge_that_did_not_finish_the_task_is_an_error(), test_a_line_that_is_not_a_step_is_skipped(), test_a_merge_that_did_not_happen_is_an_error(), test_a_started_step_waits_for_its_finish_and_then_holds_the_outcome() (+9 more)

### Community 131 - "test_upgrade.py"
Cohesion: 0.19
Nodes (8): add_missing_columns(), UpgradeError, old_database(), test_a_column_that_may_not_be_empty_is_refused(), test_a_current_database_needs_nothing_and_a_second_start_adds_nothing(), test_an_older_database_gets_the_new_columns_and_keeps_its_rows(), test_the_new_run_id_column_is_unique(), test_wal_foreign_keys_and_busy_timeout_are_on()

### Community 132 - "plan_order.py"
Cohesion: 0.22
Nodes (10): _ancestors(), visit(), _check_dependencies(), check_order(), _enforce_parallel_safety(), _normalized_files(), overlapping_tasks(), _reject_cycles() (+2 more)

### Community 133 - "role_settings"
Cohesion: 0.18
Nodes (12): format_table(), main(), role_settings(), RoleSettings, RunProfile, _limits(), table(), test_a_size_becomes_its_limits() (+4 more)

### Community 134 - "run_lock"
Cohesion: 0.21
Nodes (9): file_lock(), LockError, merge_lock(), run_lock(), test_the_lock_allows_one_merge_at_a_time_and_is_always_released(), test_a_second_story_loop_on_the_same_run_is_refused(), test_the_lock_is_released_when_the_loop_ends_even_by_an_error(), test_the_refusal_names_the_file_to_delete_after_a_crash() (+1 more)

### Community 135 - "RunControlService"
Cohesion: 0.18
Nodes (5): RunLineOut, StartedOut, StopAllOut, StoryLineOut, RunControlService

### Community 137 - "decide.py"
Cohesion: 0.23
Nodes (11): _build_problems(), _clip(), _criterion(), Decision, Findings, notes(), problems(), retry_feedback() (+3 more)

### Community 138 - "measure_attempt"
Cohesion: 0.21
Nodes (9): measure_attempt(), verify_lines(), task(), test_a_task_that_changed_nothing_fails_even_when_its_lines_pass(), test_a_task_without_verify_lines_passes_with_nothing_measured(), test_files_outside_the_task_files_do_not_fail_it(), test_the_changed_extra_and_protected_files_are_measured(), test_the_verify_lines_run_in_the_worktree_and_each_result_is_kept() (+1 more)

### Community 139 - "command_line"
Cohesion: 0.15
Nodes (9): _by_psutil(), command_line(), _windows_command_line(), test_a_process_that_has_ended_has_no_command_line(), test_on_windows_powershell_is_the_fallback_when_psutil_cannot_say(), test_on_windows_the_quick_way_is_used_and_powershell_is_not_started(), test_psutil_reads_the_command_line_of_a_running_process_and_none_of_a_gone_one(), test_the_command_line_of_a_running_process_is_found() (+1 more)

### Community 140 - "agent_definitions"
Cohesion: 0.15
Nodes (7): agent_definitions(), AgentFileError, split_agent_file(), test_a_bad_file_is_refused(), test_a_missing_file_is_refused(), test_header_and_body_are_split(), test_the_definition_is_what_claude_code_takes()

### Community 141 - "run_git"
Cohesion: 0.20
Nodes (9): _skip_reason(), changed_files(), current_branch(), _foreign_branches(), _foreign_worktrees(), _is_ours(), repository_state(), run_git() (+1 more)

### Community 143 - "wait_for"
Cohesion: 0.16
Nodes (7): wait_for(), Clock, test_a_process_that_ends_by_itself_is_done(), test_the_stop_file_appearing_ends_the_wait_as_stopped(), test_the_time_limit_still_applies_while_watching(), test_without_a_stop_file_it_is_just_a_wait(), Waiting

### Community 144 - "test_orchestrator_api.py"
Cohesion: 0.17
Nodes (8): make_client(), test_a_run_that_is_not_in_the_project_is_not_found(), test_a_source_key_or_number_that_cannot_exist_is_refused(), test_a_task_that_has_not_started_is_waiting_with_no_attempts(), test_an_agents_stream_is_shown_masked_and_cut_and_whole_only_when_asked(), test_progress_lists_every_task_with_its_attempts_agents_cost_and_merge(), world(), write_builder_stream()

### Community 145 - "api/run_control.py"
Cohesion: 0.32
Nodes (10): cancel_task(), continue_run(), continue_task(), continuing(), service(), start(), stop_all(), stop_task() (+2 more)

### Community 146 - "profiles.py"
Cohesion: 0.30
Nodes (10): _bad(), load_profiles(), _positive(), _profile(), Profiles, profiles(), _shares(), _whole() (+2 more)

### Community 147 - "test_stage_report_api.py"
Cohesion: 0.23
Nodes (10): report(), test_a_damaged_report_counts_as_not_written(), test_a_run_that_does_not_exist_is_not_found(), test_a_secret_in_a_report_is_masked_before_it_leaves(), test_a_stage_key_or_number_that_cannot_exist_is_refused(), test_a_stage_that_has_not_written_yet_says_so_instead_of_failing(), test_nothing_the_page_does_not_need_is_sent(), test_the_builder_box_has_what_changed_what_it_said_and_what_it_cost() (+2 more)

### Community 148 - "api/orchestrator.py"
Cohesion: 0.37
Nodes (6): attempt_events(), progress(), run(), service(), stage_report(), story_log()

### Community 149 - "events.py"
Cohesion: 0.29
Nodes (6): events_path(), read_events(), record(), test_a_run_without_events_reads_as_empty(), test_a_torn_last_line_from_a_crash_is_skipped(), test_events_are_read_back_in_the_order_they_were_recorded()

### Community 150 - "test_plan_order.py"
Cohesion: 0.31
Nodes (10): ordered(), safe_flags(), task(), test_a_chain_is_accepted(), test_a_task_not_claimed_safe_stays_unsafe(), test_a_task_without_files_is_never_safe(), test_bad_task_relations_are_refused(), test_ordered_tasks_may_share_files() (+2 more)

### Community 151 - "json_lines"
Cohesion: 0.29
Nodes (5): json_lines(), read_lines(), test_a_missing_file_has_no_lines(), test_lines_keep_their_line_numbers_when_one_is_bad(), test_undecodable_bytes_do_not_stop_reading()

### Community 152 - "plan_view.py"
Cohesion: 0.32
Nodes (7): _budget_lines(), _command_lines(), _footer(), _header(), _replan_lines(), _task_lines(), profile_for()

### Community 153 - "builder_prompt"
Cohesion: 0.27
Nodes (7): builder_prompt(), _cut(), _list(), full_task(), test_feedback_comes_first_and_missing_parts_are_said_so(), test_long_text_is_cut(), test_the_prompt_holds_only_this_task_in_the_right_order()

### Community 154 - "_sub_task_id"
Cohesion: 0.18
Nodes (5): _now(), _row(), _start_rows(), _sub_task_id(), _usage()

### Community 155 - "orch-model.js"
Cohesion: 0.25
Nodes (6): cancelRule(), continueRule(), newest(), rules(), stopRule(), taskWord()

### Community 156 - "claude_md_check.py"
Cohesion: 0.36
Nodes (6): check_project(), _claude_md(), _docs(), Finding, section_headings(), _sections()

### Community 157 - "test_retryable.py"
Cohesion: 0.31
Nodes (6): retryable_keys(), failed_for_good(), test_a_cancelled_task_is_never_retryable(), test_a_task_that_never_started_is_not_retryable(), test_a_task_that_used_all_its_attempts_is_not_retryable(), test_raising_the_retries_makes_it_retryable_and_leaves_its_blocked_dependent_out()

### Community 158 - "test_heartbeat.py"
Cohesion: 0.24
Nodes (4): beating(), fresh(), test_a_beat_that_stopped_is_not_fresh(), test_a_loop_beats_while_it_runs_and_the_file_goes_when_it_ends()

### Community 159 - "agent_requests.py"
Cohesion: 0.39
Nodes (4): limits(), reviewer_request(), tester_request(), test_the_reviewer_can_only_read_and_the_tester_can_edit()

### Community 160 - "test_plan_fields.py"
Cohesion: 0.50
Nodes (6): task(), test_bad_tasks_are_refused(), test_optional_fields_default_to_empty_and_unknown_fields_are_dropped(), test_paths_outside_the_repository_are_refused(), test_story_fields_are_checked(), validate_tasks()

### Community 161 - "builder.md"
Cohesion: 0.33
Nodes (5): Overview, What to do, What you must not do, Where you work, Your answer

### Community 162 - "reviewer.md"
Cohesion: 0.33
Nodes (5): Overview, What to do, What you must not do, Where you work, Your answer

### Community 163 - "tester.md"
Cohesion: 0.33
Nodes (5): Overview, What to do, What you must not do, Where you work, Your answer

### Community 164 - "orch-feed.js"
Cohesion: 0.67
Nodes (3): create(), draw(), row()

### Community 165 - "orch-run.js"
Cohesion: 0.83
Nodes (3): button(), render(), summary()

### Community 166 - "orch-stories.js"
Cohesion: 0.83
Nodes (3): bar(), card(), render()

### Community 167 - ".client"
Cohesion: 0.50
Nodes (3): test_a_used_up_budget_refuses_the_restart(), test_with_a_retry_left_a_new_loop_is_started_to_retry_it(), test_with_no_retry_left_it_says_why_and_starts_nothing()

## Knowledge Gaps
- **49 isolated node(s):** `agent-brigade`, `Planner JSON plan answer`, `Re-plan flow`, `Publisher plan block`, `Agent Brigade .claude/CLAUDE.md (graphify trigger)` (+44 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1070 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **32 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `planner.py`, `Planning Jobs`, `RunControlService`, `ContinueService`, `hook.py`, `Publisher API`, `tester_run.py`, `TaskControlService`, `JiraClient`, `Jira Sync`, `Check Model`, `services/publisher.py`, `Jira Client Tests`, `Publisher CLI Tests`, `main`, `_sub_task_id`, `builder_run.py`, `test_publisher_api.py`, `Readiness Tests`, `App Factory`, `run_directory`, `Settings Tests`, `Health & Projects API`, `Planning Pipeline Tests`, `attempt_rows.py`, `_Loop`, `pathlib`, `Re-plan Tests`, `project`, `task_run.py`, `progress.py`, `test_merge_git.py`, `StoryRunner`, `judge_attempt`, `test_reset.py`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Are the 61 inferred relationships involving `Settings` (e.g. with `create_app()` and `load_settings()`) actually correct?**
  _`Settings` has 61 INFERRED edges - model-reasoned connections that need verification._
- **What connects `agent-brigade`, `Planner JSON plan answer`, `Re-plan flow` to the rest of the system?**
  _49 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Readiness Checks` be split into smaller, more focused modules?**
  _Cohesion score 0.09178743961352658 - nodes in this community are weakly interconnected._
- **Why does `JiraClient` connect `JiraClient` to `Readiness Checks`, `Planning Jobs`, `hook.py`, `Publisher Guard`, `Jira Sync`, `Check Model`, `services/publisher.py`, `Jira Client Tests`, `Publisher CLI Tests`, `Approval Errors & Jira Write`, `Plan Check & Parse`, `App Factory`, `Health & Projects API`, `Settings`, `.client`, `FakeJira`, `_Loop`, `pathlib`, `project`, `StoryRunner`, `guard.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 75 inferred relationships involving `get_session()` (e.g. with `lifespan()` and `.approve()`) actually correct?**
  _`get_session()` has 75 INFERRED edges - model-reasoned connections that need verification._
- **Should `get_session` be split into smaller, more focused modules?**
  _Cohesion score 0.0927536231884058 - nodes in this community are weakly interconnected._