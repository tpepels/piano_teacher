#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "piano_native.hpp"

#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/core/binder_common.hpp>
#include <godot_cpp/godot.hpp>
#include <cstring>
#include <chrono>
#include <algorithm>
#include <cstdlib>
#include <dlfcn.h>
#include <utility>

#define PIANO_STRINGIFY2(x) #x
#define PIANO_STRINGIFY(x) PIANO_STRINGIFY2(x)
static constexpr const char *PYTHON_SHARED_OBJECT =
    "libpython" PIANO_STRINGIFY(PY_MAJOR_VERSION) "."
    PIANO_STRINGIFY(PY_MINOR_VERSION) ".so.1.0";

using namespace godot;

namespace {
std::string utf8(const String &value) {
    CharString encoded = value.utf8();
    return std::string(encoded.get_data(), encoded.length());
}

void store_bytes(PackedByteArray &bytes, const char *data, size_t count) {
    bytes.resize(static_cast<int64_t>(count));
    if (count != 0) std::memcpy(bytes.ptrw(), data, count);
}

struct CancellationProbe {
    const void *context;
    bool (*cancelled)(const void *);
};

PyObject *check_cancelled(PyObject *capsule, PyObject *) {
    auto *probe = static_cast<CancellationProbe *>(
        PyCapsule_GetPointer(capsule, "piano.score-cancellation"));
    if (!probe) return nullptr;
    return PyBool_FromLong(probe->cancelled(probe->context));
}

PyMethodDef cancellation_method = {"cancelled", check_cancelled, METH_NOARGS, nullptr};

PyObject *check_stopping(PyObject *capsule, PyObject *) {
    auto *stopping = static_cast<const std::atomic<bool> *>(
        PyCapsule_GetPointer(capsule, "piano.shutdown"));
    if (!stopping) return nullptr;
    return PyBool_FromLong(stopping->load());
}

PyMethodDef shutdown_method = {"shutdown_requested", check_stopping, METH_NOARGS, nullptr};

std::string python_error() {
    if (!PyErr_Occurred()) return "Unknown Python bridge failure";
    PyObject *type = nullptr, *value = nullptr, *traceback = nullptr;
    PyErr_Fetch(&type, &value, &traceback);
    PyErr_NormalizeException(&type, &value, &traceback);
    PyObject *message = value ? PyObject_Str(value) : nullptr;
    const char *utf = message ? PyUnicode_AsUTF8(message) : nullptr;
    std::string result = utf ? utf : "Python exception";
    Py_XDECREF(message);
    Py_XDECREF(type);
    Py_XDECREF(value);
    Py_XDECREF(traceback);
    return result;
}
}

void PianoNative::_bind_methods() {
    ClassDB::bind_method(D_METHOD("is_ready"), &PianoNative::is_ready);
    ClassDB::bind_method(D_METHOD("monotonic_milliseconds"), &PianoNative::monotonic_milliseconds);
    ClassDB::bind_method(D_METHOD("failure_message"), &PianoNative::failure_message);
    ClassDB::bind_method(D_METHOD("submit", "operation", "payload"),
                         &PianoNative::submit);
    ClassDB::bind_method(D_METHOD("cancel_asset", "id"), &PianoNative::cancel_asset);
    ClassDB::bind_method(D_METHOD("take_responses"), &PianoNative::take_responses);
}

int64_t PianoNative::monotonic_milliseconds() const {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

PianoNative::PianoNative() {
    // Initialize all atomics, mutexes and storage before the thread may
    // access them. A member-initializer thread start is a data race here.
    worker_ = std::thread([this] { worker_loop(); });
}

PianoNative::~PianoNative() {
    {
        // Change the predicate under the same lock used by wait_until.
        std::lock_guard<std::mutex> guard(mutex_);
        stopping_ = true;
        ready_ = false;
        pending_.clear();
        completed_.clear();
    }
    assets_.stop();
    available_.notify_all();
    timing_changed_.notify_one();
    if (worker_.joinable()) worker_.join();
    // Do not Py_Finalize(): rtmidi and native extensions may still have
    // background callbacks. There is exactly one runtime per application.
}

String PianoNative::failure_message() {
    std::lock_guard<std::mutex> guard(mutex_);
    return String::utf8(failure_.c_str());
}

void PianoNative::initialize_python() {
    // Godot loads GDExtensions with dlopen(RTLD_LOCAL). A linked libpython
    // therefore is not visible to Python's extension modules (math, rtmidi,
    // etc.), which fail with undefined symbols such as PyFloat_Type.
    // Promote the already loaded CPython SONAME into the global symbol scope
    // before Py_InitializeFromConfig imports any extension modules.
    // Keep the handle for the lifetime of the process.
    static void *python_global_handle = nullptr;
    if (python_global_handle == nullptr) {
        python_global_handle = dlopen(PYTHON_SHARED_OBJECT,
                                     RTLD_NOW | RTLD_GLOBAL | RTLD_NOLOAD);
        if (python_global_handle == nullptr)
            python_global_handle = dlopen(PYTHON_SHARED_OBJECT,
                                         RTLD_NOW | RTLD_GLOBAL);
        if (python_global_handle == nullptr) {
            const char *details = dlerror();
            std::lock_guard<std::mutex> guard(mutex_);
            failure_ = std::string("Cannot publish embedded CPython symbols: ") +
                       (details ? details : PYTHON_SHARED_OBJECT);
            return;
        }
    }
    if (!Py_IsInitialized()) {
        PyConfig config;
        PyConfig_InitPythonConfig(&config);
        const char *home = std::getenv("PIANO_TEACHER_PYTHON_HOME");
        PyStatus status = PyStatus_Ok();
        if (home && *home) status = PyConfig_SetBytesString(&config, &config.home, home);
        if (!PyStatus_Exception(status)) status = Py_InitializeFromConfig(&config);
        PyConfig_Clear(&config);
        if (PyStatus_Exception(status)) {
            std::lock_guard<std::mutex> guard(mutex_);
            failure_ = status.err_msg ? status.err_msg : "Could not initialize Python";
            return;
        }
        // Worker and rtmidi callback threads each acquire the same CPython GIL.
        PyEval_SaveThread();
    }
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *module = PyImport_ImportModule("piano_teacher.inprocess");
    PyObject *klass = module ? PyObject_GetAttrString(module, "EngineCommands") : nullptr;
    // This flag is valid until the command thread and all its helpers join.
    PyObject *capsule = klass ? PyCapsule_New(&stopping_, "piano.shutdown", nullptr) : nullptr;
    PyObject *shutdown = capsule ? PyCFunction_New(&shutdown_method, capsule) : nullptr;
    // Physical score presentation is the engine's only transport.
    PyObject *instance = shutdown ? PyObject_CallOneArg(klass, shutdown) : nullptr;
    if (!instance) {
        std::lock_guard<std::mutex> guard(mutex_);
        failure_ = python_error();
    } else {
        engine_ = instance;
    }
    Py_XDECREF(shutdown);
    Py_XDECREF(capsule);
    Py_XDECREF(klass);
    Py_XDECREF(module);
    PyGILState_Release(gil);
}

bool PianoNative::is_asset_operation(const std::string &operation) {
    // Score process IPC and independent history reads use the asset lane.
    return operation == "score.bundle" ||
           operation == "score.native_layout" || operation == "score.semantic" ||
           operation == "learning.statistics";
}

void PianoNative::asset_loop() {
    while (!stopping_) {
        auto next = assets_.take_for(std::chrono::milliseconds(250));
        if (next) {
            assets_.complete(execute(*next, next->operation != "learning.statistics"));
        } else if (!stopping_) {
            const auto gil = PyGILState_Ensure();
            PyObject *result = PyObject_CallMethod(
                static_cast<PyObject *>(engine_), "poll_asset_worker", nullptr);
            Py_XDECREF(result);
            if (PyErr_Occurred()) PyErr_Print();
            PyGILState_Release(gil);
        }
    }
    const auto gil = PyGILState_Ensure();
    PyObject *result = PyObject_CallMethod(
        static_cast<PyObject *>(engine_), "close_asset_worker", nullptr);
    Py_XDECREF(result);
    if (PyErr_Occurred()) PyErr_Print();
    PyGILState_Release(gil);
}

void PianoNative::worker_loop() {
    initialize_python();
    // Started only after CPython and the engine exist; joined below before
    // the engine is closed, so no asset request can outlive the engine.
    if (!engine_) return;
    std::thread assets([this] { asset_loop(); });
    std::thread timing([this] { timing_loop(); });
    {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!stopping_) ready_ = true;
    }
    while (!stopping_) {
        Command next;
        {
            std::unique_lock<std::mutex> guard(mutex_);
            available_.wait(guard, [this] {
                return stopping_ || !pending_.empty();
            });
            if (stopping_) break;
            next = std::move(pending_.front());
            pending_.pop_front();
        }
        Reply output = execute(next);
        // Only state-changing commands re-evaluate transport deadlines.
        // Snapshot and UI reads never re-anchor the musical clock.
        const bool wake_timing = next.operation == "practice.command" ||
                next.operation == "library.open" ||
                next.operation == "settings.update" ||
                next.operation == "midi.device.select" ||
                next.operation == "fingering.correct" ||
                next.operation == "library.health.start" ||
                next.operation == "hardware.action";
        {
            std::lock_guard<std::mutex> guard(mutex_);
            if (stopping_) break;
            completed_.push_back(std::move(output));
            tick_requested_ |= wake_timing;
        }
        if (wake_timing) timing_changed_.notify_one();
    }
    assets_.stop();
    timing.join();
    assets.join();
    if (engine_) {
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *response = PyObject_CallMethod(
            static_cast<PyObject *>(engine_), "close", nullptr);
        Py_XDECREF(response);
        PyErr_Clear();
        Py_DECREF(static_cast<PyObject *>(engine_));
        engine_ = nullptr;
        PyGILState_Release(gil);
    }
}

void PianoNative::timing_loop() {
    using Clock = std::chrono::steady_clock;
    auto next_tick = Clock::now();
    while (!stopping_) {
        {
            std::unique_lock<std::mutex> guard(mutex_);
            timing_changed_.wait_until(guard, next_tick, [this] {
                return stopping_ || tick_requested_;
            });
            if (stopping_) break;
            tick_requested_ = false;
        }
        // The one clock driver stays runnable during library, WAV and
        // fingering I/O. Python still serializes musical state mutations.
        const int interval_ms = tick_engine();
        next_tick = Clock::now() + std::chrono::milliseconds(interval_ms);
    }
}

int PianoNative::tick_engine() {
    if (!engine_) return 250;
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *response = PyObject_CallMethod(
        static_cast<PyObject *>(engine_), "tick", nullptr);
    int next_ms = 100;
    if (response && PyLong_Check(response)) {
        const long requested = PyLong_AsLong(response);
        if (!PyErr_Occurred())
            next_ms = static_cast<int>(std::clamp(requested, 10L, 500L));
    }
    if (PyErr_Occurred()) {
        // A failed background tick must be visible: silently losing
        // automatic transitions would make the score appear to freeze.
        PyErr_Print();
    }
    Py_XDECREF(response);
    PyGILState_Release(gil);
    return next_ms;
}

PianoNative::Reply PianoNative::execute(const Command &command, bool subprocess_score) {
    Reply output{command.id, 3, {}};
    if (!engine_) {
        std::lock_guard<std::mutex> guard(mutex_);
        const std::string detail = failure_.empty() ? "Python bridge unavailable" : failure_;
        store_bytes(output.bytes, detail.data(), detail.size());
        return output;
    }
    PyGILState_STATE gil = PyGILState_Ensure();
    auto *engine = static_cast<PyObject *>(engine_);
    PyObject *response = nullptr;
    if (subprocess_score) {
        struct Context {
            PianoNative *bridge;
            int64_t id;
        } context{this, command.id};
        CancellationProbe probe{&context, [](const void *data) {
            const auto &ctx = *static_cast<const Context *>(data);
            return ctx.bridge->assets_.cancelled(ctx.id);
        }};
        PyObject *capsule = PyCapsule_New(&probe, "piano.score-cancellation", nullptr);
        PyObject *cancelled = capsule ? PyCFunction_New(&cancellation_method, capsule) : nullptr;
        if (cancelled) {
            const double queued = (monotonic_milliseconds() - command.enqueued_ms) * .001;
            response = PyObject_CallMethod(engine, "asset_request", "ssdO",
                command.operation.c_str(), command.body.c_str(), 85.0 - queued, cancelled);
        }
        Py_XDECREF(cancelled);
        Py_XDECREF(capsule);
    } else {
        response = PyObject_CallMethod(engine, "request", "ss",
            command.operation.c_str(), command.body.c_str());
    }
    if (response && PyTuple_Check(response) && PyTuple_Size(response) == 2) {
        PyObject *status = PyTuple_GetItem(response, 0);
        PyObject *payload = PyTuple_GetItem(response, 1);
        const long code = PyLong_Check(status) ? PyLong_AsLong(status) : -1;
        char *ptr = nullptr;
        Py_ssize_t count = 0;
        if (PyByteArray_Check(payload)) {
            ptr = PyByteArray_AsString(payload);
            count = PyByteArray_Size(payload);
        } else {
            PyBytes_AsStringAndSize(payload, &ptr, &count);
        }
        if (!PyErr_Occurred() && code >= 0 && code <= 3 && ptr && count >= 0) {
            output.status = static_cast<int>(code);
            // The reply owns the buffer and no Python code can mutate it.
            // Allocate/copy detached bytes without the musical interpreter lock.
            Py_BEGIN_ALLOW_THREADS
            store_bytes(output.bytes, ptr, static_cast<size_t>(count));
            Py_END_ALLOW_THREADS
        } else {
            PyErr_Clear();
            const std::string error = "Invalid Python bridge response";
            store_bytes(output.bytes, error.data(), error.size());
        }
    } else {
        std::string error = python_error();
        store_bytes(output.bytes, error.data(), error.size());
    }
    Py_XDECREF(response);
    PyErr_Clear();
    PyGILState_Release(gil);
    return output;
}

int64_t PianoNative::submit(const String &operation, const String &body) {
    int64_t id;
    Command command{0, utf8(operation), utf8(body), monotonic_milliseconds()};
    const bool asset = is_asset_operation(command.operation);
    {
        std::lock_guard<std::mutex> guard(mutex_);
        if (stopping_ || !ready_) return -1;
        id = ++next_id_;
        command.id = id;
        if (!asset) pending_.push_back(std::move(command));
    }
    if (asset) return assets_.submit(std::move(command)) ? id : -1;
    available_.notify_one();
    return id;
}

void PianoNative::cancel_asset(int64_t id) {
    assets_.cancel(id);
}

Array PianoNative::take_responses() {
    std::deque<Reply> collected;
    {
        std::lock_guard<std::mutex> guard(mutex_);
        collected.swap(completed_);
    }
    auto asset_replies = assets_.drain();
    for (auto &reply : asset_replies) collected.push_back(std::move(reply));
    Array result;
    for (const Reply &reply : collected) {
        Dictionary message;
        message["id"] = reply.id;
        message["status"] = reply.status;
        message["body"] = reply.bytes;
        result.push_back(message);
    }
    return result;
}


void initialize_piano_bridge(ModuleInitializationLevel level) {
    if (level == MODULE_INITIALIZATION_LEVEL_SCENE)
        ClassDB::register_class<PianoNative>();
}

void uninitialize_piano_bridge(ModuleInitializationLevel) {}

extern "C" {
GDExtensionBool GDE_EXPORT piano_bridge_library_init(
        GDExtensionInterfaceGetProcAddress get_proc_address,
        GDExtensionClassLibraryPtr library,
        GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
    init.register_initializer(initialize_piano_bridge);
    init.register_terminator(uninitialize_piano_bridge);
    init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return init.init();
}
}
