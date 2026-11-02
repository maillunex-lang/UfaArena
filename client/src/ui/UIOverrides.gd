extends RefCounted
## Admin rules over the REAL interface of any screen (admin: Редактор игры → Интерфейс → «Все экраны»).
## A button or text is found by its caption (digits and symbols ignored, so «Забрать (3)» = «Забрать»); a rule can hide
## it, rename it, tint it, move it among its neighbours, or change where a button leads (any screen / special action from
## Main.do_action, or «none» = disabled). Data only: no code is ever executed. Unknown captions are simply not found.

static var _rx_digits := RegEx.create_from_string("[0-9]")
static var _rx_space := RegEx.create_from_string("\\s+")


static func norm(t: String) -> String:
	var s := _rx_digits.sub(t, "", true)
	for ch in ["×", "%", "/", "+", "·", ":", "(", ")", "›", "«", "»"]:
		s = s.replace(ch, " ")
	return _rx_space.sub(s, " ", true).strip_edges().left(80)


## The element's identity = its ORIGINAL caption (kept in meta, so a rename does not lose the rule).
static func key_of(n: Node) -> String:
	if n.has_meta("uo_key"):
		return String(n.get_meta("uo_key"))
	var t := ""
	if n is Button:
		t = (n as Button).text
		if t.strip_edges() == "":
			t = (n as Button).tooltip_text
		if t.strip_edges() == "":
			var l := first_label(n)
			if l:
				t = l.text
	elif n is Label:
		t = (n as Label).text
	return norm(t)


static func first_label(n: Node) -> Label:
	for c in n.get_children():
		if c is Label and (c as Label).text.strip_edges() != "":
			return c
		var d := first_label(c)
		if d:
			return d
	return null


static func rules_for(screen: String) -> Dictionary:
	var by := {}
	for r in Game.ui_part("screens.%s.rules" % screen, []):
		if r is Dictionary:
			by[String(r.get("kind", "button")) + "|" + String(r.get("key", ""))] = r
	return by


## Applies the screen's rules to every button / text under `root` (skipping `skip`, e.g. the content area for «main»).
static func apply(root: Node, screen: String, main: Node, skip: Node = null) -> void:
	var by := rules_for(screen)
	if by.is_empty() or not is_instance_valid(root):
		return
	_walk(root, by, main, skip)


static func _walk(n: Node, by: Dictionary, main: Node, skip: Node) -> void:
	for c in n.get_children():
		if c == skip:
			continue
		if c is Button:
			_one(c, "button", by, main)
		elif c is Label:
			_one(c, "label", by, main)
		else:
			_walk(c, by, main, skip)


static func _one(n: Control, kind: String, by: Dictionary, main: Node) -> void:
	var key := key_of(n)
	if key == "":
		return
	n.set_meta("uo_key", key)
	if int(n.get_meta("uo_done", -2)) == Game.layout_version:
		return
	n.set_meta("uo_done", Game.layout_version)
	var r: Variant = by.get(kind + "|" + key)
	if not (r is Dictionary):
		return
	if bool(r.get("hidden", false)):
		n.visible = false
	var lbl := String(r.get("label", ""))
	if lbl != "":
		if n is Button and norm((n as Button).text) == key:
			(n as Button).text = lbl
		if n is Label:
			(n as Label).text = lbl
		else:
			_rename_labels(n, key, lbl)
		if n is Button and (n as Button).tooltip_text != "" and norm((n as Button).tooltip_text) == key:
			(n as Button).tooltip_text = lbl
	var col := String(r.get("color", ""))
	if col != "":
		n.modulate = Color(col)
	var mv := int(r.get("move", 0))
	if mv != 0 and n.get_parent():
		if not n.has_meta("uo_idx"):
			n.set_meta("uo_idx", n.get_index())
		var p := n.get_parent()
		p.move_child(n, clampi(int(n.get_meta("uo_idx")) + mv, 0, p.get_child_count() - 1))
	var act := String(r.get("action", ""))
	if act != "" and n is Button:
		var b := n as Button
		for c in b.pressed.get_connections():
			b.pressed.disconnect(c.callable)
		if act == "none":
			b.disabled = true
		else:
			b.disabled = false
			b.pressed.connect(func(): Sfx.play("click"); main.do_action(act))


static func _rename_labels(n: Node, key: String, lbl: String) -> void:
	for c in n.get_children():
		if c is Label and norm((c as Label).text) == key:
			(c as Label).text = lbl
		_rename_labels(c, key, lbl)
