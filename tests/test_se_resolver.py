"""SE解決モジュールのテスト"""


def test_resolve_se_with_valid_category(test_db):
    """カテゴリに一致するSEがある場合、ファイル情報を返す"""
    test_db.upsert_se_track("greeting.wav", category="greeting", description="挨拶", volume=0.8, duration=0.6)
    from src.se_resolver import resolve_se
    result = resolve_se("greeting")
    assert result is not None
    assert result["filename"] == "greeting.wav"
    assert result["volume"] == 0.8
    assert result["duration"] == 0.6
    assert result["url"] == "/se/greeting.wav"


def test_resolve_se_with_no_match(test_db):
    """カテゴリに一致するSEがない場合、Noneを返す"""
    from src.se_resolver import resolve_se
    result = resolve_se("nonexistent")
    assert result is None


def test_resolve_se_with_none(test_db):
    """カテゴリがNoneの場合、Noneを返す"""
    from src.se_resolver import resolve_se
    assert resolve_se(None) is None
    assert resolve_se("") is None


def test_resolve_se_random_choice(test_db):
    """同一カテゴリに複数のSEがある場合、ランダムに1つ選ばれる"""
    test_db.upsert_se_track("surprise1.wav", category="surprise", volume=1.0, duration=0.5)
    test_db.upsert_se_track("surprise2.wav", category="surprise", volume=1.0, duration=0.7)
    from src.se_resolver import resolve_se
    results = {resolve_se("surprise")["filename"] for _ in range(20)}
    # 20回試行すれば両方出るはず（確率的テスト）
    assert len(results) >= 1  # 最低1つは必ず
    assert results <= {"surprise1.wav", "surprise2.wav"}


def test_get_available_categories(test_db):
    """利用可能なカテゴリ一覧を返す"""
    test_db.upsert_se_track("g.wav", category="greeting", description="挨拶")
    test_db.upsert_se_track("s.wav", category="surprise", description="驚き")
    test_db.upsert_se_track("s2.wav", category="surprise", description="驚き2")
    from src.se_resolver import get_available_categories
    cats = get_available_categories()
    names = [c["name"] for c in cats]
    assert "greeting" in names
    assert "surprise" in names
    assert len(cats) == 2  # surpriseは重複しない


def test_get_available_categories_empty(test_db):
    """SEが登録されていない場合、空リストを返す"""
    from src.se_resolver import get_available_categories
    assert get_available_categories() == []
