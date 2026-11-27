from conversation import ConversationHistory


def test_empty_history_text():
    assert ConversationHistory().format_history() == "No previous conversation."


def test_history_is_trimmed_to_the_newest_messages():
    history = ConversationHistory(max_messages=4)

    for number in range(5):
        history.add_user_message(f"q{number}")
        history.add_assistant_message(f"a{number}")

    assert [m.content for m in history.get_messages()] == ["q3", "a3", "q4", "a4"]


def test_get_messages_returns_a_copy():
    history = ConversationHistory()
    history.add_user_message("hello")

    history.get_messages().clear()

    assert len(history.get_messages()) == 1


def test_format_history_labels_roles():
    history = ConversationHistory()
    history.add_user_message("hi")
    history.add_assistant_message("hello")

    assert history.format_history() == "User: hi\nAssistant: hello"


def test_clear_empties_the_history():
    history = ConversationHistory()
    history.add_user_message("hi")

    history.clear()

    assert history.get_messages() == []
