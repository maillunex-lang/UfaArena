extends Control
## Hero creation window (Living Community decision D-C1): nickname + "I am 18 or older".
## Shown once to every player who has not answered yet (new players before the intro story, existing players on their
## next launch) and from Settings to change the answer. Minors never get private messages or adult content from AI.

signal finished(profile: Dictionary)

var _nick: LineEdit
var _adult: Button
var _err: Label
var _busy := false


static func open(parent: Node, first_time := true) -> Control:
	var d: Control = load("res://src/ui/HeroSetupDialog.gd").new()
	d.set_meta("first_time", first_time)
	parent.add_child(d)
	return d


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.72)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	var p := UI.solid_panel(Color("#ffe1a0"))
	p.anchor_left = 0.5
	p.anchor_right = 0.5
	p.anchor_top = 0.5
	p.anchor_bottom = 0.5
	p.offset_left = -460
	p.offset_right = 460
	p.offset_top = -380
	p.offset_bottom = 380
	p.grow_horizontal = Control.GROW_DIRECTION_BOTH
	p.grow_vertical = Control.GROW_DIRECTION_BOTH
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", UI.SP.l)
	var first: bool = get_meta("first_time", true)
	v.add_child(UI.title("Создание героя" if first else "Никнейм и возраст", UI.FS.h2))
	var hint := UI.label("Как вас будут звать в Уралии? Никнейм видят другие игроки.", UI.FS.body, UI.TEXT)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(hint)
	_nick = LineEdit.new()
	_nick.text = str(Game.profile.get("nickname", ""))
	_nick.max_length = 20
	_nick.placeholder_text = "Никнейм (3–20 символов)"
	_nick.custom_minimum_size = Vector2(0, 92)
	_nick.add_theme_font_size_override("font_size", 34)
	v.add_child(_nick)
	_adult = UI.button("", "glass", 0, 92)
	_adult.toggle_mode = true
	_adult.alignment = HORIZONTAL_ALIGNMENT_LEFT
	_adult.add_theme_font_size_override("font_size", 32)
	_adult.toggled.connect(func(on: bool): _adult.text = ("☑  " if on else "☐  ") + "Мне исполнилось 18 лет")
	_adult.button_pressed = str(Game.profile.get("age_group", "")) == "adult"
	_adult.text = ("☑  " if _adult.button_pressed else "☐  ") + "Мне исполнилось 18 лет"
	v.add_child(_adult)
	var note := UI.label("В Уралии живут ИИ-персонажи (они помечены значком «ИИ»). Игрокам 18+ они могут писать в личку, "
		+ "флиртовать и шутить по-взрослому — это можно выключить в настройках. Игрокам младше 18 ИИ в личку не пишут.",
		UI.FS.caption, UI.MUTED)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(note)
	_err = UI.label("", UI.FS.caption, Color("#ff8a7a"))
	_err.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(_err)
	var ok := UI.button("Начать" if first else "Сохранить", "primary", 0, 96)
	ok.pressed.connect(_submit)
	v.add_child(ok)
	p.add_child(v)
	add_child(p)
	UI.pop_in(p)


func _submit() -> void:
	if _busy:
		return
	var n := _nick.text.strip_edges()
	if n.length() < 3:
		_err.text = "Никнейм — от 3 до 20 символов"
		return
	_busy = true
	var body := {"adult": _adult.button_pressed}
	if n != str(Game.profile.get("nickname", "")):
		body["nickname"] = n
	var r := await Api.post_json("/player/setup", body)
	_busy = false
	if not r.ok:
		_err.text = str(r.get("message", "Не удалось сохранить, попробуйте другой никнейм"))
		return
	Game.profile = r.data.profile
	finished.emit(r.data.profile)
	queue_free()
