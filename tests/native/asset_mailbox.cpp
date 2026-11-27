#include "asset_mailbox.hpp"
#include <cassert>
#include <future>
#include <thread>

struct Work { int64_t id; };
using Mailbox = piano::AssetMailbox<Work, Work>;

int main() {
    Mailbox mailbox(3);
    assert(mailbox.submit({1}));
    assert(mailbox.submit({2}));
    assert(mailbox.take()->id == 1);
    assert(mailbox.submit({3}));
    assert(!mailbox.submit({4}));
    mailbox.cancel(2);
    assert(mailbox.submit({4}));
    mailbox.cancel(1);
    mailbox.complete({1});
    assert(mailbox.drain().empty());
    assert(mailbox.take()->id == 3);
    mailbox.complete({3});
    mailbox.cancel(3);
    assert(mailbox.drain().empty());
    assert(mailbox.take()->id == 4);
    mailbox.complete({4});
    assert(mailbox.drain().front().id == 4);

    // Real cross-thread cancellation while a job is in flight.
    Mailbox concurrent;
    std::promise<void> entered, release;
    auto released = release.get_future();
    assert(concurrent.submit({5}));
    std::thread worker([&] {
        auto job = concurrent.take();
        entered.set_value();
        released.wait();
        concurrent.complete(*job);
        assert(!concurrent.take());
    });
    entered.get_future().wait();
    concurrent.cancel(5);
    concurrent.stop();
    release.set_value();
    worker.join();
    assert(concurrent.drain().empty());
    assert(!concurrent.submit({6}));

    // Stop must wake an idle worker regardless of scheduling order.
    for (int i = 0; i < 100; ++i) {
        Mailbox idle;
        std::thread waiter([&] { assert(!idle.take()); });
        idle.stop();
        waiter.join();
    }
}
