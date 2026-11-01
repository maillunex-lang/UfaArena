extends Node
## Client configuration. Contains NO backend secrets — only the public server URL and
## the public key used to verify signed content manifests.

const CLIENT_VERSION := "0.7.2"
const CHANNEL := "dev"
const PLATFORM := "android"
const SETTINGS_PATH := "user://settings.cfg"
const PUBLIC_KEY_PATH := "res://config/content_public_key.pem"

## Default server comes from project setting uralia/server_url (public address, not a secret).
var server_url: String = ProjectSettings.get_setting("uralia/server_url", "http://10.0.2.2:8000")
var settings := {
	"graphics_quality": "auto",
	"music_volume": 0.7,
	"sfx_volume": 0.9,
	"battle_speed": 1,
	# --- UI/UX redesign settings ---
	"master_volume": 0.8,      # the single volume slider (master bus)
	"music_on": true,
	"sfx_on": true,
	"ui_scale": 1.0,           # 0.9 / 1.0 / 1.1
	"reduce_motion": false,
	"high_contrast": false,
	"colorblind": false,       # alternative colour coding: symbols + blue/orange status colours
	"vibration": true,
	"fps_limit": 0,            # 0 = by graphics tier, otherwise 30 / 60
	"battery_saver": false,
	"notify_rewards": true,
	"notify_social": true,
	"notify_guild": true,
	"notify_events": true,
	"tips_on": true,           # first-open tips (brief §21)
	"seen_tips": [],
}


func _ready() -> void:
	if OS.has_feature("editor"):
		server_url = "http://127.0.0.1:8000"  # running from the Godot editor -> local server
	if OS.has_feature("web"):
		# the Web version is served by the game server itself (/play): talk to the same origin
		var origin = JavaScriptBridge.eval("window.location.origin", true)
		if origin is String and String(origin).begins_with("http"):
			server_url = String(origin)
	var env_url := OS.get_environment("URALIA_SERVER_URL")
	if env_url != "":
		server_url = env_url
	_load()


func _load() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SETTINGS_PATH) != OK:
		return
	if not OS.has_feature("web"):  # web always uses its own origin
		server_url = cfg.get_value("net", "server_url", server_url)
	for k in settings.keys():
		settings[k] = cfg.get_value("settings", k, settings[k])


func save() -> void:
	var cfg := ConfigFile.new()
	cfg.load(SETTINGS_PATH)
	cfg.set_value("net", "server_url", server_url)
	for k in settings.keys():
		cfg.set_value("settings", k, settings[k])
	cfg.save(SETTINGS_PATH)


func public_key_pem() -> String:
	if FileAccess.file_exists(PUBLIC_KEY_PATH):
		return FileAccess.get_file_as_string(PUBLIC_KEY_PATH)
	return ""
