extends ScrollContainer
## Sight-reading configuration is a separate drawer page, not a preference.
const Design := preload("res://practice_theme.gd")
const UI := preload("res://ui_factory.gd")

signal start_requested(level: int, tempo: String)

var reading_level: OptionButton
var reading_tempo: OptionButton
var reading_start: Button
var message: Label

func _ready() -> void:
    name = "SightReadingScreen"
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    var content := UI.stack(18)
    content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    add_child(content)
    content.add_child(UI.title("Sight reading",44))
    content.add_child(UI.label("Read and play a fresh 16-bar score at a fixed tempo.",16,Design.SECONDARY_INK))
    var form := UI.stack(10)
    content.add_child(form)
    form.add_child(UI.label("Practice level",16,Design.STONE,true))
    reading_level = OptionButton.new()
    reading_level.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    reading_level.custom_minimum_size.y = 42
    for level in ["1 · Quarter and eighth notes","2 · Sixteenth notes",
                  "3 · Triads and inversions","4 · Seventh chords",
                  "5 · Chord progressions"]:
        reading_level.add_item(level)
    form.add_child(reading_level)
    form.add_child(UI.label("Tempo",16,Design.STONE,true))
    reading_tempo = OptionButton.new()
    reading_tempo.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    reading_tempo.custom_minimum_size.y = 42
    for tempo in ["Largo · 40 BPM","Lento · 50 BPM","Adagio · 60 BPM",
                  "Andante · 80 BPM","Moderato · 100 BPM","Allegretto · 112 BPM",
                  "Allegro · 132 BPM","Vivace · 160 BPM","Presto · 184 BPM"]:
        reading_tempo.add_item(tempo)
    reading_tempo.select(3)
    form.add_child(reading_tempo)
    reading_start = UI.button("Start sight reading","primary")
    reading_start.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    reading_start.pressed.connect(_start)
    content.add_child(reading_start)
    message = UI.label("",14,Design.SECONDARY_INK)
    message.hide()
    content.add_child(message)

func _start() -> void:
    present_message("")
    start_requested.emit(reading_level.selected+1,
        reading_tempo.get_item_text(reading_tempo.selected).split(" · ")[0].to_lower())

func present_busy(pending: bool) -> void:
    reading_start.disabled = pending
    reading_level.disabled = pending
    reading_tempo.disabled = pending

func present_message(value: String) -> void:
    message.text = value
    message.visible = not value.is_empty()
