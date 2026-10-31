extends Node
## Client-side state cache. The server is the source of truth: every mutation goes
## through Api and the cache is replaced with what the server returns.

signal wallet_changed
signal heroes_changed
signal profile_changed
signal afk_changed

const CURRENCY_NAMES := {
	"gold": "Золото", "crystals": "Кристаллы", "summon_essence": "Эссенция призыва",
	"ancient_seals": "Древние печати", "guild_marks": "Знаки гильдии", "nature_essence": "Эссенция природы",
}
const FACTION_COLORS := {
	"uraltau": Color("#8fb3d9"), "agidel": Color("#5fd1c4"), "steppe": Color("#e8c26a"),
	"shulgan": Color("#b06cff"), "ancients": Color("#ffe9a8"),
}
const RARITY_COLORS := {
	1: Color("#a7b0bd"), 2: Color("#6fd08c"), 3: Color("#5aa9ff"), 4: Color("#b87cff"),
	5: Color("#ffb347"), 6: Color("#ff5f7e"),
}
const CLASS_NAMES := {"guardian": "Страж", "warrior": "Батыр", "ranger": "Следопыт", "mage": "Мудрец",
	"healer": "Знахарь"}
const FACTION_NAMES := {"uraltau": "Хранители Урал-тау", "agidel": "Дети Агидели", "steppe": "Ветра Степи",
	"shulgan": "Порождения Шульгана", "ancients": "Древние"}

var profile := {}
var wallet := {}
var heroes: Array = []
var formation: Array = [null, null, null, null, null]
var campaign := {}
var afk := {}
var rarities := {}
var catalog := {}
var server_time_offset := 0.0
var loaded := false


func bootstrap() -> Dictionary:
	var r := await Api.get_json("/player/bootstrap")
	if not r.ok:
		return r
	var d: Dictionary = r.data
	profile = d.profile
	wallet = d.wallet
	heroes = d.heroes
	formation = d.formation
	campaign = d.campaign
	afk = d.afk
	rarities = d.rarities
	var st := Time.get_unix_time_from_datetime_string(d.server_time)
	server_time_offset = st - Time.get_unix_time_from_system()
	if catalog.is_empty():
		var c := await Api.get_json("/heroes")
		if c.ok:
			catalog = c.data
	loaded = true
	wallet_changed.emit()
	heroes_changed.emit()
	profile_changed.emit()
	afk_changed.emit()
	return r


func set_wallet(w: Variant) -> void:
	if w is Dictionary and not w.is_empty():
		wallet = w
		wallet_changed.emit()


func hero_by_id(id: Variant) -> Dictionary:
	for h in heroes:
		if h.id == id:
			return h
	return {}


func catalog_hero(code: String) -> Dictionary:
	for h in catalog.get("heroes", []):
		if h.code == code:
			return h
	return {}


func team_power() -> int:
	var p := 0
	for id in formation:
		if id:
			p += int(hero_by_id(id).get("power", 0))
	return p


func refresh_heroes() -> void:
	var r := await Api.get_json("/player/heroes")
	if r.ok:
		heroes = r.data.heroes
		heroes_changed.emit()


func refresh_afk() -> void:
	var r := await Api.get_json("/rewards/afk")
	if r.ok:
		afk = r.data
		afk_changed.emit()


func refresh_campaign() -> Dictionary:
	var r := await Api.get_json("/campaign")
	if r.ok:
		campaign["regions"] = r.data.regions
	return r


func advance_onboarding(step: int) -> void:
	if int(profile.get("onboarding_step", 0)) >= step:
		return
	profile["onboarding_step"] = step
	await Api.post_json("/player/onboarding", {"step": step})


func save_formation(slots: Array) -> Dictionary:
	var r := await Api.post_json("/formation", {"slots": slots})
	if r.ok:
		formation = r.data.slots
		heroes_changed.emit()
	return r


static func fmt(n: Variant) -> String:
	var v := int(n)
	if v >= 1_000_000:
		return "%.1fM" % (v / 1_000_000.0)
	if v >= 10_000:
		return "%.1fK" % (v / 1000.0)
	return str(v)


static func rewards_text(rw: Dictionary) -> String:
	var parts := []
	for k in rw:
		if int(rw[k]) > 0:
			parts.append("%s +%s" % [CURRENCY_NAMES.get(k, k), fmt(rw[k])])
	return ", ".join(parts)
