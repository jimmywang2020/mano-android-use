from mano_android_use.grounder import normalize_action


def test_gui_plus_tool_call():
    text = (
        'thinking...<tool_call>{"name":"mobile_use",'
        '"arguments":{"action":"click","coordinate":[120,400]}}</tool_call>'
    )
    action = normalize_action(text)
    assert action["action"] == "click"
    assert action["coordinate"] == [120, 400]


def test_glm_json():
    action = normalize_action('{"action":"click","coordinate":[10,20]}')
    assert action["coordinate"] == [10, 20]


def test_bbox_to_click():
    action = normalize_action('{"action":"click","bbox":[100,200,300,400]}')
    assert action["action"] == "click"
    assert action["coordinate"] == [200, 300]


def test_bbox_bracket_form():
    action = normalize_action("point at [[0.1,0.2,0.3,0.4]]")
    assert action["action"] == "click"
    assert abs(action["coordinate"][0] - 200) < 1e-6


def test_trailing_comma_and_narration():
    text = (
        'I will fix JSON.\n'
        'The original JSON was:\n'
        '{"action": "click", "bbox": [415, 868, 509, 961],}\n'
        "Then more commentary..."
    )
    action = normalize_action(text)
    assert action["action"] == "click"
    assert action["coordinate"] == [462.0, 914.5]
