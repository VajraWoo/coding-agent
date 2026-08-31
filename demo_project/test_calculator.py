from calculator import add


def test_adds_two_numbers():
    assert add(2, 3) == 5


def test_adds_negative_number():
    assert add(-2, 5) == 3
