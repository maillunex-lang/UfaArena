extends Node
## Music (cross-fade) and pooled one-shot sound effects.

const MUSIC := {
	"hub": "res://assets/audio/music/hub_kurai_theme.ogg",
	"battle": "res://assets/audio/music/battle_kurai_drums.ogg",
	"victory": "res://assets/audio/music/victory_sting.ogg",
}
const SFX := {
	"click": "res://assets/third_party/audio_rpg_sound_pack/interface1.wav",
	"open": "res://assets/third_party/audio_rpg_sound_pack/interface2.wav",
	"back": "res://assets/third_party/audio_rpg_sound_pack/interface3.wav",
	"coin": "res://assets/third_party/audio_rpg_sound_pack/coin.wav",
	"coins": "res://assets/third_party/audio_rpg_sound_pack/coin2.wav",
	"swing": "res://assets/third_party/audio_rpg_sound_pack/swing.wav",
	"swing2": "res://assets/third_party/audio_rpg_sound_pack/swing2.wav",
	"swing3": "res://assets/third_party/audio_rpg_sound_pack/swing3.wav",
	"magic": "res://assets/third_party/audio_rpg_sound_pack/magic1.wav",
	"spell": "res://assets/third_party/audio_rpg_sound_pack/spell.wav",
	"unsheathe": "res://assets/third_party/audio_rpg_sound_pack/sword-unsheathe.wav",
	"heal": "res://assets/third_party/audio_rpg_sound_pack/bubble.wav",
	"enemy_die": "res://assets/third_party/audio_rpg_sound_pack/shade1.wav",
	"boss": "res://assets/third_party/audio_rpg_sound_pack/giant1.wav",
	"door": "res://assets/third_party/audio_rpg_sound_pack/door.wav",
}

var _music_a: AudioStreamPlayer
var _music_b: AudioStreamPlayer
var _current := ""
var _pool: Array[AudioStreamPlayer] = []


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_music_a = AudioStreamPlayer.new()
	_music_b = AudioStreamPlayer.new()
	add_child(_music_a)
	add_child(_music_b)
	for i in 8:
		var p := AudioStreamPlayer.new()
		add_child(p)
		_pool.append(p)


func _lin(v: float) -> float:
	return linear_to_db(max(v, 0.0001))


func music(id: String, loop := true) -> void:
	if id == _current:
		return
	_current = id
	var stream: AudioStream = Content.audio("music/%s.ogg" % id)  # content package override
	if stream == null:
		stream = load(MUSIC[id])
	if stream is AudioStreamOggVorbis:
		(stream as AudioStreamOggVorbis).loop = loop
	var old := _music_a if _music_a.playing else _music_b
	var nxt := _music_b if old == _music_a else _music_a
	nxt.stream = stream
	nxt.volume_db = -40
	nxt.play()
	var target := _lin(float(Config.settings.music_volume))
	var tw := create_tween().set_parallel(true)
	tw.tween_property(nxt, "volume_db", target, 1.2)
	if old.playing:
		tw.tween_property(old, "volume_db", -40.0, 1.2)
		tw.chain().tween_callback(old.stop)


func reload_music() -> void:
	var id := _current
	_current = ""
	if id != "":
		music(id)


func apply_volume() -> void:
	for p in [_music_a, _music_b]:
		if p.playing:
			p.volume_db = _lin(float(Config.settings.music_volume))


func play(id: String, pitch_jitter := 0.06) -> void:
	if not SFX.has(id):
		return
	for p in _pool:
		if not p.playing:
			p.stream = load(SFX[id])
			p.pitch_scale = 1.0 + randf_range(-pitch_jitter, pitch_jitter)
			p.volume_db = _lin(float(Config.settings.sfx_volume))
			p.play()
			return
