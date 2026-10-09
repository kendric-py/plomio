from packages.automation.src.service import filter_notifiable_changes


def _change(field, old, new, breached):
    return {'field': field, 'old_value': old, 'new_value': new, 'threshold_breached': breached}


def test_stable_price_below_threshold_does_not_notify_again():
    # Цена не менялась с прошлой проверки, но всё ещё ниже порога относительно baseline.
    changes = [
        _change('PRICE', 137000, 137000, True),
        _change('DISCOUNTED_PRICE', 134260, 134260, True),
    ]
    assert filter_notifiable_changes(changes) == []


def test_price_drop_that_breaches_threshold_notifies():
    changes = [_change('PRICE', 151000, 137000, True)]
    assert filter_notifiable_changes(changes) == changes


def test_first_check_already_below_threshold_notifies():
    changes = [_change('PRICE', None, 137000, True)]
    assert filter_notifiable_changes(changes) == changes


def test_price_change_without_breach_is_not_notified():
    assert filter_notifiable_changes([_change('PRICE', 100, 90, False)]) == []
    assert filter_notifiable_changes([_change('PRICE', 100, 120, False)]) == []


def test_non_price_fields_always_notify():
    changes = [
        _change('IN_STOCK', False, True, True),
        _change('TITLE', 'a', 'b', False),
        _change('RATING', 4.5, 4.6, False),
    ]
    assert filter_notifiable_changes(changes) == changes


def test_price_drop_alongside_stable_price_keeps_only_the_changed_one():
    stable = _change('PRICE', 137000, 137000, True)
    dropped = _change('DISCOUNTED_PRICE', 134260, 120000, True)
    assert filter_notifiable_changes([stable, dropped]) == [dropped]
