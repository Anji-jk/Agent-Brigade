"""Which tasks a restarted loop would retry: Failed ones that still have an attempt left."""

from core.runs import run_directory
from pipeline.control import task_control as tc
from pipeline.stages import story_loop as s
from pipeline.stages.retry import retryable_keys
from tests.pipeline.stages.stage_setup import FAIL, RUN
from tests.pipeline.stages.test_story_loop import StoryRunner, project

KEYS = ["SMT-62", "SMT-63"]


def failed_for_good(tmp_path, max_retries=0):
    repo, config, engine = project(tmp_path, first_verify=(FAIL,), max_retries=max_retries)
    s.run_story(config, RUN, StoryRunner(), engine=engine)
    return repo, engine


def test_a_task_that_used_all_its_attempts_is_not_retryable(tmp_path):
    repo, engine = failed_for_good(tmp_path, max_retries=0)
    assert retryable_keys(engine, repo, RUN, KEYS, max_retries=0) == []


def test_raising_the_retries_makes_it_retryable_and_leaves_its_blocked_dependent_out(tmp_path):
    repo, engine = failed_for_good(tmp_path, max_retries=0)
    assert retryable_keys(engine, repo, RUN, KEYS, max_retries=2) == ["SMT-62"]


def test_a_task_that_never_started_is_not_retryable(tmp_path):
    repo, config, engine = project(tmp_path)
    assert retryable_keys(engine, repo, RUN, KEYS, max_retries=2) == []


def test_a_cancelled_task_is_never_retryable(tmp_path):
    repo, engine = failed_for_good(tmp_path, max_retries=0)
    tc.settle(run_directory(repo, RUN), "SMT-62", tc.CANCELLED, "judge", 1)
    assert retryable_keys(engine, repo, RUN, KEYS, max_retries=2) == []
