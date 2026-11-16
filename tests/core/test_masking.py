from core.masking import MASK, mask_secrets


def test_tokens_with_a_known_prefix_are_masked():
    text = "ghp_" + "a" * 30 + " and sk-ant-" + "b" * 20 + " and github_pat_" + "c" * 30
    out = mask_secrets(text)
    assert out == f"{MASK} and {MASK} and {MASK}"


def test_a_secret_assignment_keeps_its_name_and_hides_the_value():
    assert mask_secrets("JIRA_API_TOKEN=abcdef123456") == f"JIRA_API_TOKEN={MASK}"
    assert mask_secrets('db_password: "hunter2hunter2"') == f'db_password: "{MASK}"'


def test_a_bearer_token_keeps_the_word_bearer():
    assert mask_secrets("Authorization: Bearer abcdefghijklmnop1234") == (
        f"Authorization: Bearer {MASK}"
    )


def test_ordinary_text_is_left_alone():
    text = "Read frontend/src/App.jsx (27 lines); the token count is 12"
    assert mask_secrets(text) == text
