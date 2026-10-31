#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "piano_native.hpp"

#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/core/binder_common.hpp>
#include <godot_cpp/godot.hpp>
#include <cstring>
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
    ClassDB::bind_method(D_METHOD("failure_message"), &PianoNative::failure_message);
    ClassDB::bind_method(D_METHOD("submit", "method", "path", "body"),
                         &PianoNative::submit);
    ClassDB::bind_method(D_METHOD("take_responses"), &PianoNative::take_responses);
    ClassDB::bind_method(D_METHOD("live_events_json", "after_sequence"),
                         &PianoNative::live_events_json);
}

PianoNative::PianoNative() {
    // Initialize all atomics, mutexes and storage before the thread may
    // access them. A member-initializer thread start is a data race here.
    worker_ = std::thread([this] { worker_loop(); });
}

PianoNative::~PianoNative() {
    stopping_ = true;
    available_.notify_all();
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
    PyObject *instance = klass ? PyObject_CallNoArgs(klass) : nullptr;
    if (!instance) {
        std::lock_guard<std::mutex> guard(mutex_);
        failure_ = python_error();
    } else {
        engine_ = instance;
        ready_ = true;
    }
    Py_XDECREF(klass);
    Py_XDECREF(module);
    PyGILState_Release(gil);
}

void PianoNative::worker_loop() {
    initialize_python();
    while (!stopping_) {
        Command next;
        {
            std::unique_lock<std::mutex> guard(mutex_);
            available_.wait(guard, [this] {return stopping_ || !pending_.empty();});
            if (stopping_) break;
            next = std::move(pending_.front());
            pending_.pop_front();
        }
        Reply output = execute(next);
        {
            std::lock_guard<std::mutex> guard(mutex_);
            completed_.push_back(std::move(output));
        }
    }
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

PianoNative::Reply PianoNative::execute(const Command &command) {
    Reply output{command.id, 500, {}};
    if (!engine_) {
        std::lock_guard<std::mutex> guard(mutex_);
        const std::string detail = failure_.empty() ? "Python bridge unavailable" : failure_;
        output.bytes.assign(detail.begin(), detail.end());
        return output;
    }
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *response = PyObject_CallMethod(
        static_cast<PyObject *>(engine_), "request", "sss",
        command.method.c_str(), command.path.c_str(), command.body.c_str());
    if (response && PyTuple_Check(response) && PyTuple_Size(response) == 2) {
        output.status = static_cast<int>(PyLong_AsLong(PyTuple_GetItem(response, 0)));
        PyObject *payload = PyTuple_GetItem(response, 1);
        char *ptr = nullptr;
        Py_ssize_t count = 0;
        if (PyBytes_AsStringAndSize(payload, &ptr, &count) == 0 && count >= 0)
            output.bytes.assign(ptr, ptr + count);
        else PyErr_Clear();
    } else {
        std::string error = python_error();
        output.bytes.assign(error.begin(), error.end());
    }
    Py_XDECREF(response);
    PyGILState_Release(gil);
    return output;
}

int64_t PianoNative::submit(const String &method, const String &path,
                             const String &body) {
    if (stopping_ || !ready_) return -1;
    int64_t id;
    {
        std::lock_guard<std::mutex> guard(mutex_);
        id = ++next_id_;
        pending_.push_back(Command{id, utf8(method), utf8(path), utf8(body)});
    }
    available_.notify_one();
    return id;
}

Array PianoNative::take_responses() {
    std::deque<Reply> collected;
    {
        std::lock_guard<std::mutex> guard(mutex_);
        collected.swap(completed_);
    }
    Array result;
    for (const Reply &reply : collected) {
        Dictionary message;
        message["id"] = reply.id;
        message["status"] = reply.status;
        PackedByteArray bytes;
        bytes.resize(static_cast<int>(reply.bytes.size()));
        if (!reply.bytes.empty())
            std::memcpy(bytes.ptrw(), reply.bytes.data(), reply.bytes.size());
        message["body"] = bytes;
        result.push_back(message);
    }
    return result;
}

String PianoNative::live_events_json(int64_t after_sequence) {
    if (!ready_) return "[]";
    // Event ring reads are tiny and only take the GIL. No networking or
    // intermediate Python process; the MIDI callback itself remains async.
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *events = PyObject_CallMethod(static_cast<PyObject *>(engine_),
                                           "drain_midi_events", "L",
                                           static_cast<long long>(after_sequence));
    PyObject *json = PyImport_ImportModule("json");
    PyObject *encoded = events && json
        ? PyObject_CallMethod(json, "dumps", "O", events) : nullptr;
    const char *data = encoded ? PyUnicode_AsUTF8(encoded) : nullptr;
    String output = data ? String::utf8(data) : "[]";
    Py_XDECREF(encoded);
    Py_XDECREF(json);
    Py_XDECREF(events);
    PyErr_Clear();
    PyGILState_Release(gil);
    return output;
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
