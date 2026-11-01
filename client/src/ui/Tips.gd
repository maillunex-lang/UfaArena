extends RefCounted
## Contextual tips on the first opening of each section (brief §21: gradual depth, new mechanics explained when
## first opened, never repeated). Seen tips are stored locally; Settings → «Обучение» can show them again or turn
## them off. Tips never block the screen: a small card above the navigation with «Понятно».

const TIPS := {
	"heroes": ["Герои", "Здесь вся коллекция. Фильтруйте по фракции, редкости, классу и уровню. На карточке — уровень, звёзды и боевой рейтинг ⚔. Нажмите на героя, чтобы прокачать его и посмотреть навыки."],
	"formation": ["Формация", "Передний ряд принимает удары, задний наносит урон и лечит. Три-пять героев одной фракции дают бонус отряду."],
	"campaign": ["Поход", "Выберите этап на карте: откроется подготовка с вашим отрядом, противниками и наградами. Первое прохождение даёт дополнительные награды."],
	"summon": ["Призыв", "Шансы и гарантия открыты на каждой карточке. Перед призывом вы увидите полную стоимость и последствия. Повторный герой превращается в осколки для вознесения."],
	"quests": ["Задания", "Ежедневные задания обновляются в полночь, основные ведут по сюжету, достижения выдают награды автоматически."],
	"guild": ["Гильдия", "Вступите в гильдию или создайте свою: общий босс, задания дня, магазин знаков, война гильдий и общий чат."],
	"events": ["Центр событий", "Все события с таймерами в одном месте. Вклад в события дают бои, дозоры, задания и помощь друзьям."],
	"inventory": ["Инвентарь", "Все ваши ресурсы с точными количествами. Нажмите на ресурс, чтобы узнать, где его получить и на что потратить."],
	"world": ["Мир Уралии", "Регионы похода, боссы, испытания и события. Итоги мировых событий меняют регионы навсегда."],
	"shop": ["Магазин", "Перед покупкой открывается окно с полным составом, лимитами и сроком предложения."],
	"arena": ["Арена", "Бои с отрядами других игроков. Победы поднимают рейтинг и лигу; награды — в конце сезона."],
	"raids": ["Рейды", "Боссы с фазами: условия фазы подсказывают, какие классы и фракции сильнее. Попытки восстанавливаются со временем."],
	"chat": ["Чат", "Мировой и гильдейский каналы, личные сообщения. ИИ-жители всегда помечены значком «ИИ»."],
	"fortress": ["Крепость", "Здания дают постоянные бонусы всем героям и ускоряют дозор."],
}


static func seen() -> Array:
	var s = Config.settings.get("seen_tips", [])
	return s if s is Array else []


static func reset() -> void:
	Config.settings["seen_tips"] = []
	Config.save()


static func maybe_show(main: Node, key: String) -> void:
	if not TIPS.has(key) or not bool(Config.settings.get("tips_on", true)) or key in seen():
		return
	if int(Game.profile.get("onboarding_step", 0)) == 0:
		return  # the intro story is on screen first
	var arr := seen()
	arr.append(key)
	Config.settings["seen_tips"] = arr
	Config.save()
	for old in main.get_tree().get_nodes_in_group("tip_card"):
		old.queue_free()
	var p := UI.solid_panel(Color("#bfe3ff"))
	p.name = "TipCard"
	p.add_to_group("tip_card")
	p.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	p.offset_left = 24
	p.offset_right = -24
	p.offset_top = -560
	p.offset_bottom = -250
	p.grow_vertical = Control.GROW_DIRECTION_BEGIN
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	var h := HBoxContainer.new()
	var ic := GameIcon.new()
	ic.kind = "quests"
	ic.custom_minimum_size = Vector2(48, 48)
	h.add_child(ic)
	h.add_child(UI.label("Подсказка · " + String(TIPS[key][0]), 30, UI.GOLD, true))
	v.add_child(h)
	var t := UI.label(String(TIPS[key][1]), 26, UI.TEXT)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(t)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var off := UI.button("Больше не показывать", "dim", 0, 76)
	off.add_theme_font_size_override("font_size", 24)
	off.pressed.connect(func():
		Config.settings["tips_on"] = false
		Config.save()
		p.queue_free())
	row.add_child(off)
	var ok := UI.button("Понятно", "accent", 0, 76)
	ok.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ok.pressed.connect(p.queue_free)
	row.add_child(ok)
	v.add_child(row)
	p.add_child(v)
	main.ui.add_child(p)
	UI.pop_in(p)
