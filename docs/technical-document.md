# Agent Brigade — Technical Document

Agent Brigade is a tool that takes a Jira story and produces tested, reviewed, locally committed code for it. A team of AI agents does the work, each with one job, and a plain-code orchestrator runs them. This document is the design for building it.

## 1. Introduction

### 1.1 Purpose

This document specifies what Agent Brigade must do and how it will be built. It covers:

- requirements, architecture and components;

- the orchestrator and the agents;

- data, integrations, interfaces and security;

- testing and the delivery plan.

It is written before implementation and is the reference the build is checked against.

### 1.2 Audience

- **Developers** who will build Agent Brigade.

- **Reviewers and team leads** who approve the design.

- **Teams** who will connect their own projects to it.

No prior knowledge of the system is assumed. Terms are explained in the glossary (section 18).

### 1.3 Scope

| In scope                                                         | Out of scope                                          |
|------------------------------------------------------------------|-------------------------------------------------------|
| Turning written requirements into Jira stories and sub-tasks     | Deployment of the code that agents produce            |
| Planning a story into an ordered, checkable plan                 | Merging into a project's main branch without a person |
| Building each sub-task with separate AI agents                   | Resolving merge conflicts automatically               |
| Verifying, committing and merging work into a local story branch | Bugs raised after deployment                          |
| Keeping Jira statuses, labels and comments in step               | A dashboard across several projects                   |
| Monitoring progress, tokens and cost                             | Running on a shared server for many users (later)     |
| Documentation and a report per story                             |                                                       |
| GitHub as an optional tracker instead of Jira                    |                                                       |

### 1.4 Key terms

| Term           | Meaning                                                                                         |
|----------------|-------------------------------------------------------------------------------------------------|
| Target project | Any Git repository whose stories Agent Brigade builds. Agent Brigade never changes its own code |
| Story          | A Jira story: the unit that is planned and built                                                |
| Sub-task       | A Jira sub-task under a story: one piece of work built by the agents                            |
| Agent          | One Claude Code session with one role                                                           |
| Orchestrator   | The plain-code engine that runs agents, checks their work and decides outcomes                  |

## 2. Background and problem statement

AI coding agents can write working code, but used one at a time from a chat window they are hard to trust, hard to scale and invisible to the rest of the team.

### 2.1 Problems this project solves

| Problem                                                   | What happens today                                     | Consequence                                             |
|-----------------------------------------------------------|--------------------------------------------------------|---------------------------------------------------------|
| Requirements arrive as meetings, documents and messages   | Someone rewrites them into Jira by hand                | Slow, inconsistent tickets; missing acceptance criteria |
| One agent writes, tests and judges its own work           | The agent reports success it has not proven            | Defects pass unnoticed                                  |
| Agents run one task at a time in the developer's checkout | Work is serial, and a bad change can damage local work | Low throughput, risky experiments                       |
| No limits on agents                                       | Long or looping sessions                               | Unpredictable cost                                      |
| Progress lives in a terminal                              | The team cannot see what was done or why it failed     | Status meetings and manual Jira updates                 |
| A crash or usage limit mid-task                           | Work and context are lost                              | Repeated spend and time                                 |

### 2.2 Proposed solution

Agent Brigade puts a clear process around AI agents.

1.  **Intake.** Requirements become well-formed Jira stories and sub-tasks, and a person confirms before anything is written.

2.  **Planning.** A planning agent turns a story into an ordered plan. The plan names files and dependencies and gives every sub-task pass/fail criteria.

3.  **Building.** Each sub-task runs in its own isolated copy of the code. Three separate agents handle it in turn: a builder, a tester and a reviewer.

4.  **Verification.** The orchestrator measures the results itself. It checks which files changed, whether the change stayed in scope, and whether the tests pass.

5.  **Integration.** Verified work is committed and merged into one local branch per story.

6.  **Visibility.** Jira, a local web page and a report all show the same state, cost and history.

## 3. Goals and non-goals

The primary goal: produce a verified, reviewable story branch from a Jira story, with no manual step between planning and the last commit.

### 3.1 Goals

| Sl. No. | Goal                                        | Measured by                                                                                                                                   |
|---------|---------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| G1      | Well-formed Jira work from any requirements | Every created sub-task has a description and acceptance criteria and sits under an existing epic; nothing is created before a person confirms |
| G2      | Executable plans                            | Every sub-task in the plan has files, dependencies, a parallel-safe mark and pass/fail criteria; the plan is validated each time it is loaded |
| G3      | No single point of trust                    | The agent that builds never tests or reviews its own work; changed files and test results are measured by the orchestrator                    |
| G4      | Bounded cost                                | Every agent has a turn limit and a spending cap; a story can have a budget that parallel work cannot exceed                                   |
| G5      | Visible and controllable                    | Each agent's state, events, tokens and cost appear live; any sub-task can be stopped with no process left behind                              |
| G6      | Recoverable                                 | A crash, closed window or usage limit leaves work that continues from the stage it reached                                                    |
| G7      | Faster where safe                           | Independent sub-tasks run in parallel (default 3, maximum 5); the combined result is tested before it counts                                  |
| G8      | Jira always true                            | Statuses, labels and comments match Agent Brigade's records after every step                                                                  |
| G9      | Works on any project                        | Connecting a project needs settings and the project's own CLAUDE.md, no code change                                                           |
| G10     | Built to a high standard                    | Every code file has unit tests; CI runs tests, lint and format checks                                                                         |

### 3.2 Non-goals

- **Merging into main automatically.** Sub-tasks merge into the story branch automatically. Merging a story into main stays a human decision.

- **Automatic conflict resolution.** A conflict stops the sub-task for a person.

- **Writing a project's rules.** A project's CLAUDE.md (its structure, commands and rules for agents) is written by that project's developers.

- **Multi-agent chat.** Agents do not talk to each other. Each is an isolated session, and the orchestrator passes only measured facts between them.

## 4. Users and use cases

Three kinds of people use Agent Brigade. Each needs one part of it.

| User                      | Needs                                                   | Uses                                     |
|---------------------------|---------------------------------------------------------|------------------------------------------|
| Product owner or analyst  | Turn meeting notes and documents into Jira work quickly | Publisher tab                            |
| Developer or tech lead    | Plan stories, run the agents, inspect and merge results | Planning, Orchestrator and Delivery tabs |
| Team members and managers | Know what is being built, what failed and what it cost  | Jira board and Overview tab              |

### 4.1 Main use cases

1.  **Publish requirements.** Upload a transcript or paste text, review the proposed stories and sub-tasks, then confirm to create them in Jira.

2.  **Plan a story.** Sync from Jira, check the story is ready, set an optional budget and get a plan. Approve it, or ask for a re-plan.

3.  **Build a story.** Click Build, watch each sub-task move through the builder, tester and reviewer, and see Jira update live.

4.  **Handle a problem.** Cancel a sub-task, continue after an interruption, or start a fresh attempt.

5.  **Deliver.** Generate the feature documentation and the story report, then merge the story branch yourself.

6.  **Connect a new project.** Fill in the settings, write the project's CLAUDE.md, and start.

## 5. Requirements

Each requirement is written so it can be checked by running the feature on a real project.

### 5.1 Functional requirements

| ID    | Area       | Requirement                                                                                                                                |
|-------|------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| FR-1  | Intake     | Accept requirements as chat text or uploaded transcripts and documents; propose stories and sub-tasks under existing epics only            |
| FR-2  | Intake     | Write nothing to Jira until a person confirms; refuse duplicates, unknown epics and sub-tasks missing a description or acceptance criteria |
| FR-3  | Sync       | Import new and changed epics, stories and sub-tasks from Jira                                                                              |
| FR-4  | Checks     | Before planning, check the story, its sub-tasks and the project's CLAUDE.md; report each failure with its fix                              |
| FR-5  | Planning   | Ask for an optional budget, then produce a plan: order, dependencies, files, parallel-safe marks and the story branch name                 |
| FR-6  | Planning   | Dependencies missing from Jira are written back as "is blocked by" links with a comment, only after the plan is approved                   |
| FR-7  | Planning   | Re-plan takes the requested changes and replaces the existing plan                                                                         |
| FR-8  | Build      | Create the story branch; give each sub-task its own isolated copy of the code; run builder, tester and reviewer as separate sessions       |
| FR-9  | Build      | Verify changed files, scope and tests independently of the agents; merge passing work into the story branch in dependency order            |
| FR-10 | Build      | Retry a failed sub-task with feedback, up to a configurable limit (0 to 5)                                                                 |
| FR-11 | Control    | Cancel, continue after an interruption, re-attempt, and run independent sub-tasks in parallel up to a configurable limit                   |
| FR-12 | Jira       | Move statuses, set labels and post comments as defined in section 12.1                                                                     |
| FR-13 | Monitoring | Show live events per agent; record tokens and cost per agent, sub-task, story and project                                                  |
| FR-14 | Delivery   | Write a feature document in the project's docs folder in its existing format; produce a report per story                                   |
| FR-15 | Projects   | Connect any Git project through settings only                                                                                              |
| FR-16 | Optional   | Use GitHub Issues and Projects instead of Jira                                                                                             |

### 5.2 Non-functional requirements

| ID    | Quality         | Requirement                                                                                                     |
|-------|-----------------|-----------------------------------------------------------------------------------------------------------------|
| NFR-1 | Safety          | Agents receive no credentials; each role gets only the tools it needs; nothing is pushed to a remote by default |
| NFR-2 | Consistency     | One store decides every status; Jira, the page and reports only reflect it                                      |
| NFR-3 | Durability      | A crash never leaves a half-written record                                                                      |
| NFR-4 | Concurrency     | Git operations, merges and budget checks are serialised with locks                                              |
| NFR-5 | Privacy         | The web page is reachable only from the local machine and never shows secrets                                   |
| NFR-6 | Testability     | Unit tests for every code file; external services are replaced by test doubles in unit tests                    |
| NFR-7 | Portability     | Runs on Windows and Linux; no machine-specific paths                                                            |
| NFR-8 | Configurability | All settings are read and validated in one place, with a clear error naming any bad value                       |
| NFR-9 | Performance     | Status and events appear on the page within a few seconds of happening                                          |

## 6. Technology stack

The stack is chosen to run entirely on a developer's machine, with no servers to manage.

| Layer            | Technology                                                  | Why                                                                                                     |
|------------------|-------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| Language         | Python 3.12                                                 | Mature tooling for subprocesses, Git and HTTP; quick to test                                            |
| Backend          | FastAPI + uvicorn                                           | Typed request and response models; built-in support for streaming live events                           |
| Database         | SQLite through SQLAlchemy 2                                 | One file per project, nothing to install; SQLAlchemy keeps a later move to Postgres simple              |
| Frontend         | One HTML page with JavaScript                               | No build step; easy for any developer to change                                                         |
| Live updates     | Server-sent events                                          | One-way stream from server to page;                                                                     |
| AI runtime       | Claude Code CLI, run headless                               | Uses the developer's own Claude Code; supports per-session tools, models, limits and resumable sessions |
| Tracker          | Jira Cloud REST API v3                                      | Where teams already plan and follow work                                                                |
| Optional tracker | GitHub REST and GraphQL APIs (Issues, sub-issues, Projects) | For teams that track work in GitHub                                                                     |
| Version control  | Git, with worktrees                                         | A separate working folder per sub-task without copying the repository                                   |
| Quality          | pytest, ruff, GitHub Actions                                | The same checks locally and in CI                                                                       |

*(figure: see the original .docx)*

Figure 1. The Agent Brigade workflow from requirements to final deliverables.

## 7. System architecture

Agent Brigade runs as one local application.

- A web page calls a backend.

- The backend hands story work to the orchestrator.

- The orchestrator runs agents and writes results to the target project and the tracker.

*(figure: see the original .docx)*

Agent Brigade architecture · page, backend, orchestrator, agents, trackers, target project

The orchestrator (highlighted) is the only component that decides outcomes. Agents change code only inside isolated working copies. All records live in the target project's .agent-brigade/ folder, and Jira is updated from those records.

### 7.1 Components

| Component        | Responsibility                                                                                                                       |
|------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| Web page         | Five tabs (Publisher, Planning, Orchestrator, Overview, Delivery) with live updates; available on the local machine only             |
| Backend          | API for the page; runs use cases such as plan, build and cancel; streams events; reads all settings                                  |
| Orchestrator     | Schedules sub-tasks, runs the agent steps, verifies results, merges, enforces budgets and limits, recovers from failures             |
| Agent runner     | Starts Claude Code for one role with that role's model, tools and limits and a filtered environment; records events, tokens and cost |
| Tracker adapters | Jira (default) or GitHub: sync items, change statuses, set labels, post comments, add dependency links                               |
| Database layer   | Stores projects, stories, sub-tasks, attempts, agent runs, checks, merges and outbound tracker actions                               |
| Target project   | The code being built, with its tests, its CLAUDE.md, its docs folder and the .agent-brigade/ folder                                  |

### 7.2 Design principles

| Principle                   | Meaning                                                                     | Reason                                                    |
|-----------------------------|-----------------------------------------------------------------------------|-----------------------------------------------------------|
| Verify, do not trust        | The orchestrator measures changed files and test results itself             | An agent can be confidently wrong                         |
| Separate roles              | Builder, tester and reviewer are different sessions with different tools    | No agent grades its own work                              |
| Single source of truth      | The database decides every status; everything else mirrors it               | Two writers for one status disagree after the first crash |
| Orchestrator is code        | Scheduling and decisions are deterministic Python, not an agent             | Code can be tested, resumed and reasoned about            |
| Isolation                   | One working copy per sub-task; nothing touches the developer's own checkout | Parallel work cannot collide; failures are cheap          |
| Local first                 | Commits stay local unless a person chooses otherwise                        | Every outcome can be inspected and undone                 |
| Tool and project kept apart | Agent Brigade holds code only; each project holds its own data and rules    | One installation serves many projects                     |
| One place for settings      | Every setting is read and validated in one module                           | Easy to find, check and change                            |

## 8. The orchestrator

The orchestrator is the heart of Agent Brigade. It is plain Python code, not an AI agent, and it owns every decision: what starts, what counts as done, and what Jira shows.

**Why it is code and not an agent.** Scheduling and judging must be deterministic. A loop in code can be unit-tested, resumed after a crash and explained. An AI choosing what to run next cannot.

### 8.1 Responsibilities

- Load and validate the approved plan before every build.

- Create the story branch, and one isolated working copy (Git worktree) per sub-task attempt.

- Start each role as a fresh Claude Code session with that role's model, effort, tools and limits.

- Measure facts between roles: changed files, whether the change stayed within the sub-task's scope, and the test result.

- Decide the outcome, merge passing work under a lock, and update the database, the page and Jira.

- Enforce the story budget, the parallel limit, the retry limit and the test time limit.

### 8.2 Scheduling loop

1.  Take the story's run lock. A lock left by a process that has died is taken over.

2.  Work out each sub-task's state from the database. A record that says "running" but whose process is gone becomes **interrupted**.

3.  Choose what starts:

    - interrupted and retryable sub-tasks first, then ready ones in plan order;

    - two sub-tasks run together only if both are marked parallel-safe;

    - never more than the parallel limit at once.

4.  Before each agent starts, check the budget and reserve that agent's cap in one locked step.

5.  Wait for any sub-task to finish, record the result, then choose again.

6.  If a sub-task needs a person, or a limit is reached, start nothing new and let running work finish.

7.  When nothing more can run, move the story to **In Review** and write the story report.

### 8.3 One sub-task, step by step

*(figure: see the original .docx)*

One sub-task through the orchestrator · 4 steps, 1 decision, retry loop

| Step | Who          | What happens                                                                          | Passed to the next step                                     |
|------|--------------|---------------------------------------------------------------------------------------|-------------------------------------------------------------|
| 1    | Orchestrator | Creates the working copy from the story branch and checks the project's tests can run | Sub-task description and criteria, CLAUDE.md, relevant docs |
| 2    | Builder      | Implements the change and its unit tests                                              | Nothing it claims is trusted                                |
| 3    | Orchestrator | Measures changed files and scope; runs the tests                                      | Measured facts only                                         |
| 4    | Tester       | Writes tests for each acceptance criterion; may write only test files                 | Measured facts again                                        |
| 5    | Orchestrator | Runs the full test suite within the test time limit                                   | Pass or fail, with the end of the output                    |
| 6    | Reviewer     | Reads the change against the criteria with read-only tools                            | Verdict and reasons                                         |
| 7    | Orchestrator | Decides; commits; merges into the story branch                                        | Database, page and Jira updated                             |

The agents never talk to each other. Each sees only what the orchestrator measured, so no role inherits another role's mistaken belief.

### 8.4 Sub-task outcomes

| Outcome      | Meaning                                                                                 | What happens next                                                                             |
|--------------|-----------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| Done         | Passed every check and was merged                                                       | Dependent sub-tasks may start; Jira → Done                                                    |
| Failed       | A check found a defect, or the merge conflicted                                         | Retried with a fresh builder that is told what went wrong; after the last retry, Jira → Error |
| Needs review | The result could not be judged (crash, timeout, unusable report, budget or usage limit) | A person looks; nothing is committed                                                          |
| Interrupted  | The process ended without recording a result                                            | Continued from the stage it reached; finished agents are not re-run                           |
| Cancelled    | A person stopped it                                                                     | Working copy kept; Jira stays In Progress with a comment                                      |
| Blocked      | A dependency failed, needs review or was cancelled                                      | Waits; Jira stays To Do with a comment                                                        |

### 8.5 Merging into the story branch

- **Fast-forward.** Nothing else was merged since the sub-task started, so the branch moves forward and the earlier test run still holds.

- **Real merge.** Another sub-task merged first, so the tests run again on the combined code.

- **Conflict or failing combined tests.** The sub-task fails and the story branch is left unchanged.

- **Order.** A sub-task counts as done only after it is merged. A dependent sub-task therefore always starts from code that already has what it needs.

### 8.6 Attempts and cost

- Each retry or continuation is a new attempt within the same story run.

- Earlier attempts are archived.

- Every attempt's tokens and cost add up to the sub-task's total, so no spending is hidden.

## 9. Agents

Six agents do the AI work. Each is defined in one Markdown file whose header sets its name, description, tools, model, effort and maximum turns. A project can therefore change a role's model without touching code.

| Agent          | Runs when                                  | Reads                                                               | Produces                                                                                                    | Tools                                                        |
|----------------|--------------------------------------------|---------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------|
| Jira Publisher | A person chats on the Publisher tab        | Requirements text, transcripts, documents; the existing epics       | Proposed stories and sub-tasks with descriptions and acceptance criteria                                    | No file-writing tools; Jira is written by code after Confirm |
| Planner        | Plan or Re-plan is clicked                 | The story and sub-tasks, CLAUDE.md, the docs folder, the repository | The plan: order, dependencies (including any Jira lacks), files, parallel-safe marks, branch name, concerns | Read-only                                                    |
| Builder        | Each sub-task attempt                      | The sub-task, its criteria, retry feedback                          | Code changes and unit tests                                                                                 | Read, edit, write; the project's test command                |
| Tester         | After the builder's work passes the checks | The criteria and the measured change                                | Tests for every criterion, in test folders only                                                             | Read; write test files; the test command                     |
| Reviewer       | After the full suite passes                | The change, the criteria, the test result                           | Accept or reject, with reasons                                                                              | Read-only                                                    |
| Documenter     | After a story's sub-tasks are done         | The story, the merged change, an existing doc as a format example   | A feature document in the project's docs folder                                                             | Read; write in the docs folder only                          |

### 9.1 Rules for every agent

- **Tools are set on the command line per role.** Permission prompts are off for unattended runs. A tool limit set this way cannot be talked around, the way an instruction in a prompt can.

- **Credentials.** Agents receive only an allowlist of environment variables: basic process variables and Claude's own login and proxy settings. Jira and GitHub tokens never reach an agent.

- **Limits.** Every session has a turn limit, a time limit and a spending cap. The model that actually ran is recorded.

- **Sessions.** The Publisher keeps one resumable session per chat, so earlier messages are remembered. Every other agent starts fresh each time.

- **Project rules.** Each target project's CLAUDE.md describes its structure, commands and rules. Agents read it; Agent Brigade never writes it.

## 10. Features

Ten core features make up the first release. Each is described with its key points, its advantages and what it achieves.

### 10.1 Requirements to Jira (Publisher)

A chat turns requirements into Jira stories and sub-tasks under existing epics.

- Accepts typed text and uploaded transcripts or documents.

- One remembered session per chat, so requirements can be refined over several messages.

- Shows the full proposal before writing anything; only **Confirm** creates items in Jira.

- A publish guard refuses:

  - unknown epics;

  - duplicates;

  - sub-tasks without a description or acceptance criteria.

**Advantages:** consistent tickets from messy input; a person keeps the final say.

**Achieves:** a board where every sub-task can be built and checked.

### 10.2 Sync from Jira

Brings the board's current epics, stories, sub-tasks, statuses and "is blocked by" links into Agent Brigade on demand.

**Advantages:** planning works from the board as it is now, without a Jira call on every click.

**Achieves:** Agent Brigade and Jira start each plan in agreement.

### 10.3 Readiness checks

Before planning, the checks confirm that:

- the story exists and has sub-tasks;

- every sub-task has a description and acceptance criteria;

- the project's CLAUDE.md has the required sections: Purpose, Project structure, Commands, Rules and Docs;

- the checkout is clean and the test command runs.

Each failure names the item and the fix. A missing docs folder is a warning, not a blocker.

**Achieves:** no money is spent on a story that cannot be built.

### 10.4 Planning, approval and re-plan

- **Plan** opens an optional budget popup, which can be skipped. The Planner then writes the plan to the project's .agent-brigade/ folder.

- The plan is never written to Jira.

- **Approve** writes any newly found dependencies to Jira as "is blocked by" links with a comment. Git is untouched until Build.

- **Re-plan** asks what should change and replaces the same plan file.

**Advantages:** wrong plans are cheap to correct; dependencies become visible to the whole team.

**Achieves:** an executable, checkable plan approved by a person.

### 10.5 Development loop

Every sub-task runs builder → tester → reviewer in its own working copy. The orchestrator verifies between steps (section 8).

**Advantages:**

- no agent grades itself;

- parallel work cannot collide;

- combined work is always tested.

**Achieves:** verified code on one local story branch.

### 10.6 Run control

| Action              | Effect                                                                |
|---------------------|-----------------------------------------------------------------------|
| Cancel              | Stops a sub-task and every process it started; keeps the working copy |
| Detect interruption | Finds records whose process is gone after a crash or restart          |
| Show what was left  | Lists working copies and partial work from a stopped attempt          |
| Continue            | Resumes from the stage reached, keeping finished agent work           |
| Re-attempt          | Starts a fresh attempt after a person's fix                           |
| Run side by side    | Several independent sub-tasks at once, up to the parallel limit       |

Every control action also posts a Jira comment.

**Achieves:** no lost work, and no stray processes.

### 10.7 Jira sync

Statuses, labels and comments follow the flow in section 12.1. The database decides, and Jira is corrected after every step.

**Achieves:** the team follows progress on the board without opening Agent Brigade.

### 10.8 Cost and usage monitoring

For every agent run, Agent Brigade records:

- input, output and cache tokens;

- cost and duration;

- the model used.

These are totalled per sub-task, per story run and for the project to date. The Overview tab shows the totals and a history of runs. The Orchestrator tab shows live events.

**Achieves:** spending is visible and explainable, and limits can be tuned from real figures.

### 10.9 Deliverables

- The Documenter writes a feature document in the project's docs folder, matching the existing format.

- A story report lists:

  - sub-tasks, attempts and outcomes;

  - tokens and cost;

  - merges and the branch.

- An optional cleanup removes working copies that are no longer needed.

- Output is local commits only.

**Achieves:** every story ends with code, docs and a record a reviewer can read in minutes.

### 10.10 Connecting a project

A project is connected by filling in the settings (section 14) and writing its CLAUDE.md. No code changes.

**Achieves:** one installation serves any Git project.

## 11. Data design

A database is the main store. A few files sit beside it where a person or an agent needs to read them directly.

Everything lives in the target project's .agent-brigade/ folder. That folder holds a .gitignore of \*, so the project's Git status stays clean.

### 11.1 Project files

| File         | Contents                                                          | Written by                             |
|--------------|-------------------------------------------------------------------|----------------------------------------|
| brigade.db   | The database (tables below)                                       | Backend and orchestrator               |
| plan.json    | The current approved plan for a story; replaced on re-plan        | Planner, validated by the orchestrator |
| jira.json    | The last Sync from Jira                                           | Jira sync                              |
| events.jsonl | One line per event, appended as work happens; feeds the live view | Orchestrator                           |
| reports/     | One report per story                                              | Delivery                               |

Working copies are created outside the project, in a configurable folder.

### 11.2 Database tables

| Table               | Main fields                                                                                                    | Purpose                           |
|---------------------|----------------------------------------------------------------------------------------------------------------|-----------------------------------|
| projects            | name, repository, local path, base branch                                                                      | The connected project             |
| tracker_items       | key, type (epic, story, sub-task), parent, summary, status, synced at                                          | Local copy of the board           |
| chat_sessions       | Claude session id, created at                                                                                  | Publisher conversations           |
| publish_records     | session, proposed items, confirmed at, created keys                                                            | What was written to Jira and when |
| story_runs          | story key, status, branch, plan file, budget, cost, start, end                                                 | One story's planning and build    |
| sub_tasks           | story run, key, status, depends on, size, current stage                                                        | One sub-task's state              |
| attempts            | sub-task, number, working copy, outcome, reason, start, end                                                    | One try at a sub-task             |
| agent_runs          | attempt, role, model requested and used, effort, turns, input/output/cache tokens, cost, duration, exit reason | One Claude Code session           |
| checks              | attempt, kind (scope, tests, combined tests), passed, output tail                                              | Facts the orchestrator measured   |
| merges              | attempt, kind (fast-forward or real), commit, tests passed, time                                               | Every merge into a story branch   |
| budget_reservations | story run, agent run, amount, released                                                                         | Money held for running agents     |

### 11.3 Data rules

- **Transactions and atomic writes.** No record is ever half-written.

- **Locks:**

  - one scheduler per story;

  - one Git operation at a time per repository;

  - one merge at a time per branch;

  - one budget check at a time.

- **Totals include every attempt,** so the page, the reports and Jira comments always agree.

## 12. Integrations

Jira is the default tracker, GitHub can replace it, and Claude Code is the AI runtime. Each sits behind an interface, so the orchestrator never calls an outside service directly.

### 12.1 Jira (default tracker)

Agent Brigade connects to Jira Cloud through its REST API (v3), using an account email and API token. Descriptions and comments use Atlassian Document Format.

**Status, label and comment flow**

| Item            | Event                                         | Status            | Label            | Comment                          |
|-----------------|-----------------------------------------------|-------------------|------------------|----------------------------------|
| Story, sub-task | Created                                       | To Do             | –                | –                                |
| Epic            | First story under it starts building          | In Progress       | –                | –                                |
| Story           | Build starts                                  | In Progress       | –                | Plan summary and branch          |
| Sub-task        | An attempt starts                             | In Progress       | –                | Attempt number                   |
| Sub-task        | Merged into the story branch                  | Done              | –                | Result and cost                  |
| Sub-task        | Failed after the last retry                   | Error             | –                | Reason and test output           |
| Sub-task        | Stopped by a person                           | stays In Progress | brigade-stopped  | Who stopped it and what was left |
| Sub-task        | Waiting on a dependency that did not finish   | stays To Do       | brigade-blocked  | Which dependency                 |
| Story           | Nothing more can run; a sub-task is in Error  | In Review         | brigade-error    | Story report                     |
| Story           | All sub-tasks Done; branch not yet merged     | In Review         | brigade-unmerged | Story report                     |
| Story           | Story branch merged into main (extra feature) | Done              | brigade-merged   | Merge commit                     |

**Rules**

- Status names are matched by name, and the mapping can be configured.

- Every call is logged.

- A Jira error never stops a build. The next sync step catches the board up.

- Dependencies are written only as "is blocked by" links, and only after approval.

### 12.2 GitHub (optional tracker)

Teams that track work in GitHub instead of Jira set the tracker setting to github. The orchestrator is identical; only the tracker adapter changes.

| Jira concept | GitHub equivalent                                                                                    |
|--------------|------------------------------------------------------------------------------------------------------|
| Story        | A GitHub Issue describing the request                                                                |
| Sub-task     | A sub-issue linked to the parent Issue                                                               |
| Epic         | A milestone or a parent Issue                                                                        |
| Status       | A Status field on a GitHub Project board with four places: To do, In progress, Needs attention, Done |
| Labels       | Issue labels with the same names                                                                     |
| Comments     | A comment on the sub-issue per finished attempt; the story report on the parent Issue                |
| Dependencies | "Blocked by" relationships between Issues                                                            |

**Behaviour**

- **Connect once.** Read the board and map its columns by name. The board token is never stored, only the name of the setting it comes from.

- **Create sub-issues** from the approved plan, and record what was created so a repeat never duplicates.

- **Sync cards after every step.** Compare each card with the database and move only the ones that differ.

- **Tolerate GitHub's own automation.** An item that is already on the board is treated as success. A card that cannot be found yet is looked up again after a short wait.

**Advantages:** one product serves Jira teams and GitHub-only teams.

**Cost:** a second adapter to build and test. It ships disabled by default.

### 12.3 GitHub (code hosting)

- A fine-grained token is limited to the project repository. It has Contents and Issues set to read and write, and no pull request permission.

- Pushing and pull requests are an extra feature, off by default (section 17).

- In CI, the settings come from a GitHub environment named brigade: credentials as secrets, everything else as variables.

### 12.4 Claude Code

- Runs headless with streamed JSON events.

- Turns, time and spend are limited per session.

- Tools are given per role, and permission prompts are off.

- The model that actually ran is read from the session's start event.

- A usage limit is reported with its reset time. The story stops cleanly and can be continued after the reset.

## 13. Interfaces

The page talks to the backend through a JSON API and one live event stream. The API below is the proposed contract and may be refined during implementation.

### 13.1 API

| Group      | Endpoint                                                        | Purpose                                                 |
|------------|-----------------------------------------------------------------|---------------------------------------------------------|
| Publisher  | POST /api/publisher/sessions                                    | Start a chat                                            |
| Publisher  | POST /api/publisher/sessions/{id}/messages                      | Send text or files; receive the proposal                |
| Publisher  | POST /api/publisher/sessions/{id}/confirm                       | Run the guard, then create items in Jira                |
| Sync       | POST /api/tracker/sync                                          | Sync from Jira (or GitHub)                              |
| Stories    | GET /api/stories, GET /api/stories/{key}                        | Stories with sub-tasks and status                       |
| Planning   | POST /api/stories/{key}/checks                                  | Readiness checks                                        |
| Planning   | POST /api/stories/{key}/plan                                    | Plan, with an optional budget                           |
| Planning   | POST /api/stories/{key}/replan                                  | Re-plan with the requested changes                      |
| Planning   | POST /api/stories/{key}/approve                                 | Approve; write dependency links                         |
| Build      | POST /api/stories/{key}/build                                   | Start the orchestrator for the story                    |
| Control    | POST /api/subtasks/{key}/cancel, /continue, /reattempt          | Run control                                             |
| Monitoring | GET /api/runs/{id}, GET /api/usage                              | Records, tokens and cost by project, story or sub-task  |
| Monitoring | GET /api/events/stream                                          | Live events                                             |
| Delivery   | POST /api/stories/{key}/document, GET /api/stories/{key}/report | Feature document and story report                       |
| Project    | GET /api/project                                                | Connected project and a settings check, without secrets |

### 13.2 User interface

| Tab          | Shows                                                                            | Actions                                                               |
|--------------|----------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| Publisher    | Chat, uploaded files, the proposed epics, stories and sub-tasks                  | Send, Confirm                                                         |
| Planning     | Stories from Jira, check results, the plan with order, dependencies and concerns | Sync from Jira, Plan (budget popup), Re-plan (changes popup), Approve |
| Orchestrator | Sub-tasks by Jira key with stage and status; a live event feed per agent         | Build, Cancel, Continue, Re-attempt                                   |
| Overview     | Project totals; tokens and cost per run; history of runs                         | Filter, open a run                                                    |
| Delivery     | Feature document, story report, leftover working copies                          | Document, Report, Clean up                                            |

The page is served only on the local machine (127.0.0.1). It masks every secret and loads nothing from third parties.

## 14. Configuration and security

All settings come from environment variables, which are read from a .env file locally and from a GitHub environment in CI. They are read and validated in one module. Agent settings (model, effort, tools, turns) live in each agent's definition file instead.

### 14.1 Settings

| Setting               | Meaning                                        | Allowed values            | Secret |
|-----------------------|------------------------------------------------|---------------------------|--------|
| BRIGADE_GITHUB_TOKEN  | Fine-grained token for the project repository  | –                         | yes    |
| JIRA_EMAIL            | Jira account email                             | –                         | yes    |
| JIRA_API_TOKEN        | Jira API token                                 | –                         | yes    |
| JIRA_SITE_URL         | https://\<site\>.atlassian.net                 | –                         | no     |
| JIRA_PROJECT_KEY      | The Jira project's key                         | –                         | no     |
| BRIGADE_REPOSITORY    | OWNER/REPO of the target project               | –                         | no     |
| BRIGADE_PROJECT_PATH  | Local checkout of the target project           | –                         | no     |
| BRIGADE_BASE_BRANCH   | Branch that story branches start from          | –                         | no     |
| BRIGADE_WORKTREE_ROOT | Folder for working copies, outside the project | –                         | no     |
| BRIGADE_MAX_RETRIES   | Retries after a failed attempt                 | 0 to 5                    | no     |
| BRIGADE_MAX_PARALLEL  | Sub-tasks running at once                      | 1 to 8, default 3         | no     |
| BRIGADE_TEST_TIMEOUT  | Seconds a test run may take (extra)            | 60 to 86400, default 1200 | no     |
| BRIGADE_TRACKER       | Which tracker to use (optional)                | jira (default) or github  | no     |

**Loading rules**

- The shell takes precedence over .env.

- A bad value stops start-up with a message naming the setting.

- Values are never printed or logged.

**GitHub environment brigade**

- The three credentials are secrets; everything else is a variable.

- GitHub does not allow names that start with GITHUB\_.

- Environments in private repositories need a paid GitHub plan. Otherwise, repository Actions secrets are used.

### 14.2 Threats and controls

| Risk                                                       | Control                                                                                                                                         |
|------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| An agent does more than its role allows                    | Tools set per role on the command line; the orchestrator checks changed files and scope after every agent; the tester may write only test files |
| A credential reaches an agent                              | Environment allowlist; .env is ignored by Git and never copied into working copies; the Planner cannot read .agent-brigade/                     |
| An agent reads files outside the project by full path      | Not fully prevented in this version. Mitigated by the allowlist and by running only trusted stories; a sandbox is planned                       |
| Instructions hidden in a ticket or file (prompt injection) | Role limits, independent checks, trusted authors only; network restriction planned                                                              |
| Runaway cost                                               | Turn limit and spending cap per agent; story budget with reservations across parallel work                                                      |
| Unchecked code reaches main                                | Local commits only; story-to-main merge is done by a person; push and pull requests are opt-in                                                  |
| Two processes damage a record                              | Transactions, atomic writes and four locks (section 11.3)                                                                                       |
| The page leaks data                                        | Local machine only; secrets masked; no third-party requests                                                                                     |

## 15. Testing, observability and CI

Every code file has unit tests, and a feature is accepted only when its tests pass and it has been run on a real project.

### 15.1 Testing strategy

| Level        | What                             | How                                                                                                                                               |
|--------------|----------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| Unit         | Every module                     | pytest; Jira, GitHub and Claude Code replaced by test doubles. Covers plan validation, status mapping, budget arithmetic, locks and atomic writes |
| Architecture | Dependencies between modules     | A test fails when a lower layer imports a higher one                                                                                              |
| API          | Every endpoint                   | FastAPI test client against the request and response schemas                                                                                      |
| End to end   | One full story on a real project | Real Jira, real Claude Code, real Git: intake, plan, build, sync and deliver                                                                      |
| Interface    | The five tabs                    | Browser check at desktop and phone widths                                                                                                         |

**Acceptance.** Each feature in section 10 has a checklist of acceptance criteria. A feature is done when a developer can show every criterion passing on a real project.

### 15.2 Observability

| Signal      | Where it appears                                                     |
|-------------|----------------------------------------------------------------------|
| Live events | events.jsonl, streamed to the Orchestrator tab                       |
| Per agent   | Tokens, cost, duration, model used and exit reason                   |
| Totals      | Per sub-task, per story and per project to date, on the Overview tab |
| Logs        | Structured, with secrets masked                                      |
| Audit       | Every outbound call to Jira or GitHub                                |

### 15.3 Continuous integration

On every push and pull request, GitHub Actions runs three steps. A change merges only when all three pass.

1.  The unit and API tests.

2.  The lint check.

3.  The format check.

### 15.4 Running it

- Agent Brigade runs on a developer's machine as a local web server, beside their Claude Code login.

- No server deployment is needed in this version.

- Settings are already modelled as a GitHub environment, so running inside GitHub Actions later needs no redesign.

## 16. Advantages, limitations and risks

The design protects against mistakes, such as a wrong plan, a failing test or runaway cost. It does not protect against a deliberately hostile ticket, so until a sandbox exists, Agent Brigade should run only stories from trusted authors.

### 16.1 Advantages

- **Verification instead of trust.** Separate roles, with results measured by the orchestrator.

- **Bounded, visible cost.** A cap per agent, a budget per story, and figures for every run.

- **Low risk.** Isolated working copies and local branches; nothing is pushed by default.

- **One version of the truth.** The page, reports and Jira all reflect the same records.

- **Recoverable.** Crashes, closed windows and usage limits do not lose work.

- **Faster where safe.** Independent sub-tasks run in parallel, and combined work is tested.

- **Reusable.** Any Git project can be connected through settings.

- **Team-friendly.** Progress is visible on the Jira board without anyone writing status updates.

### 16.2 Limitations

| Limitation                                 | Effect                                                                         | Mitigation                                    |
|--------------------------------------------|--------------------------------------------------------------------------------|-----------------------------------------------|
| No sandbox in this version                 | Agents run as the user and could read files by full path or use the network    | Trusted stories only; sandbox planned         |
| One machine, one user                      | No shared queue or multi-user access                                           | GitHub-native execution later                 |
| Test duration sets the pace                | Combined merges re-run the tests; parallel work shares one CPU                 | Faster test command; configurable time limit  |
| Claude usage limits                        | Parallel work uses the quota faster                                            | Lower the parallel limit                      |
| File lists come from the Planner           | A sub-task that edits an unlisted file fails the scope check after using a run | Stronger plan validation                      |
| Conflicts need a person                    | Work waits for a decision                                                      | Extra: analyse and re-run                     |
| Some behaviour is visible only at run time | The reviewer judges it by reading code                                         | Hidden acceptance tests (future)              |
| Jira availability and rate limits          | Board updates may lag                                                          | Logged actions, retried on the next sync step |

### 16.3 Project risks

| Risk                                       | Likelihood | Impact | Response                                                                       |
|--------------------------------------------|------------|--------|--------------------------------------------------------------------------------|
| Agent output quality varies between models | Medium     | Medium | Model per role in each agent file; tune from recorded results                  |
| Tracker workflows differ between teams     | Medium     | Medium | Status names mapped by configuration                                           |
| Projects have weak or slow test suites     | High       | High   | Readiness checks; a CLAUDE.md that states the test command; time limit         |
| Scope grows before the core is stable      | Medium     | High   | Build in the order of section 17; extras only after the core passes acceptance |

## 17. Implementation plan and future enhancements

The build runs in eight phases. Each phase ends only when its acceptance criteria pass on a real project.

### 17.1 Implementation phases

1.  **Foundation.** The application skeleton: settings, database, the layer test, CI and the empty page.

2.  **Requirements to Jira.** The Jira connection, the Publisher agent, the publish guard and the Publisher tab.

3.  **Planning.** Sync from Jira, the readiness checks, the Planner agent, the budget, approval, re-plan and the Planning tab.

4.  **Development loop.** Working copies, the builder → tester → reviewer steps, the checks, merging, retries, and the Orchestrator tab with live events.

5.  **Run control.** Cancel, interruption detection, continue, re-attempt and parallel sub-tasks.

6.  **Jira sync and monitoring.** The status, label and comment flow; cost and usage totals; the Overview tab.

7.  **Deliverables.** The Documenter agent, story reports, optional cleanup and connecting a project.

8.  **Extra features.** Each extra behind its own setting (below).

### 17.2 Extra features

| Extra                               | Description                                                                                                   | Achieves                                 |
|-------------------------------------|---------------------------------------------------------------------------------------------------------------|------------------------------------------|
| Merge detection                     | Notices when a story branch is merged into main, then marks the story Done with brigade-merged                | The board shows what really shipped      |
| Merge order                         | Recommends the order to merge story branches that depend on each other                                        | Fewer conflicts at the human merge       |
| Analyse and re-run failed sub-tasks | An agent studies a failure and proposes a fix; a person approves before it re-runs                            | Failures recover without starting over   |
| Database backup                     | Timestamped copies of the database, with restore                                                              | History survives mistakes                |
| Push and pull request               | Opt-in push of the story branch and a pull request; the token gains pull request permission only when enabled | A reviewed route to GitHub               |
| GitHub tracker                      | Use GitHub Issues and Projects instead of Jira (section 12.2)                                                 | Teams without Jira can use Agent Brigade |

### 17.3 Future enhancements

- **Isolation.** A sandbox for agents, with outgoing network traffic restricted.

- **GitHub-native runs.** A label or a Jira transition starts a run inside GitHub Actions.

- **Hidden acceptance tests.** Tests the builder cannot see in advance, for independent checking.

- **Conflict help.** An agent that proposes conflict resolutions for a person to approve.

- **After deployment.** Bug tickets handled after release.

- **More intake sources.** Requirements from more places, such as Jira's own AI assistant.

- **Shared use.** An optional Postgres store for teams that share one installation.

## Conclusion and glossary

### 18.1 Conclusion

Agent Brigade gives a team a controlled way to turn requirements into tested code with AI agents.

- **What people do.** People write and approve the work in Jira.

- **What the system does.** A Planner turns each story into a checkable plan. Separate builder, tester and reviewer agents do the work in isolated copies, and a plain-code orchestrator verifies every result before it counts.

- **What it guarantees.** Cost is capped, progress is visible on the board, and failures are recoverable. The final merge always stays with a person.

- **What is deferred.** The sandbox and GitHub-native runs come later and do not change the architecture.

### 18.2 Glossary

| Term           | Meaning                                                                                  |
|----------------|------------------------------------------------------------------------------------------|
| Agent          | One Claude Code session with one role                                                    |
| Attempt        | One try at a sub-task; a retry or continuation is a new attempt in the same run          |
| Budget         | The most a story's agents may spend in total                                             |
| CLAUDE.md      | The target project's file describing its structure, commands and rules for agents        |
| Epic           | A large body of work in Jira that groups stories                                         |
| Fast-forward   | A merge where nothing else changed the branch, so no new test run is needed              |
| Orchestrator   | The plain-code engine that schedules agents, checks results and decides outcomes         |
| Parallel-safe  | A sub-task that lists its files and shares none with sub-tasks it is not ordered against |
| Plan           | The ordered list of sub-tasks with dependencies, files and criteria                      |
| Real merge     | A merge that combines two changes; the tests run again                                   |
| Reservation    | Money held for an agent that is still running                                            |
| Story          | A Jira story: the unit that is planned and built                                         |
| Story branch   | The local branch that collects every merged sub-task of a story                          |
| Story run      | One plan-and-build of a story, with all its attempts and costs                           |
| Sub-task       | A Jira sub-task: one piece of work built by the agents                                   |
| Target project | The Git repository whose stories are built                                               |
| Worktree       | A separate working folder of the same Git repository, so parallel work cannot collide    |
