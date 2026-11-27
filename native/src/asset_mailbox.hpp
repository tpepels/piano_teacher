#pragma once

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <optional>
#include <utility>

namespace piano {

// Single-consumer mailbox. Commands and replies are native values only;
// no scene objects or Python references cross the queue. All state,
// including cancellation and the wait predicate, has one mutex owner.
template <typename Command, typename Reply>
class AssetMailbox {
    std::mutex mutex_;
    std::condition_variable available_;
    std::deque<Command> pending_;
    std::deque<Reply> completed_;
    std::optional<int64_t> active_;
    bool discard_active_ = false;
    bool stopped_ = false;
    const std::size_t capacity_;

public:
    explicit AssetMailbox(std::size_t capacity = 8) : capacity_(capacity) {}

    bool submit(Command command) {
        {
            std::lock_guard<std::mutex> guard(mutex_);
            const auto count = pending_.size() + completed_.size()
                             + (active_.has_value() ? 1 : 0);
            if (stopped_ || count >= capacity_) return false;
            pending_.push_back(std::move(command));
        }
        available_.notify_one();
        return true;
    }

    std::optional<Command> take() {
        std::unique_lock<std::mutex> guard(mutex_);
        available_.wait(guard, [this] {
            return stopped_ || !pending_.empty();
        });
        return take_pending();
    }

    std::optional<Command> take_for(std::chrono::milliseconds interval) {
        std::unique_lock<std::mutex> guard(mutex_);
        available_.wait_for(guard, interval, [this] {
            return stopped_ || !pending_.empty();
        });
        return take_pending();
    }

    bool cancelled(int64_t id) {
        std::lock_guard<std::mutex> guard(mutex_);
        return stopped_ || active_ != id || discard_active_;
    }

    void complete(Reply reply) {
        std::lock_guard<std::mutex> guard(mutex_);
        if (active_ != reply.id) return;
        if (!stopped_ && !discard_active_)
            completed_.push_back(std::move(reply));
        active_.reset();
        discard_active_ = false;
    }

    // The active supervisor observes cancellation without waiting for the child.
    void cancel(int64_t id) {
        std::lock_guard<std::mutex> guard(mutex_);
        auto erase_id = [id](auto &queue) {
            queue.erase(std::remove_if(queue.begin(), queue.end(),
                [id](const auto &item) { return item.id == id; }), queue.end());
        };
        erase_id(pending_);
        erase_id(completed_);
        if (active_ == id) discard_active_ = true;
    }

    std::deque<Reply> drain() {
        std::deque<Reply> result;
        std::lock_guard<std::mutex> guard(mutex_);
        result.swap(completed_);
        return result;
    }

    void stop() {
        {
            std::lock_guard<std::mutex> guard(mutex_);
            stopped_ = true;
            pending_.clear();
            completed_.clear();
            discard_active_ = true;
        }
        available_.notify_all();
    }
private:
    std::optional<Command> take_pending() {
        if (stopped_ || pending_.empty()) return std::nullopt;
        Command command = std::move(pending_.back());
        pending_.pop_back();
        active_ = command.id;
        discard_active_ = false;
        return command;
    }
};

} // namespace piano
