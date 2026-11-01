extends Node
## Client-side state cache. The server is the source of truth: every mutation goes
## through Api and the cache is replaced with what the server returns.

signal wallet_changed
signal heroes_changed
signal profile_changed
signal afk_changed

const CURRENCY_NAMES := {
	"gold": "Золото", "crystals": "Кристаллы", "summon_essence": "Эссенция призыва",
	"ancient_seals": "Печатные знаки", "guild_marks": "Знаки гильдии", "nature_essence": "Эссенция природы",
}
## Fallbacks; the server catalog (factions[].color/name) overrides these at runtime.
const FACTION_COLORS := {
	"stone_sky": Color("#5fb8b0"), "living_kurai": Color("#7cb860"), "ashen_reach": Color("#a35bc9"),
	"shulgan": Color("#8a5bd6"),
}
const RARITY_COLORS := {
	1: Color("#a7b0bd"), 2: Color("#6fd08c"), 3: Color("#5aa9ff"), 4: Color("#b87cff"),
	5: Color("#ffb347"), 6: Color("#ff5f7e"),
}
const CLASS_NAMES := {"warrior": "Воин", "guardian": "Защитник", "mage": "Маг", "healer": "Поддержка",
	"ranger": "Следопыт", "summoner": "Призыватель", "assassin": "Убийца", "hybrid": "Гибрид"}
const FACTION_NAMES := {"stone_sky": "Каменное Небо", "living_kurai": "Живой Курай", "ashen_reach": "Пепельный Предел",
	"shulgan": "Порождения Глубины"}
const STATUS_NAMES := {"atk+": "Атака ↑", "atk-": "Атака ↓", "def+": "Защита ↑", "def-": "Защита ↓", "spd+": "Скорость ↑",
	"spd-": "Замедление", "dr+": "Урон ↓", "cc_resist+": "Стойкость", "accuracy-": "Точность ↓", "heal_received-": "Лечение ↓",
	"regen+": "Восстановление", "dodge+": "Уклонение", "taunt": "Провокация", "guard": "Заслон"}


func faction_color(code: String) -> Color:
	for f in catalog.get("factions", []):
		if f.code == code and f.has("color"):
			return Color(f.color)
	return FACTION_COLORS.get(code, Color.GRAY)


func faction_name(code: String) -> String:
	for f in catalog.get("factions", []):
		if f.code == code:
			return f.name
	return FACTION_NAMES.get(code, code)


func playable_factions() -> Array:
	var out := []
	for f in catalog.get("factions", []):
		if f.get("playable", true):
			out.append(f)
	return out

var profile := {}
var wallet := {}
var heroes: Array = []
var formation: Array = [null, null, null, null, null]
var campaign := {}
var afk := {}
var rarities := {}
var catalog := {}
var server_time_offset := 0.0
var cosmetics := {}  # equipped cosmetics resolved by the server (frame, title, hero_skins, ...)
var test_mode := true
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
	cosmetics = d.get("cosmetics", {})
	test_mode = d.get("test_mode", true)
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


func hero_name(code: String) -> String:
	var h := catalog_hero(code)
	return String(h.get("name", code)) if not h.is_empty() else code


const BUILDING_NAMES := {"summon_hall": "Зал призыва", "forge": "Кузница", "training": "Тренировочный двор", "alchemy": "Алхимическая башня", "storage": "Хранилище", "guild_house": "Дом гильдий"}


func building_name(code: String) -> String:
	return String(BUILDING_NAMES.get(code, code))


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


func set_cosmetics(c: Variant) -> void:
	if c is Dictionary:
		cosmetics = c
		Models.clear_cache()
		profile_changed.emit()


static func rub(kopecks: Variant) -> String:
	var v := int(kopecks) / 100
	var s := str(v)
	if v >= 1000:
		s = "%d %03d" % [v / 1000, v % 1000]
	return s + " ₽"


static func fmt(n: Variant) -> String:
	var v := int(n)
	if v >= 1_000_000:
		return "%.1fM" % (v / 1_000_000.0)
	if v >= 10_000:
		return "%.1fK" % (v / 1000.0)
	return str(v)


## Exact value with thin grouping for detail views ("12 345"); fmt() stays abbreviated for the resource bar.
static func exact(n: Variant) -> String:
	var v := int(n)
	var neg := v < 0
	var s := str(abs(v))
	var out := ""
	while s.length() > 3:
		out = " " + s.substr(s.length() - 3) + out
		s = s.substr(0, s.length() - 3)
	return ("-" if neg else "") + s + out


static func rewards_text(rw: Dictionary) -> String:
	var parts := []
	for k in rw:
		if int(rw[k]) > 0:
			parts.append("%s +%s" % [CURRENCY_NAMES.get(k, k), fmt(rw[k])])
	return ", ".join(parts)
