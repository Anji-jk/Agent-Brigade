from pipeline.feed.items import Item, feed, shorten, stable_index


def item(index, **kw):
    return Item(index=index, kind=kw.pop("kind", "say"), title=kw.pop("title", "t"), **kw)


def test_short_text_is_not_cut():
    assert shorten("a\nb") == ("a\nb", False)


def test_many_lines_keep_the_first_and_last_ones():
    text = "\n".join(f"line {n}" for n in range(200))
    out, cut = shorten(text)
    assert cut
    assert out.startswith("line 0\n") and out.endswith("line 199")
    assert "... 120 lines hidden ..." in out


def test_one_huge_line_is_cut_in_the_middle():
    out, cut = shorten("x" * 40_000)
    assert cut and "characters hidden" in out and len(out) < 17_000


def test_full_text_is_kept_up_to_a_ceiling():
    text = "\n".join(f"line {n}" for n in range(200))
    assert shorten(text, full=True) == (text, False)
    out, cut = shorten("y" * 2_100_000, full=True)
    assert cut and len(out) == 2_000_000


def test_secrets_are_masked_in_every_text_of_an_item():
    token = "ghp_" + "a" * 30
    one = item(0, title=f"cat {token}", detail=f"TOKEN={token}x")
    one.result = {"status": "ok", "summary": token, "detail": f"{token} out", "at": None}
    shown = one.to_dict()
    assert token not in str(shown)
    assert shown["result"]["status"] == "ok"


def test_a_secret_is_masked_before_a_long_text_is_cut():
    token = "ghp_" + "a" * 30
    text = "\n".join([token] + ["x"] * 200)
    assert token not in item(0, detail=text).to_dict()["detail"]


def test_an_item_waiting_for_its_result_is_pending():
    waiting = item(0, awaits_result=True)
    assert waiting.pending and waiting.to_dict()["pending"] is True
    waiting.result = {"status": "ok", "summary": "done"}
    assert not waiting.pending


def test_next_points_at_the_first_pending_item():
    items = [item(0), item(1, awaits_result=True), item(2)]
    assert stable_index(items) == 1
    assert feed(items, after=0)["next"] == 1
    assert stable_index([item(0), item(1)]) == 2


def test_feed_returns_only_what_comes_after():
    items = [item(n, title=f"t{n}") for n in range(4)]
    got = feed(items, after=2)
    assert [x["title"] for x in got["items"]] == ["t2", "t3"]
    assert (got["from"], got["count"]) == (2, 4)
    assert feed(items, after=99)["items"] == [] and feed(items, after=-5)["from"] == 0


def test_the_whole_text_is_given_when_the_feed_is_asked_for_in_full():
    text = "\n".join(f"line {n}" for n in range(200))
    items = [item(0, detail=text)]
    assert "lines hidden" in feed(items)["items"][0]["detail"]
    assert feed(items, full=True)["items"][0]["detail"] == text
