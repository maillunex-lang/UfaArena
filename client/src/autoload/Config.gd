extends Node
## Client configuration. Contains NO backend secrets — only the public server URL and
## the public key used to verify signed content manifests.

const CLIENT_VERSION := "0.1.0"
const CHANNEL := "dev"
const PLATFORM := "android"
const SETTINGS_PATH := "user://settings.cfg"
const PUBLIC_KEY_PATH := "res://config/content_public_key.pem"

var server_url := "http://10.0.2.2:8000"  # Android emulator -> host machine
var settings := {
	"graphics_quality": "auto",
	"music_volume": 0.7,
	"sfx_volume": 0.9,
	"battle_speed": 1,
}


func _ready() -> void:
	if OS.get_name() != "Android":
		server_url = "http://127.0.0.1:8000"
	var env_url := OS.get_environment("URALIA_SERVER_URL")
	if env_url != "":
		server_url = env_url
	_load()


func _load() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SETTINGS_PATH) != OK:
		return
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
