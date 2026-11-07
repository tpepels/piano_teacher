#pragma once
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/string.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace godot {

// Only this class communicates with CPython. Every Godot rendering call is
// made on the main thread; the Python worker does not touch Godot objects.
class PianoNative : public RefCounted {
    GDCLASS(PianoNative, RefCounted)

    struct Command {
        int64_t id;
        std::string operation, body;
    };
    struct Reply {
        int64_t id;
        int status;
        std::vector<uint8_t> bytes;
    };

    std::mutex mutex_;
    std::condition_variable available_;
    std::deque<Command> pending_;
    // Read-only score asset preparation (seconds of Verovio engraving) runs
    // on its own thread so it can never delay the musical tick on worker_.
    std::condition_variable assets_available_;
    std::deque<Command> asset_pending_;
    std::deque<Reply> completed_;
    std::thread worker_;
    std::atomic<bool> stopping_{false};
    std::atomic<bool> ready_{false};
    std::string failure_;
    int64_t next_id_ = 0;

    // Opaque Python objects only used while holding the GIL.
    void *engine_ = nullptr;
    void initialize_python();
    void worker_loop();
    void asset_loop();
    static bool is_asset_operation(const std::string &operation);
    int tick_engine();
    Reply execute(const Command &command);
protected:
    static void _bind_methods();

public:
    PianoNative();
    ~PianoNative();

    bool is_ready() const { return ready_.load(); }
    String failure_message();
    int64_t submit(const String &operation, const String &body);
    Array take_responses();
};

} // namespace godot
