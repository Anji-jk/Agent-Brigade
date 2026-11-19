# Graph Report - Agent-Brigade  (2026-11-13)

## Corpus Check
- 171 files · ~68,173 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 13 file(s) not represented in the graph (top: (none) 5, .css 4, .example 1)

## Summary
- 1871 nodes · 5412 edges · 104 communities (80 shown, 24 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 409 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Agent Runner
- Plan View Rendering
- Readiness Checks
- Plan Field Validation
- DB Engine & Lifespan
- Planning CLI
- Planning Jobs
- Publisher API
- Projects Service
- Tracker Models
- Transcript & Messages
- Publisher Guard
- Planning API
- Project Commands
- Jira Client
- Tracker Items Board
- Jira Sync
- Run IDs & Folders
- Plan Formatting Tests
- Check Model
- Planning API Tests
- Publisher Service
- Jira Client Tests
- Publisher CLI Tests
- Planner Prompt
- Settings & Errors
- Plan Approval
- Readiness Tests
- Publisher API Tests
- Approval Errors & Jira Write
- Plan Check & Parse
- App Factory
- Upload Text Extraction
- Settings Tests
- Health & Projects API
- Settings Class
- Planning Pipeline Tests
- Git Repo Helpers
- Planner & Runner Docs
- Story Runs Repository
- Uploaded Files
- Plan File Validation
- Planner Answer Parsing
- Story Samples
- DB Models
- Project Check
- ADF Conversion
- CI Workflow
- Publisher Files
- Technical Document Concepts
- Plan Block Parsing
- Publisher Records
- Atomic JSON Writes
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
- Plan Panel UI
- Planning Tree
- App Shell JS
- Planning Plan Screen
- Safety Screen
- Backend & Database Docs
- Plan View UI
- Story Card UI
- Story Tasks Tests
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
- Docs Folder
- Test Client Fixture
- CLI Parsers
- Markdown UI
- Popup UI
- VS Live Share Config
- Phases & Testing Docs
- Brigade Favicon
- agent-brigade

## God Nodes (most connected - your core abstractions)
1. `JiraClient` - 73 edges
2. `Settings` - 70 edges
3. `get_session()` - 60 edges
4. `plan_story()` - 48 edges
5. `PlanValidationError` - 46 edges
6. `load_plan()` - 45 edges
7. `PlanningService` - 40 edges
8. `read_story()` - 39 edges
9. `approve_plan()` - 39 edges
10. `story()` - 38 edges

## Surprising Connections (you probably didn't know these)
- `run()` --uses--> `TrackerError`  [INFERRED]
  backend/api/planning.py → core/trackers/errors.py
- `run()` --uses--> `StoryError`  [INFERRED]
  backend/api/planning.py → core/trackers/jira/story.py
- `run()` --uses--> `SyncError`  [INFERRED]
  backend/api/planning.py → core/trackers/jira/sync.py
- `run()` --uses--> `ApprovalError`  [INFERRED]
  backend/api/planning.py → pipeline/planning/approval.py
- `run()` --uses--> `JiraWriteError`  [INFERRED]
  backend/api/planning.py → pipeline/planning/approval.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Builder, tester and reviewer sub-task loop** — docs_technical_document_builder_agent, docs_technical_document_tester_agent, docs_technical_document_reviewer_agent, docs_technical_document_orchestrator [EXTRACTED 1.00]
- **Five-tab web page** — docs_technical_document_publisher_tab, docs_technical_document_planning_tab, docs_technical_document_orchestrator_tab, docs_technical_document_overview_tab, docs_technical_document_delivery_tab [EXTRACTED 1.00]
- **index.html tab panels** — frontend_index_publisher_section, frontend_index_planning_section, frontend_index_orchestrator_section, frontend_index_sidebar_nav [EXTRACTED 1.00]
- **Architecture decision records 0001-0004** — docs_adr_0001_one_central_database, docs_adr_0002_core_pipeline_backend_layers, docs_adr_0003_plain_html_frontend, docs_adr_0004_agents_in_claude_agents [EXTRACTED 1.00]
- **Epic to Stories hierarchy in Jira plan** — docs_screens_01_publisher_epic_101, docs_screens_01_publisher_story_101, docs_screens_01_publisher_story_102, docs_screens_01_publisher_story_103 [EXTRACTED 1.00]
- **Epic to Story to Sub-task hierarchy** — docs_screens_02_planning_stories_epic_101, docs_screens_02_planning_stories_story_101, docs_screens_02_planning_stories_story_102, docs_screens_02_planning_stories_story_103, docs_screens_02_planning_stories_subtasks [EXTRACTED 1.00]
- **Planning flow: browse JIRA tree, pick story, review and approve plan** — docs_screens_03_planning_plan_jira_projects_tree, docs_screens_03_planning_plan_story_list, docs_screens_03_planning_plan_plan_panel, docs_screens_03_planning_plan_approve_replan [INFERRED 0.85]

## Communities (104 total, 24 thin omitted)

### Community 0 - "Agent Runner"
Cohesion: 0.06
Nodes (48): agent_header(), AgentError, AgentReply, AgentRequest, claude_command(), claude_settings(), ClaudeCliRunner, parse_reply() (+40 more)

### Community 1 - "Plan View Rendering"
Cohesion: 0.07
Nodes (41): _budget_lines(), _footer(), _header(), _replan_lines(), _task_lines(), load_planner_limits(), planner_limits(), PlannerLimits (+33 more)

### Community 2 - "Readiness Checks"
Cohesion: 0.06
Nodes (33): acceptance_criteria(), _label(), _blocked_by(), check_story_key(), format_story(), _item(), _links(), read_story() (+25 more)

### Community 3 - "Plan Field Validation"
Cohesion: 0.09
Nodes (34): _acceptance_criteria(), check_task(), _complexity(), _flag(), _paths(), PlanValidationError, relative_path(), _story_fields() (+26 more)

### Community 4 - "DB Engine & Lifespan"
Cohesion: 0.07
Nodes (17): lifespan(), get_engine(), make_engine(), session_factory(), init_db(), add_missing_columns(), UpgradeError, _Reader (+9 more)

### Community 5 - "Planning CLI"
Cohesion: 0.09
Nodes (22): approve(), fetch_story(), finish(), plan(), project_root(), replan(), show(), check_budget() (+14 more)

### Community 6 - "Planning Jobs"
Cohesion: 0.11
Nodes (13): _finish(), JobContext, _plan(), PlanningJob, run_job(), PlanningService, Conflict, Executor (+5 more)

### Community 7 - "Publisher API"
Cohesion: 0.12
Nodes (22): confirm(), download(), file_out(), list_chats(), open_chat(), _plan(), read_uploads(), run() (+14 more)

### Community 8 - "Projects Service"
Cohesion: 0.08
Nodes (8): list_projects(), sync_env_project(), JiraClient, check(), main(), story(), sync(), test_from_settings_names_what_is_missing()

### Community 9 - "Tracker Models"
Cohesion: 0.10
Nodes (18): kind_of(), _name(), Story, WorkItem, _answers(), _dependencies(), _doc_target(), _inside() (+10 more)

### Community 10 - "Transcript & Messages"
Cohesion: 0.12
Nodes (27): message_with_files(), wrap(), fix_prompt(), find_transcript(), main(), parse_transcript(), project_folder_name(), read_chat() (+19 more)

### Community 11 - "Publisher Guard"
Cohesion: 0.11
Nodes (25): check_against_jira(), _norm(), _story(), _subtasks(), Plan, PlannedStory, PlannedSubtask, created_note() (+17 more)

### Community 12 - "Planning API"
Cohesion: 0.18
Nodes (27): approve(), checks(), get_run(), plan(), replan(), run(), run_out(), service() (+19 more)

### Community 13 - "Project Commands"
Cohesion: 0.10
Nodes (16): CommandResult, project_python(), project_test_command(), run_command(), _since(), split_command(), venv_python(), test_models_can_be_imported_first() (+8 more)

### Community 14 - "Jira Client"
Cohesion: 0.11
Nodes (13): quote_jql(), _board_item(), Issue, as_json(), cut(), epic(), epics(), main() (+5 more)

### Community 15 - "Tracker Items Board"
Cohesion: 0.15
Nodes (22): board(), BoardItem, _fields(), _key_order(), last_synced(), replace_board(), _row_fields(), SyncCounts (+14 more)

### Community 16 - "Jira Sync"
Cohesion: 0.14
Nodes (17): get_session(), board_items(), sync_board(), SyncError, SyncResult, board(), engine(), project_id() (+9 more)

### Community 17 - "Run IDs & Folders"
Cohesion: 0.10
Nodes (15): taken(), new_run_id(), project_folder(), run_directory(), RunIdError, validate_run_id(), test_a_run_folder_is_inside_the_projects_brigade_folder(), test_a_run_id_is_the_story_key_the_date_and_4_hex_characters() (+7 more)

### Community 18 - "Plan Formatting Tests"
Cohesion: 0.15
Nodes (20): format_plan(), _records(), planned(), test_a_budget_shows_what_planning_used_and_what_is_left(), test_a_budget_smaller_than_the_task_limits_gets_a_warning(), test_a_replan_and_a_replaced_plan_are_shown(), test_notes_no_links_and_approval_are_shown(), test_the_plan_reads_like_the_planning_screen() (+12 more)

### Community 19 - "Check Model"
Cohesion: 0.16
Nodes (10): Check, plural(), StoryCheck, check_checkout(), check_project_files(), check_tests(), format_checks(), run_checks() (+2 more)

### Community 20 - "Planning API Tests"
Cohesion: 0.12
Nodes (16): Inline, Later, make_world(), plan(), test_a_failed_readiness_check_fails_the_run_with_the_check_text(), test_a_refused_plan_fails_the_run_with_the_reason(), test_a_story_not_on_the_board_or_a_bad_key_is_refused(), test_approve_with_jira_down_keeps_the_plan_waiting() (+8 more)

### Community 21 - "Publisher Service"
Cohesion: 0.17
Nodes (10): PublisherService, ChatSummary, ChatView, ConfirmResult, Conflict, display_id(), NotFound, PublisherError (+2 more)

### Community 22 - "Jira Client Tests"
Cohesion: 0.21
Nodes (22): JiraError, body(), issue_json(), make(), wrapped(), test_a_blocks_link_puts_the_blocker_in_the_inward_issue(), test_a_comment_goes_to_its_own_issue_as_rich_text(), test_check_lists_the_space_and_its_epics() (+14 more)

### Community 23 - "Publisher CLI Tests"
Cohesion: 0.24
Nodes (22): run(), epic_reply(), reply(), issue(), ok(), runner(), factory(), handler() (+14 more)

### Community 24 - "Planner Prompt"
Cohesion: 0.13
Nodes (19): _clean(), _cut(), _money(), planner_prompt(), _previous_plan(), _subtask(), previous(), prompt() (+11 more)

### Community 25 - "Settings & Errors"
Cohesion: 0.14
Nodes (8): get_settings(), TrackerError, main(), main(), PublisherChat, _create(), Created, verify()

### Community 26 - "Plan Approval"
Cohesion: 0.14
Nodes (11): utc_now(), _check(), _comment(), mark_superseded(), _pair(), _waiting(), load_plan(), plan_path() (+3 more)

### Community 27 - "Readiness Tests"
Cohesion: 0.22
Nodes (20): Epic, item(), ready_project(), settings(), statuses(), story(), test_a_ready_story(), test_all_done_fails() (+12 more)

### Community 28 - "Publisher API Tests"
Cohesion: 0.15
Nodes (16): docx_bytes(), proposal(), start(), test_a_bad_file_is_refused_before_the_agent_runs(), test_a_chat_that_is_busy_refuses_a_second_message(), test_a_confirm_that_creates_nothing_withdraws_the_proposal(), test_a_failed_start_leaves_no_chat(), test_a_new_chat_gets_an_id_and_a_checked_proposal() (+8 more)

### Community 29 - "Approval Errors & Jira Write"
Cohesion: 0.26
Nodes (18): ApprovalError, approve_plan(), JiraWriteError, blockers(), setup(), test_a_comment_that_failed_is_added_on_the_next_try_without_a_second_link(), test_a_link_jira_does_not_show_afterwards_is_not_approved(), test_a_link_that_is_already_in_jira_is_not_written_or_commented_again() (+10 more)

### Community 30 - "Plan Check & Parse"
Cohesion: 0.22
Nodes (17): check_plan(), parse_plan(), PlanCheck, jira(), plan(), story(), subtask(), test_a_broken_plan_block_is_refused() (+9 more)

### Community 31 - "App Factory"
Cohesion: 0.13
Nodes (9): create_app(), load_settings(), client(), make_settings(), test_a_bad_setting_stops_startup_and_names_it(), test_local_only_project_is_named_after_its_folder(), test_no_project_in_env_means_an_empty_list(), test_starting_twice_does_not_duplicate_and_picks_up_changes() (+1 more)

### Community 32 - "Upload Text Extraction"
Cohesion: 0.17
Nodes (13): check_upload(), _docx(), extract_text(), FileRejected, _pdf(), _plain(), blank_pdf(), test_docx_paragraphs_and_tables_are_read() (+5 more)

### Community 33 - "Settings Tests"
Cohesion: 0.15
Nodes (18): clean_env(), load(), test_a_path_with_a_hidden_escape_character_is_rejected(), test_defaults_when_nothing_is_set(), test_docs_dir_and_test_command(), test_docs_dir_must_be_inside_the_project(), test_empty_values_in_env_file_mean_not_set(), test_ensure_dirs_creates_folders() (+10 more)

### Community 34 - "Health & Projects API"
Cohesion: 0.14
Nodes (5): health(), db_session(), list_projects(), HealthOut, ProjectOut

### Community 36 - "Planning Pipeline Tests"
Cohesion: 0.26
Nodes (19): main(), jira_board(), planner(), project(), test_a_failed_readiness_check_stops_before_the_planner(), test_a_run_id_is_used_once(), test_without_a_docs_folder_doc_targets_are_left_out(), test_approve_with_nothing_to_write_says_so() (+11 more)

### Community 37 - "Git Repo Helpers"
Cohesion: 0.16
Nodes (15): current_branch(), test_clean_checkout_on_main(), test_uncommitted_changes_and_another_branch(), test_unknown_base_branch(), git(), make_repo(), test_a_failing_git_command_says_which(), test_bad_base_branches_are_refused() (+7 more)

### Community 38 - "Planner & Runner Docs"
Cohesion: 0.12
Nodes (18): Agent Brigade CLAUDE.md, Agent runner (claude_runner), Planner agent, Planner JSON plan answer, Re-plan flow, Publisher agent, pipeline.publisher.cli read-only tool, Choosing the Epic procedure (+10 more)

### Community 39 - "Story Runs Repository"
Cohesion: 0.20
Nodes (13): fail_unfinished(), get_run(), latest_runs(), _of_story(), run_id_taken(), runs_of_story(), runs_with_status(), start_run() (+5 more)

### Community 40 - "Uploaded Files"
Cohesion: 0.18
Nodes (11): chat_folder(), find(), list_files(), safe_name(), save(), stored_names(), StoredFile, test_a_name_that_is_not_a_stored_name_is_not_saved() (+3 more)

### Community 41 - "Plan File Validation"
Cohesion: 0.21
Nodes (17): save_plan(), validate_tasks(), document(), task(), test_a_bad_run_id_never_becomes_a_path(), test_a_bad_stored_plan_is_refused(), test_a_plan_is_never_overwritten(), test_a_saved_plan_is_read_back_checked() (+9 more)

### Community 42 - "Planner Answer Parsing"
Cohesion: 0.16
Nodes (7): _candidate_documents(), parse_planner_answer(), fix_prompt(), ask_planner(), _metrics(), planner_request(), repository_state()

### Community 43 - "Story Samples"
Cohesion: 0.25
Nodes (14): answer(), entry(), merge(), test_a_good_answer_becomes_the_plan_and_records_only_new_jira_links(), test_a_jira_dependency_the_planner_left_out_is_put_back(), test_bad_dependencies_are_refused(), test_cycles_sizes_paths_and_empty_outcomes_are_refused(), test_doc_targets_must_be_in_the_docs_folder() (+6 more)

### Community 44 - "DB Models"
Cohesion: 0.29
Nodes (14): AgentRun, Attempt, Base, BudgetReservation, ChatSession, Check, Merge, Project (+6 more)

### Community 45 - "Project Check"
Cohesion: 0.23
Nodes (13): check_project(), _claude_md(), _docs(), Finding, section_headings(), _sections(), test_bom_in_claude_md_is_fine(), test_everything_found() (+5 more)

### Community 46 - "ADF Conversion"
Cohesion: 0.16
Nodes (7): adf_to_text(), _inline(), text_to_adf(), _error(), _wait_seconds(), test_adf_lists_code_and_mentions(), test_adf_round_trip_keeps_paragraphs_and_lines()

### Community 47 - "CI Workflow"
Cohesion: 0.11
Nodes (17): runs-on, steps, jobs, checks, name, on, pull_request, push (+9 more)

### Community 48 - "Publisher Files"
Cohesion: 0.21
Nodes (6): prepare_files(), save_files(), TurnResult, Upload, _add(), Turn

### Community 49 - "Technical Document Concepts"
Cohesion: 0.12
Nodes (14): Agent Brigade Technical Document, Agent Brigade, Story budget and reservations, Builder agent, Worktree isolation per sub-task, Four locks, Merging into the story branch, Orchestrator (+6 more)

### Community 50 - "Plan Block Parsing"
Cohesion: 0.15
Nodes (7): split_files(), find_plan_block(), without_plan_block(), _Builder, _is_tool_result(), _texts(), test_the_last_plan_block_is_taken_and_removed_from_the_text()

### Community 51 - "Publisher Records"
Cohesion: 0.30
Nodes (7): confirmed_keys(), confirmed_records(), created_from(), last_confirmed(), open_proposal(), withdraw_open_proposal(), PublishRecord

### Community 52 - "Atomic JSON Writes"
Cohesion: 0.22
Nodes (5): write_json_atomic(), test_a_failed_replace_leaves_no_temporary(), test_a_failed_write_keeps_the_old_file_and_leaves_no_temporary(), test_replaces_an_existing_file(), test_writes_json_and_creates_the_folder()

### Community 53 - "Thread UI"
Cohesion: 0.29
Nodes (12): add(), clearThread(), createdLinks(), fileChip(), linkItem(), notice(), publisherBubble(), replay() (+4 more)

### Community 54 - "Planning UI"
Cohesion: 0.38
Nodes (13): card(), check(), epicShown(), hit(), init(), load(), notice(), plan() (+5 more)

### Community 55 - "Re-plan Tests"
Cohesion: 0.44
Nodes (12): replan_story(), story(), first_plan(), test_a_plan_of_another_story_or_a_missing_run_is_named(), test_a_refused_replan_leaves_the_old_plan_waiting(), test_a_replaced_plan_cannot_be_replanned_again(), test_a_replan_is_a_new_run_made_from_the_old_one_and_your_idea(), test_a_replan_needs_a_project() (+4 more)

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

### Community 63 - "Plan Panel UI"
Cohesion: 0.44
Nodes (9): approve(), finished(), learn(), open(), paint(), pick(), refresh(), replan() (+1 more)

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
Cohesion: 0.39
Nodes (3): prohibitions(), test_forbidding_text_is_found(), test_ordinary_text_passes()

### Community 68 - "Backend & Database Docs"
Cohesion: 0.29
Nodes (6): Backend JSON API, FastAPI backend, SQLite database (brigade.db), Live events (events.jsonl, SSE), Overview tab, Settings and environment variables

### Community 69 - "Plan View UI"
Cohesion: 0.52
Nodes (6): budgetLines(), header(), links(), metrics(), notes(), render()

### Community 70 - "Story Card UI"
Cohesion: 0.52
Nodes (6): badge(), button(), panel(), render(), runLine(), viewButton()

### Community 71 - "Story Tasks Tests"
Cohesion: 0.43
Nodes (5): work_item(), test_a_subtask_without_criteria_stops_before_anything_runs(), test_long_jira_text_is_cut_with_a_marker(), test_more_than_thirty_open_subtasks_are_refused(), test_subtasks_need_criteria_and_at_least_one_open_item()

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

## Knowledge Gaps
- **49 isolated node(s):** `agent-brigade`, `Agent Brigade Technical Document`, `Builder agent`, `Tester agent`, `Claude Code CLI runtime` (+44 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 500 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JiraClient` connect `Projects Service` to `Readiness Checks`, `Planning CLI`, `Planning Jobs`, `Publisher Guard`, `Jira Client`, `Jira Sync`, `Check Model`, `Planning API Tests`, `Publisher Service`, `Jira Client Tests`, `Publisher CLI Tests`, `Settings & Errors`, `Plan Approval`, `Approval Errors & Jira Write`, `Plan Check & Parse`, `App Factory`, `Health & Projects API`, `Settings Class`, `ADF Conversion`, `Publisher Records`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Are the 31 inferred relationships involving `JiraClient` (e.g. with `create_app()` and `JobContext`) actually correct?**
  _`JiraClient` has 31 INFERRED edges - model-reasoned connections that need verification._
- **What connects `agent-brigade`, `Agent Brigade Technical Document`, `Builder agent` to the rest of the system?**
  _49 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Agent Runner` be split into smaller, more focused modules?**
  _Cohesion score 0.05851619644723093 - nodes in this community are weakly interconnected._
- **Why does `Settings` connect `Settings Class` to `Agent Runner`, `Planning CLI`, `Planning Jobs`, `Projects Service`, `Jira Client`, `Jira Sync`, `Check Model`, `Publisher Service`, `Jira Client Tests`, `Publisher CLI Tests`, `Settings & Errors`, `Readiness Tests`, `Publisher API Tests`, `App Factory`, `Settings Tests`, `Health & Projects API`, `ADF Conversion`, `Publisher Records`, `Re-plan Tests`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 29 inferred relationships involving `Settings` (e.g. with `create_app()` and `load_settings()`) actually correct?**
  _`Settings` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Should `Plan View Rendering` be split into smaller, more focused modules?**
  _Cohesion score 0.06874717322478517 - nodes in this community are weakly interconnected._