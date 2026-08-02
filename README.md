# llm-review

## 2.1 Abstract

A system that simulates the peer-review process of a scientific paper by a conference committee.

Given an input paper, several independent reviewers evaluate it in parallel, each with its own sensitivity and attitude (e.g. more or less strict, more attentive to methodological soundness, to empirical results, or to novelty). A meta-reviewer synthesizes the judgments, an area chair makes the final decision (acceptance or request for revision), and an author agent produces revision notes in response to the remarks. The loop repeats — a new review that takes the author's rebuttal into account — until the work is accepted or the maximum number of rounds is reached.

**Objectives.** (i) Study how the review outcome and dynamics change with the committee composition and the individual reviewers' attitudes, and (ii) compare agentic reviews against real ones.

**Motivations.**
- *Problem:* speeding up real-world reviews with the help of agentic applications.
- *Proposed solution:* _(TBD)_
- *Technologies / methodologies:* Python 3.12, uv, LangChain, LangGraph, PostgreSQL, Redis.
- *Results:* _(TBD)_

## 2.2 In

## Scripts

Cross-platform Python scripts under `resource/scripts/`.

| Script | Command | Description |
|---|---|---|
| start-venv | `python resource/scripts/1-start-venv.py` | Create `.venv` and install dependencies (`uv venv` + `uv sync`) |
| start-docker | `python resource/scripts/2-start-docker.py` | Start the Postgres + Redis infra (`docker compose ... up -d`) |
| run-app | `uv run python resource/scripts/3-run-app.py` | Start uvicorn (`main:app`, host/port from `APP_HOST`/`APP_PORT`, default `0.0.0.0:8081`) |
| run-test | `python resource/scripts/4-run-test.py` | Run pytest with coverage (`--cov=src`, term-missing) |
