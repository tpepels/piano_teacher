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
#include "asset_mailbox.hpp"

namespace godot {

// Only this class communicates with CPython. Every Godot rendering call is
// made on the main thread; the Python worker does not touch Godot objects.
class PianoNative : public RefCounted {
    GDCLASS(PianoNative, RefCounted)

    struct Command {
        int64_t id;
        std::string operation, body;
        int64_t enqueued_ms;
        bool source_commit = false;
    };
    struct Reply {
        int64_t id;
        int status;
        PackedByteArray bytes;
    };

    std::mutex mutex_;
    std::condition_variable available_;
    std::condition_variable timing_changed_;
    bool tick_requested_ = false;
    std::deque<Command> pending_;
    // Independent, bounded read-only work lane. It never holds the musical
    // command queue lock while preparing or cancelling a score.
    piano::AssetMailbox<Command, Reply> assets_;
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
    void timing_loop();
    void asset_loop();
    void source_loop();
    void publish(Reply reply, bool wake_timing);
    static bool is_asset_operation(const std::string &operation);
    int tick_engine();
    Reply execute(const Command &command, bool subprocess_score = false);
protected:
    static void _bind_methods();

public:
    PianoNative();
    ~PianoNative();

    bool is_ready() const { return ready_.load(); }
    int64_t monotonic_milliseconds() const;
    String failure_message();
    void schedule_source_commit(int64_t id);
    int64_t submit(const String &operation, const String &body);
    void cancel_asset(int64_t id);
    Array take_responses();
};

} // namespace godot
