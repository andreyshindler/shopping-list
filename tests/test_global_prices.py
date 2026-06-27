import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.global_prices import find_variants, global_estimate, is_ambiguous
from app.models import (
    Base,
    GlobalProduct,
    PendingItem,
    PriceHistory,
    ShoppingList,
    UserProduct,
)
from app.services import (
    add_item_from_pending,
    create_list_from_text,
    end_list,
    get_or_create_user,
    resolve_custom_variant,
    resolve_variant,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_peppers(session):
    session.add_all(
        [
            GlobalProduct(name="פלפל אדום ארוז", normalized_name="פלפל אדום ארוז", price=12.0),
            GlobalProduct(name="פלפל אדום 500 גרם", normalized_name="פלפל אדום 500 גרם", price=10.0),
            GlobalProduct(name="פלפל צהוב ארוז", normalized_name="פלפל צהוב ארוז", price=14.0),
            GlobalProduct(name="פלפל ירוק", normalized_name="פלפל ירוק", price=8.0),
            GlobalProduct(name="חלב תנובה 3%", normalized_name="חלב תנובה 3%", price=6.0),
        ]
    )
    session.flush()


def test_find_variants_collapses_near_duplicates(session):
    _seed_peppers(session)
    variants = find_variants(session, "פלפל")
    labels = [v.name for v in variants]
    # The two "פלפל אדום ..." SKUs collapse to one representative (the cheaper one).
    assert "פלפל אדום 500 גרם" in labels
    assert "פלפל אדום ארוז" not in labels
    # Distinct colours each appear, cheapest-first.
    assert {"פלפל ירוק", "פלפל אדום 500 גרם", "פלפל צהוב ארוז"} <= set(labels)
    assert variants[0].price <= variants[-1].price


def test_find_variants_returns_all_matches_for_grouping(session):
    # All matches are kept (snacks/spices included) so the picker can group them.
    session.add_all(
        [
            GlobalProduct(name="פלפל אדום", normalized_name="פלפל אדום", price=10.9),
            GlobalProduct(name="פלפל צהוב", normalized_name="פלפל צהוב", price=11.9),
            GlobalProduct(name="ציפס פלפל צילי", normalized_name="ציפס פלפל צילי", price=5.5),
            GlobalProduct(
                name="פלפל שחור טחון בשקית", normalized_name="פלפל שחור טחון בשקית", price=8.5
            ),
        ]
    )
    session.flush()
    names = [v.name for v in find_variants(session, "פלפל")]
    assert {"פלפל אדום", "פלפל צהוב", "ציפס פלפל צילי", "פלפל שחור טחון בשקית"} <= set(names)


def test_create_list_groups_suggestions_by_category(session):
    session.add_all(
        [
            GlobalProduct(name="פלפל אדום", normalized_name="פלפל אדום", price=10.9),
            GlobalProduct(name="פלפל צהוב", normalized_name="פלפל צהוב", price=11.9),
            GlobalProduct(name="ציפס פלפל צילי", normalized_name="ציפס פלפל צילי", price=5.5),
            GlobalProduct(
                name="פלפל שחור טחון בשקית", normalized_name="פלפל שחור טחון בשקית", price=8.5
            ),
        ]
    )
    session.flush()
    user = get_or_create_user(session, 7, "T", "ILS")
    sl = create_list_from_text(session, user, "פלפל")
    by_cat = {s.name: s.category for s in sl.items[0].suggestions}
    # Fresh peppers -> Produce, chips (head word) -> Snacks, black pepper phrase -> Pantry.
    assert by_cat["פלפל אדום"] == "Produce"
    assert by_cat["ציפס פלפל צילי"] == "Snacks"
    assert by_cat["פלפל שחור טחון בשקית"] == "Pantry"


def test_find_variants_matches_whole_words_only(session):
    # "שוקו" (chocolate milk) must not bring back "שוקולד" (chocolate bar).
    session.add_all(
        [
            GlobalProduct(name="שוקו תנובה", normalized_name="שוקו תנובה", price=4.5),
            GlobalProduct(name="שוקו בקרטון", normalized_name="שוקו בקרטון", price=5.0),
            GlobalProduct(name="שוקולד פרה", normalized_name="שוקולד פרה", price=6.0),
            GlobalProduct(name="שוקולד מריר", normalized_name="שוקולד מריר", price=7.0),
        ]
    )
    session.flush()
    names = [v.name for v in find_variants(session, "שוקו")]
    assert {"שוקו תנובה", "שוקו בקרטון"} <= set(names)
    assert not any("שוקולד" in n for n in names)


def test_custom_variant_price_remembered_from_history(session):
    _seed_peppers(session)
    user = get_or_create_user(session, 9, "T", "ILS")
    sl1 = create_list_from_text(session, user, "פלפל")
    item = sl1.items[0]

    # User adds a free-text product that has no history yet -> no price.
    resolve_custom_variant(session, item, "פלפל חלפיניו")
    session.flush()
    assert item.predicted_price is None

    # They complete the list and enter a real price for it.
    session.add(
        PriceHistory(user_id=user.id, normalized_name="פלפל חלפיניו", price=9.9)
    )
    session.flush()

    # Next time the term is typed, the remembered product carries the paid price.
    sl2 = create_list_from_text(session, user, "פלפל")
    chosen = next(s for s in sl2.items[0].suggestions if s.name == "פלפל חלפיניו")
    assert chosen.price == 9.9
    resolve_variant(session, sl2.items[0], chosen)
    session.flush()
    assert sl2.items[0].predicted_price == 9.9


def test_global_estimate_is_median(session):
    _seed_peppers(session)
    variants = find_variants(session, "פלפל")
    assert global_estimate(variants) is not None


def test_is_ambiguous_only_for_generic_terms(session):
    _seed_peppers(session)
    assert is_ambiguous("פלפל", find_variants(session, "פלפל")) is True
    # A single match is never ambiguous.
    assert is_ambiguous("חלב", find_variants(session, "חלב")) is False


def test_create_list_uses_global_fallback_and_flags_ambiguous(session):
    _seed_peppers(session)
    user = get_or_create_user(session, 1, "T", "ILS")
    sl = create_list_from_text(session, user, "פלפל")
    item = sl.items[0]
    assert item.needs_choice is True
    assert item.predicted_price is not None  # global median fills the estimate
    assert sl.predicted_total > 0
    assert len(item.suggestions) >= 3


def test_picker_shows_even_with_history_but_keeps_personal_price(session):
    # Milk variants in the catalog, and the user has bought generic "חלב" before.
    session.add_all(
        [
            GlobalProduct(name="חלב 3% תנובה", normalized_name="חלב 3% תנובה", price=6.6),
            GlobalProduct(name="חלב 1% טרה", normalized_name="חלב 1% טרה", price=6.9),
        ]
    )
    user = get_or_create_user(session, 8, "T", "ILS")
    session.add(PriceHistory(user_id=user.id, normalized_name="חלב", price=5.0))
    session.flush()

    sl = create_list_from_text(session, user, "חלב")
    item = sl.items[0]
    assert item.needs_choice is True  # picker still offered despite history
    assert item.predicted_price == 5.0  # ...but the personal price wins over the catalog


def test_resolve_variant_rewrites_item_and_remembers_pick(session):
    _seed_peppers(session)
    user = get_or_create_user(session, 2, "T", "ILS")
    sl = create_list_from_text(session, user, "פלפל")
    item = sl.items[0]
    chosen = next(s for s in item.suggestions if s.name == "פלפל צהוב ארוז")

    resolve_variant(session, item, chosen)
    session.flush()

    assert item.needs_choice is False
    assert item.raw_name == "פלפל צהוב ארוז"
    assert item.predicted_price == 14.0
    assert item.suggestions == []
    assert sl.predicted_total == 14.0

    pick = session.query(UserProduct).one()
    assert pick.query_normalized == "פלפל"
    assert pick.chosen_normalized == "פלפל צהוב ארוז"
    assert pick.pick_count == 1


def test_carried_over_unpicked_item_shows_picker_again(session):
    _seed_peppers(session)
    user = get_or_create_user(session, 5, "T", "ILS")
    # First list: leave the ambiguous "פלפל" unpicked, then end the list early.
    sl1 = create_list_from_text(session, user, "פלפל")
    assert sl1.items[0].needs_choice is True
    end_list(session, sl1)
    session.flush()
    pending = session.query(PendingItem).filter_by(user_id=user.id).one()

    # Re-add it to a new list via carry-over: the picker must come back.
    sl2 = ShoppingList(user_id=user.id)
    session.add(sl2)
    session.flush()
    item = add_item_from_pending(session, sl2, pending)
    session.flush()
    assert item.needs_choice is True
    assert len(item.suggestions) >= 3


def test_custom_variant_resolves_and_resurfaces_next_time(session):
    _seed_peppers(session)
    user = get_or_create_user(session, 6, "T", "ILS")
    sl1 = create_list_from_text(session, user, "פלפל")
    item = sl1.items[0]

    # User ignores the suggestions and types their own product.
    resolve_custom_variant(session, item, "פלפל חלפיניו")
    session.flush()
    assert item.needs_choice is False
    assert item.raw_name == "פלפל חלפיניו"
    assert item.suggestions == []

    # Next time the generic term is typed, the custom product is offered as a variant.
    sl2 = create_list_from_text(session, user, "פלפל")
    names = [s.name for s in sl2.items[0].suggestions]
    assert "פלפל חלפיניו" in names
    assert names[0] == "פלפל חלפיניו"  # the user's pick is ranked first


def test_previous_pick_is_ordered_first_but_picker_still_shown(session):
    _seed_peppers(session)
    user = get_or_create_user(session, 3, "T", "ILS")
    # First list: pick yellow pepper.
    sl1 = create_list_from_text(session, user, "פלפל")
    chosen = next(s for s in sl1.items[0].suggestions if s.name == "פלפל צהוב ארוז")
    resolve_variant(session, sl1.items[0], chosen)
    session.flush()

    # Second list with the same generic term still offers the picker...
    sl2 = create_list_from_text(session, user, "פלפל")
    item = sl2.items[0]
    assert item.needs_choice is True
    # ...with the previously-picked variant ranked first.
    assert item.suggestions[0].name == "פלפל צהוב ארוז"
