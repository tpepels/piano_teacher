import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from piano_teacher.server import Handler, PracticeEngine


def test_library_and_settings_http_endpoints(tmp_path):
    music = tmp_path / 'music'
    music.mkdir()
    (music / 'Prelude.mid').write_bytes(b'fake')
    engine = PracticeEngine(tmp_path / 'state', enable_midi=False)
    # Handler uses class engine, consistent with the normal single service process.
    class LocalHandler(Handler):
        pass
    LocalHandler.engine = engine
    server = ThreadingHTTPServer(('127.0.0.1', 0), LocalHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    def get(path):
        with urlopen(base + path, timeout=3) as reply:
            return json.load(reply)
    def post(path, value):
        payload = json.dumps(value).encode()
        with urlopen(Request(base + path, payload, {'Content-Type': 'application/json'}), timeout=3) as reply:
            return json.load(reply)
    try:
        assert 'music_dir' in get('/settings')
        new = post('/settings', {'music_dir': str(music), 'fullscreen': False})
        assert new['fullscreen'] is False
        assert new['music_dir'] == str(music)
        listing = get('/library')
        assert listing['count'] == 1
        assert listing['pieces'][0]['id'] == 'Prelude.mid'
        try:
            post('/settings', {'music_dir': str(tmp_path / 'absent')})
            assert False, 'Expected HTTP 400'
        except HTTPError as error:
            assert error.code == 400
        assert get('/settings')['music_dir'] == str(music)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        engine.db.close()
